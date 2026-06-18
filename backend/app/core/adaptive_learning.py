"""
Adaptive Learning Engine — continuous improvement from user interactions.

Learns from thumbs-up/down, implicit signals (NOT_FOUND, re-asks, corrections), and
successful retrieval patterns. Applies learnings to:
  - Query expansion (KB + all modes)
  - Chunk reranking boosts
  - Retrieval confidence thresholds
  - Per-user / per-mode tuning

No GPU fine-tuning required; improves RAG + routing like production feedback loops.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_last_interaction_by_user: Dict[str, str] = {}

from backend.app.core.database import get_sqlite_path
from backend.app.core.legacy_db import connect_app_db, use_postgres_legacy

DB_PATH = get_sqlite_path()

_MAX_BOOST = 0.22
_MAX_PENALTY = -0.18
_QUERY_NORM_RE = re.compile(r"\s+")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    return connect_app_db()


def chunk_key_from_result(chunk: Dict[str, Any]) -> str:
    meta = chunk.get("metadata") or {}
    content = (chunk.get("content") or "")[:96]
    raw = "|".join(
        [
            str(meta.get("doc_id", "")),
            str(meta.get("filename", "")),
            str(meta.get("chunk_index", "")),
            content,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:32]


def normalize_query(q: str) -> str:
    return _QUERY_NORM_RE.sub(" ", (q or "").strip().lower())[:500]


def ensure_learning_schema() -> None:
    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = _connect()
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS adaptive_interactions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        query TEXT NOT NULL,
        query_norm TEXT NOT NULL,
        answer_preview TEXT,
        intent TEXT,
        found_in_kb INTEGER DEFAULT 0,
        best_score REAL DEFAULT 0,
        chunk_keys TEXT,
        chat_id TEXT,
        thread_id TEXT,
        implicit_signal TEXT,
        scope_key TEXT DEFAULT 'global',
        created_at TEXT NOT NULL
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS adaptive_feedback (
        id TEXT PRIMARY KEY,
        interaction_id TEXT,
        user_id TEXT NOT NULL,
        signal TEXT NOT NULL,
        value REAL DEFAULT 1,
        comment TEXT,
        scope_key TEXT DEFAULT 'global',
        created_at TEXT NOT NULL
    )"""
    )
    cols_i = {row[1] for row in c.execute("PRAGMA table_info(adaptive_interactions)").fetchall()}
    if "scope_key" not in cols_i:
        c.execute("ALTER TABLE adaptive_interactions ADD COLUMN scope_key TEXT DEFAULT 'global'")
    cols_f = {row[1] for row in c.execute("PRAGMA table_info(adaptive_feedback)").fetchall()}
    if "scope_key" not in cols_f:
        c.execute("ALTER TABLE adaptive_feedback ADD COLUMN scope_key TEXT DEFAULT 'global'")
    c.execute(
        """CREATE TABLE IF NOT EXISTS adaptive_query_patterns (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        mode TEXT NOT NULL,
        query_norm TEXT NOT NULL,
        successful_expansion TEXT NOT NULL,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        last_used TEXT
    )"""
    )
    c.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_aqp_user_mode_q
        ON adaptive_query_patterns(COALESCE(user_id,''), mode, query_norm)"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS adaptive_chunk_boosts (
        chunk_key TEXT NOT NULL,
        user_id TEXT NOT NULL DEFAULT '',
        mode TEXT NOT NULL DEFAULT 'knowledge_base',
        boost_score REAL DEFAULT 0,
        success_count INTEGER DEFAULT 0,
        fail_count INTEGER DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (chunk_key, user_id, mode)
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS adaptive_mode_stats (
        user_id TEXT NOT NULL,
        mode TEXT NOT NULL,
        total_turns INTEGER DEFAULT 0,
        positive_signals INTEGER DEFAULT 0,
        negative_signals INTEGER DEFAULT 0,
        not_found_count INTEGER DEFAULT 0,
        avg_best_score REAL DEFAULT 0,
        threshold_delta REAL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (user_id, mode)
    )"""
    )
    c.execute(
        """CREATE TABLE IF NOT EXISTS adaptive_scope_promotions (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        source_scope TEXT NOT NULL,
        target_scope TEXT NOT NULL,
        promoted_by TEXT NOT NULL,
        interactions_copied INTEGER DEFAULT 0,
        feedback_copied INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )"""
    )
    conn.commit()
    conn.close()


def promote_scope_to_global(
    user_id: str,
    *,
    matter_id: str,
    promoted_by: str,
    limit: int = 500,
) -> Dict[str, Any]:
    """
    Explicit admin action: clone scoped matter interactions/feedback into global scope.
    Keeps original rows unchanged and writes a promotion audit record.
    """
    ensure_learning_schema()
    source_scope = f"matter:{(matter_id or '').strip()}"
    if source_scope == "matter:":
        return {"ok": False, "error": "matter_id is required"}
    conn = _connect()
    promoted_interactions = 0
    promoted_feedback = 0
    try:
        rows = conn.execute(
            """
            SELECT id, mode, query, query_norm, answer_preview, intent, found_in_kb,
                   best_score, chunk_keys, chat_id, thread_id, implicit_signal
            FROM adaptive_interactions
            WHERE user_id=? AND scope_key=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(user_id), source_scope, int(limit)),
        ).fetchall()
        for r in rows:
            conn.execute(
                """
                INSERT INTO adaptive_interactions
                (id, user_id, mode, query, query_norm, answer_preview, intent, found_in_kb,
                 best_score, chunk_keys, chat_id, thread_id, implicit_signal, scope_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'global', ?)
                """,
                (
                    str(uuid.uuid4()),
                    str(user_id),
                    r[1],
                    r[2],
                    r[3],
                    r[4],
                    r[5],
                    r[6],
                    r[7],
                    r[8],
                    r[9],
                    r[10],
                    "scope_promoted",
                    _utc(),
                ),
            )
            promoted_interactions += 1

        fb_rows = conn.execute(
            """
            SELECT interaction_id, signal, value, comment
            FROM adaptive_feedback
            WHERE user_id=? AND scope_key=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (str(user_id), source_scope, int(limit)),
        ).fetchall()
        for r in fb_rows:
            conn.execute(
                """
                INSERT INTO adaptive_feedback
                (id, interaction_id, user_id, signal, value, comment, scope_key, created_at)
                VALUES (?, ?, ?, ?, ?, ?, 'global', ?)
                """,
                (
                    str(uuid.uuid4()),
                    r[0],
                    str(user_id),
                    r[1],
                    r[2],
                    r[3],
                    _utc(),
                ),
            )
            promoted_feedback += 1

        conn.execute(
            """
            INSERT INTO adaptive_scope_promotions
            (id, user_id, source_scope, target_scope, promoted_by, interactions_copied, feedback_copied, created_at)
            VALUES (?, ?, ?, 'global', ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                str(user_id),
                source_scope,
                str(promoted_by),
                promoted_interactions,
                promoted_feedback,
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "ok": True,
        "source_scope": source_scope,
        "target_scope": "global",
        "interactions_copied": promoted_interactions,
        "feedback_copied": promoted_feedback,
    }


def record_interaction(
    user_id: str,
    mode: str,
    query: str,
    *,
    answer: str = "",
    intent: str = "",
    found_in_kb: bool = False,
    best_score: float = 0.0,
    chunks: Optional[List[Dict[str, Any]]] = None,
    chat_id: str = "",
    thread_id: str = "",
    implicit_signal: str = "",
    learning_handled: bool = False,
    scope_key: str = "global",
) -> str:
    """Log each chat turn for learning (called after every response)."""
    from backend.app.core.schema_migrations import safe_sqlite

    fallback_id = str(uuid.uuid4())

    def _write() -> str:
        return _record_interaction_impl(
            user_id,
            mode,
            query,
            answer=answer,
            intent=intent,
            found_in_kb=found_in_kb,
            best_score=best_score,
            chunks=chunks,
            chat_id=chat_id,
            thread_id=thread_id,
            implicit_signal=implicit_signal,
            learning_handled=learning_handled,
            scope_key=scope_key,
            interaction_id=fallback_id,
        )

    out = safe_sqlite("record_interaction", _write, default=None)
    return out or fallback_id


def _record_interaction_impl(
    user_id: str,
    mode: str,
    query: str,
    *,
    answer: str = "",
    intent: str = "",
    found_in_kb: bool = False,
    best_score: float = 0.0,
    chunks: Optional[List[Dict[str, Any]]] = None,
    chat_id: str = "",
    thread_id: str = "",
    implicit_signal: str = "",
    learning_handled: bool = False,
    scope_key: str = "global",
    interaction_id: str = "",
) -> str:
    ensure_learning_schema()
    iid = interaction_id or str(uuid.uuid4())
    qn = normalize_query(query)
    keys = [chunk_key_from_result(c) for c in (chunks or [])[:12]]
    preview = (answer or "")[:600]
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO adaptive_interactions
            (id, user_id, mode, query, query_norm, answer_preview, intent, found_in_kb,
             best_score, chunk_keys, chat_id, thread_id, implicit_signal, scope_key, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                iid,
                str(user_id),
                mode or "knowledge_base",
                query[:2000],
                qn,
                preview,
                intent[:80],
                1 if found_in_kb else 0,
                float(best_score),
                json.dumps(keys),
                chat_id,
                thread_id,
                implicit_signal[:40],
                (scope_key or "global")[:120],
                _utc(),
            ),
        )
        conn.commit()
        try:
            _bump_mode_stats(
                conn,
                str(user_id),
                mode,
                positive=found_in_kb and len(preview) > 80,
                negative=not found_in_kb,
                not_found=not found_in_kb,
                best_score=best_score,
            )
            conn.commit()
        except Exception as exc:
            logger.warning("mode_stats bump skipped: %s", exc)
    finally:
        conn.close()

    if not found_in_kb:
        _learn_from_not_found(str(user_id), mode, qn)
    elif keys and len(preview) > 100 and not learning_handled:
        _implicit_positive_chunks(str(user_id), mode, keys, weight=0.05)

    if not learning_handled:
        try:
            from backend.app.core.neural_finetuning import add_pairs_from_interaction, maybe_auto_train

            if found_in_kb and chunks:
                add_pairs_from_interaction(str(user_id), query, chunks, source="kb_turn")
            elif found_in_kb and preview and mode in ("web_search", "deep_case", "open_law", "hybrid"):
                from backend.app.core.neural_finetuning import add_training_pair

                add_training_pair(query, preview, user_id=str(user_id), source="web_turn")

            def _bg_train() -> None:
                try:
                    maybe_auto_train(str(user_id))
                except Exception:
                    pass

            import threading

            threading.Thread(target=_bg_train, daemon=True, name="neural-auto-train").start()
        except Exception:
            pass

    _last_interaction_by_user[str(user_id)] = iid
    return iid


