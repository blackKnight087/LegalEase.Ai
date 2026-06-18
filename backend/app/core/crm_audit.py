"""CRM lead-scoped audit trail."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from backend.app.core.crm_schema import ensure_crm_v2_schema
from backend.app.core.database import connect_data_db


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_crm_audit(
    lead_id: str,
    user_id: str,
    action: str,
    detail: str = "",
) -> None:
    ensure_crm_v2_schema()
    aid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO crm_audit_log (audit_id, lead_id, user_id, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (aid, str(lead_id), str(user_id), action, (detail or "")[:2000], _utc()),
    )
    conn.commit()
    conn.close()
    try:
        from backend.app.core.audit_service import log_audit

        log_audit(f"crm_{action}", user_id=user_id, detail=f"lead={lead_id}: {detail[:200]}")
    except Exception:
        pass


def list_crm_audit(lead_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_crm_v2_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT audit_id, lead_id, user_id, action, detail, created_at
        FROM crm_audit_log WHERE lead_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (str(lead_id), limit),
    ).fetchall()
    conn.close()
    return [
        {
            "audit_id": r[0],
            "lead_id": r[1],
            "user_id": r[2],
            "action": r[3],
            "detail": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]
