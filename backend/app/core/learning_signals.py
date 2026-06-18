"""
Unified learning signal registry and processors.

Explicit: thumbs_up, thumbs_down, copy, regenerate, helpful, follow_up_click, export_*
Implicit: dwell_time, mode_switch, edit_diff, save_to_matter
Structured tags on negative feedback map to preference dimensions.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Signal taxonomy ---------------------------------------------------------

POSITIVE_SIGNALS = frozenset({
    "thumbs_up",
    "helpful",
    "verbal_positive",
    "copy",
    "follow_up_click",
    "export_docx",
    "export_pdf",
    "export_client_safe",
    "save_to_matter",
    "edit_diff_accept",
})

NEGATIVE_SIGNALS = frozenset({
    "thumbs_down",
    "verbal_negative",
    "regenerate",
    "wrong",
    "not_helpful",
    "mode_switch",
})

SFT_ELIGIBLE = frozenset({
    "thumbs_up",
    "helpful",
    "verbal_positive",
    "copy",
    "export_docx",
    "export_pdf",
    "save_to_matter",
})

IMPLICIT_SIGNALS = frozenset({
    "dwell_time",
    "mode_switch",
    "follow_up_click",
    "edit_diff",
    "regenerate_pending",
})

SIGNAL_REWARDS: Dict[str, float] = {
    "thumbs_up": 1.0,
    "helpful": 0.9,
    "verbal_positive": 0.88,
    "copy": 0.85,
    "follow_up_click": 0.35,
    "export_docx": 0.95,
    "export_pdf": 0.95,
    "export_client_safe": 0.92,
    "save_to_matter": 0.9,
    "edit_diff_accept": 0.75,
    "thumbs_down": -1.0,
    "verbal_negative": -0.95,
    "regenerate": -0.55,
    "wrong": -0.8,
    "not_helpful": -0.7,
    "mode_switch": -0.45,
    "dwell_time": 0.15,
}

FEEDBACK_TAGS: Dict[str, Dict[str, Any]] = {
    "too_long": {"prefer_concise": 0.15, "depth": "quick"},
    "too_short": {"prefer_concise": -0.1, "detail_level": 0.12, "depth": "detailed"},
    "wrong_section": {"citation_style": "inline"},
    "not_in_documents": {},
    "good_structure": {"prefer_headings": 0.1, "structure": "sections"},
    "good_citations": {"citation_style": "inline"},
    "wrong_tone": {"tone": "professional"},
    "missed_follow_up": {"follow_up_style": "specific"},
}

TAG_LABELS: List[Dict[str, str]] = [
    {"id": "too_long", "label": "Too long"},
    {"id": "too_short", "label": "Too short"},
    {"id": "wrong_section", "label": "Wrong section"},
    {"id": "not_in_documents", "label": "Not in my documents"},
    {"id": "good_structure", "label": "Good structure"},
    {"id": "good_citations", "label": "Good citations"},
    {"id": "wrong_tone", "label": "Wrong tone"},
    {"id": "missed_follow_up", "label": "Missed follow-up context"},
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def _ensure_column(conn, table: str, column: str, col_def: str) -> None:
    from backend.app.core.sql_compat import ensure_columns

    ensure_columns(conn, table, ((column, col_def, f"ALTER TABLE {table} ADD COLUMN {column} {col_def}"),))


def ensure_signal_schema() -> None:
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.human_training import ensure_human_training_schema
    from backend.app.core.legacy_db import use_postgres_legacy

    ensure_learning_schema()
    ensure_human_training_schema()
    if use_postgres_legacy():
        return
    conn = _connect()
    try:
        _ensure_column(conn, "adaptive_feedback", "tags_json", "TEXT DEFAULT '[]'")
        _ensure_column(conn, "adaptive_feedback", "metadata_json", "TEXT DEFAULT '{}'")
        _ensure_column(conn, "human_labels", "tags_json", "TEXT DEFAULT '[]'")
        _ensure_column(conn, "human_labels", "metadata_json", "TEXT DEFAULT '{}'")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS learning_signal_events (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            signal TEXT NOT NULL,
            interaction_id TEXT,
            chat_id TEXT,
            mode TEXT DEFAULT 'knowledge_base',
            query TEXT,
            answer_preview TEXT,
            metadata_json TEXT DEFAULT '{}',
            reward REAL DEFAULT 0,
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS regenerate_chains (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            original_interaction_id TEXT NOT NULL,
            replacement_interaction_id TEXT,
            query TEXT,
            original_answer TEXT,
            replacement_answer TEXT,
            outcome TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            resolved_at TEXT
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS edit_preference_pairs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            interaction_id TEXT,
            query TEXT,
            original_answer TEXT NOT NULL,
            edited_answer TEXT NOT NULL,
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_signal_events_uid
            ON learning_signal_events(user_id, created_at DESC)"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_regen_chains_uid
            ON regenerate_chains(user_id, created_at DESC)"""
        )
        conn.commit()
    finally:
        conn.close()