def get_last_interaction_id(user_id: str) -> str:
    return _last_interaction_by_user.get(str(user_id), "")


def record_feedback(
    user_id: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
    thread_id: str = "",
    signal: str = "thumbs_up",
    value: float = 1.0,
    comment: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    scope_key: str = "global",
) -> Dict[str, Any]:
    """Explicit user feedback — drives strongest learning updates."""
    ensure_learning_schema()
    last_err: Optional[Exception] = None
    for attempt in range(4):
        conn = _connect()
        try:
            return _record_feedback_inner(
                conn,
                user_id,
                interaction_id=interaction_id,
                chat_id=chat_id,
                thread_id=thread_id,
                signal=signal,
                value=value,
                comment=comment,
                tags=tags,
                metadata=metadata,
                scope_key=scope_key,
            )
        except sqlite3.OperationalError as exc:
            last_err = exc
            if "locked" not in str(exc).lower() or attempt >= 3:
                raise
            import time

            time.sleep(0.15 * (attempt + 1))
        finally:
            conn.close()
    if last_err:
        raise last_err
    return {"ok": False, "error": "feedback failed"}


def _record_feedback_inner(
    conn: sqlite3.Connection,
    user_id: str,
    *,
    interaction_id: str = "",
    chat_id: str = "",
    thread_id: str = "",
    signal: str = "thumbs_up",
    value: float = 1.0,
    comment: str = "",
    tags: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    scope_key: str = "global",
) -> Dict[str, Any]:
        row = None
        if interaction_id:
            row = conn.execute(
                "SELECT id, mode, query, query_norm, chunk_keys, found_in_kb FROM adaptive_interactions WHERE id=? AND user_id=?",
                (interaction_id, str(user_id)),
            ).fetchone()
        elif chat_id:
            row = conn.execute(
                """SELECT id, mode, query, query_norm, chunk_keys, found_in_kb
                FROM adaptive_interactions WHERE chat_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1""",
                (chat_id, str(user_id)),
            ).fetchone()
        elif thread_id:
            row = conn.execute(
                """SELECT id, mode, query, query_norm, chunk_keys, found_in_kb
                FROM adaptive_interactions WHERE thread_id=? AND user_id=? ORDER BY created_at DESC LIMIT 1""",
                (thread_id, str(user_id)),
            ).fetchone()

        if not row:
            row = conn.execute(
                """SELECT id, mode, query, query_norm, chunk_keys, found_in_kb
                FROM adaptive_interactions WHERE user_id=? ORDER BY created_at DESC LIMIT 1""",
                (str(user_id),),
            ).fetchone()

        if not row and chat_id:
            try:
                ch_row = conn.execute(
                    """SELECT question, answer, mode FROM chat_history
                    WHERE id=? AND user_id=? LIMIT 1""",
                    (chat_id, str(user_id)),
                ).fetchone()
            except Exception:
                ch_row = None
            if ch_row:
                iid = str(uuid.uuid4())
                qn = normalize_query(ch_row[0] or "")
                conn.execute(
                    """INSERT INTO adaptive_interactions
                    (id, user_id, mode, query, query_norm, answer_preview, intent, found_in_kb,
                     best_score, chunk_keys, chat_id, thread_id, implicit_signal, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        iid,
                        str(user_id),
                        ch_row[2] or "knowledge_base",
                        (ch_row[0] or "")[:2000],
                        qn,
                        (ch_row[1] or "")[:600],
                        "",
                        1,
                        0.5,
                        "[]",
                        chat_id,
                        thread_id,
                        "feedback_bootstrap",
                        _utc(),
                    ),
                )
                row = (
                    iid,
                    ch_row[2] or "knowledge_base",
                    ch_row[0],
                    qn,
                    "[]",
                    1,
                )

        if not row:
            return {"ok": False, "error": "interaction not found — send a message first, then retry feedback"}

        iid, mode, query, qn, chunk_json, found = row
        keys = json.loads(chunk_json or "[]")
        fid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO adaptive_feedback (id, interaction_id, user_id, signal, value, comment, created_at)
            VALUES (?,?,?,?,?,?,?)""",
            (fid, iid, str(user_id), signal, float(value), comment[:500], _utc()),
        )
        try:
            conn.execute(
                "UPDATE adaptive_feedback SET scope_key = ? WHERE id = ?",
                ((scope_key or "global")[:120], fid),
            )
        except Exception:
            pass

        positive = signal in (
            "thumbs_up", "helpful", "verbal_positive", "copy", "follow_up_click",
            "export_docx", "export_pdf", "export_client_safe", "save_to_matter",
        )
        negative = signal in (
            "thumbs_down", "verbal_negative", "regenerate", "wrong", "not_helpful", "mode_switch",
        )

        tags_json = json.dumps(list(tags or [])[:8], ensure_ascii=False)
        meta_json = json.dumps(metadata or {}, ensure_ascii=False)
        try:
            conn.execute(
                "UPDATE adaptive_feedback SET tags_json=?, metadata_json=? WHERE id=?",
                (tags_json, meta_json, fid),
            )
        except Exception:
            pass

        if positive:
            _apply_positive_learning(conn, str(user_id), mode, qn, query, keys)
            _bump_mode_stats(conn, str(user_id), mode, positive=True)
            preview_row = conn.execute(
                "SELECT answer_preview FROM adaptive_interactions WHERE id=?",
                (iid,),
            ).fetchone()
            answer_text = (preview_row[0] if preview_row else "") or ""
            try:
                from backend.app.core.feedback_async import (
                    FEEDBACK_FAST,
                    defer_positive_feedback_side_effects,
                )

                if FEEDBACK_FAST and len(answer_text) >= 40:
                    defer_positive_feedback_side_effects(
                        str(user_id),
                        mode=mode,
                        query=query,
                        answer_text=answer_text,
                        signal=signal,
                    )
                elif len(answer_text) >= 40:
                    from backend.app.core.neural_finetuning import add_training_pair, collect_pairs_from_feedback

                    if signal in (
                        "thumbs_up", "helpful", "verbal_positive", "copy",
                        "export_docx", "export_pdf", "save_to_matter",
                    ):
                        add_training_pair(query, answer_text, user_id=str(user_id), source=signal)
                    collect_pairs_from_feedback(str(user_id), limit=50)
                    try:
                        from backend.app.core.learning_engine import learn_from_kb_success, learn_from_web_success

                        if mode in ("web_search", "open_law", "deep_case", "hybrid"):
                            learn_from_web_success(
                                str(user_id), query, answer_text,
                                source="thumbs_up", confidence=0.92,
                            )
                        else:
                            learn_from_kb_success(
                                str(user_id), query, answer_text,
                                source="thumbs_up", confidence=0.92,
                            )
                    except Exception:
                        pass
                    try:
                        from backend.app.core.improvement_automation import schedule_improvement_pipeline

                        schedule_improvement_pipeline(str(user_id), trigger=signal)
                    except Exception:
                        pass
            except Exception:
                pass
        elif negative:
            _apply_negative_learning(conn, str(user_id), mode, qn, keys)
            _bump_mode_stats(conn, str(user_id), mode, negative=True)
            try:
                from backend.app.core.learning_engine import learn_from_kb_failure

                learn_from_kb_failure(str(user_id), query)
            except Exception:
                pass

        conn.commit()
        return {"ok": True, "interaction_id": iid, "signal": signal}


