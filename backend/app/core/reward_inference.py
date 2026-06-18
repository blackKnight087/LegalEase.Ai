"""
Inference-time RLHF / RLAIF — apply stored human rewards during synthesis.

Rewards collected in human_labels and preference_pairs now shape prompts,
candidate reranking, and retrieval boosts at answer generation time.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ENABLED = os.getenv("INFERENCE_REWARD_ENABLED", "1").lower() in {"1", "true", "yes"}
RERANK_ENABLED = os.getenv("INFERENCE_REWARD_RERANK", "1").lower() in {"1", "true", "yes"}
RERANK_CANDIDATES = int(os.getenv("INFERENCE_REWARD_RERANK_CANDIDATES", "3"))
HUMAN_PRIOR_WEIGHT = float(os.getenv("INFERENCE_HUMAN_REWARD_WEIGHT", "0.65"))
RLAIF_WEIGHT = float(os.getenv("INFERENCE_RLAIF_WEIGHT", "0.35"))
MIN_REWARD_SAMPLES = int(os.getenv("INFERENCE_REWARD_MIN_SAMPLES", "2"))


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def get_reward_summary(user_id: str) -> Dict[str, Any]:
    """Aggregate human + RLAIF reward history for a user."""
    if not user_id:
        return {"samples": 0, "avg_reward": 0.0, "positive": 0, "negative": 0}
    try:
        from backend.app.core.human_training import ensure_human_training_schema

        ensure_human_training_schema()
    except Exception:
        return {"samples": 0, "avg_reward": 0.0, "positive": 0, "negative": 0}

    conn = _connect()
    try:
        row = conn.execute(
            """SELECT COUNT(*), AVG(reward),
                      SUM(CASE WHEN reward > 0 THEN 1 ELSE 0 END),
                      SUM(CASE WHEN reward < 0 THEN 1 ELSE 0 END)
            FROM human_labels WHERE user_id=?""",
            (str(user_id),),
        ).fetchone()
    finally:
        conn.close()

    if not row or not row[0]:
        return {"samples": 0, "avg_reward": 0.0, "positive": 0, "negative": 0}
    return {
        "samples": int(row[0]),
        "avg_reward": round(float(row[1] or 0), 4),
        "positive": int(row[2] or 0),
        "negative": int(row[3] or 0),
    }


def _recent_high_reward_patterns(user_id: str, limit: int = 5) -> List[str]:
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT query, answer_preview, reward, rlaif_json
            FROM human_labels
            WHERE user_id=? AND reward > 0.5
            ORDER BY created_at DESC LIMIT ?""",
            (str(user_id), limit),
        ).fetchall()
    finally:
        conn.close()

    patterns: List[str] = []
    for q, a, reward, rlaif_raw in rows:
        if not a or len(a) < 40:
            continue
        rlaif = {}
        try:
            rlaif = json.loads(rlaif_raw or "{}")
        except Exception:
            pass
        style_bits = []
        for key in ("clarity", "structure", "tone", "conciseness"):
            val = rlaif.get(key)
            if val is not None and float(val) >= 0.7:
                style_bits.append(key)
        hint = f"Q: {(q or '')[:120]} → preferred style: {', '.join(style_bits) or 'clear grounded answer'}"
        patterns.append(hint)
    return patterns


