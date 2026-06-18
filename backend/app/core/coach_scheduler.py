"""
Scheduled auto-coaching — daily, weekly, and monthly improvement tiers.

Daily (default 1 day): lightweight coach + retrieval learning sync.
Weekly (7 days): preference digest, SFT export, semantic follow-up stats.
Monthly (30 days): full pipeline — neural train, re-index, Modelfile, DPO export.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUTO_SCHEDULE = os.getenv("COACH_AUTO_SCHEDULE", "1").lower() in {"1", "true", "yes"}
DAILY_INTERVAL_DAYS = float(os.getenv("COACH_AUTO_INTERVAL_DAYS", os.getenv("COACH_DAILY_INTERVAL_DAYS", "1")))
WEEKLY_INTERVAL_DAYS = float(os.getenv("COACH_WEEKLY_INTERVAL_DAYS", "7"))
MONTHLY_INTERVAL_DAYS = float(os.getenv("COACH_MONTHLY_INTERVAL_DAYS", "30"))
MIN_NEW_FEEDBACK = int(os.getenv("COACH_AUTO_MIN_NEW_FEEDBACK", "1"))
WEEKLY_MIN_FEEDBACK = int(os.getenv("COACH_WEEKLY_MIN_FEEDBACK", "3"))
MONTHLY_MIN_FEEDBACK = int(os.getenv("COACH_MONTHLY_MIN_FEEDBACK", "5"))
CHECK_INTERVAL_SEC = int(os.getenv("COACH_AUTO_CHECK_INTERVAL_SEC", "1800"))

_started = False


def _parse_iso(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _elapsed_days(last_iso: Optional[str]) -> float:
    last = _parse_iso(last_iso or "")
    if not last:
        return 999.0
    return (datetime.now(timezone.utc) - last).total_seconds() / 86400


def count_feedback_since(user_id: str, since_iso: str = "") -> int:
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    from backend.app.core.database import connect_data_db

    conn = connect_data_db()
    try:
        if since_iso:
            row = conn.execute(
                """SELECT COUNT(*) FROM adaptive_feedback f
                JOIN adaptive_interactions i ON i.id = f.interaction_id
                WHERE i.user_id = ? AND f.created_at > ?""",
                (str(user_id), since_iso),
            ).fetchone()
        else:
            row = conn.execute(
                """SELECT COUNT(*) FROM adaptive_feedback f
                JOIN adaptive_interactions i ON i.id = f.interaction_id
                WHERE i.user_id = ?""",
                (str(user_id),),
            ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def list_coach_enabled_users() -> List[str]:
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema, _connect

    ensure_coach_schema()
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.database import connect_data_db

    ensure_learning_schema()
    uids: set[str] = set()
    conn = _connect()
    try:
        for row in conn.execute("SELECT user_id FROM ollama_coach_prefs WHERE enabled = 1").fetchall():
            uids.add(str(row[0]))
    finally:
        conn.close()
    conn2 = connect_data_db()
    try:
        for row in conn2.execute(
            "SELECT DISTINCT user_id FROM adaptive_interactions WHERE user_id IS NOT NULL AND user_id != ''"
        ).fetchall():
            uids.add(str(row[0]))
    finally:
        conn2.close()
    return list(uids)


def _ensure_schedule_columns(conn) -> None:
    from backend.app.core.gemini_ollama_coach import _ensure_column

    _ensure_column(conn, "ollama_coach_prefs", "last_weekly_coach_at", "TEXT")
    _ensure_column(conn, "ollama_coach_prefs", "last_monthly_coach_at", "TEXT")


def get_schedule_prefs(user_id: str) -> Dict[str, Any]:
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema, _connect

    ensure_coach_schema()
    conn = _connect()
    try:
        _ensure_schedule_columns(conn)
        conn.commit()
        row = conn.execute(
            """SELECT enabled, auto_schedule_enabled, last_auto_coach_at, last_run_at,
                      feedback_count_at_last_coach, last_weekly_coach_at, last_monthly_coach_at
            FROM ollama_coach_prefs WHERE user_id=?""",
            (str(user_id),),
        ).fetchone()
        if not row:
            return {
                "auto_schedule_enabled": True,
                "daily": {"due": False, "interval_days": DAILY_INTERVAL_DAYS},
                "weekly": {"due": False, "interval_days": WEEKLY_INTERVAL_DAYS},
                "monthly": {"due": False, "interval_days": MONTHLY_INTERVAL_DAYS},
                "new_feedback_since_last": 0,
            }
        last_daily = row[2] or row[3]
        last_weekly = row[5] if len(row) > 5 else None
        last_monthly = row[6] if len(row) > 6 else None
        new_fb = count_feedback_since(str(user_id), last_daily or "")
        new_fb_weekly = count_feedback_since(str(user_id), last_weekly or "")
        new_fb_monthly = count_feedback_since(str(user_id), last_monthly or "")
        auto_on = bool(row[1] if len(row) > 1 else 1)

        daily_due = _tier_due("daily", last_daily, new_fb, auto_on)
        weekly_due = _tier_due("weekly", last_weekly, new_fb_weekly, auto_on)
        monthly_due = _tier_due("monthly", last_monthly, new_fb_monthly, auto_on)

        return {
            "auto_schedule_enabled": auto_on,
            "last_auto_coach_at": last_daily,
            "last_weekly_coach_at": last_weekly,
            "last_monthly_coach_at": last_monthly,
            "feedback_count_at_last_coach": int(row[4] if len(row) > 4 and row[4] else 0),
            "new_feedback_since_last": new_fb,
            "daily": {
                "due": daily_due,
                "interval_days": DAILY_INTERVAL_DAYS,
                "min_feedback": MIN_NEW_FEEDBACK,
                "elapsed_days": round(_elapsed_days(last_daily), 2),
            },
            "weekly": {
                "due": weekly_due,
                "interval_days": WEEKLY_INTERVAL_DAYS,
                "min_feedback": WEEKLY_MIN_FEEDBACK,
                "elapsed_days": round(_elapsed_days(last_weekly), 2),
            },
            "monthly": {
                "due": monthly_due,
                "interval_days": MONTHLY_INTERVAL_DAYS,
                "min_feedback": MONTHLY_MIN_FEEDBACK,
                "elapsed_days": round(_elapsed_days(last_monthly), 2),
            },
            "due": daily_due or weekly_due or monthly_due,
            "next_tier": (
                "monthly" if monthly_due else "weekly" if weekly_due else "daily" if daily_due else None
            ),
        }
    finally:
        conn.close()


def _is_due(last_iso: Optional[str], new_feedback: int, auto_enabled: bool) -> bool:
    """Backward-compatible helper for tests and legacy callers (daily tier)."""
    return _tier_due("daily", last_iso, new_feedback, auto_enabled)


def _tier_due(tier: str, last_iso: Optional[str], new_feedback: int, auto_enabled: bool) -> bool:
    if not auto_enabled or not AUTO_SCHEDULE:
        return False
    from backend.app.core.gemini_ollama_coach import coach_available

    if not coach_available():
        return False

    intervals = {
        "daily": (DAILY_INTERVAL_DAYS, MIN_NEW_FEEDBACK),
        "weekly": (WEEKLY_INTERVAL_DAYS, WEEKLY_MIN_FEEDBACK),
        "monthly": (MONTHLY_INTERVAL_DAYS, MONTHLY_MIN_FEEDBACK),
    }
    interval_days, min_fb = intervals.get(tier, (DAILY_INTERVAL_DAYS, MIN_NEW_FEEDBACK))
    if new_feedback < min_fb and last_iso:
        return False
    elapsed = _elapsed_days(last_iso)
    if not last_iso:
        return new_feedback >= min_fb
    return elapsed >= interval_days and new_feedback >= min_fb


def set_auto_schedule(user_id: str, enabled: bool) -> Dict[str, Any]:
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema, _connect, _utc

    ensure_coach_schema()
    uid = str(user_id)
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO ollama_coach_prefs (user_id, enabled, auto_schedule_enabled, updated_at)
            VALUES (?, 0, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET auto_schedule_enabled=excluded.auto_schedule_enabled, updated_at=excluded.updated_at""",
            (uid, 1 if enabled else 0, _utc()),
        )
        conn.commit()
    finally:
        conn.close()
    return get_schedule_prefs(uid)