def record_implicit_correction(
    user_id: str,
    mode: str,
    previous_query_norm: str,
    correction_query: str,
) -> None:
    """User re-phrased after a bad answer — learn expansion mapping."""
    ensure_learning_schema()
    prev = previous_query_norm or ""
    corr = normalize_query(correction_query)
    if not prev or not corr or prev == corr:
        return
    conn = _connect()
    try:
        _upsert_query_pattern(conn, str(user_id), mode, prev, correction_query, success_delta=2)
        conn.execute(
            "UPDATE adaptive_query_patterns SET fail_count = fail_count + 1 WHERE query_norm=? AND COALESCE(user_id,'')=?",
            (prev, str(user_id)),
        )
        conn.commit()
    finally:
        conn.close()


def teach_query_expansion(
    user_id: str,
    mode: str,
    query_norm: str,
    expansion: str,
    *,
    success_delta: int = 2,
) -> None:
    """Settings coach — teach retrieval how to expand a query pattern."""
    qn = normalize_query(query_norm or "")
    exp = (expansion or "").strip()
    if not qn or not exp:
        return
    ensure_learning_schema()
    conn = _connect()
    try:
        _upsert_query_pattern(conn, str(user_id), mode, qn, exp, success_delta=success_delta)
        conn.commit()
    finally:
        conn.close()


