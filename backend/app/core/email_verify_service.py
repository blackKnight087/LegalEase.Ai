"""Email verification tokens (Day 8)."""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.p2_saas_schema import ensure_p2_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def ensure_email_verify_schema() -> None:
    from backend.app.core.legacy_db import use_postgres_legacy

    if use_postgres_legacy():
        from backend.app.core.pg_rest_schema import ensure_pg_rest_schema

        ensure_pg_rest_schema()
        return
    ensure_p2_saas_schema()
    conn = connect_data_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verify_tokens (
            token_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            verified_at TEXT DEFAULT '',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def create_verify_token(user_id: str, email: str, *, hours: int = 48) -> Dict[str, Any]:
    ensure_email_verify_schema()
    raw = secrets.token_urlsafe(32)
    token_id = str(uuid.uuid4())
    expires = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO email_verify_tokens
        (token_id, user_id, token_hash, email, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (token_id, str(user_id), _hash_token(raw), email.strip().lower(), expires, now),
    )
    conn.commit()
    conn.close()
    base = os.getenv("PUBLIC_APP_URL", "http://localhost:3000").rstrip("/")
    return {"token": raw, "verify_url": f"{base}/verify-email?token={raw}"}


def verify_email_token(raw_token: str) -> Dict[str, Any]:
    ensure_email_verify_schema()
    th = _hash_token((raw_token or "").strip())
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT token_id, user_id, email, expires_at, verified_at
        FROM email_verify_tokens WHERE token_hash = ?
        """,
        (th,),
    ).fetchone()
    if not row:
        conn.close()
        return {"ok": False, "error": "Invalid or expired token"}
    token_id, user_id, email, expires_at, verified_at = row
    if verified_at:
        conn.close()
        return {"ok": True, "already_verified": True, "user_id": str(user_id)}
    if str(expires_at) < _utc():
        conn.close()
        return {"ok": False, "error": "Token expired"}
    now = _utc()
    conn.execute(
        "UPDATE email_verify_tokens SET verified_at = ? WHERE token_id = ?",
        (now, str(token_id)),
    )
    conn.commit()
    conn.close()
    return {"ok": True, "user_id": str(user_id), "email": str(email)}


def send_verification_email(user_id: str, email: str) -> Dict[str, Any]:
    """Create token and email verification link."""
    out = create_verify_token(user_id, email)
    try:
        from backend.app.core.email_service import send_verify_email

        send_verify_email(email, verify_url=str(out.get("verify_url") or ""))
    except Exception:
        pass
    return {"ok": True, "verify_url": out.get("verify_url")}
