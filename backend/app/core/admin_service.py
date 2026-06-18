"""Admin operations — users, plans, usage."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.core.audit_service import log_audit
from backend.app.core.database import connect_data_db
from backend.app.core.saas_ops_schema import ensure_saas_ops_schema
from backend.app.core.stripe_billing import upgrade_membership


def list_users(*, query: str = "", limit: int = 50) -> List[Dict[str, Any]]:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    q = (query or "").strip()
    if q:
        like = f"%{q}%"
        rows = conn.execute(
            """
            SELECT id, username, membership, role, created_at, COALESCE(suspended, 0)
            FROM users
            WHERE username LIKE ? OR id LIKE ?
            ORDER BY created_at DESC LIMIT ?
            """,
            (like, like, int(limit)),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, username, membership, role, created_at, COALESCE(suspended, 0)
            FROM users ORDER BY created_at DESC LIMIT ?
            """,
            (int(limit),),
        ).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "username": r[1],
            "membership": r[2],
            "role": r[3],
            "created_at": r[4],
            "suspended": bool(r[5]),
        }
        for r in rows
    ]


def set_user_suspended(user_id: str, suspended: bool, *, admin_id: str = "") -> bool:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    cur = conn.execute(
        "UPDATE users SET suspended = ? WHERE id = ?",
        (1 if suspended else 0, str(user_id)),
    )
    conn.commit()
    conn.close()
    if cur.rowcount:
        log_audit(
            "admin_suspend" if suspended else "admin_unsuspend",
            user_id=str(user_id),
            detail=f"by_admin={admin_id}",
        )
    return cur.rowcount > 0


def set_user_plan(user_id: str, plan: str, *, admin_id: str = "") -> bool:
    ok = upgrade_membership(str(user_id), plan)
    if ok:
        log_audit("admin_plan_override", user_id=str(user_id), detail=f"plan={plan} by={admin_id}")
    return ok


def get_usage_summary() -> Dict[str, Any]:
    ensure_saas_ops_schema()
    conn = connect_data_db()
    out: Dict[str, Any] = {"users": 0, "documents": 0, "chat_turns": 0, "matters": 0, "ml_jobs_queued": 0}
    try:
        out["users"] = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    except Exception:
        pass
    for table, key in (
        ("documents", "documents"),
        ("chat_history", "chat_turns"),
        ("matters", "matters"),
    ):
        try:
            out[key] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            pass
    try:
        out["ml_jobs_queued"] = int(
            conn.execute("SELECT COUNT(*) FROM ml_jobs WHERE status='QUEUED'").fetchone()[0]
        )
    except Exception:
        pass
    conn.close()
    return out


def get_system_health() -> Dict[str, Any]:
    health: Dict[str, Any] = {"api": "ok"}
    try:
        from backend.app.core.job_queue import _redis

        r = _redis()
        health["redis"] = "ok" if r else "unavailable"
    except Exception:
        health["redis"] = "unknown"
    try:
        from backend.app.core.stripe_billing import stripe_enabled

        health["stripe"] = "enabled" if stripe_enabled() else "mock_or_off"
    except Exception:
        health["stripe"] = "unknown"
    try:
        from llms import generator_status

        gen = generator_status() or {}
        health["llm"] = "online" if gen.get("online") or gen.get("available") else "offline"
    except Exception:
        health["llm"] = "unknown"
    return health