def _mark_tier_done(user_id: str, tier: str, feedback_count: int) -> None:
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema, _connect, _utc

    ensure_coach_schema()
    conn = _connect()
    try:
        _ensure_schedule_columns(conn)
        now = _utc()
        if tier == "daily":
            conn.execute(
                """UPDATE ollama_coach_prefs SET
                    last_auto_coach_at=?, feedback_count_at_last_coach=?, updated_at=?
                WHERE user_id=?""",
                (now, feedback_count, now, str(user_id)),
            )
        elif tier == "weekly":
            conn.execute(
                "UPDATE ollama_coach_prefs SET last_weekly_coach_at=?, updated_at=? WHERE user_id=?",
                (now, now, str(user_id)),
            )
        elif tier == "monthly":
            conn.execute(
                "UPDATE ollama_coach_prefs SET last_monthly_coach_at=?, updated_at=? WHERE user_id=?",
                (now, now, str(user_id)),
            )
        conn.commit()
    finally:
        conn.close()


def _run_weekly_tier(user_id: str, membership: str) -> Dict[str, Any]:
    """Weekly: coach analyze + preference updates + SFT export."""
    from backend.app.core.improvement_automation import ensure_coach_auto_enabled

    ensure_coach_auto_enabled(str(user_id))
    result: Dict[str, Any] = {"tier": "weekly", "ok": True}
    try:
        from backend.app.core.gemini_ollama_coach import analyze_feedback

        analysis = analyze_feedback(str(user_id), membership=membership, apply=True)
        result["coach"] = analysis
    except Exception as exc:
        result["coach"] = {"ok": False, "error": str(exc)[:200]}

    try:
        from backend.app.core.human_training import export_sft_jsonl

        result["sft_export"] = export_sft_jsonl(str(user_id))
    except Exception as exc:
        result["sft_export"] = {"ok": False, "error": str(exc)[:120]}

    try:
        from backend.app.core.neural_finetuning import collect_pairs_from_feedback

        result["pairs_collected"] = collect_pairs_from_feedback(str(user_id), limit=200)
    except Exception as exc:
        result["pairs_collected"] = 0
        result["pairs_error"] = str(exc)[:80]

    return result