def apply_learned_query_expansion(
    user_id: str,
    mode: str,
    query: str,
    current_expansion: str = "",
) -> str:
    """Merge successful past expansions for similar queries."""
    qn = normalize_query(query)
    if not qn:
        return current_expansion or query

    try:
        from backend.app.services.legal_query_parser import (
            is_law_replacement_intent,
            is_section_lookup_query,
        )

        if is_section_lookup_query(query):
            # Never expand section lookups into law-replacement queries (poisons rescue).
            return current_expansion or query
    except ImportError:
        is_law_replacement_intent = None  # type: ignore
        is_section_lookup_query = None  # type: ignore

    ensure_learning_schema()
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT successful_expansion, success_count, fail_count
            FROM adaptive_query_patterns
            WHERE mode=? AND (user_id=? OR user_id IS NULL OR user_id='')
            AND (query_norm=? OR query_norm LIKE ?)
            ORDER BY success_count DESC LIMIT 5""",
            (mode, str(user_id), qn, f"%{qn[:40]}%"),
        ).fetchall()
    finally:
        conn.close()

    best_exp = current_expansion or query
    best_score = 0
    for exp, succ, fail in rows:
        net = int(succ) - int(fail) * 2
        if net > best_score and exp:
            if is_section_lookup_query and is_law_replacement_intent and is_law_replacement_intent(
                exp.lower()
            ):
                continue
            best_score = net
            best_exp = exp

    # Global synonym shortcuts learned from aggregates
    shortcuts = _global_query_shortcuts(qn)
    if shortcuts and best_score < 3:
        best_exp = f"{shortcuts} {best_exp}".strip()

    if best_exp != query and len(best_exp) > len(query) + 5:
        return best_exp[:800]
    return current_expansion or query


def apply_chunk_boosts(
    user_id: str,
    mode: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Rerank chunks using historical success boosts."""
    if not chunks:
        return chunks
    ensure_learning_schema()
    keys = [chunk_key_from_result(c) for c in chunks]
    conn = _connect()
    boosts: Dict[str, float] = {}
    try:
        for ck in keys:
            rows = conn.execute(
                """SELECT boost_score FROM adaptive_chunk_boosts
                WHERE chunk_key=? AND mode=? AND (user_id=? OR user_id IS NULL OR user_id='')
                ORDER BY success_count DESC LIMIT 3""",
                (ck, mode, str(user_id)),
            ).fetchall()
            if rows:
                boosts[ck] = sum(float(r[0]) for r in rows[:2])
    finally:
        conn.close()

    for ch in chunks:
        ck = chunk_key_from_result(ch)
        delta = boosts.get(ck, 0.0)
        delta = max(_MAX_PENALTY, min(_MAX_BOOST, delta))
        if "final_score" in ch:
            ch["final_score"] = float(ch.get("final_score", 0)) + delta
            ch["adaptive_boost"] = delta
        if "hybrid_score" in ch:
            ch["hybrid_score"] = float(ch.get("hybrid_score", 0)) + delta * 0.5

    chunks.sort(
        key=lambda c: float(c.get("final_score", c.get("hybrid_score", 0))),
        reverse=True,
    )
    return chunks


