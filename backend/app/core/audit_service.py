"""Global audit trail for compliance and admin."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.observability import emit_event
from backend.app.core.saas_ops_schema import ensure_saas_ops_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_audit(
    action: str,
    *,
    user_id: str = "",
    detail: str = "",
    ip_address: str = "",
) -> None:
    ensure_saas_ops_schema()
    aid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO audit_events (id, user_id, action, detail, ip_address, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (aid, str(user_id or ""), action, (detail or "")[:2000], ip_address, now),
    )
    conn.commit()
    conn.close()
    emit_event("audit", action=action, user_id=user_id, detail=detail[:200])


def list_audit_events(
    *,
    limit: int = 100,
    user_id: Optional[str] = None,
    action_prefix: Optional[str] = None,
) -> List[Dict[str, Any]]:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    sql = """
        SELECT id, user_id, action, detail, ip_address, created_at
        FROM audit_events
        WHERE 1=1
    """
    params: list = []
    if user_id:
        sql += " AND user_id = ?"
        params.append(str(user_id))
    if action_prefix:
        sql += " AND action LIKE ?"
        params.append(f"{action_prefix}%")
    sql += " ORDER BY created_at DESC LIMIT ?"
    params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "user_id": r[1],
            "action": r[2],
            "detail": r[3],
            "ip_address": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]
