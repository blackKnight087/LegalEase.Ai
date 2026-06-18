"""Pilot program — track early paying law firms (Phase 6 GTM)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_pilot_schema() -> None:
    conn = connect_data_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pilot_firms (
            pilot_id TEXT PRIMARY KEY,
            firm_name TEXT NOT NULL,
            contact_email TEXT NOT NULL,
            plan TEXT NOT NULL DEFAULT 'Pro',
            org_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'active',
            notes TEXT DEFAULT '',
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def register_pilot_firm(
    *,
    firm_name: str,
    contact_email: str,
    plan: str = "Pro",
    org_id: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    ensure_pilot_schema()
    pid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO pilot_firms
        (pilot_id, firm_name, contact_email, plan, org_id, status, notes, started_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
        """,
        (pid, firm_name.strip(), contact_email.strip(), plan, org_id, notes, now, now),
    )
    conn.commit()
    conn.close()
    return {"pilot_id": pid, "firm_name": firm_name, "plan": plan, "status": "active"}


def list_pilot_firms(*, status: str = "") -> List[Dict[str, Any]]:
    ensure_pilot_schema()
    conn = connect_data_db()
    if status:
        rows = conn.execute(
            "SELECT pilot_id, firm_name, contact_email, plan, org_id, status, notes, started_at FROM pilot_firms WHERE status = ? ORDER BY started_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT pilot_id, firm_name, contact_email, plan, org_id, status, notes, started_at FROM pilot_firms ORDER BY started_at DESC"
        ).fetchall()
    conn.close()
    return [
        {
            "pilot_id": r[0],
            "firm_name": r[1],
            "contact_email": r[2],
            "plan": r[3],
            "org_id": r[4],
            "status": r[5],
            "notes": r[6],
            "started_at": r[7],
        }
        for r in rows
    ]


def update_pilot_status(pilot_id: str, status: str, notes: str = "") -> bool:
    ensure_pilot_schema()
    conn = connect_data_db()
    cur = conn.execute(
        "UPDATE pilot_firms SET status = ?, notes = ?, updated_at = ? WHERE pilot_id = ?",
        (status, notes, _utc(), pilot_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def pilot_summary() -> Dict[str, Any]:
    firms = list_pilot_firms()
    active = [f for f in firms if f.get("status") == "active"]
    return {
        "total": len(firms),
        "active": len(active),
        "target": 5,
        "on_track": len(active) >= 3,
        "firms": firms,
    }