def _dpo_avoidance_hints(user_id: str, query: str, limit: int = 3) -> List[str]:
    """Surface rejected-answer patterns similar to the current query."""
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT query, rejected_answer, reward_delta
            FROM preference_pairs
            WHERE user_id=?
            ORDER BY created_at DESC LIMIT ?""",
            (str(user_id), limit * 3),
        ).fetchall()
    finally:
        conn.close()

    ql = (query or "").lower()
    hints: List[str] = []
    for q, rejected, delta in rows:
        if not rejected:
            continue
        q_l = (q or "").lower()
        overlap = bool(ql and q_l and (ql in q_l or q_l in ql or _token_overlap(ql, q_l) >= 2))
        if not overlap and len(hints) >= limit:
            continue
        snippet = re.sub(r"\s+", " ", rejected)[:180]
        hints.append(f"Avoid answers like: {snippet}")
        if len(hints) >= limit:
            break
    return hints


def _token_overlap(a: str, b: str) -> int:
    ta = set(re.findall(r"[a-z0-9]+", a))
    tb = set(re.findall(r"[a-z0-9]+", b))
    return len(ta & tb)


def build_reward_prompt_block(
    user_id: str,
    query: str = "",
    mode: str = "knowledge_base",
) -> str:
    """Inject RLHF/RLAIF guidance into synthesis system prompt."""
    if not ENABLED or not user_id:
        return ""

    summary = get_reward_summary(user_id)
    if summary["samples"] < MIN_REWARD_SAMPLES:
        return ""

    parts: List[str] = [
        "LEARNED REWARD GUIDANCE (from user feedback — style and format only, never override documents):"
    ]
    if summary["avg_reward"] < 0:
        parts.append(
            "- Recent feedback trend is negative: be more precise, cite sections clearly, avoid speculation."
        )
    elif summary["avg_reward"] > 0.5:
        parts.append(
            "- Recent feedback trend is positive: maintain clear structure and document-grounded tone."
        )

    for hint in _recent_high_reward_patterns(user_id):
        parts.append(f"- {hint}")

    for avoid in _dpo_avoidance_hints(user_id, query):
        parts.append(f"- {avoid}")

    if mode:
        parts.append(f"- Active mode: {mode}.")
    return "\n".join(parts)


def should_rerank_candidates(user_id: str) -> bool:
    if not ENABLED or not RERANK_ENABLED or not user_id:
        return False
    summary = get_reward_summary(user_id)
    return summary["samples"] >= MIN_REWARD_SAMPLES and summary["negative"] >= 1


def _similarity_bonus(query: str, answer: str, preferred_answers: List[str]) -> float:
    if not preferred_answers or not answer:
        return 0.0
    q_tokens = set(re.findall(r"[a-z0-9]+", (query or "").lower()))
    a_tokens = set(re.findall(r"[a-z0-9]+", answer.lower()))
    best = 0.0
    for pref in preferred_answers:
        p_tokens = set(re.findall(r"[a-z0-9]+", pref.lower()))
        if not p_tokens:
            continue
        overlap = len(a_tokens & p_tokens) / max(len(p_tokens), 1)
        q_overlap = len(q_tokens & p_tokens) / max(len(q_tokens), 1) if q_tokens else 0
        best = max(best, overlap * 0.6 + q_overlap * 0.4)
    return min(1.0, best)


def compute_composite_reward(
    user_id: str,
    query: str,
    answer: str,
    *,
    rlaif: Optional[Dict[str, Any]] = None,
    membership: str = "Free",
) -> float:
    """Score a candidate answer using human history + optional live RLAIF."""
    if not answer or len(answer.strip()) < 20:
        return -1.0

    summary = get_reward_summary(user_id)
    human_prior = max(-1.0, min(1.0, float(summary.get("avg_reward") or 0)))

    conn = _connect()
    preferred: List[str] = []
    try:
        rows = conn.execute(
            """SELECT answer_preview FROM human_labels
            WHERE user_id=? AND reward > 0.5 AND answer_preview IS NOT NULL
            ORDER BY created_at DESC LIMIT 5""",
            (str(user_id),),
        ).fetchall()
        preferred = [r[0] for r in rows if r and r[0]]
    finally:
        conn.close()

    sim_bonus = _similarity_bonus(query, answer, preferred)

    rlaif_score = 0.0
    if rlaif and rlaif.get("overall") is not None:
        rlaif_score = float(rlaif["overall"])
    elif ENABLED and len(answer) >= 40:
        try:
            from backend.app.core.human_training import rlaif_score_style_only

            live = rlaif_score_style_only(
                query, answer, user_id=str(user_id), membership=membership
            )
            if live and live.get("overall") is not None:
                rlaif_score = float(live["overall"])
        except Exception:
            pass

    composite = (
        human_prior * HUMAN_PRIOR_WEIGHT
        + rlaif_score * RLAIF_WEIGHT
        + sim_bonus * 0.25
    )
    return round(composite, 4)


def select_best_candidate(
    user_id: str,
    query: str,
    candidates: List[str],
    *,
    membership: str = "Free",
) -> Tuple[str, Dict[str, Any]]:
    """Pick highest-reward candidate; optionally store inference preference pair."""
    if not candidates:
        return "", {"skipped": True}
    if len(candidates) == 1:
        return candidates[0], {"scores": [compute_composite_reward(user_id, query, candidates[0], membership=membership)]}

    scored: List[Tuple[str, float]] = []
    for cand in candidates:
        scored.append((cand, compute_composite_reward(user_id, query, cand, membership=membership)))
    scored.sort(key=lambda x: x[1], reverse=True)
    best, best_score = scored[0]
    worst = scored[-1][0] if scored[-1][1] < best_score - 0.05 else ""

    meta = {
        "reranked": True,
        "best_score": best_score,
        "scores": [s for _, s in scored],
        "candidate_count": len(candidates),
    }

    if worst and best and worst != best and best_score > 0.3:
        try:
            from backend.app.core.human_training import record_preference_pair

            record_preference_pair(
                user_id,
                query=query,
                chosen=best[:2000],
                rejected=worst[:2000],
                source="inference_rerank",
            )
            meta["preference_pair_recorded"] = True
        except Exception as exc:
            logger.debug("inference preference pair skipped: %s", exc)

    return best, meta


def enrich_profile_rewards(profile: Any, user_id: str, query: str = "") -> None:
    """Attach reward block to intent profile signals."""
    if not user_id or not profile:
        return
    if (profile.signals or {}).get("kb_no_learning_inject"):
        return
    try:
        from backend.app.core.kb_strict_policy import kb_learning_inject_allowed

        if not kb_learning_inject_allowed():
            return
    except ImportError:
        pass
    block = build_reward_prompt_block(
        user_id,
        query=query or (profile.signals or {}).get("original_query", ""),
        mode=str((profile.signals or {}).get("mode") or "knowledge_base"),
    )
    if block:
        profile.signals = dict(profile.signals or {})
        profile.signals["reward_block"] = block
