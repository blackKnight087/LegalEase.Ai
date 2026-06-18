"""
Human-labeled training pipeline: SFT, preference pairs (DPO-style), RLHF/RLAIF rewards.

Rules:
  - SFT pairs ONLY from verified thumbs-up / helpful / copy (never Gemini-generated Q→A).
  - Preference pairs: chosen=thumbs_up answer vs rejected=thumbs_down on similar query.
  - RLHF reward: human signal weights.
  - RLAIF reward: Gemini scores STYLE only (via coach_guards) — never legal correctness.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
EXPORT_DIR = ROOT / "Data" / "human_training"
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

RLAIF_ENABLED = os.getenv("GEMINI_RLAIF_STYLE", "1").lower() in {"1", "true", "yes"}
HUMAN_REWARD_WEIGHT = float(os.getenv("HUMAN_REWARD_WEIGHT", "1.0"))
RLAIF_REWARD_WEIGHT = float(os.getenv("RLAIF_REWARD_WEIGHT", "0.25"))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def ensure_human_training_schema() -> None:
    from backend.app.core.legacy_db import use_postgres_legacy

    if use_postgres_legacy():
        from backend.app.core.pg_core_schema import ensure_pg_core_schema

        ensure_pg_core_schema()
        return
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS human_labels (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            interaction_id TEXT,
            signal TEXT NOT NULL,
            reward REAL DEFAULT 0,
            rlaif_json TEXT DEFAULT '{}',
            mode TEXT DEFAULT 'knowledge_base',
            query TEXT,
            answer_preview TEXT,
            comment TEXT,
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS preference_pairs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            query TEXT NOT NULL,
            chosen_answer TEXT NOT NULL,
            rejected_answer TEXT NOT NULL,
            chosen_interaction_id TEXT,
            rejected_interaction_id TEXT,
            reward_delta REAL DEFAULT 1.0,
            source TEXT DEFAULT 'human',
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_human_labels_uid
            ON human_labels(user_id, created_at DESC)"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_pref_pairs_uid
            ON preference_pairs(user_id, created_at DESC)"""
        )
        conn.commit()
    finally:
        conn.close()


def _signal_reward(signal: str) -> float:
    return {
        "thumbs_up": 1.0,
        "helpful": 0.9,
        "verbal_positive": 0.88,
        "copy": 0.85,
        "thumbs_down": -1.0,
        "verbal_negative": -0.95,
        "regenerate": -0.4,
    }.get(signal, 0.0)


