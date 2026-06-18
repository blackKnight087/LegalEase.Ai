"""
Runtime coach — Gemini feedback analysis for Settings/tuning ONLY.

Does NOT inject into Knowledge Base answers (KB_BLOCK_RUNTIME_COACH=1 default).

Triggers lightweight analyze→apply cycles on feedback and periodically
during chat so persona, preferences, and query healings update immediately.
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ENABLED = os.getenv("CHAT_COACH_RUNTIME", "1").lower() in {"1", "true", "yes"}
POSITIVE_COACH_EVERY = int(os.getenv("CHAT_COACH_POSITIVE_EVERY", "3"))
MIN_FEEDBACK_FOR_ANALYZE = int(os.getenv("CHAT_COACH_MIN_FEEDBACK", "2"))

_running: set[str] = set()
_lock = threading.Lock()


def _count_recent_feedback(user_id: str) -> int:
    try:
        from backend.app.core.database import connect_data_db
        from backend.app.core.human_training import ensure_human_training_schema

        ensure_human_training_schema()
        conn = connect_data_db()
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM human_labels WHERE user_id=?",
                (str(user_id),),
            ).fetchone()
            return int(row[0] if row else 0)
        finally:
            conn.close()
    except Exception:
        return 0


def _count_positive_since_coach(user_id: str) -> int:
    try:
        from backend.app.core.gemini_ollama_coach import ensure_coach_schema, get_coach_prefs
        from backend.app.core.database import connect_data_db
        from backend.app.core.human_training import ensure_human_training_schema

        ensure_coach_schema()
        ensure_human_training_schema()
        prefs = get_coach_prefs(user_id)
        since = prefs.get("last_run_at") or ""
        conn = connect_data_db()
        try:
            if since:
                row = conn.execute(
                    """SELECT COUNT(*) FROM human_labels
                    WHERE user_id=? AND reward > 0 AND created_at > ?""",
                    (str(user_id), since),
                ).fetchone()
            else:
                row = conn.execute(
                    """SELECT COUNT(*) FROM human_labels
                    WHERE user_id=? AND reward > 0""",
                    (str(user_id),),
                ).fetchone()
            return int(row[0] if row else 0)
        finally:
            conn.close()
    except Exception:
        return 0


def _mark_runtime_coach(user_id: str) -> None:
    try:
        from backend.app.core.gemini_ollama_coach import ensure_coach_schema, _utc
        from backend.app.core.database import connect_data_db

        ensure_coach_schema()
        conn = connect_data_db()
        try:
            conn.execute(
                """UPDATE ollama_coach_prefs SET last_run_at=?, updated_at=? WHERE user_id=?""",
                (_utc(), _utc(), str(user_id)),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _run_coach_analyze_apply(user_id: str, membership: str, *, trigger: str) -> Dict[str, Any]:
    from backend.app.core.gemini_ollama_coach import (
        _build_coach_prompt,
        _call_gemini_coach,
        _fetch_correction_rows,
        _fetch_feedback_rows,
        _sanitize_insights,
        apply_coaching_insights,
        coach_available,
        get_coach_prefs,
        get_directives,
        store_coach_memory,
    )

    if not coach_available():
        return {"ok": False, "skipped": True, "reason": "coach_unavailable"}

    prefs = get_coach_prefs(user_id)
    if not prefs.get("enabled"):
        return {"ok": False, "skipped": True, "reason": "coach_disabled"}

    feedback = _fetch_feedback_rows(user_id, limit=12)
    if len(feedback) < MIN_FEEDBACK_FOR_ANALYZE:
        return {"ok": False, "skipped": True, "reason": "insufficient_feedback"}

    prompt = _build_coach_prompt(
        user_id,
        feedback,
        _fetch_correction_rows(user_id, limit=5),
        user_directives=get_directives(user_id),
    )
    insights = _sanitize_insights(_call_gemini_coach(prompt, user_id, membership))
    store_coach_memory(user_id, f"runtime_{trigger}", insights.get("summary", "")[:400], insights=insights)
    applied = apply_coaching_insights(user_id, insights)
    _mark_runtime_coach(user_id)
    return {"ok": True, "trigger": trigger, "applied": applied, "insights_summary": insights.get("summary", "")[:200]}


def schedule_runtime_coach(
    user_id: str,
    *,
    trigger: str = "feedback",
    membership: str = "Free",
    force: bool = False,
) -> Dict[str, Any]:
    """Background coach analyze→apply during chat."""
    if not ENABLED:
        return {"ok": False, "skipped": True, "reason": "chat_coach_runtime_disabled"}

    uid = str(user_id)
    if not force and trigger in ("thumbs_up", "helpful", "verbal_positive"):
        if _count_positive_since_coach(uid) < POSITIVE_COACH_EVERY:
            return {"ok": False, "skipped": True, "reason": "positive_threshold_not_met"}

    with _lock:
        if uid in _running:
            return {"ok": False, "skipped": True, "reason": "already_running"}
        _running.add(uid)

    def _job() -> None:
        try:
            result = _run_coach_analyze_apply(uid, membership, trigger=trigger)
            logger.info("[CHAT COACH] user=%s trigger=%s result=%s", uid[:8], trigger, result.get("ok"))
            if result.get("ok"):
                try:
                    from backend.app.core.llm_finetuning import maybe_auto_train_llm

                    maybe_auto_train_llm(uid)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("[CHAT COACH] failed user=%s: %s", uid[:8], exc)
        finally:
            with _lock:
                _running.discard(uid)

    threading.Thread(target=_job, daemon=True, name=f"chat-coach-{uid[:8]}").start()
    return {"ok": True, "scheduled": True, "trigger": trigger}


def apply_rlaif_to_preferences(
    user_id: str,
    rlaif: Optional[Dict[str, Any]],
) -> bool:
    """Immediately apply RLAIF style scores to user preferences."""
    if not rlaif or not user_id:
        return False
    try:
        from backend.app.core.user_preferences import get_preference_profile, save_preference_profile

        current = get_preference_profile(str(user_id))["profile"]
        updated = False
        patch: Dict[str, Any] = {}

        clarity = float(rlaif.get("clarity") or 0)
        structure = float(rlaif.get("structure") or 0)
        tone = float(rlaif.get("tone") or 0)
        conciseness = float(rlaif.get("conciseness") or 0)

        detail = float(current.get("detail_level", 0.5))
        if clarity >= 0.75 and detail < 0.85:
            patch["detail_level"] = min(1.0, detail + 0.1)
            updated = True
        if conciseness >= 0.75 and detail > 0.25:
            patch["detail_level"] = max(0.2, detail - 0.1)
            updated = True
        if structure >= 0.75:
            patch["prefer_bullets"] = min(1.0, float(current.get("prefer_bullets", 0.5)) + 0.15)
            patch["prefer_headings"] = min(1.0, float(current.get("prefer_headings", 0.7)) + 0.1)
            updated = True
        if tone >= 0.8:
            patch["tone"] = "warm" if current.get("tone") == "professional" else current.get("tone", "professional")
            updated = True
        if patch:
            merged = {**current, **patch}
            save_preference_profile(str(user_id), merged)
        return updated
    except Exception as exc:
        logger.debug("RLAIF preference apply skipped: %s", exc)
        return False


def on_feedback_coach_hook(
    user_id: str,
    signal: str,
    *,
    rlaif: Optional[Dict[str, Any]] = None,
    membership: str = "Free",
    comment: str = "",
) -> Dict[str, Any]:
    """Called from learning_signals after feedback — runtime coach + RLAIF apply."""
    out: Dict[str, Any] = {}

    if rlaif:
        out["rlaif_applied"] = apply_rlaif_to_preferences(user_id, rlaif)

    if signal in ("thumbs_up", "helpful", "verbal_positive", "copy"):
        out["coach"] = schedule_runtime_coach(user_id, trigger=signal, membership=membership)
    elif signal in ("thumbs_down", "verbal_negative") and comment:
        out["coach"] = schedule_runtime_coach(user_id, trigger=signal, membership=membership, force=True)

    return out


def get_runtime_coach_block(user_id: str) -> str:
    """Recent runtime coach insights — Settings tuning only, not KB chat answers."""
    if not user_id:
        return ""
    import os

    if os.getenv("KB_BLOCK_RUNTIME_COACH", "1").lower() in {"1", "true", "yes"}:
        return ""
    try:
        from backend.app.core.gemini_ollama_coach import get_coach_memory_block

        return get_coach_memory_block(str(user_id))
    except Exception:
        return ""
