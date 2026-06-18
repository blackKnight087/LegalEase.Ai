"""
Litigation Operating System — Mission Control dashboard, firm hearings, analytics, orders, AI tools.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import ensure_columns, execute_script
from backend.app.core.lawyer_digest import _parse_hearing_date, get_hearing_digest
from backend.app.core.matter_hearings_intel import list_hearings, schedule_hearing
from backend.app.core.matter_repo import get_matter, list_matters
from backend.app.core.practice_schema import ensure_practice_schema

LIMITATION_TYPES = (
    "appeal",
    "filing",
    "reply",
    "compliance",
    "execution",
    "limitation",
)
TASK_TEMPLATES = (
    "Draft Petition",
    "Collect Evidence",
    "Call Witness",
    "Prepare Affidavit",
    "Review CCTV",
    "File Reply",
    "Client Meeting",
    "Court Appearance",
)
ORDER_TYPES = ("order", "judgment", "interim_order", "application", "reply", "affidavit")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today() -> date:
    return date.today()


def _ensure_litigation_tables(conn) -> None:
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS matter_court_orders (
            order_id TEXT PRIMARY KEY,
            matter_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            order_type TEXT DEFAULT 'order',
            title TEXT NOT NULL,
            order_date TEXT DEFAULT '',
            court_name TEXT DEFAULT '',
            judge TEXT DEFAULT '',
            summary TEXT DEFAULT '',
            document_id TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_court_orders_mid ON matter_court_orders(matter_id);
        CREATE INDEX IF NOT EXISTS idx_court_orders_user ON matter_court_orders(user_id);
        """
    )
    ensure_columns(
        conn,
        "matter_hearings",
        (
            ("hearing_time", "TEXT DEFAULT ''", "ALTER TABLE matter_hearings ADD COLUMN hearing_time TEXT DEFAULT ''"),
            ("stage", "TEXT DEFAULT ''", "ALTER TABLE matter_hearings ADD COLUMN stage TEXT DEFAULT ''"),
            (
                "assigned_lawyer",
                "TEXT DEFAULT ''",
                "ALTER TABLE matter_hearings ADD COLUMN assigned_lawyer TEXT DEFAULT ''",
            ),
        ),
    )


def _user_matter_ids(user_id: str) -> List[str]:
    return [m["matter_id"] for m in list_matters(user_id, include_archived=False)]


def _count_deadlines_due(user_id: str, *, within_days: int = 7) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    end = (_today() + timedelta(days=within_days)).isoformat()
    today_s = _today().isoformat()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return 0
    placeholders = ",".join("?" * len(mids))
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM matter_deadlines
        WHERE matter_id IN ({placeholders})
          AND status NOT IN ('done', 'completed', 'cancelled')
          AND due_date >= ? AND due_date <= ?
        """,
        (*mids, today_s, end),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _count_open_tasks(user_id: str, *, hearing_linked: bool = False) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return 0
    placeholders = ",".join("?" * len(mids))
    q = f"""
        SELECT COUNT(*) FROM matter_tasks
        WHERE matter_id IN ({placeholders}) AND status NOT IN ('done', 'completed', 'cancelled')
    """
    if hearing_linked:
        q += " AND (title LIKE '%hearing%' OR title LIKE '%court%' OR title LIKE '%affidavit%')"
    row = conn.execute(q, mids).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _count_evidence_records(user_id: str) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return 0
    placeholders = ",".join("?" * len(mids))
    row = conn.execute(
        f"SELECT COUNT(*) FROM matter_evidence WHERE matter_id IN ({placeholders})",
        mids,
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _count_evidence_pending(user_id: str) -> int:
    """Backward-compatible alias for evidence record count."""
    return _count_evidence_records(user_id)


def _count_evidence_pending_review(user_id: str) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return 0
    ph = ",".join("?" * len(mids))
    task_row = conn.execute(
        f"""
        SELECT COUNT(*) FROM matter_tasks
        WHERE matter_id IN ({ph})
          AND status NOT IN ('done', 'completed', 'cancelled')
          AND LOWER(title) LIKE '%evidence%'
        """,
        mids,
    ).fetchone()
    cx_row = conn.execute(
        f"SELECT COUNT(*) FROM matter_contradictions WHERE matter_id IN ({ph})",
        mids,
    ).fetchone()
    conn.close()
    return int(task_row[0] if task_row else 0) + int(cx_row[0] if cx_row else 0)


def _count_overdue_deadlines(user_id: str) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return 0
    ph = ",".join("?" * len(mids))
    today_s = _today().isoformat()
    row = conn.execute(
        f"""
        SELECT COUNT(*) FROM matter_deadlines
        WHERE matter_id IN ({ph})
          AND status NOT IN ('done', 'completed', 'cancelled')
          AND due_date != '' AND due_date < ?
        """,
        (*mids, today_s),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _count_contradictions(user_id: str) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return 0
    ph = ",".join("?" * len(mids))
    try:
        row = conn.execute(
            f"SELECT COUNT(*) FROM matter_contradictions WHERE matter_id IN ({ph})",
            mids,
        ).fetchone()
    except Exception:
        row = None
    conn.close()
    return int(row[0]) if row else 0


def _count_orders_awaiting_review(user_id: str) -> int:
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    cutoff = (_today() - timedelta(days=30)).isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) FROM matter_court_orders
        WHERE user_id = ?
          AND (
            TRIM(COALESCE(summary, '')) = ''
            OR (created_at >= ? AND TRIM(COALESCE(document_id, '')) = '')
          )
        """,
        (str(user_id), cutoff),
    ).fetchone()
    conn.close()
    return int(row[0]) if row else 0