def record_human_label(
    user_id: str,
    *,
    interaction_id: str = "",
    signal: str,
    mode: str = "knowledge_base",
    query: str = "",
    answer_preview: str = "",
    comment: str = "",
    rlaif: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Record human-labeled training signal with optional RLAIF style score."""
    ensure_human_training_schema()
    uid = str(user_id)
    reward = _signal_reward(signal) * HUMAN_REWARD_WEIGHT
    if rlaif and rlaif.get("overall") is not None:
        reward += float(rlaif["overall"]) * RLAIF_REWARD_WEIGHT

    lid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO human_labels
            (id, user_id, interaction_id, signal, reward, rlaif_json, mode, query, answer_preview, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                lid,
                uid,
                interaction_id or "",
                signal,
                reward,
                json.dumps(rlaif or {}, ensure_ascii=False),
                mode,
                (query or "")[:500],
                (answer_preview or "")[:800],
                (comment or "")[:400],
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "label_id": lid, "reward": reward}


def record_preference_pair(
    user_id: str,
    *,
    query: str,
    chosen: str,
    rejected: str,
    chosen_interaction_id: str = "",
    rejected_interaction_id: str = "",
    source: str = "human",
    reward_delta: float = 1.0,
) -> Optional[str]:
    if not query or not chosen or not rejected or chosen == rejected:
        return None
    ensure_human_training_schema()
    pid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO preference_pairs
            (id, user_id, query, chosen_answer, rejected_answer, chosen_interaction_id,
             rejected_interaction_id, reward_delta, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                pid,
                str(user_id),
                query[:500],
                chosen[:2000],
                rejected[:2000],
                chosen_interaction_id,
                rejected_interaction_id,
                reward_delta,
                source[:30],
                _utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return pid


def maybe_build_preference_pair(
    user_id: str,
    *,
    interaction_id: str,
    signal: str,
    query: str,
    answer_preview: str,
) -> Optional[str]:
    """On thumbs_down, pair with best prior thumbs_up on similar query (DPO-style export)."""
    if signal not in ("thumbs_down", "verbal_negative") or not query or not answer_preview:
        return None
    ensure_human_training_schema()
    from backend.app.core.adaptive_learning import normalize_query

    qn = normalize_query(query)
    uid = str(user_id)
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT i.id, i.answer_preview FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id=? AND f.signal IN ('thumbs_up', 'helpful', 'verbal_positive', 'copy', 'export_docx', 'export_pdf', 'save_to_matter')
            AND i.query_norm = ?
            ORDER BY f.created_at DESC LIMIT 1""",
            (uid, qn),
        ).fetchone()
        if not row:
            return None
        chosen_id, chosen = row[0], row[1]
        if not chosen or chosen == answer_preview:
            return None
        pid = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO preference_pairs
            (id, user_id, query, chosen_answer, rejected_answer, chosen_interaction_id,
             rejected_interaction_id, reward_delta, source, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'human', ?)""",
            (
                pid,
                uid,
                query[:500],
                (chosen or "")[:2000],
                answer_preview[:2000],
                chosen_id,
                interaction_id,
                1.0,
                _utc(),
            ),
        )
        conn.commit()
        return pid
    finally:
        conn.close()


def rlaif_score_style_only(
    query: str,
    answer_preview: str,
    *,
    user_id: str = "",
    membership: str = "Free",
) -> Optional[Dict[str, Any]]:
    """
    RLAIF: Gemini scores answer STYLE/format only — guarded, offline path.
    Never scores legal correctness.
    """
    if not RLAIF_ENABLED or not answer_preview or len(answer_preview) < 40:
        return None
    try:
        from backend.app.core.gemini_ollama_coach import coach_available, score_answer_style_rlaif

        if not coach_available():
            return None
        return score_answer_style_rlaif(
            query,
            answer_preview,
            user_id=str(user_id),
            membership=membership,
        )
    except Exception as exc:
        logger.debug("RLAIF style score skipped: %s", exc)
        return None


def export_sft_jsonl(user_id: str, *, limit: int = 2000) -> Dict[str, Any]:
    """Supervised fine-tuning export — human thumbs-up only."""
    ensure_human_training_schema()
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    uid = str(user_id)
    lines: List[str] = []
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT i.query, i.answer_preview, i.mode, f.signal
            FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id=? AND f.signal IN ('thumbs_up', 'helpful', 'verbal_positive', 'copy', 'export_docx', 'export_pdf', 'save_to_matter')
            ORDER BY f.created_at DESC LIMIT ?""",
            (uid, limit),
        ).fetchall()
    finally:
        conn.close()

    for q, a, mode, sig in rows:
        if not q or not a or len(a) < 40:
            continue
        record = {
            "messages": [
                {"role": "system", "content": f"You are LegalEase KB assistant ({mode}). Ground in documents."},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ],
            "metadata": {"signal": sig, "source": "human_sft", "user_id": uid},
        }
        lines.append(json.dumps(record, ensure_ascii=False))

    if not lines:
        return {"status": "empty", "record_count": 0, "path": ""}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = EXPORT_DIR / f"sft_{uid}_{ts}.jsonl"
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "record_count": len(lines), "path": str(out), "format": "sft"}


