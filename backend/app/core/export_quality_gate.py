"""
Export quality gate — block Modelfile / ollama create until learning quality thresholds met.
"""
from __future__ import annotations

import os
import time
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

MIN_DISTINCT_SFT_QUERIES = int(os.getenv("EXPORT_MIN_DISTINCT_QUERIES", "5"))
MIN_POSITIVE_WEEK_RATIO = float(os.getenv("EXPORT_MIN_POSITIVE_WEEK_RATIO", "0.55"))
MIN_NET_POSITIVE_WEEK = int(os.getenv("EXPORT_MIN_NET_POSITIVE_WEEK", "0"))
REQUIRE_EVAL_PASS = os.getenv("EXPORT_REQUIRE_EVAL_PASS", "1").lower() in {"1", "true", "yes"}
HOLDOUT_CACHE_TTL_SEC = int(os.getenv("HOLDOUT_CACHE_TTL_SEC", "900"))

_holdout_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_holdout_cache_lock = threading.Lock()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def count_distinct_positive_queries(user_id: str) -> int:
    from backend.app.core.database import connect_data_db
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    conn = connect_data_db()
    try:
        row = conn.execute(
            """SELECT COUNT(DISTINCT i.query_norm) FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id = ? AND f.signal IN (
                'thumbs_up', 'helpful', 'verbal_positive', 'copy', 'export_docx', 'export_pdf', 'save_to_matter'
            )""",
            (str(user_id),),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def week_feedback_balance(user_id: str, days: int = 7) -> Dict[str, Any]:
    from backend.app.core.database import connect_data_db
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    since = (_utc_now() - timedelta(days=days)).isoformat()
    conn = connect_data_db()
    try:
        pos = conn.execute(
            """SELECT COUNT(*) FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id = ? AND f.created_at >= ?
            AND f.signal IN ('thumbs_up', 'helpful', 'verbal_positive', 'copy', 'export_docx', 'export_pdf', 'save_to_matter')""",
            (str(user_id), since),
        ).fetchone()
        neg = conn.execute(
            """SELECT COUNT(*) FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id = ? AND f.created_at >= ?
            AND f.signal IN ('thumbs_down', 'verbal_negative', 'regenerate', 'wrong', 'not_helpful', 'mode_switch')""",
            (str(user_id), since),
        ).fetchone()
        p = int(pos[0] if pos else 0)
        n = int(neg[0] if neg else 0)
        total = p + n
        ratio = (p / total) if total else 1.0
        return {
            "positive": p,
            "negative": n,
            "net": p - n,
            "ratio": round(ratio, 3),
            "days": days,
        }
    finally:
        conn.close()


def _cached_holdout_eval(user_id: str, *, refresh: bool = False) -> Dict[str, Any]:
    """Run holdout RAG probes with TTL cache — avoids hammering KB on every UI poll."""
    uid = str(user_id)
    now = time.time()
    with _holdout_cache_lock:
        cached = _holdout_cache.get(uid)
        if cached and not refresh and (now - cached[0]) < HOLDOUT_CACHE_TTL_SEC:
            out = dict(cached[1])
            out["cached"] = True
            return out
    try:
        from backend.app.core.eval_holdout import run_holdout_eval

        result = run_holdout_eval(uid)
    except Exception as exc:
        result = {"passed": False, "error": str(exc)[:120], "summary": str(exc)[:120]}
    with _holdout_cache_lock:
        _holdout_cache[uid] = (now, result)
    out = dict(result)
    out["cached"] = False
    return out


def check_export_quality_gate(
    user_id: str,
    *,
    force: bool = False,
    include_holdout: bool = True,
    refresh_holdout: bool = False,
) -> Dict[str, Any]:
    """
    Returns {passed, reasons, checks}.
    force=True skips gate (manual override from Settings).
    include_holdout=False skips expensive RAG probes (for /learning/progress polls).
    """
    if force:
        return {"passed": True, "forced": True, "reasons": [], "checks": {}}

    uid = str(user_id)
    reasons: List[str] = []
    checks: Dict[str, Any] = {}

    distinct = count_distinct_positive_queries(uid)
    checks["distinct_positive_queries"] = distinct
    if distinct < MIN_DISTINCT_SFT_QUERIES:
        reasons.append(
            f"Need at least {MIN_DISTINCT_SFT_QUERIES} distinct positively-rated queries "
            f"(have {distinct})."
        )

    balance = week_feedback_balance(uid)
    checks["week_feedback"] = balance
    if balance["net"] < MIN_NET_POSITIVE_WEEK:
        reasons.append(
            f"Net feedback this week is negative ({balance['positive']} up vs {balance['negative']} down)."
        )
    if balance["positive"] + balance["negative"] >= 3 and balance["ratio"] < MIN_POSITIVE_WEEK_RATIO:
        reasons.append(
            f"Positive feedback ratio this week too low ({int(balance['ratio'] * 100)}%)."
        )

    eval_result: Dict[str, Any] = {"skipped": True}
    if REQUIRE_EVAL_PASS and include_holdout:
        try:
            eval_result = _cached_holdout_eval(uid, refresh=refresh_holdout)
            checks["holdout_eval"] = eval_result
            if not eval_result.get("passed", False):
                reasons.append(
                    eval_result.get("summary") or "Holdout eval did not pass."
                )
        except Exception as exc:
            checks["holdout_eval"] = {"passed": False, "error": str(exc)[:120]}
            reasons.append(f"Holdout eval error: {str(exc)[:80]}")
    elif REQUIRE_EVAL_PASS:
        with _holdout_cache_lock:
            cached = _holdout_cache.get(uid)
        if cached:
            eval_result = dict(cached[1])
            eval_result["cached"] = True
            checks["holdout_eval"] = eval_result
            if not eval_result.get("passed", False):
                reasons.append(
                    eval_result.get("summary") or "Holdout eval did not pass (cached)."
                )
        else:
            checks["holdout_eval"] = {
                "skipped": True,
                "reason": "Holdout not run on progress poll — run export or wait for cache.",
            }

    passed = len(reasons) == 0
    return {
        "passed": passed,
        "reasons": reasons,
        "checks": checks,
        "thresholds": {
            "min_distinct_queries": MIN_DISTINCT_SFT_QUERIES,
            "min_positive_week_ratio": MIN_POSITIVE_WEEK_RATIO,
            "require_eval_pass": REQUIRE_EVAL_PASS,
        },
    }