def signal_reward(signal: str, *, metadata: Optional[Dict[str, Any]] = None) -> float:
    base = SIGNAL_REWARDS.get(signal, 0.0)
    meta = metadata or {}
    if signal == "dwell_time":
        ms = int(meta.get("dwell_ms") or 0)
        if ms >= 45000:
            return 0.35
        if ms >= 15000:
            return 0.2
        if ms < 3000:
            return -0.1
        return 0.1
    return base


def is_positive(signal: str) -> bool:
    return signal in POSITIVE_SIGNALS


def is_negative(signal: str) -> bool:
    return signal in NEGATIVE_SIGNALS


def is_sft_eligible(signal: str) -> bool:
    return signal in SFT_ELIGIBLE


def apply_tags_to_preferences(user_id: str, tags: List[str]) -> int:
    if not tags:
        return 0
    from backend.app.core.user_preferences import get_preference_profile, save_preference_profile

    profile = dict(get_preference_profile(str(user_id))["profile"])
    applied = 0
    for tag in tags:
        spec = FEEDBACK_TAGS.get(tag)
        if not spec:
            continue
        for k, v in spec.items():
            if k in profile and isinstance(v, float) and isinstance(profile.get(k), (int, float)):
                profile[k] = max(0.0, min(1.0, float(profile[k]) + v))
            else:
                profile[k] = v
            applied += 1
    if applied:
        try:
            save_preference_profile(str(user_id), profile)
        except Exception as exc:
            logger.warning("apply_tags_to_preferences save failed user=%s: %s", user_id, exc)
            return 0
    return applied