def get_adaptive_threshold(
    user_id: str,
    mode: str,
    base: float = 0.28,
) -> float:
    """Slightly lower threshold when user historically gets good KB answers."""
    ensure_learning_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT threshold_delta, not_found_count, total_turns FROM adaptive_mode_stats WHERE user_id=? AND mode=?",
            (str(user_id), mode),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return base
    delta, nf, total = float(row[0]), int(row[1]), int(row[2])
    if total < 2:
        return base + delta
    nf_rate = nf / max(total, 1)
    if nf_rate > 0.4:
        return min(base + 0.04, base + delta + 0.02)
    if nf_rate < 0.15:
        return max(0.20, base + delta - 0.03)
    return max(0.20, min(0.38, base + delta))


def get_retrieval_k_boost(user_id: str, mode: str) -> int:
    """Extra k when mode has high NOT_FOUND rate."""
    ensure_learning_schema()
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT not_found_count, total_turns FROM adaptive_mode_stats WHERE user_id=? AND mode=?",
            (str(user_id), mode),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return 0
    nf, total = int(row[0]), int(row[1])
    if total >= 4 and nf / max(total, 1) > 0.30:
        return 4
    return 0


def enhance_intent_profile(
    user_id: str,
    mode: str,
    profile: Any,
    raw_query: str,
) -> Any:
    """Apply learned query expansion and retrieval_k to IntentProfile."""
    expanded = apply_learned_query_expansion(
        user_id,
        mode,
        raw_query,
        getattr(profile, "expanded_query", "") or raw_query,
    )
    profile.expanded_query = expanded
    k_boost = get_retrieval_k_boost(user_id, mode)
    if k_boost:
        profile.retrieval_k = min(20, (profile.retrieval_k or 8) + k_boost)
    return profile