def _tomorrow_board(user_id: str) -> List[Dict[str, Any]]:
    tomorrow = (_today() + timedelta(days=1)).isoformat()
    return list_firm_hearings(user_id, from_date=tomorrow, to_date=tomorrow, limit=50)


def _upcoming_timeline(user_id: str, *, days: int = 14, limit: int = 20) -> List[Dict[str, Any]]:
    start = _today().isoformat()
    end = (_today() + timedelta(days=days)).isoformat()
    rows = list_firm_hearings(user_id, from_date=start, to_date=end, limit=limit)
    return [
        {
            "hearing_id": h.get("hearing_id"),
            "matter_id": h.get("matter_id"),
            "matter_name": h.get("matter_name"),
            "hearing_date": h.get("hearing_date"),
            "hearing_time": h.get("hearing_time") or "",
            "court_name": h.get("court_name") or "",
            "purpose": h.get("purpose") or "",
            "judge": h.get("judge") or "",
        }
        for h in rows
    ]


def _vip_client_matters(matters: List[Dict[str, Any]], *, limit: int = 10) -> List[Dict[str, str]]:
    vip: List[Dict[str, str]] = []
    for m in matters:
        tier = str(m.get("status_tier") or "").lower()
        if tier in ("vip", "retainer", "priority"):
            vip.append({"matter_id": m["matter_id"], "matter_name": m.get("matter_name") or ""})
    return vip[:limit]


def _high_risk_matters(user_id: str, matters: List[Dict[str, Any]], *, limit: int = 10) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = [m["matter_id"] for m in matters]
    critical_mids: set[str] = set()
    if mids:
        ph = ",".join("?" * len(mids))
        soon = (_today() + timedelta(days=7)).isoformat()
        for row in conn.execute(
            f"""
            SELECT DISTINCT matter_id FROM matter_deadlines
            WHERE matter_id IN ({ph})
              AND due_date <= ? AND due_date >= ?
              AND status NOT IN ('done', 'completed', 'cancelled')
            """,
            (*mids, soon, _today().isoformat()),
        ).fetchall():
            critical_mids.add(str(row[0]))
    conn.close()

    out: List[Dict[str, Any]] = []
    for m in matters:
        pri = str(m.get("priority") or "").lower()
        tier = str(m.get("status_tier") or "").lower()
        mid = m["matter_id"]
        if pri in ("critical", "urgent") and (mid in critical_mids or tier == "high"):
            out.append(
                {
                    "matter_id": mid,
                    "matter_name": m.get("matter_name") or "",
                    "priority": m.get("priority") or "",
                    "has_critical_deadline": mid in critical_mids,
                }
            )
    return out[:limit]


def _today_tasks(user_id: str, *, limit: int = 15) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return []
    ph = ",".join("?" * len(mids))
    today_s = _today().isoformat()
    rows = conn.execute(
        f"""
        SELECT task_id, matter_id, title, due_date, status, assignee
        FROM matter_tasks
        WHERE matter_id IN ({ph})
          AND status NOT IN ('done', 'completed', 'cancelled')
          AND due_date != '' AND due_date <= ?
        ORDER BY due_date ASC LIMIT ?
        """,
        (*mids, today_s, limit),
    ).fetchall()
    conn.close()
    names = {m["matter_id"]: m.get("matter_name", "") for m in list_matters(user_id)}
    return [
        {
            "task_id": r[0],
            "matter_id": r[1],
            "matter_name": names.get(r[1], ""),
            "title": r[2],
            "due_date": r[3],
            "status": r[4],
            "assignee": r[5] or "Unassigned",
        }
        for r in rows
    ]