def export_dpo_jsonl(user_id: str, *, limit: int = 500) -> Dict[str, Any]:
    """DPO-style preference export from human_labels preference_pairs."""
    ensure_human_training_schema()
    uid = str(user_id)
    lines: List[str] = []
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT query, chosen_answer, rejected_answer, reward_delta
            FROM preference_pairs WHERE user_id=? ORDER BY created_at DESC LIMIT ?""",
            (uid, limit),
        ).fetchall()
    finally:
        conn.close()

    for q, chosen, rejected, delta in rows:
        if not q or not chosen or not rejected:
            continue
        record = {
            "prompt": q,
            "chosen": chosen,
            "rejected": rejected,
            "metadata": {"reward_delta": delta, "source": "human_dpo", "user_id": uid},
        }
        lines.append(json.dumps(record, ensure_ascii=False))

    if not lines:
        return {"status": "empty", "record_count": 0, "path": ""}

    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = EXPORT_DIR / f"dpo_{uid}_{ts}.jsonl"
    out.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "record_count": len(lines), "path": str(out), "format": "dpo"}


def training_pipeline_status(user_id: str) -> Dict[str, Any]:
    ensure_human_training_schema()
    uid = str(user_id)
    conn = _connect()
    try:
        labels = conn.execute(
            "SELECT COUNT(*), AVG(reward) FROM human_labels WHERE user_id=?",
            (uid,),
        ).fetchone()
        pairs = conn.execute(
            "SELECT COUNT(*) FROM preference_pairs WHERE user_id=?",
            (uid,),
        ).fetchone()
        pos = conn.execute(
            """SELECT COUNT(*) FROM human_labels WHERE user_id=? AND signal IN ('thumbs_up','helpful','copy')""",
            (uid,),
        ).fetchone()
        neg = conn.execute(
            "SELECT COUNT(*) FROM human_labels WHERE user_id=? AND signal='thumbs_down'",
            (uid,),
        ).fetchone()
    finally:
        conn.close()
    return {
        "human_labels": int(labels[0] if labels else 0),
        "avg_reward": round(float(labels[1] or 0), 4),
        "preference_pairs": int(pairs[0] if pairs else 0),
        "positive_labels": int(pos[0] if pos else 0),
        "negative_labels": int(neg[0] if neg else 0),
        "rlaif_enabled": RLAIF_ENABLED,
        "sft_ready": int(pos[0] if pos else 0) >= 5,
        "dpo_ready": int(pairs[0] if pairs else 0) >= 2,
    }


def process_feedback_for_training(
    user_id: str,
    *,
    interaction_id: str,
    signal: str,
    comment: str = "",
    membership: str = "Free",
    tags: Optional[List[str]] = None,
    skip_rlaif: bool = False,
) -> Dict[str, Any]:
    """Full human-label + preference + RLAIF + retrieval learning hook."""
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.retrieval_learning import learn_from_feedback
    from backend.app.core.user_preferences import learn_from_feedback_signal
    from backend.app.core.learning_signals import apply_tags_to_preferences

    ensure_learning_schema()
    ensure_human_training_schema()

    detail: Dict[str, Any] = {}
    conn = _connect()
    try:
        row = conn.execute(
            """SELECT i.mode, i.query, i.answer_preview FROM adaptive_interactions i
            WHERE i.id=? AND i.user_id=?""",
            (interaction_id, str(user_id)),
        ).fetchone()
        if row:
            detail = {"mode": row[0], "query": row[1], "answer_preview": row[2]}
    finally:
        conn.close()

    rlaif = None
    if (
        not skip_rlaif
        and signal in ("thumbs_up", "helpful", "verbal_positive")
        and detail.get("answer_preview")
    ):
        rlaif = rlaif_score_style_only(
            detail.get("query", ""),
            detail.get("answer_preview", ""),
            user_id=str(user_id),
            membership=membership,
        )

    label = record_human_label(
        user_id,
        interaction_id=interaction_id,
        signal=signal,
        mode=detail.get("mode", "knowledge_base"),
        query=detail.get("query", ""),
        answer_preview=detail.get("answer_preview", ""),
        comment=comment,
        rlaif=rlaif,
    )

    pair_id = maybe_build_preference_pair(
        user_id,
        interaction_id=interaction_id,
        signal=signal,
        query=detail.get("query", ""),
        answer_preview=detail.get("answer_preview", ""),
    )

    prefs = learn_from_feedback_signal(
        user_id,
        signal,
        mode=detail.get("mode", ""),
        query=detail.get("query", ""),
        answer_preview=detail.get("answer_preview", ""),
    )

    retrieval = learn_from_feedback(
        user_id,
        signal,
        query=detail.get("query", ""),
        answer_preview=detail.get("answer_preview", ""),
        mode=detail.get("mode", "knowledge_base"),
    )

    if tags:
        apply_tags_to_preferences(str(user_id), tags)

    return {
        "label": label,
        "preference_pair_id": pair_id,
        "rlaif": rlaif,
        "preferences_updated": bool(prefs),
        "retrieval_learning": retrieval,
        "tags_applied": len(tags or []),
        "reward_recorded": label.get("reward"),
    }