def learning_stats(user_id: str) -> Dict[str, Any]:
    ensure_learning_schema()
    conn = _connect()
    try:
        modes = conn.execute(
            """SELECT mode, total_turns, positive_signals, negative_signals,
                      not_found_count, threshold_delta, avg_best_score
            FROM adaptive_mode_stats WHERE user_id=?""",
            (str(user_id),),
        ).fetchall()
        patterns = conn.execute(
            """SELECT query_norm, successful_expansion, success_count
            FROM adaptive_query_patterns WHERE user_id=? ORDER BY success_count DESC LIMIT 10""",
            (str(user_id),),
        ).fetchall()
        top_chunks = conn.execute(
            """SELECT chunk_key, boost_score, success_count FROM adaptive_chunk_boosts
            WHERE user_id=? ORDER BY success_count DESC LIMIT 8""",
            (str(user_id),),
        ).fetchall()
    finally:
        conn.close()

    mode_rows = []
    for m in modes:
        feedback = int(m[2] or 0) + int(m[3] or 0)
        pos_rate = round(int(m[2] or 0) / feedback, 3) if feedback else None
        acc_pct = round(int(m[2] or 0) / feedback * 100, 1) if feedback else None
        mode_rows.append(
            {
                "mode": m[0],
                "turns": m[1],
                "positive": m[2],
                "negative": m[3],
                "not_found_rate": round(m[4] / max(m[1], 1), 3),
                "threshold_delta": m[5],
                "avg_retrieval_score": round(float(m[6] or 0), 3),
                "positive_rate": pos_rate,
                "accuracy_pct": acc_pct,
                "hit_rate_pct": round((1 - m[4] / max(m[1], 1)) * 100, 1),
            }
        )

    total_turns = sum(r["turns"] for r in mode_rows)
    total_pos = sum(r["positive"] for r in mode_rows)
    total_neg = sum(r["negative"] for r in mode_rows)
    feedback_total = total_pos + total_neg
    summary = {
        "total_turns": total_turns,
        "total_positive": total_pos,
        "total_negative": total_neg,
        "feedback_count": feedback_total,
        "positive_rate": round(total_pos / feedback_total, 3) if feedback_total else None,
        "accuracy_pct": round(total_pos / feedback_total * 100, 1) if feedback_total else None,
        "avg_hit_rate_pct": round(
            sum(r["hit_rate_pct"] * r["turns"] for r in mode_rows) / max(total_turns, 1),
            1,
        )
        if mode_rows
        else None,
    }

    return {
        "modes": mode_rows,
        "summary": summary,
        "learned_queries": [
            {"query": p[0], "expansion": p[1], "success": p[2]} for p in patterns
        ],
        "top_chunks": [
            {"key": c[0][:12], "boost": c[1], "hits": c[2]} for c in top_chunks
        ],
        "auto_improve_enabled": True,
    }


