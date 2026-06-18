"""E-signature — mock (dev) and DocuSign-ready envelope flow."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.saas_schema import ensure_saas_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _provider() -> str:
    p = (os.getenv("ESIGN_PROVIDER") or "mock").strip().lower()
    return p if p in ("mock", "docusign") else "mock"


def create_signing_request(
    user_id: str,
    *,
    document_title: str,
    document_body: str,
    signer_name: str,
    signer_email: str,
    matter_id: str = "",
) -> Dict[str, Any]:
    ensure_saas_schema()
    rid = str(uuid.uuid4())
    now = _utc()
    provider = _provider()
    sign_url = ""
    external_id = ""
    status = "PENDING"

    if provider == "docusign" and os.getenv("DOCUSIGN_INTEGRATION_KEY"):
        out = _docusign_create_envelope(
            document_title, document_body, signer_name, signer_email
        )
        if out.get("error"):
            provider = "mock"
        else:
            external_id = out.get("envelope_id", "")
            sign_url = out.get("sign_url", "")
            status = "SENT"

    if provider == "mock" or not sign_url:
        base = (os.getenv("PUBLIC_APP_URL") or "http://localhost:3000").rstrip("/")
        sign_url = f"{base}/esign/mock/{rid}?email={signer_email}"
        status = "MOCK_READY"

    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO signing_requests
        (request_id, user_id, matter_id, document_title, document_body,
         signer_name, signer_email, provider, external_id, status, sign_url, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            rid,
            str(user_id),
            matter_id,
            document_title[:200],
            document_body[:50000],
            signer_name,
            signer_email,
            provider,
            external_id,
            status,
            sign_url,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return {
        "request_id": rid,
        "provider": provider,
        "status": status,
        "sign_url": sign_url,
        "signer_email": signer_email,
    }


def get_signing_request(user_id: str, request_id: str) -> Optional[Dict[str, Any]]:
    ensure_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT request_id, document_title, signer_name, signer_email, provider,
               status, sign_url, created_at
        FROM signing_requests WHERE request_id=? AND user_id=?
        """,
        (request_id, str(user_id)),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "request_id": row[0],
        "document_title": row[1],
        "signer_name": row[2],
        "signer_email": row[3],
        "provider": row[4],
        "status": row[5],
        "sign_url": row[6],
        "created_at": row[7],
    }


def mark_signed(request_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    conn = connect_data_db()
    conn.execute(
        "UPDATE signing_requests SET status='SIGNED', updated_at=? WHERE request_id=?",
        (_utc(), request_id),
    )
    conn.commit()
    conn.close()
    return {"request_id": request_id, "status": "SIGNED"}


def _docusign_create_envelope(
    title: str,
    body: str,
    signer_name: str,
    signer_email: str,
) -> Dict[str, Any]:
    """DocuSign REST v2.1 — requires DOCUSIGN_* env vars."""
    try:
        import requests
    except ImportError:
        return {"error": "requests not available"}
    base = os.getenv("DOCUSIGN_BASE_URL", "https://demo.docusign.net/restapi").rstrip("/")
    account = os.getenv("DOCUSIGN_ACCOUNT_ID", "")
    token = os.getenv("DOCUSIGN_ACCESS_TOKEN", "")
    if not account or not token:
        return {"error": "DocuSign not configured (DOCUSIGN_ACCOUNT_ID, DOCUSIGN_ACCESS_TOKEN)"}
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    envelope = {
        "emailSubject": title[:100],
        "documents": [
            {
                "documentId": "1",
                "name": title[:100],
                "documentBase64": __import__("base64").b64encode(body.encode("utf-8")).decode(),
            }
        ],
        "recipients": {
            "signers": [
                {
                    "email": signer_email,
                    "name": signer_name,
                    "recipientId": "1",
                    "routingOrder": "1",
                }
            ]
        },
        "status": "sent",
    }
    try:
        r = requests.post(
            f"{base}/v2.1/accounts/{account}/envelopes",
            json=envelope,
            headers=headers,
            timeout=30,
        )
        if r.status_code not in (200, 201):
            return {"error": f"DocuSign HTTP {r.status_code}"}
        env_id = r.json().get("envelopeId", "")
        return {
            "envelope_id": env_id,
            "sign_url": f"{base}/signing/{env_id}" if env_id else "",
        }
    except Exception as exc:
        return {"error": str(exc)}
