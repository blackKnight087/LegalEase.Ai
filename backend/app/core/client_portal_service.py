"""Client portal — read-only matter status via secure token."""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter, list_matter_notes
from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.trust_service import get_or_create_trust_account


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_portal_access(
    user_id: str,
    matter_id: str,
    client_email: str,
    *,
    days_valid: int = 30,
) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    ensure_saas_schema()
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=days_valid)).isoformat()
    aid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO client_portal_access
        (access_id, user_id, matter_id, client_email, access_token, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (aid, str(user_id), matter_id, client_email.strip(), token, expires, now.isoformat()),
    )
    conn.commit()
    conn.close()
    return {
        "access_id": aid,
        "portal_token": token,
        "expires_at": expires,
        "portal_path": f"/portal/{token}",
    }


def resolve_portal_token(token: str) -> Optional[Dict[str, str]]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT user_id, matter_id, client_email, expires_at
        FROM client_portal_access WHERE access_token=?
        """,
        (token.strip(),),
    ).fetchone()
    conn.close()
    if not row:
        return None
    if row[3] < _utc():
        return None
    return {
        "user_id": row[0],
        "matter_id": row[1],
        "client_email": row[2],
    }


def get_client_portal_view(token: str) -> Dict[str, Any]:
    ctx = resolve_portal_token(token)
    if not ctx:
        return {"error": "Invalid or expired portal link"}
    matter = get_matter(ctx["user_id"], ctx["matter_id"])
    if not matter:
        return {"error": "Matter not found"}
    notes = list_matter_notes(ctx["user_id"], ctx["matter_id"], limit=10)
    trust = get_or_create_trust_account(ctx["user_id"], ctx["matter_id"])
    return {
        "client_email": ctx["client_email"],
        "matter": {
            "matter_name": matter.get("matter_name"),
            "case_number": matter.get("case_number"),
            "practice_area": matter.get("practice_area"),
            "status_tier": matter.get("status_tier"),
            "venue": matter.get("venue"),
            "updated_at": matter.get("updated_at"),
        },
        "recent_notes": [
            {"content": n["raw_content"][:300], "timestamp": n["timestamp"]}
            for n in notes
        ],
        "trust_summary": {
            "trust_balance_inr": trust.get("trust_balance", 0),
            "operating_balance_inr": trust.get("operating_balance", 0),
        },
        "disclaimer": "Read-only client view. Contact your advocate for legal advice.",
    }


def record_portal_client_upload(
    token: str,
    filename: str,
    *,
    size_bytes: int = 0,
) -> Dict[str, Any]:
    """Record a client upload via portal token (lawyer reviews in matter notes)."""
    ctx = resolve_portal_token(token)
    if not ctx:
        return {"error": "Invalid or expired portal link"}
    ensure_saas_schema()
    from backend.app.core.matter_repo import add_matter_note

    safe_name = (filename or "upload").replace("..", "").strip()[:200]
    note = (
        f"[Client portal upload] {safe_name}"
        + (f" ({size_bytes} bytes)" if size_bytes else "")
        + f" from {ctx['client_email']}"
    )
    add_matter_note(ctx["user_id"], ctx["matter_id"], note)
    return {"ok": True, "matter_id": ctx["matter_id"], "filename": safe_name}


def record_portal_signature(
    token: str,
    *,
    signer_name: str = "",
    intent: str = "acknowledge",
) -> Dict[str, Any]:
    """Record client e-sign intent via portal token (stub — DocuSign partnership for live flow)."""
    ctx = resolve_portal_token(token)
    if not ctx:
        return {"error": "Invalid or expired portal link"}
    ensure_saas_schema()
    conn = connect_data_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS portal_signatures (
            sign_id TEXT PRIMARY KEY,
            access_token TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            signer_name TEXT DEFAULT '',
            intent TEXT DEFAULT 'acknowledge',
            signed_at TEXT NOT NULL
        )
        """
    )
    sid = str(uuid.uuid4())
    now = _utc()
    conn.execute(
        """
        INSERT INTO portal_signatures
        (sign_id, access_token, matter_id, signer_name, intent, signed_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            sid,
            token.strip(),
            ctx["matter_id"],
            (signer_name or ctx["client_email"])[:200],
            (intent or "acknowledge")[:80],
            now,
        ),
    )
    conn.commit()
    conn.close()
    from backend.app.core.matter_repo import add_matter_note

    add_matter_note(
        ctx["user_id"],
        ctx["matter_id"],
        f"[Client e-sign] {signer_name or ctx['client_email']} — intent: {intent} at {now}",
    )
    return {
        "ok": True,
        "sign_id": sid,
        "matter_id": ctx["matter_id"],
        "signed_at": now,
        "provider": "portal_stub",
        "note": "Signature intent recorded. Live DocuSign requires ESIGN_PROVIDER and API credentials.",
    }