# ---------- internal helpers ----------


def _bump_mode_stats(
    conn: sqlite3.Connection,
    user_id: str,
    mode: str,
    *,
    positive: bool = False,
    negative: bool = False,
    not_found: bool = False,
    best_score: float = 0.0,
) -> None:
    row = conn.execute(
        "SELECT total_turns, positive_signals, negative_signals, not_found_count, avg_best_score, threshold_delta FROM adaptive_mode_stats WHERE user_id=? AND mode=?",
        (user_id, mode),
    ).fetchone()
    if row:
        t, pos, neg, nf, avg, delta = row
        t += 1
        if positive:
            pos += 1
            delta = max(-0.05, float(delta) - 0.002)
        if negative:
            neg += 1
            delta = min(0.05, float(delta) + 0.003)
        if not_found:
            nf += 1
        avg = (float(avg) * (t - 1) + best_score) / t if t else best_score
        conn.execute(
            """UPDATE adaptive_mode_stats SET total_turns=?, positive_signals=?, negative_signals=?,
            not_found_count=?, avg_best_score=?, threshold_delta=?, updated_at=? WHERE user_id=? AND mode=?""",
            (t, pos, neg, nf, avg, delta, _utc(), user_id, mode),
        )
    else:
        conn.execute(
            """INSERT INTO adaptive_mode_stats
            (user_id, mode, total_turns, positive_signals, negative_signals, not_found_count,
             avg_best_score, threshold_delta, updated_at)
            VALUES (?,?,1,?,?,?,?,?,?)""",
            (
                user_id,
                mode,
                1 if positive else 0,
                1 if negative else 0,
                1 if not_found else 0,
                best_score,
                0.01 if negative else -0.01 if positive else 0,
                _utc(),
            ),
        )