def record_signal_event(
    user_id: str,
    signal: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
    mode: str = "knowledge_base",
    query: str = "",
    answer_preview: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ensure_signal_schema()
    meta = metadata or {}
    reward = signal_reward(signal, metadata=meta)
    eid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO learning_signal_events
            (id, user_id, signal, interaction_id, chat_id, mode, query, answer_preview,
             metadata_json, reward, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                eid,
                str(user_id),
                signal[:40],
                interaction_id or "",
                chat_id or "",
                mode[:40],
                (query or "")[:500],
                (answer_preview or "")[:800],
                json.dumps(meta, ensure_ascii=False),
                reward,
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "event_id": eid, "signal": signal, "reward": reward}


def register_regenerate(
    user_id: str,
    *,
    interaction_id: str,
    query: str = "",
    answer_preview: str = "",
) -> str:
    ensure_signal_schema()
    rid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO regenerate_chains
            (id, user_id, original_interaction_id, query, original_answer, outcome, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (
                rid,
                str(user_id),
                interaction_id,
                (query or "")[:500],
                (answer_preview or "")[:2000],
                "pending",
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return rid


def resolve_regenerate_chain(
    user_id: str,
    *,
    replacement_interaction_id: str,
    replacement_answer: str,
    outcome: str = "accepted",
) -> Optional[str]:
    """Link regenerate → new answer; build preference pair if original was rejected."""
    ensure_signal_schema()
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT id, original_interaction_id, query, original_answer
            FROM regenerate_chains
            WHERE user_id=? AND outcome='pending'
            ORDER BY created_at DESC LIMIT 1""",
            (str(user_id),),
        ).fetchone()
        if not row:
            return None
        chain_id, orig_iid, query, orig_ans = row[0], row[1], row[2], row[3]
        conn.execute(
            """UPDATE regenerate_chains SET
                replacement_interaction_id=?, replacement_answer=?, outcome=?, resolved_at=?
            WHERE id=?""",
            (
                replacement_interaction_id,
                (replacement_answer or "")[:2000],
                outcome[:20],
                _utc(),
                chain_id,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    if orig_ans and replacement_answer and orig_ans != replacement_answer:
        try:
            from backend.app.core.human_training import record_preference_pair

            record_preference_pair(
                str(user_id),
                query=query or "",
                chosen=replacement_answer,
                rejected=orig_ans,
                chosen_interaction_id=replacement_interaction_id,
                rejected_interaction_id=orig_iid,
                source="regenerate_chain",
            )
        except Exception as exc:
            logger.debug("regenerate pair skipped: %s", exc)
    return chain_id


def record_edit_diff_pair(
    user_id: str,
    *,
    interaction_id: str,
    query: str,
    original_answer: str,
    edited_answer: str,
) -> Dict[str, Any]:
    ensure_signal_schema()
    orig = (original_answer or "").strip()
    edited = (edited_answer or "").strip()
    if not orig or not edited or orig == edited:
        return {"ok": False, "error": "edited text must differ from original"}
    if len(edited) < 20:
        return {"ok": False, "error": "edited text too short"}

    pid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO edit_preference_pairs
            (id, user_id, interaction_id, query, original_answer, edited_answer, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (pid, str(user_id), interaction_id or "", query[:500], orig[:2000], edited[:2000], _utc()),
        )
        conn.commit()
    finally:
        conn.close()

    record_signal_event(
        str(user_id),
        "edit_diff_accept",
        interaction_id=interaction_id,
        query=query,
        answer_preview=edited[:800],
        metadata={"pair_id": pid},
    )
    return {"ok": True, "pair_id": pid}


def process_dwell_time(
    user_id: str,
    *,
    interaction_id: str,
    dwell_ms: int,
    mode: str = "knowledge_base",
    answer_length: int = 0,
) -> Dict[str, Any]:
    from backend.app.core.user_preferences import get_preference_profile, save_preference_profile

    event = record_signal_event(
        str(user_id),
        "dwell_time",
        interaction_id=interaction_id,
        mode=mode,
        metadata={"dwell_ms": dwell_ms, "answer_length": answer_length},
    )
    profile = dict(get_preference_profile(str(user_id))["profile"])
    if dwell_ms >= 20000 and answer_length > 800:
        profile["detail_level"] = min(1.0, float(profile.get("detail_level", 0.5)) + 0.04)
    elif dwell_ms < 2500 and answer_length > 400:
        profile["prefer_concise"] = min(1.0, float(profile.get("prefer_concise", 0.5)) + 0.06)
    save_preference_profile(str(user_id), profile)
    return event


def process_mode_switch(
    user_id: str,
    *,
    from_mode: str,
    to_mode: str,
    interaction_id: str = "",
    query: str = "",
) -> Dict[str, Any]:
    """KB/Open Law switch after weak answer → implicit retrieval failure."""
    kb_modes = {"knowledge_base", "kb"}
    web_modes = {"open_law", "web_search", "deep_case", "hybrid"}
    if from_mode not in kb_modes or to_mode not in web_modes:
        return {"ok": True, "skipped": True}

    event = record_signal_event(
        str(user_id),
        "mode_switch",
        interaction_id=interaction_id,
        mode=from_mode,
        query=query,
        metadata={"from_mode": from_mode, "to_mode": to_mode},
    )
    if query:
        try:
            from backend.app.core.retrieval_learning import learn_from_feedback

            learn_from_feedback(str(user_id), "thumbs_down", query=query, mode=from_mode)
        except Exception:
            pass
    return event


def process_follow_up_click(
    user_id: str,
    *,
    interaction_id: str,
    follow_up_text: str,
    mode: str = "knowledge_base",
) -> Dict[str, Any]:
    from backend.app.core.user_preferences import record_session_hint

    record_session_hint(str(user_id), "last_follow_up_clicked", follow_up_text[:120])
    return record_signal_event(
        str(user_id),
        "follow_up_click",
        interaction_id=interaction_id,
        mode=mode,
        query=follow_up_text,
        metadata={"follow_up": follow_up_text[:200]},
    )


def process_export_signal(
    user_id: str,
    *,
    export_type: str,
    interaction_id: str = "",
    query: str = "",
    answer_preview: str = "",
    mode: str = "deep_case",
) -> Dict[str, Any]:
    signal = {
        "docx": "export_docx",
        "pdf": "export_pdf",
        "client_safe": "export_client_safe",
    }.get(export_type, f"export_{export_type}")
    event = record_signal_event(
        str(user_id),
        signal,
        interaction_id=interaction_id,
        mode=mode,
        query=query,
        answer_preview=answer_preview,
    )
    if is_sft_eligible(signal) and answer_preview and len(answer_preview) >= 40:
        try:
            from backend.app.core.neural_finetuning import add_training_pair

            add_training_pair(
                query or "legal export",
                answer_preview[:1200],
                user_id=str(user_id),
                source=signal,
            )
        except Exception:
            pass
    return event


def process_learning_signal(
    user_id: str,
    signal: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
    comment: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    membership: str = "Free",
) -> Dict[str, Any]:
    """
    Unified entry for explicit feedback + implicit signals.
    Delegates to adaptive_learning / human_training where appropriate.
    """
    import sqlite3

    try:
        ensure_signal_schema()
    except sqlite3.Error:
        logger.exception("ensure_signal_schema failed — feedback skipped, KB unaffected")
        return {"ok": False, "error": "schema"}
    sig = (signal or "").strip().lower()
    meta = dict(metadata or {})
    tag_list = [t for t in (tags or []) if t][:8]

    if sig in ("dwell_time",):
        return process_dwell_time(
            str(user_id),
            interaction_id=interaction_id,
            dwell_ms=int(meta.get("dwell_ms") or 0),
            mode=str(meta.get("mode") or "knowledge_base"),
            answer_length=int(meta.get("answer_length") or 0),
        )

    if sig == "mode_switch":
        return process_mode_switch(
            str(user_id),
            from_mode=str(meta.get("from_mode") or ""),
            to_mode=str(meta.get("to_mode") or ""),
            interaction_id=interaction_id,
            query=str(meta.get("query") or ""),
        )

    if sig == "follow_up_click":
        return process_follow_up_click(
            str(user_id),
            interaction_id=interaction_id,
            follow_up_text=str(meta.get("follow_up") or comment or ""),
            mode=str(meta.get("mode") or "knowledge_base"),
        )

    if sig == "edit_diff":
        return record_edit_diff_pair(
            str(user_id),
            interaction_id=interaction_id,
            query=str(meta.get("query") or ""),
            original_answer=str(meta.get("original") or ""),
            edited_answer=str(meta.get("edited") or comment or ""),
        )

    if sig.startswith("export_") or sig in ("export_docx", "export_pdf", "export_client_safe"):
        export_type = sig.replace("export_", "")
        return process_export_signal(
            str(user_id),
            export_type=export_type,
            interaction_id=interaction_id,
            query=str(meta.get("query") or ""),
            answer_preview=str(meta.get("answer_preview") or ""),
            mode=str(meta.get("mode") or "deep_case"),
        )

    if sig == "save_to_matter":
        if not interaction_id and not chat_id:
            return record_signal_event(
                str(user_id),
                "save_to_matter",
                query=str(meta.get("query") or ""),
                answer_preview=str(meta.get("answer_preview") or comment or "")[:800],
                mode=str(meta.get("mode") or "knowledge_base"),
                metadata=meta,
            )
        return record_signal_event(
            str(user_id),
            "save_to_matter",
            interaction_id=interaction_id,
            query=str(meta.get("query") or ""),
            answer_preview=str(meta.get("answer_preview") or comment or "")[:800],
            mode=str(meta.get("mode") or "knowledge_base"),
            metadata=meta,
        )

    if sig == "regenerate":
        detail = _interaction_detail(str(user_id), interaction_id, chat_id, meta)
        chain_id = ""
        if detail.get("interaction_id"):
            chain_id = register_regenerate(
                str(user_id),
                interaction_id=detail["interaction_id"],
                query=detail.get("query", ""),
                answer_preview=detail.get("answer_preview", ""),
            )
        result = _record_feedback_with_tags(
            str(user_id),
            signal=sig,
            interaction_id=interaction_id,
            chat_id=chat_id,
            comment=comment,
            tags=tag_list,
            metadata={**meta, "thread_id": meta.get("thread_id") or ""},
        )
        result["regenerate_chain_id"] = chain_id
        return result

    if sig in POSITIVE_SIGNALS or sig in NEGATIVE_SIGNALS or sig in ("helpful", "wrong", "not_helpful"):
        if not interaction_id and not chat_id and sig not in ("save_to_matter",):
            return record_signal_event(
                str(user_id),
                sig,
                metadata={**(meta or {}), "comment": comment, "tags": tag_list},
            )
        try:
            from backend.app.core.feedback_async import FEEDBACK_FAST, record_feedback_instant

            if FEEDBACK_FAST and sig in (
                "thumbs_up", "thumbs_down", "helpful", "verbal_positive", "verbal_negative", "copy",
            ):
                result = record_feedback_instant(
                    str(user_id),
                    interaction_id=interaction_id,
                    chat_id=chat_id,
                    thread_id=str(meta.get("thread_id") or ""),
                    signal=sig,
                    comment=_compose_comment(comment, tag_list),
                    tags=tag_list,
                    metadata={**meta, "thread_id": meta.get("thread_id") or ""},
                )
            else:
                result = _record_feedback_with_tags(
                    str(user_id),
                    signal=sig,
                    interaction_id=interaction_id,
                    chat_id=chat_id,
                    comment=comment,
                    tags=tag_list,
                    metadata={**meta, "thread_id": meta.get("thread_id") or ""},
                )
        except Exception as exc:
            result = {"ok": False, "error": str(exc)[:120]}
        if tag_list and result.get("ok"):
            try:
                result["tags_applied"] = apply_tags_to_preferences(str(user_id), tag_list)
            except Exception as exc:
                result["tags_applied"] = 0
                result["tags_error"] = str(exc)[:120]

        if result.get("ok") and sig in (
            "thumbs_up", "thumbs_down", "helpful", "verbal_positive", "verbal_negative",
            "copy", "regenerate",
            "follow_up_click", "export_docx", "export_pdf", "save_to_matter",
        ):
            try:
                from backend.app.core.feedback_async import (
                    FEEDBACK_FAST,
                    defer_feedback_job,
                    json_safe,
                    run_feedback_enrichment,
                )

                if FEEDBACK_FAST:
                    iid = str(result.get("interaction_id") or interaction_id or "")
                    defer_feedback_job(
                        f"fb-enrich-{str(user_id)[:8]}",
                        run_feedback_enrichment,
                        str(user_id),
                        sig,
                        interaction_id=iid,
                        chat_id=chat_id,
                        comment=comment,
                        tag_list=tag_list,
                        meta=meta,
                        membership=membership,
                    )
                    result["queued"] = True
                    result["training_pipeline"] = {"ok": True, "queued": True}
                    result["chat_coach"] = {"ok": True, "queued": True}
                    return json_safe(result)

                from backend.app.core.human_training import process_feedback_for_training

                result["training_pipeline"] = process_feedback_for_training(
                    str(user_id),
                    interaction_id=result.get("interaction_id") or interaction_id,
                    signal=sig,
                    comment=_compose_comment(comment, tag_list),
                    membership=membership,
                    tags=tag_list,
                )
            except Exception as exc:
                result["training_pipeline"] = {"ok": False, "error": str(exc)[:120]}
            try:
                from backend.app.core.chat_coach_runtime import on_feedback_coach_hook

                tp = result.get("training_pipeline") or {}
                result["chat_coach"] = on_feedback_coach_hook(
                    str(user_id),
                    sig,
                    rlaif=tp.get("rlaif") if isinstance(tp, dict) else None,
                    membership=membership,
                    comment=_compose_comment(comment, tag_list),
                )
            except Exception as exc:
                result["chat_coach"] = {"ok": False, "error": str(exc)[:120]}

            if sig in ("thumbs_down", "verbal_negative") and result.get("ok"):
                coach_comment = _compose_comment(comment, tag_list)
                if not coach_comment and sig == "verbal_negative":
                    coach_comment = str(
                        meta.get("verbal_message") or meta.get("comment") or "Verbal negative feedback"
                    )
                if coach_comment or tag_list:
                    try:
                        from backend.app.core.gemini_ollama_coach import process_negative_feedback

                        result["coach"] = process_negative_feedback(
                            str(user_id),
                            interaction_id=result.get("interaction_id") or interaction_id,
                            chat_id=chat_id,
                            user_comment=coach_comment,
                            membership=membership,
                        )
                    except Exception as exc:
                        result["coach"] = {"ok": False, "error": str(exc)[:120]}

            if sig in ("verbal_positive", "helpful", "thumbs_up") and result.get("ok"):
                try:
                    from backend.app.core.improvement_automation import schedule_improvement_pipeline

                    schedule_improvement_pipeline(str(user_id), trigger=sig)
                except Exception:
                    pass

        try:
            from backend.app.core.feedback_async import json_safe

            return json_safe(result)
        except Exception:
            return result

    return record_signal_event(
        str(user_id),
        sig,
        interaction_id=interaction_id,
        chat_id=chat_id,
        metadata=meta,
    )


def _compose_comment(comment: str, tags: List[str]) -> str:
    parts = [comment.strip()] if comment.strip() else []
    if tags:
        parts.append("Tags: " + ", ".join(tags))
    return " | ".join(parts)[:500]


def _interaction_detail(
    user_id: str,
    interaction_id: str,
    chat_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    from backend.app.core.adaptive_learning import ensure_learning_schema

    meta = metadata or {}
    ensure_learning_schema()
    conn = _connect()
    try:
        row = None
        if interaction_id:
            row = conn.execute(
                """SELECT id, mode, query, answer_preview FROM adaptive_interactions
                WHERE id=? AND user_id=?""",
                (interaction_id, str(user_id)),
            ).fetchone()
        elif chat_id:
            row = conn.execute(
                """SELECT id, mode, query, answer_preview FROM adaptive_interactions
                WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1""",
                (chat_id, str(user_id)),
            ).fetchone()
        elif str(meta.get("thread_id") or "").strip():
            row = conn.execute(
                """SELECT id, mode, query, answer_preview FROM adaptive_interactions
                WHERE thread_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1""",
                (str(meta.get("thread_id")), str(user_id)),
            ).fetchone()
        if not row:
            return {}
        return {
            "interaction_id": row[0],
            "mode": row[1],
            "query": row[2],
            "answer_preview": row[3],
        }
    finally:
        conn.close()


def _record_feedback_with_tags(
    user_id: str,
    *,
    signal: str,
    interaction_id: str,
    chat_id: str,
    comment: str,
    tags: List[str],
    metadata: Dict[str, Any],
) -> Dict[str, Any]:
    from backend.app.core.adaptive_learning import record_feedback

    result = record_feedback(
        user_id,
        interaction_id=interaction_id,
        chat_id=chat_id,
        thread_id=str(metadata.get("thread_id") or ""),
        signal=signal,
        comment=_compose_comment(comment, tags),
        tags=tags,
        metadata=metadata,
        scope_key=str(metadata.get("scope_key") or "global"),
    )
    return result


def signal_stats(user_id: str) -> Dict[str, Any]:
    ensure_signal_schema()
    uid = str(user_id)
    conn = _connect()
    try:
        events = conn.execute(
            "SELECT signal, COUNT(*) FROM learning_signal_events WHERE user_id=? GROUP BY signal",
            (uid,),
        ).fetchall()
        pending_regen = conn.execute(
            "SELECT COUNT(*) FROM regenerate_chains WHERE user_id=? AND outcome='pending'",
            (uid,),
        ).fetchone()
        edits = conn.execute(
            "SELECT COUNT(*) FROM edit_preference_pairs WHERE user_id=?",
            (uid,),
        ).fetchone()
    finally:
        conn.close()
    return {
        "events_by_signal": {str(s): int(c) for s, c in events},
        "pending_regenerates": int(pending_regen[0] if pending_regen else 0),
        "edit_pairs": int(edits[0] if edits else 0),
        "available_tags": TAG_LABELS,
    }