def _lawyer_workload(user_id: str) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return []
    ph = ",".join("?" * len(mids))
    rows = conn.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(assignee), ''), 'Unassigned') AS lawyer, COUNT(*) AS cnt
        FROM matter_tasks
        WHERE matter_id IN ({ph})
          AND status NOT IN ('done', 'completed', 'cancelled')
        GROUP BY lawyer
        ORDER BY cnt DESC
        LIMIT 10
        """,
        mids,
    ).fetchall()
    conn.close()
    return [{"lawyer": r[0], "open_tasks": int(r[1])} for r in rows]


def _matter_health_scores(user_id: str, matters: List[Dict[str, Any]], *, limit: int = 5) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = [m["matter_id"] for m in matters]
    if not mids:
        conn.close()
        return []
    ph = ",".join("?" * len(mids))
    today_s = _today().isoformat()
    task_counts = {
        r[0]: int(r[1])
        for r in conn.execute(
            f"""
            SELECT matter_id, COUNT(*) FROM matter_tasks
            WHERE matter_id IN ({ph}) AND status NOT IN ('done','completed','cancelled')
            GROUP BY matter_id
            """,
            mids,
        ).fetchall()
    }
    overdue = {
        r[0]: int(r[1])
        for r in conn.execute(
            f"""
            SELECT matter_id, COUNT(*) FROM matter_deadlines
            WHERE matter_id IN ({ph}) AND due_date < ? AND status NOT IN ('done','completed','cancelled')
            GROUP BY matter_id
            """,
            (*mids, today_s),
        ).fetchall()
    }
    conn.close()

    scored: List[Dict[str, Any]] = []
    for m in matters:
        mid = m["matter_id"]
        factors: List[str] = []
        score = 100
        ot = task_counts.get(mid, 0)
        if ot:
            score -= min(30, ot * 5)
            factors.append(f"{ot} open task(s)")
        od = overdue.get(mid, 0)
        if od:
            score -= min(40, od * 15)
            factors.append(f"{od} overdue deadline(s)")
        if str(m.get("priority") or "").lower() in ("urgent", "critical", "high"):
            score -= 15
            factors.append("High priority")
        scored.append(
            {
                "matter_id": mid,
                "matter_name": m.get("matter_name") or "",
                "score": max(0, min(100, score)),
                "factors": factors or ["No issues detected"],
            }
        )
    scored.sort(key=lambda x: x["score"])
    return scored[:limit]


def _build_urgent_alerts(
    user_id: str,
    *,
    matters: List[Dict[str, Any]],
    today_board: List[Dict[str, Any]],
    orders_awaiting: int = 0,
) -> List[Dict[str, str]]:
    alerts: List[Dict[str, str]] = []
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    today_s = _today().isoformat()
    critical_end = (_today() + timedelta(days=3)).isoformat()
    if mids:
        ph = ",".join("?" * len(mids))
        for row in conn.execute(
            f"""
            SELECT matter_id, title, due_date FROM matter_deadlines
            WHERE matter_id IN ({ph})
              AND status NOT IN ('done', 'completed', 'cancelled')
              AND due_date >= ? AND due_date <= ?
            ORDER BY due_date ASC LIMIT 5
            """,
            (*mids, today_s, critical_end),
        ).fetchall():
            alerts.append(
                {
                    "type": "limitation_critical",
                    "message": f"Critical deadline: {row[1]} due {row[2][:10]}",
                    "matter_id": str(row[0]),
                    "href_tab": "limitation",
                }
            )
    conn.close()

    urgent_mids = {
        m["matter_id"]
        for m in matters
        if str(m.get("priority") or "").lower() in ("critical", "urgent")
    }
    for h in today_board:
        mid = str(h.get("matter_id") or "")
        if mid in urgent_mids:
            alerts.append(
                {
                    "type": "urgent_hearing_today",
                    "message": f"Urgent matter in court today: {h.get('matter_name', 'Matter')}",
                    "matter_id": mid,
                    "href_tab": "hearings",
                }
            )

    if orders_awaiting > 0:
        alerts.append(
            {
                "type": "orders_review",
                "message": f"{orders_awaiting} court order(s) awaiting review or document link",
                "matter_id": "",
                "href_tab": "orders",
            }
        )

    if mids:
        ensure_practice_schema()
        conn2 = connect_data_db()
        ph = ",".join("?" * len(mids))
        row = conn2.execute(
            f"""
            SELECT COUNT(*) FROM matter_tasks
            WHERE matter_id IN ({ph})
              AND status NOT IN ('done', 'completed', 'cancelled')
              AND due_date != '' AND due_date < ?
            """,
            (*mids, today_s),
        ).fetchone()
        conn2.close()
        overdue = int(row[0]) if row else 0
        if overdue:
            alerts.append(
                {
                    "type": "overdue_tasks",
                    "message": f"{overdue} overdue task(s) need attention",
                    "matter_id": "",
                    "href_tab": "tasks",
                }
            )

    return alerts[:20]


def _table_count(conn, table: str, mids: List[str], *, user_col: str = "") -> int:
    if not mids:
        return 0
    ph = ",".join("?" * len(mids))
    try:
        if user_col:
            row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {user_col} = ?", (user_col,)).fetchone()
        else:
            row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE matter_id IN ({ph})", mids).fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def get_litigation_diagnostics(user_id: str) -> Dict[str, Any]:
    """Phase 1 module health — row counts, route checks, sync info, issues."""
    from backend.app.core.legacy_db import connect_app_db
    from backend.app.core.user_preferences import get_preference_profile

    ensure_practice_schema()
    matters = list_matters(user_id, include_archived=False)
    mids = [m["matter_id"] for m in matters]
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    ph = ",".join("?" * len(mids)) if mids else ""

    def cnt(sql: str, params: tuple = ()) -> int:
        try:
            row = conn.execute(sql, params).fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return -1

    counts = {
        "matters": len(mids),
        "hearings": cnt(f"SELECT COUNT(*) FROM matter_hearings WHERE matter_id IN ({ph})", mids) if mids else 0,
        "tasks": cnt(f"SELECT COUNT(*) FROM matter_tasks WHERE matter_id IN ({ph})", mids) if mids else 0,
        "deadlines": cnt(f"SELECT COUNT(*) FROM matter_deadlines WHERE matter_id IN ({ph})", mids) if mids else 0,
        "evidence": cnt(f"SELECT COUNT(*) FROM matter_evidence WHERE matter_id IN ({ph})", mids) if mids else 0,
        "orders": cnt("SELECT COUNT(*) FROM matter_court_orders WHERE user_id=?", (str(user_id),)),
        "documents": 0,
    }
    conn.close()

    if mids:
        try:
            app_conn = connect_app_db()
            dph = ",".join("?" * len(mids))
            row = app_conn.execute(
                f"SELECT COUNT(*) FROM documents WHERE uploader_id=? AND matter_id IN ({dph})",
                (str(user_id), *mids),
            ).fetchone()
            counts["documents"] = int(row[0]) if row else 0
            app_conn.close()
        except Exception:
            counts["documents"] = 0

    from backend.app.core.court_sync_settings import get_court_sync_settings
    from backend.app.core.court_sync_log import get_last_court_sync

    sync = get_court_sync_settings(user_id)
    profile = get_preference_profile(user_id)
    last_log = get_last_court_sync(user_id)
    last_sync = {
        "at": (last_log or {}).get("created_at") or profile.get("court_sync_last_at") or profile.get("last_court_sync") or "",
        "mode": (last_log or {}).get("source") or profile.get("court_sync_mode") or sync.get("preferred_mode") or "paste",
        "status": (last_log or {}).get("status") or "",
    }

    import os

    ecourts_key_set = bool(os.getenv("ECOURTSINDIA_API_KEY", "").strip()) or bool(sync.get("api_configured"))
    llm_health = "unknown"
    try:
        from llms import get_generator

        client = get_generator(user_id=user_id)
        if client:
            llm_health = "ok"
        else:
            llm_health = "unconfigured"
    except Exception as exc:
        llm_health = f"error: {exc}"

    issues: List[str] = []
    warnings: List[str] = []
    if counts["hearings"] == 0:
        warnings.append("No hearings — import a cause list via Court Sync or Cause List tab.")
    if not sync.get("api_configured") and not ecourts_key_set:
        warnings.append("eCourtsIndia API key not set — paste/PDF mode still works.")
    awaiting = _count_orders_awaiting_review(user_id)
    if awaiting:
        warnings.append(f"{awaiting} court order(s) need summary or document link.")

    def mod_status(key: str) -> str:
        c = counts.get(key, 0)
        if c < 0:
            issues.append(f"Could not read {key} table.")
            return "error"
        if c == 0:
            return "empty"
        if key == "orders" and awaiting:
            return "partial"
        return "ok"

    modules = [
        {"id": "mission_control", "label": "Mission Control", "status": "ok" if matters else "empty", "records": counts["matters"]},
        {"id": "hearings", "label": "Hearings", "status": mod_status("hearings"), "records": max(0, counts["hearings"])},
        {"id": "tasks", "label": "Tasks", "status": mod_status("tasks"), "records": max(0, counts["tasks"])},
        {"id": "orders", "label": "Orders", "status": mod_status("orders"), "records": max(0, counts["orders"])},
        {"id": "evidence", "label": "Evidence", "status": mod_status("evidence"), "records": max(0, counts["evidence"])},
        {"id": "limitation", "label": "Limitation", "status": mod_status("deadlines"), "records": max(0, counts["deadlines"])},
        {"id": "documents", "label": "Documents", "status": mod_status("documents"), "records": max(0, counts["documents"])},
        {"id": "court_sync", "label": "Court Sync", "status": "ok" if sync.get("api_configured") else "partial", "records": 0},
    ]

    routes: Dict[str, str] = {}
    for name, fn in {
        "dashboard": lambda: get_litigation_dashboard(user_id),
        "hearings": lambda: list_firm_hearings(user_id, limit=1),
        "tasks": lambda: list_firm_litigation_tasks(user_id, limit=1),
        "orders": lambda: list_court_orders(user_id, limit=1),
        "calendar": lambda: get_calendar_events(user_id),
    }.items():
        try:
            fn()
            routes[name] = "ok"
        except Exception as exc:
            routes[name] = "error"
            issues.append(f"Route {name}: {exc}")

    overall = "ok"
    if issues:
        overall = "error"
    elif not matters:
        overall = "empty"
    elif any(m["status"] in ("empty", "partial") for m in modules) or warnings:
        overall = "partial"

    return {
        "ok": True,
        "generated_at": _utc(),
        "overall_status": overall,
        "table_counts": counts,
        "modules": modules,
        "routes": routes,
        "issues": issues,
        "warnings": warnings,
        "last_sync": last_sync,
        "court_sync": {
            "api_configured": sync.get("api_configured") or ecourts_key_set,
            "preferred_mode": sync.get("preferred_mode"),
            "api_key_source": sync.get("api_key_source"),
            "ecourtsindia_env_key": bool(os.getenv("ECOURTSINDIA_API_KEY", "").strip()),
        },
        "llm_health": llm_health,
        "checks": {
            "ecourtsindia_api_key": "ok" if ecourts_key_set else "missing",
            "llm": llm_health,
            "last_court_sync": "ok" if last_sync.get("at") else "never",
        },
    }


def get_litigation_dashboard(user_id: str) -> Dict[str, Any]:
    """Mission Control KPIs for daily litigation practice."""
    digest = get_hearing_digest(user_id, days_ahead=30, days_back=0)
    today_count = digest.get("today_count", 0)
    week_count = digest.get("week_count", 0)

    matters = list_matters(user_id, include_archived=False)
    urgent = sum(1 for m in matters if str(m.get("priority", "")).lower() in ("high", "urgent", "critical"))
    vip = sum(1 for m in matters if str(m.get("status_tier", "")).lower() in ("vip", "retainer", "priority"))

    limitation_due = _count_deadlines_due(user_id, within_days=14)
    limitation_critical = _count_deadlines_due(user_id, within_days=3)
    pending_tasks = _count_open_tasks(user_id)
    evidence_records = _count_evidence_records(user_id)
    evidence_pending_review = _count_evidence_pending_review(user_id)

    affidavits_pending = _count_open_tasks(user_id, hearing_linked=True)
    court_appearances = today_count

    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    mids = _user_matter_ids(user_id)
    drafts_pending = 0
    if mids:
        ph = ",".join("?" * len(mids))
        try:
            row = conn.execute(
                f"""
                SELECT COUNT(*) FROM matter_tasks
                WHERE matter_id IN ({ph})
                  AND status NOT IN ('done', 'completed')
                  AND (title LIKE '%draft%' OR title LIKE '%petition%' OR title LIKE '%affidavit%')
                """,
                mids,
            ).fetchone()
            drafts_pending = int(row[0]) if row else 0
        except Exception:
            pass
    conn.close()

    tomorrow_board = _tomorrow_board(user_id)
    recent_orders = list_court_orders(user_id, limit=10)
    today_tasks = _today_tasks(user_id)
    vip_list = _vip_client_matters(matters)
    high_risk = _high_risk_matters(user_id, matters)
    timeline = _upcoming_timeline(user_id)
    orders_awaiting = _count_orders_awaiting_review(user_id)
    alerts = _build_urgent_alerts(
        user_id,
        matters=matters,
        today_board=digest.get("today") or [],
        orders_awaiting=orders_awaiting,
    )

    return {
        "today_hearings": today_count,
        "tomorrow_hearings": len(tomorrow_board),
        "this_week_hearings": week_count,
        "upcoming_hearings": len(digest.get("upcoming") or []),
        "urgent_matters": urgent,
        "vip_clients": vip,
        "high_risk_matters": len(high_risk),
        "limitation_deadlines": limitation_due,
        "limitation_critical": limitation_critical,
        "pending_tasks": pending_tasks,
        "evidence_records": evidence_records,
        "evidence_pending": evidence_records,
        "evidence_pending_review": evidence_pending_review,
        "affidavits_pending": affidavits_pending,
        "court_appearances": today_count,
        "drafts_pending": drafts_pending,
        "orders_awaiting_review": orders_awaiting,
        "active_matters": len(matters),
        "today_board": digest.get("today") or [],
        "tomorrow_board": tomorrow_board,
        "week_board": digest.get("this_week") or [],
        "upcoming_timeline": timeline,
        "recent_orders": recent_orders,
        "today_tasks": today_tasks,
        "urgent_alerts": alerts,
        "vip_client_matters": vip_list,
        "high_risk_list": high_risk,
        "lawyer_workload": _lawyer_workload(user_id),
        "matter_health": _matter_health_scores(user_id, matters),
        "generated_at": _utc(),
    }


def list_firm_hearings(
    user_id: str,
    *,
    matter_id: str = "",
    status: str = "",
    from_date: str = "",
    to_date: str = "",
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """All hearings across matters with full management fields."""
    matters = list_matters(user_id, include_archived=False)
    if matter_id:
        matters = [m for m in matters if m["matter_id"] == matter_id]
    names = {m["matter_id"]: m.get("matter_name", "") for m in matters}
    case_nums = {m["matter_id"]: m.get("case_number", "") for m in matters}
    out: List[Dict[str, Any]] = []
    fd = _parse_hearing_date(from_date) if from_date else None
    td = _parse_hearing_date(to_date) if to_date else None

    for m in matters:
        mid = m["matter_id"]
        for h in list_hearings(user_id, mid):
            if status and (h.get("status") or "").lower() != status.lower():
                continue
            hd = _parse_hearing_date(h.get("hearing_date") or "")
            if fd and hd and hd < fd:
                continue
            if td and hd and hd > td:
                continue
            out.append(
                {
                    **h,
                    "matter_id": mid,
                    "matter_name": names.get(mid, ""),
                    "case_number": case_nums.get(mid, ""),
                    "stage": h.get("stage") or h.get("purpose", ""),
                    "assigned_lawyer": h.get("assigned_lawyer") or "",
                    "hearing_time": h.get("hearing_time") or "",
                }
            )
    out.sort(key=lambda x: (x.get("hearing_date") or "", x.get("hearing_time") or ""))
    return out[:limit]


def get_calendar_events(
    user_id: str,
    *,
    year: int = 0,
    month: int = 0,
) -> Dict[str, Any]:
    """Events for calendar month/week/day views."""
    today = _today()
    y = year or today.year
    mo = month or today.month
    start = date(y, mo, 1)
    if mo == 12:
        end = date(y + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(y, mo + 1, 1) - timedelta(days=1)

    hearings = list_firm_hearings(user_id, from_date=start.isoformat(), to_date=end.isoformat(), limit=500)
    events = []
    for h in hearings:
        d = h.get("hearing_date") or ""
        events.append(
            {
                "id": h.get("hearing_id"),
                "type": "hearing",
                "title": f"{h.get('matter_name', 'Matter')} — {h.get('purpose') or 'Hearing'}",
                "date": d[:10] if d else "",
                "time": h.get("hearing_time") or "",
                "court": h.get("court_name") or "",
                "judge": h.get("judge") or "",
                "matter_id": h.get("matter_id"),
                "status": h.get("status") or "scheduled",
            }
        )

    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if mids:
        ph = ",".join("?" * len(mids))
        for row in conn.execute(
            f"""
            SELECT deadline_id, matter_id, title, due_date, deadline_type, status
            FROM matter_deadlines
            WHERE matter_id IN ({ph}) AND due_date >= ? AND due_date <= ?
            """,
            (*mids, start.isoformat(), end.isoformat()),
        ).fetchall():
            events.append(
                {
                    "id": row[0],
                    "type": "deadline",
                    "title": row[2],
                    "date": row[3][:10] if row[3] else "",
                    "time": "",
                    "court": "",
                    "matter_id": row[1],
                    "deadline_type": row[4],
                    "status": row[5],
                }
            )
    conn.close()
    events.sort(key=lambda e: (e.get("date") or "", e.get("time") or ""))
    return {"year": y, "month": mo, "events": events, "hearing_count": len([e for e in events if e["type"] == "hearing"])}


def list_firm_litigation_tasks(user_id: str, *, matter_id: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = [matter_id] if matter_id else _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return []
    names = {m["matter_id"]: m.get("matter_name", "") for m in list_matters(user_id)}
    ph = ",".join("?" * len(mids))
    rows = conn.execute(
        f"""
        SELECT task_id, matter_id, title, due_date, status, assignee, created_at
        FROM matter_tasks WHERE matter_id IN ({ph})
        ORDER BY CASE WHEN due_date = '' THEN 1 ELSE 0 END, due_date ASC
        LIMIT ?
        """,
        (*mids, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "task_id": r[0],
            "matter_id": r[1],
            "matter_name": names.get(r[1], ""),
            "title": r[2],
            "due_date": r[3],
            "status": r[4],
            "assignee": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def create_litigation_task(
    user_id: str,
    *,
    matter_id: str,
    title: str,
    due_date: str = "",
    assignee: str = "",
) -> Dict[str, Any]:
    from backend.app.core.matter_workflow import add_task

    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    return add_task(user_id, matter_id, title=title, due_date=due_date, assignee=assignee)


def update_litigation_task(user_id: str, task_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return {"error": "Task not found"}
    ph = ",".join("?" * len(mids))
    row = conn.execute(
        f"SELECT matter_id FROM matter_tasks WHERE task_id = ? AND matter_id IN ({ph})",
        (task_id, *mids),
    ).fetchone()
    conn.close()
    if not row:
        return {"error": "Task not found"}
    from backend.app.core.matter_workflow import update_task

    out = update_task(user_id, row[0], task_id, **fields)
    if not out:
        return {"error": "No fields to update"}
    return {"ok": True, "matter_id": row[0], **out}


def delete_litigation_task(user_id: str, task_id: str) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return {"error": "Task not found"}
    ph = ",".join("?" * len(mids))
    row = conn.execute(
        f"SELECT matter_id FROM matter_tasks WHERE task_id = ? AND matter_id IN ({ph})",
        (task_id, *mids),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Task not found"}
    from backend.app.core.matter_workflow import delete_task

    ok = delete_task(user_id, row[0], task_id)
    conn.close()
    if not ok:
        return {"error": "Task not found"}
    return {"ok": True, "deleted": task_id}


def create_firm_hearing(user_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    matter_id = body.get("matter_id") or ""
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    try:
        hearing = schedule_hearing(
            user_id,
            matter_id,
            hearing_date=body.get("hearing_date") or "",
            court_name=body.get("court_name") or "",
            purpose=body.get("purpose") or "",
            notes=body.get("notes") or "",
            judge_name=body.get("judge") or "",
        )
        if body.get("status") or body.get("hearing_time") or body.get("assigned_lawyer"):
            hid = hearing.get("hearing_id") or hearing.get("id")
            if hid:
                update_firm_hearing(
                    user_id,
                    str(hid),
                    {
                        k: v
                        for k, v in {
                            "status": body.get("status"),
                            "hearing_time": body.get("hearing_time"),
                            "assigned_lawyer": body.get("assigned_lawyer"),
                            "stage": body.get("stage"),
                        }.items()
                        if v
                    },
                )
        return {"ok": True, "hearing": hearing}
    except ValueError as exc:
        return {"error": str(exc)}


def delete_court_order(user_id: str, order_id: str) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    cur = conn.execute(
        "DELETE FROM matter_court_orders WHERE order_id=? AND user_id=?",
        (order_id, str(user_id)),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        return {"error": "Order not found"}
    return {"ok": True, "deleted": order_id}


def list_firm_limitation_deadlines(user_id: str, *, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if not mids:
        conn.close()
        return []
    names = {m["matter_id"]: m.get("matter_name", "") for m in list_matters(user_id)}
    ph = ",".join("?" * len(mids))
    rows = conn.execute(
        f"""
        SELECT deadline_id, matter_id, title, due_date, deadline_type, status, notes
        FROM matter_deadlines WHERE matter_id IN ({ph})
        ORDER BY due_date ASC LIMIT ?
        """,
        (*mids, limit),
    ).fetchall()
    conn.close()
    today = _today()
    out: List[Dict[str, Any]] = []
    for r in rows:
        due = (r[3] or "")[:10]
        days_remaining: Optional[int] = None
        if due:
            try:
                days_remaining = (date.fromisoformat(due) - today).days
            except ValueError:
                pass
        out.append(
            {
                "deadline_id": r[0],
                "matter_id": r[1],
                "matter_name": names.get(r[1], ""),
                "title": r[2],
                "due_date": r[3],
                "deadline_type": r[4],
                "status": r[5],
                "notes": r[6],
                "days_remaining": days_remaining,
            }
        )
    return out


def get_litigation_notifications(user_id: str) -> Dict[str, Any]:
    matters = list_matters(user_id, include_archived=False)
    digest = get_hearing_digest(user_id, days_ahead=7)
    orders_awaiting = _count_orders_awaiting_review(user_id)
    alerts = _build_urgent_alerts(
        user_id,
        matters=matters,
        today_board=digest.get("today") or [],
        orders_awaiting=orders_awaiting,
    )
    from backend.app.core.court_sync_log import list_court_sync_history

    notifications: List[Dict[str, Any]] = list(alerts)
    for entry in list_court_sync_history(user_id, limit=5):
        if entry.get("status") != "ok":
            err_text = ", ".join(entry.get("errors") or []) or (entry.get("detail") or "")[:120]
            notifications.append(
                {
                    "type": "sync_failure",
                    "message": f"Court sync failed ({entry.get('source')}): {err_text or 'unknown error'}",
                    "matter_id": "",
                    "href_tab": "court-sync",
                    "created_at": entry.get("created_at"),
                }
            )
    return {"notifications": notifications, "unread_count": len(notifications)}


def list_court_orders(user_id: str, *, matter_id: str = "", q: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    sql = "SELECT order_id, matter_id, order_type, title, order_date, court_name, judge, summary, document_id, tags, created_at FROM matter_court_orders WHERE user_id=?"
    params: List[Any] = [str(user_id)]
    if matter_id:
        sql += " AND matter_id=?"
        params.append(matter_id)
    if q.strip():
        sql += " AND (title LIKE ? OR summary LIKE ? OR tags LIKE ?)"
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    sql += " ORDER BY order_date DESC, created_at DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    names = {m["matter_id"]: m.get("matter_name", "") for m in list_matters(user_id)}
    return [
        {
            "order_id": r[0],
            "matter_id": r[1],
            "matter_name": names.get(r[1], ""),
            "order_type": r[2],
            "title": r[3],
            "order_date": r[4],
            "court_name": r[5],
            "judge": r[6],
            "summary": r[7],
            "document_id": r[8],
            "tags": r[9],
            "created_at": r[10],
        }
        for r in rows
    ]


def save_court_order(user_id: str, body: Dict[str, Any], *, order_id: str = "") -> Dict[str, Any]:
    matter_id = body.get("matter_id") or ""
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    ensure_practice_schema()
    conn = connect_data_db()
    _ensure_litigation_tables(conn)
    now = _utc()
    oid = order_id or str(uuid.uuid4())
    otype = body.get("order_type") or "order"
    if otype not in ORDER_TYPES:
        otype = "order"
    title = (body.get("title") or "Court order").strip()
    existing = conn.execute(
        "SELECT order_id FROM matter_court_orders WHERE order_id=? AND user_id=?",
        (oid, str(user_id)),
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE matter_court_orders SET matter_id=?, order_type=?, title=?, order_date=?,
                court_name=?, judge=?, summary=?, document_id=?, tags=?, updated_at=?
            WHERE order_id=? AND user_id=?
            """,
            (
                matter_id,
                otype,
                title,
                body.get("order_date") or "",
                body.get("court_name") or "",
                body.get("judge") or "",
                body.get("summary") or "",
                body.get("document_id") or "",
                body.get("tags") or "",
                now,
                oid,
                str(user_id),
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_court_orders
            (order_id, matter_id, user_id, order_type, title, order_date, court_name, judge,
             summary, document_id, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                oid,
                matter_id,
                str(user_id),
                otype,
                title,
                body.get("order_date") or "",
                body.get("court_name") or "",
                body.get("judge") or "",
                body.get("summary") or "",
                body.get("document_id") or "",
                body.get("tags") or "",
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()
    return {"order_id": oid, "saved": True}


def get_watchlist_dashboard(user_id: str) -> Dict[str, Any]:
    from backend.app.core.legal_watchlist import list_watches

    items = list_watches(user_id)
    matters = {m["matter_id"]: m for m in list_matters(user_id)}
    buckets: Dict[str, List[Dict[str, Any]]] = {
        "urgent_hearings": [],
        "high_risk": [],
        "vip_clients": [],
        "high_value": [],
        "critical_deadlines": [],
    }
    for w in items:
        mid = w.get("matter_id") or ""
        m = matters.get(mid) or {}
        entry = {**w, "matter_name": m.get("matter_name", "")}
        wt = (w.get("watch_type") or "").lower()
        if wt == "hearing":
            buckets["urgent_hearings"].append(entry)
        elif "risk" in (w.get("label") or "").lower():
            buckets["high_risk"].append(entry)
        elif m.get("status_tier", "").lower() == "vip":
            buckets["vip_clients"].append(entry)
        else:
            buckets["high_risk"].append(entry)

    for m in matters.values():
        if str(m.get("priority", "")).lower() in ("high", "urgent"):
            if not any(x.get("matter_id") == m["matter_id"] for x in buckets["high_risk"]):
                buckets["high_risk"].append(
                    {"matter_id": m["matter_id"], "matter_name": m.get("matter_name"), "label": "Urgent matter", "watch_type": "matter"}
                )
        if str(m.get("status_tier", "")).lower() == "vip":
            buckets["vip_clients"].append(
                {"matter_id": m["matter_id"], "matter_name": m.get("matter_name"), "label": "VIP client", "watch_type": "client"}
            )

    ensure_practice_schema()
    conn = connect_data_db()
    mids = _user_matter_ids(user_id)
    if mids:
        ph = ",".join("?" * len(mids))
        soon = (_today() + timedelta(days=5)).isoformat()
        for row in conn.execute(
            f"""
            SELECT deadline_id, matter_id, title, due_date FROM matter_deadlines
            WHERE matter_id IN ({ph}) AND due_date <= ? AND status NOT IN ('done','completed')
            ORDER BY due_date LIMIT 20
            """,
            (*mids, soon),
        ).fetchall():
            buckets["critical_deadlines"].append(
                {
                    "deadline_id": row[0],
                    "matter_id": row[1],
                    "matter_name": matters.get(row[1], {}).get("matter_name", ""),
                    "title": row[2],
                    "due_date": row[3],
                }
            )
    conn.close()
    return {"buckets": buckets, "total_watches": len(items)}


def get_litigation_analytics(user_id: str) -> Dict[str, Any]:
    matters = list_matters(user_id, include_archived=True)
    active = [m for m in matters if not m.get("is_archived") and str(m.get("status_tier", "")).lower() not in ("closed", "disposed")]
    disposed = [
        m
        for m in matters
        if m.get("is_archived") or str(m.get("status_tier", "")).lower() in ("closed", "disposed")
    ]

    digest = get_hearing_digest(user_id, days_ahead=60)
    hearings = list_firm_hearings(user_id, limit=500)

    by_court: Dict[str, int] = {}
    by_lawyer: Dict[str, int] = {}
    for h in hearings:
        court = h.get("court_name") or "Unknown"
        by_court[court] = by_court.get(court, 0) + 1
        lawyer = h.get("assigned_lawyer") or "Unassigned"
        by_lawyer[lawyer] = by_lawyer.get(lawyer, 0) + 1

    total_cases = len(active) + len(disposed)
    win_rate = round(100.0 * len(disposed) / total_cases, 1) if total_cases else 0.0

    overdue = _count_overdue_deadlines(user_id)
    open_tasks = _count_open_tasks(user_id)
    evidence_count = _count_evidence_records(user_id)
    contradiction_count = _count_contradictions(user_id)

    def _risk_score(base: int, penalty: int, count: int, cap: int = 40) -> int:
        return max(5, min(98, base - min(cap, count * penalty)))

    risk_score = {
        "success_probability": _risk_score(90, 6, overdue),
        "evidence_strength": _risk_score(85, 4, max(0, 8 - min(evidence_count, 8))),
        "witness_reliability": _risk_score(80, 7, contradiction_count),
        "document_completeness": _risk_score(88, 3, open_tasks),
    }

    return {
        "active_cases": len(active),
        "disposed_cases": len(disposed),
        "upcoming_hearings": len(digest.get("upcoming") or []),
        "win_rate_pct": win_rate,
        "court_workload": [{"court": k, "hearings": v} for k, v in sorted(by_court.items(), key=lambda x: -x[1])[:12]],
        "lawyer_workload": [{"lawyer": k, "hearings": v} for k, v in sorted(by_lawyer.items(), key=lambda x: -x[1])[:12]],
        "risk_score": risk_score,
        "metrics_source": "computed",
        "risk_factors": {
            "overdue_deadlines": overdue,
            "open_tasks": open_tasks,
            "evidence_records": evidence_count,
            "contradictions": contradiction_count,
        },
    }


def get_matter_war_room(user_id: str, matter_id: str) -> Dict[str, Any]:
    m = get_matter(user_id, matter_id)
    if not m:
        return {"error": "Matter not found"}
    return {
        "matter": m,
        "hearings": list_hearings(user_id, matter_id),
        "tasks": list_firm_litigation_tasks(user_id, matter_id=matter_id, limit=50),
        "orders": list_court_orders(user_id, matter_id=matter_id, limit=30),
        "deadlines": _list_deadlines(user_id, matter_id),
        "prep_available": True,
        "collaboration_url": f"/collaboration?matter={matter_id}",
        "documents_url": f"/matters/{matter_id}",
    }


def _list_deadlines(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT deadline_id, title, due_date, deadline_type, status, notes
        FROM matter_deadlines WHERE matter_id=? ORDER BY due_date
        """,
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "deadline_id": r[0],
            "title": r[1],
            "due_date": r[2],
            "deadline_type": r[3],
            "status": r[4],
            "notes": r[5],
        }
        for r in rows
    ]


def run_litigation_ai(
    user_id: str,
    *,
    tool: str,
    matter_id: str,
    extra: str = "",
) -> Dict[str, Any]:
    """AI litigation assistant — hearing brief, order summary, timeline, etc."""
    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    tool = (tool or "").strip().lower()
    if tool == "hearing_brief" or tool == "prep_pack":
        from backend.app.core.hearing_prep_pack import build_hearing_prep_pack

        return build_hearing_prep_pack(user_id, matter_id, use_ai=True)
    if tool == "timeline":
        from backend.app.core.matter_workflow import list_timeline

        return {"ok": True, "events": list_timeline(user_id, matter_id)}
    if tool == "contradictions":
        from backend.app.core.matter_enhancements import analyze_contradictions

        return analyze_contradictions(user_id, matter_id)
    if tool == "order_summary":
        orders = list_court_orders(user_id, matter_id=matter_id, limit=5)
        text = "\n".join(f"{o['title']}: {o['summary']}" for o in orders) or extra or "No orders on file."
        return _ai_text(user_id, matter_id, f"Summarize these court orders for counsel:\n{text}")
    if tool == "cross_examination":
        return _ai_text(
            user_id,
            matter_id,
            "Generate 10 cross-examination questions for the opposing witness based on case facts. "
            f"Context: {extra[:2000]}",
        )
    if tool == "evidence_gaps":
        from backend.app.core.matter_evidence import list_evidence

        ev = list_evidence(user_id, matter_id)
        ev_text = json.dumps([e.get("title") for e in ev[:20]])
        return _ai_text(user_id, matter_id, f"List missing evidence gaps for this case. Current evidence: {ev_text}")
    return {"error": f"Unknown tool: {tool}. Use hearing_brief, timeline, contradictions, order_summary, cross_examination, evidence_gaps"}


def _ai_text(user_id: str, matter_id: str, prompt: str) -> Dict[str, Any]:
    m = get_matter(user_id, matter_id) or {}
    try:
        from llms import get_generator

        client = get_generator(user_id=user_id)
        if not client:
            return {"ok": False, "text": "", "error": "LLM not configured"}
        full = (
            f"Matter: {m.get('matter_name')}. Case: {m.get('case_number')}. Court: {m.get('venue')}.\n\n{prompt}"
        )
        text = (client.generate(full, max_tokens=1200, temperature=0.35) or "").strip()
        return {"ok": True, "text": text, "matter_id": matter_id}
    except Exception as exc:
        return {"ok": False, "text": "", "error": str(exc)}


def update_firm_hearing(user_id: str, hearing_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT h.hearing_id, h.matter_id FROM matter_hearings h
        JOIN matters m ON m.matter_id = h.matter_id
        WHERE h.hearing_id = ? AND m.user_id = ?
        """,
        (hearing_id, str(user_id)),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Hearing not found"}
    mid = row[1]
    allowed = {
        "hearing_date", "hearing_time", "court_name", "judge", "purpose", "stage",
        "status", "notes", "assigned_lawyer", "next_hearing_date",
    }
    sets = []
    params = []
    for k, v in fields.items():
        if k in allowed and v is not None:
            sets.append(f"{k}=?")
            params.append(v)
    if not sets:
        conn.close()
        return {"error": "No fields to update"}
    params.append(hearing_id)
    conn.execute(f"UPDATE matter_hearings SET {', '.join(sets)} WHERE hearing_id=?", params)
    conn.commit()
    conn.close()
    for h in list_hearings(user_id, mid):
        if h.get("hearing_id") == hearing_id:
            return {"ok": True, "hearing": h}
    return {"ok": True}
