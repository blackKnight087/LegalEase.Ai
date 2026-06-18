"""
Retrieval learning — adaptive query expansion + semantic pairs from human feedback.

Improves FAISS retrieval without Gemini writing answers:
  - thumbs-up: reinforce query→expansion patterns
  - thumbs-down: record failed patterns for rescue
  - semantic template mining from successful answers
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _extract_legal_tokens(text: str) -> List[str]:
    tokens: List[str] = []
    for m in re.finditer(r"\b(?:section|article|order|rule)\s*[\d\.]+[a-z]?\b", text or "", re.I):
        tokens.append(m.group(0).lower())
    for m in re.finditer(r"\b(?:ipc|bns|bnss|bsa|crpc|it act|companies act)\b", text or "", re.I):
        tokens.append(m.group(0).lower())
    return list(dict.fromkeys(tokens))[:8]


def build_semantic_expansion(query: str, answer_preview: str) -> str:
    """Build retrieval expansion from human-verified answer (tokens only, no prose injection)."""
    q = (query or "").strip()
    tokens = _extract_legal_tokens(f"{q} {answer_preview}")
    if not tokens:
        return ""
    return " ".join(tokens)


def learn_from_feedback(
    user_id: str,
    signal: str,
    *,
    query: str = "",
    answer_preview: str = "",
    mode: str = "knowledge_base",
) -> Dict[str, Any]:
    """Apply retrieval learning from human feedback."""
    from backend.app.core.adaptive_learning import normalize_query, teach_query_expansion

    result: Dict[str, Any] = {"expansion_taught": False, "neural_pair": False}
    q = (query or "").strip()
    if not q:
        return result

    qn = normalize_query(q)
    expansion = build_semantic_expansion(q, answer_preview)

    if signal in ("thumbs_up", "helpful", "verbal_positive", "copy") and expansion:
        teach_query_expansion(str(user_id), mode, qn, expansion, success_delta=3)
        result["expansion_taught"] = True
        result["expansion"] = expansion[:120]

        try:
            from backend.app.core.neural_finetuning import add_training_pair

            if answer_preview and len(answer_preview) >= 60:
                added = add_training_pair(
                    q,
                    answer_preview[:1200],
                    user_id=str(user_id),
                    source="retrieval_learning",
                )
                result["neural_pair"] = bool(added)
        except Exception as exc:
            result["neural_error"] = str(exc)[:80]

    elif signal in ("thumbs_down", "verbal_negative"):
        try:
            from backend.app.core.adaptive_learning import normalize_query
            from backend.app.core.database import connect_data_db

            qn = normalize_query(q)
            conn = connect_data_db()
            try:
                conn.execute(
                    "UPDATE adaptive_query_patterns SET fail_count = fail_count + 2 "
                    "WHERE COALESCE(user_id,'')=? AND query_norm=?",
                    (str(user_id), qn),
                )
                conn.commit()
            finally:
                conn.close()
            result["failure_recorded"] = True
        except Exception as exc:
            result["failure_error"] = str(exc)[:80]

    return result


def retrieval_learning_stats(user_id: str) -> Dict[str, Any]:
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.neural_finetuning import ensure_neural_tuning_schema, tuning_status

    ensure_learning_schema()
    ensure_neural_tuning_schema()
    from backend.app.core.database import connect_data_db

    conn = connect_data_db()
    expansions = 0
    try:
        row = conn.execute(
            """SELECT COUNT(*) FROM adaptive_query_patterns
            WHERE user_id=? AND success_count > 0""",
            (str(user_id),),
        ).fetchone()
        expansions = int(row[0] if row else 0)
    finally:
        conn.close()

    neural = tuning_status(str(user_id))
    return {
        "query_expansions": expansions,
        "neural_pairs": neural.get("total_pairs", 0),
        "unused_neural_pairs": neural.get("unused_pairs", 0),
    }
