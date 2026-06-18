"""
Non-blocking feedback enrichment — keeps /learning/feedback under ~200ms.

Heavy work (Gemini RLAIF, neural pairs, coach, negative feedback analysis) runs in
daemon threads so KB chat and the next question are never blocked.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FEEDBACK_FAST = os.getenv("FEEDBACK_FAST", "1").lower() in {"1", "true", "yes"}
FEEDBACK_SKIP_RLAIF = os.getenv("FEEDBACK_SKIP_RLAIF", "1").lower() in {"1", "true", "yes"}

_schema_ready = False
_schema_lock = threading.Lock()


def json_safe(value: Any) -> Any:
    """Ensure API responses never break FastAPI JSON encoding."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)[:500]


def ensure_schema_once() -> None:
    global _schema_ready
    if _schema_ready:
        return
    with _schema_lock:
        if _schema_ready:
            return
        from backend.app.core.learning_signals import ensure_signal_schema

        ensure_signal_schema()
        _schema_ready = True


def record_feedback_instant(
    user_id: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
    thread_id: str = "",
    signal: str = "thumbs_up",
    comment: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Minimal SQLite write (<100ms target). All learning side-effects run in background.
    """
    import uuid

    ensure_schema_once()
    from backend.app.core.adaptive_learning import normalize_query, _utc
    from backend.app.core.database import connect_data_db

    meta = metadata or {}
    tag_list = list(tags or [])[:8]
    uid = str(user_id)
    conn = connect_data_db(timeout=5.0)
    try:
        row = None
        if interaction_id:
            row = conn.execute(
                "SELECT id, mode, query, query_norm, chunk_keys FROM adaptive_interactions WHERE id=? AND user_id=?",
                (interaction_id, uid),
            ).fetchone()
        elif chat_id:
            row = conn.execute(
                """SELECT id, mode, query, query_norm, chunk_keys
                FROM adaptive_interactions WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1""",
                (chat_id, uid),
            ).fetchone()
        elif thread_id:
            row = conn.execute(
                """SELECT id, mode, query, query_norm, chunk_keys
                FROM adaptive_interactions WHERE thread_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1""",
                (thread_id, uid),
            ).fetchone()
        if not row:
            row = conn.execute(
                """SELECT id, mode, query, query_norm, chunk_keys
                FROM adaptive_interactions WHERE user_id=? ORDER BY created_at DESC LIMIT 1""",
                (uid,),
            ).fetchone()

        if not row:
            return {"ok": False, "error": "interaction not found — send a message first, then retry feedback"}

        iid, mode, query, qn, chunk_json = row[0], row[1], row[2], row[3], row[4]
        fid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO adaptive_feedback (id, interaction_id, user_id, signal, value, comment, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (fid, iid, uid, signal, 1.0 if signal in ("thumbs_up", "helpful", "copy") else -1.0, comment[:500], _utc()),
        )
        try:
            conn.execute(
                "UPDATE adaptive_feedback SET tags_json=?, metadata_json=? WHERE id=?",
                (
                    json.dumps(tag_list, ensure_ascii=False),
                    json.dumps(meta, ensure_ascii=False),
                    fid,
                ),
            )
        except Exception:
            pass
        preview_row = conn.execute(
            "SELECT answer_preview FROM adaptive_interactions WHERE id=?",
            (iid,),
        ).fetchone()
        answer_text = (preview_row[0] if preview_row else "") or ""
        conn.commit()

        keys = []
        try:
            keys = json.loads(chunk_json or "[]")
        except Exception:
            keys = []

        positive = signal in (
            "thumbs_up", "helpful", "verbal_positive", "copy",
            "export_docx", "export_pdf", "save_to_matter",
        )
        if positive:

            def _bg_positive() -> None:
                try:
                    from backend.app.core.adaptive_learning import _apply_positive_learning, _connect

                    c2 = _connect()
                    try:
                        _apply_positive_learning(c2, uid, mode, qn, query, keys)
                        c2.commit()
                    finally:
                        c2.close()
                except Exception as exc:
                    logger.debug("feedback positive learning bg: %s", exc)
                defer_positive_feedback_side_effects(
                    uid, mode=mode, query=query, answer_text=answer_text, signal=signal,
                )

            defer_feedback_job(f"fb-pos-lite-{uid[:8]}", _bg_positive)
        elif signal in ("thumbs_down", "verbal_negative", "regenerate"):
            def _bg_negative() -> None:
                try:
                    from backend.app.core.adaptive_learning import _apply_negative_learning, _connect

                    c2 = _connect()
                    try:
                        _apply_negative_learning(c2, uid, mode, qn, keys)
                        c2.commit()
                    finally:
                        c2.close()
                except Exception as exc:
                    logger.debug("feedback negative learning bg: %s", exc)

            defer_feedback_job(f"fb-neg-lite-{uid[:8]}", _bg_negative)

        return {"ok": True, "interaction_id": iid, "feedback_id": fid, "queued": True}
    finally:
        conn.close()


def defer_feedback_job(name: str, fn, *args, **kwargs) -> None:
    def _run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception as exc:
            logger.warning("[FEEDBACK BG] %s failed: %s", name, exc)

    threading.Thread(target=_run, daemon=True, name=name[:24]).start()


def run_feedback_enrichment(
    user_id: str,
    signal: str,
    *,
    interaction_id: str,
    chat_id: str,
    comment: str,
    tag_list: List[str],
    meta: Dict[str, Any],
    membership: str,
) -> None:
    """Background: RLAIF, human training, coach hooks, negative Gemini coach."""
    iid = interaction_id or ""
    composed = comment
    if tag_list:
        from backend.app.core.learning_signals import _compose_comment

        composed = _compose_comment(comment, tag_list)

    try:
        from backend.app.core.human_training import process_feedback_for_training

        process_feedback_for_training(
            str(user_id),
            interaction_id=iid,
            signal=signal,
            comment=composed,
            membership=membership,
            tags=tag_list,
            skip_rlaif=FEEDBACK_SKIP_RLAIF,
        )
    except Exception as exc:
        logger.debug("feedback training_pipeline bg: %s", exc)

    try:
        from backend.app.core.chat_coach_runtime import on_feedback_coach_hook

        on_feedback_coach_hook(
            str(user_id),
            signal,
            rlaif=None,
            membership=membership,
            comment=composed,
        )
    except Exception as exc:
        logger.debug("feedback coach bg: %s", exc)

    if signal in ("thumbs_down", "verbal_negative") and (composed or tag_list):
        try:
            from backend.app.core.gemini_ollama_coach import process_negative_feedback

            process_negative_feedback(
                str(user_id),
                interaction_id=iid,
                chat_id=chat_id,
                user_comment=composed,
                membership=membership,
            )
        except Exception as exc:
            logger.debug("feedback negative coach bg: %s", exc)

    if signal in ("verbal_positive", "helpful", "thumbs_up", "copy"):
        try:
            from backend.app.core.improvement_automation import schedule_improvement_pipeline

            schedule_improvement_pipeline(str(user_id), trigger=signal, membership=membership)
        except Exception:
            pass


def defer_positive_feedback_side_effects(
    user_id: str,
    *,
    mode: str,
    query: str,
    answer_text: str,
    signal: str,
) -> None:
    """Defer neural pairs + learn_from_kb_success triggered by thumbs-up in record_feedback."""
    if len((answer_text or "").strip()) < 40:
        return

    def _job() -> None:
        try:
            from backend.app.core.neural_finetuning import add_training_pair, collect_pairs_from_feedback

            if signal in (
                "thumbs_up", "helpful", "verbal_positive", "copy",
                "export_docx", "export_pdf", "save_to_matter",
            ):
                add_training_pair(query, answer_text, user_id=str(user_id), source=signal)
            collect_pairs_from_feedback(str(user_id), limit=50)
        except Exception as exc:
            logger.debug("feedback neural pairs bg: %s", exc)
        try:
            from backend.app.core.learning_engine import learn_from_kb_success, learn_from_web_success

            if mode in ("web_search", "open_law", "deep_case", "hybrid"):
                learn_from_web_success(
                    str(user_id), query, answer_text, source=signal, confidence=0.92,
                )
            else:
                learn_from_kb_success(
                    str(user_id), query, answer_text, source=signal, confidence=0.92,
                )
        except Exception as exc:
            logger.debug("feedback learn_success bg: %s", exc)
        try:
            from backend.app.core.improvement_automation import schedule_improvement_pipeline

            schedule_improvement_pipeline(str(user_id), trigger=signal)
        except Exception:
            pass

    defer_feedback_job(f"fb-pos-{str(user_id)[:8]}", _job)