def _run_monthly_tier(user_id: str, membership: str) -> Dict[str, Any]:
    """Monthly: full improvement pipeline + DPO export + session hint reset."""
    from backend.app.core.improvement_automation import run_full_improvement_pipeline

    result = run_full_improvement_pipeline(
        str(user_id), trigger="scheduled_monthly", membership=membership, force_export=True
    )
    result["tier"] = "monthly"

    try:
        from backend.app.core.human_training import export_dpo_jsonl, export_sft_jsonl

        result["sft_export"] = export_sft_jsonl(str(user_id))
        result["dpo_export"] = export_dpo_jsonl(str(user_id))
    except Exception as exc:
        result["export_error"] = str(exc)[:120]

    try:
        from backend.app.core.user_preferences import save_preference_profile, get_preference_profile

        data = get_preference_profile(str(user_id))
        save_preference_profile(str(user_id), {**data["profile"], "session_hints": {}})
    except Exception:
        pass

    return result


def run_auto_coach_for_user(user_id: str, membership: str = "Free", *, tier: str = "") -> Dict[str, Any]:
    """Run scheduled improvement for the highest due tier (monthly > weekly > daily)."""
    from backend.app.core.improvement_automation import ensure_coach_auto_enabled, run_full_improvement_pipeline

    sched = get_schedule_prefs(user_id)
    chosen = tier or sched.get("next_tier")
    if not chosen:
        return {"ok": False, "skipped": True, "reason": "not_due", "schedule": sched}

    ensure_coach_auto_enabled(str(user_id))
    logger.info("[COACH AUTO] Running %s tier for user %s", chosen, str(user_id)[:8])

    try:
        if chosen == "monthly":
            result = _run_monthly_tier(str(user_id), membership)
        elif chosen == "weekly":
            result = _run_weekly_tier(str(user_id), membership)
        else:
            result = run_full_improvement_pipeline(
                str(user_id), trigger="scheduled_daily", membership=membership
            )
            result["tier"] = "daily"
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:200], "tier": chosen}

    total_fb = count_feedback_since(str(user_id))
    _mark_tier_done(str(user_id), chosen, total_fb)

    return {**result, "scheduled": True, "schedule": get_schedule_prefs(str(user_id))}


def run_scheduled_coaching_pass() -> List[Dict[str, Any]]:
    if not AUTO_SCHEDULE:
        return []
    results: List[Dict[str, Any]] = []
    for uid in list_coach_enabled_users():
        try:
            sched = get_schedule_prefs(uid)
            if not sched.get("due"):
                continue
            results.append(run_auto_coach_for_user(uid))
        except Exception as exc:
            logger.warning("[COACH AUTO] Failed for user %s: %s", uid[:8], exc)
            results.append({"ok": False, "user_id": uid, "error": str(exc)[:200]})
    if results:
        logger.info("[COACH AUTO] Completed pass: %s users coached", len(results))
    return results


def _scheduler_loop() -> None:
    while True:
        try:
            run_scheduled_coaching_pass()
        except Exception as exc:
            logger.warning("[COACH AUTO] Scheduler loop error: %s", exc)
        time.sleep(max(300, CHECK_INTERVAL_SEC))


def start_coach_scheduler() -> None:
    global _started
    if _started or not AUTO_SCHEDULE:
        return
    _started = True

    def _bootstrap():
        time.sleep(30)
        try:
            from backend.app.core.gemini_ollama_coach import ensure_coach_schema

            ensure_coach_schema()
            run_scheduled_coaching_pass()
        except Exception as exc:
            logger.warning("[COACH AUTO] Bootstrap pass failed: %s", exc)
        _scheduler_loop()

    threading.Thread(target=_bootstrap, daemon=True, name="coach-auto-scheduler").start()
    logger.info(
        "[COACH AUTO] Scheduler started (daily=%sd weekly=%sd monthly=%sd check=%ss)",
        DAILY_INTERVAL_DAYS,
        WEEKLY_INTERVAL_DAYS,
        MONTHLY_INTERVAL_DAYS,
        CHECK_INTERVAL_SEC,
    )
