"""Product KPI metrics for SaaS dashboard — MAU, DAU, retention, AI accuracy."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from backend.app.core.database import connect_data_db
from backend.app.core.saas_ops_schema import ensure_saas_ops_schema


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago_iso(days: int) -> str:
    return (_utc_now() - timedelta(days=days)).isoformat()


def get_product_kpis() -> Dict[str, Any]:
    """Aggregate north-star metrics from existing tables."""
    ensure_saas_ops_schema()
    conn = connect_data_db()
    out: Dict[str, Any] = {
        "generated_at": _utc_now().isoformat(),
        "users_total": 0,
        "dau": 0,
        "mau": 0,
        "new_users_7d": 0,
        "chat_turns_7d": 0,
        "chat_turns_30d": 0,
        "documents_total": 0,
        "matters_total": 0,
        "subscriptions_by_plan": {},
        "ai": {
            "feedback_positive": 0,
            "feedback_negative": 0,
            "hit_rate_pct": 0.0,
            "not_found_rate_pct": 0.0,
        },
        "plans": {"Free": 0, "Pro": 0, "Legal Pro": 0},
        "retention_proxy_pct": 0.0,
    }
    try:
        out["users_total"] = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
    except Exception:
        pass
    try:
        out["new_users_7d"] = int(
            conn.execute(
                "SELECT COUNT(*) FROM users WHERE created_at >= ?",
                (_days_ago_iso(7),),
            ).fetchone()[0]
        )
    except Exception:
        pass
    for days, key in ((1, "dau"), (30, "mau")):
        try:
            out[key] = int(
                conn.execute(
                    """
                    SELECT COUNT(DISTINCT user_id) FROM chat_history
                    WHERE created_at >= ?
                    """,
                    (_days_ago_iso(days),),
                ).fetchone()[0]
            )
        except Exception:
            pass
    for days, key in ((7, "chat_turns_7d"), (30, "chat_turns_30d")):
        try:
            out[key] = int(
                conn.execute(
                    "SELECT COUNT(*) FROM chat_history WHERE created_at >= ?",
                    (_days_ago_iso(days),),
                ).fetchone()[0]
            )
        except Exception:
            pass
    for table, key in (("documents", "documents_total"), ("matters", "matters_total")):
        try:
            out[key] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        except Exception:
            pass
    try:
        rows = conn.execute(
            "SELECT membership, COUNT(*) FROM users GROUP BY membership"
        ).fetchall()
        for mem, cnt in rows:
            label = str(mem or "Free")
            out["plans"][label] = int(cnt)
    except Exception:
        pass
    try:
        rows = conn.execute(
            """
            SELECT plan, COUNT(*) FROM subscriptions
            WHERE status IN ('active', 'trialing', 'past_due')
            GROUP BY plan
            """
        ).fetchall()
        out["subscriptions_by_plan"] = {str(r[0]): int(r[1]) for r in rows}
    except Exception:
        pass
    try:
        pos = int(
            conn.execute(
                "SELECT COUNT(*) FROM adaptive_interactions WHERE feedback = 'up'"
            ).fetchone()[0]
        )
        neg = int(
            conn.execute(
                "SELECT COUNT(*) FROM adaptive_interactions WHERE feedback = 'down'"
            ).fetchone()[0]
        )
        hits = int(
            conn.execute(
                "SELECT COUNT(*) FROM adaptive_interactions WHERE found = 1"
            ).fetchone()[0]
        )
        all_ix = int(conn.execute("SELECT COUNT(*) FROM adaptive_interactions").fetchone()[0])
        nf = int(
            conn.execute(
                "SELECT COUNT(*) FROM adaptive_interactions WHERE found = 0"
            ).fetchone()[0]
        )
        out["ai"]["feedback_positive"] = pos
        out["ai"]["feedback_negative"] = neg
        if all_ix:
            out["ai"]["hit_rate_pct"] = round(100.0 * hits / all_ix, 1)
            out["ai"]["not_found_rate_pct"] = round(100.0 * nf / all_ix, 1)
    except Exception:
        pass
    conn.close()
    if out["mau"]:
        out["retention_proxy_pct"] = round(100.0 * out["dau"] / out["mau"], 1)
    return out