def _upsert_query_pattern(
    conn: sqlite3.Connection,
    user_id: str,
    mode: str,
    query_norm: str,
    expansion: str,
    success_delta: int = 1,
) -> None:
    row = conn.execute(
        "SELECT id, success_count FROM adaptive_query_patterns WHERE COALESCE(user_id,'')=? AND mode=? AND query_norm=?",
        (user_id, mode, query_norm),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE adaptive_query_patterns SET success_count=success_count+?, successful_expansion=?, last_used=? WHERE id=?",
            (success_delta, expansion[:800], _utc(), row[0]),
        )
    else:
        conn.execute(
            """INSERT INTO adaptive_query_patterns
            (id, user_id, mode, query_norm, successful_expansion, success_count, fail_count, last_used)
            VALUES (?,?,?,?,?,?,0,?)""",
            (str(uuid.uuid4()), user_id, mode, query_norm, expansion[:800], success_delta, _utc()),
        )


def _upsert_chunk_boost(
    conn: sqlite3.Connection,
    user_id: str,
    mode: str,
    chunk_key: str,
    delta: float,
    success: bool,
) -> None:
    row = conn.execute(
        "SELECT boost_score, success_count, fail_count FROM adaptive_chunk_boosts WHERE chunk_key=? AND COALESCE(user_id,'')=? AND mode=?",
        (chunk_key, user_id, mode),
    ).fetchone()
    if row:
        boost, sc, fc = float(row[0]), int(row[1]), int(row[2])
        boost = max(_MAX_PENALTY, min(_MAX_BOOST, boost + delta))
        if success:
            sc += 1
        else:
            fc += 1
        conn.execute(
            "UPDATE adaptive_chunk_boosts SET boost_score=?, success_count=?, fail_count=?, updated_at=? WHERE chunk_key=? AND COALESCE(user_id,'')=? AND mode=?",
            (boost, sc, fc, _utc(), chunk_key, user_id, mode),
        )
    else:
        conn.execute(
            """INSERT INTO adaptive_chunk_boosts
            (chunk_key, user_id, mode, boost_score, success_count, fail_count, updated_at)
            VALUES (?,?,?,?,?,?,?)""",
            (
                chunk_key,
                user_id,
                mode,
                max(_MAX_PENALTY, min(_MAX_BOOST, delta)),
                1 if success else 0,
                0 if success else 1,
                _utc(),
            ),
        )


def _apply_positive_learning(
    conn: sqlite3.Connection,
    user_id: str,
    mode: str,
    qn: str,
    query: str,
    keys: List[str],
) -> None:
    exp = apply_learned_query_expansion(user_id, mode, query, query)
    _upsert_query_pattern(conn, user_id, mode, qn, exp or query, success_delta=3)
    for ck in keys[:8]:
        _upsert_chunk_boost(conn, user_id, mode, ck, 0.08, success=True)


def _apply_negative_learning(
    conn: sqlite3.Connection,
    user_id: str,
    mode: str,
    qn: str,
    keys: List[str],
) -> None:
    conn.execute(
        "UPDATE adaptive_query_patterns SET fail_count = fail_count + 2 WHERE COALESCE(user_id,'')=? AND query_norm=?",
        (user_id, qn),
    )
    for ck in keys[:8]:
        _upsert_chunk_boost(conn, user_id, mode, ck, -0.06, success=False)


def _learn_from_not_found(user_id: str, mode: str, qn: str) -> None:
    conn = _connect()
    try:
        conn.execute(
            "UPDATE adaptive_query_patterns SET fail_count = fail_count + 1 WHERE COALESCE(user_id,'')=? AND query_norm=?",
            (user_id, qn),
        )
        conn.commit()
    finally:
        conn.close()


def _implicit_positive_chunks(user_id: str, mode: str, keys: List[str], weight: float = 0.05) -> None:
    conn = _connect()
    try:
        for ck in keys[:6]:
            _upsert_chunk_boost(conn, user_id, mode, ck, weight, success=True)
        conn.commit()
    finally:
        conn.close()


def _global_query_shortcuts(qn: str) -> str:
    """Static + learned-friendly expansions for common legal shorthand."""
    rules = [
        (r"\b(diff|difference)\b.*\b(\d{3})\b.*\b(\d{3})\b", "compare IPC section"),
        (r"\ball\s+(offence|offenses?|criminal)\b", "list all IPC criminal offences sections"),
        (r"\bipc\s*(\d{3})\b", r"IPC Section \1 definition punishment"),
    ]
    for pat, repl in rules:
        m = re.search(pat, qn)
        if m:
            if "\\1" in repl:
                return re.sub(pat, repl, qn)
            return repl
    return ""
