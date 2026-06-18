"""
Layered retrieval coordinator — semantic first, entity rerank, keyword fallback.

Used by the legal orchestrator after document scoping. Does not hardcode case names.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_K = 12
_RERANK_TOP = 8


def _entity_rerank_score(chunk: Dict[str, Any], needles: List[str], topic_terms: List[str]) -> float:
    body = (chunk.get("content") or "").lower()
    meta = chunk.get("metadata") or {}
    fn = str(meta.get("filename") or "").lower()
    base = float(chunk.get("final_score") or chunk.get("score") or chunk.get("hybrid_score") or 0.0)
    bonus = 0.0
    for n in needles:
        nl = n.lower()
        if len(nl) >= 3 and nl in body:
            bonus += 1.8
        if nl in fn:
            bonus += 0.5
    for t in topic_terms:
        if len(t) >= 4 and t in body:
            bonus += 0.4
    return base + bonus


def _retrieval_confidence(chunks: List[Dict[str, Any]], needles: List[str]) -> float:
    if not chunks:
        return 0.0
    top = float(chunks[0].get("final_score") or chunks[0].get("score") or 0.0)
    body = (chunks[0].get("content") or "").lower()
    ent_hits = sum(1 for n in needles if n.lower() in body)
    return min(1.0, top * 0.15 + ent_hits * 0.25 + (0.2 if len(chunks) >= 3 else 0))


def coordinated_retrieve(
    query: str,
    index_dir: Any,
    *,
    scope: Optional[Dict[str, Any]] = None,
    user_id: str = "",
    k: int = _DEFAULT_K,
    base_chunks: Optional[List[Dict[str, Any]]] = None,
    mode: str = "",
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Run layered retrieval: use base_chunks if provided, else universal path;
    entity rerank; keyword fallback when confidence is low.
    """
    scope = dict(scope or {})
    diag: Dict[str, Any] = {
        "query": (query or "")[:200],
        "mode": mode,
        "stages": [],
        "scope_reason": scope.get("reason"),
    }

    needles: List[str] = []
    topic_terms: List[str] = []
    try:
        from backend.app.core.case_entity_resolver import extract_entity_needles

        needles = extract_entity_needles(query)
    except Exception:
        pass
    try:
        from backend.app.core.kb_context_resolver import extract_query_signals

        sig = extract_query_signals(query)
        topic_terms = list(sig.get("tokens") or [])[:12]
    except Exception:
        topic_terms = [
            w.lower()
            for w in re.findall(r"[A-Za-z]{4,}", query or "")
            if w.lower() not in {"what", "when", "where", "explain", "document"}
        ][:12]

    diag["entities"] = needles[:8]
    diag["topic_terms"] = topic_terms[:8]

    chunks: List[Dict[str, Any]] = list(base_chunks or [])

    if not chunks:
        try:
            from backend.app.core.universal_kb import universal_retrieve

            chunks = universal_retrieve(query, index_dir, scope=scope, k=k)
            diag["stages"].append("semantic_universal")
            diag["mode"] = mode or "coordinated_semantic"
        except Exception as exc:
            logger.debug("coordinated semantic failed: %s", exc)
            chunks = []

    if needles and chunks:
        chunks = sorted(
            chunks,
            key=lambda c: _entity_rerank_score(c, needles, topic_terms),
            reverse=True,
        )
        diag["stages"].append("entity_rerank")

    conf = _retrieval_confidence(chunks, needles)
    diag["confidence"] = round(conf, 3)

    if conf < 0.35 or len(chunks) < 2:
        try:
            from backend.app.core.kb_doc_scope import retrieve_scoped_docstore_chunks

            kw = retrieve_scoped_docstore_chunks(
                query, index_dir, scope, top_k=k
            )
            if kw:
                seen = {(c.get("content") or "")[:80] for c in chunks}
                for c in kw:
                    key = (c.get("content") or "")[:80]
                    if key and key not in seen:
                        chunks.append(c)
                        seen.add(key)
                diag["stages"].append("keyword_fallback")
                if needles:
                    chunks = sorted(
                        chunks,
                        key=lambda c: _entity_rerank_score(c, needles, topic_terms),
                        reverse=True,
                    )
        except Exception as exc:
            logger.debug("keyword fallback failed: %s", exc)

    # Deprioritize statute-definition chunks when query is witness/person focused
    if needles and not re.search(r"\b(?:ipc|bns|section)\s*\d", (query or ""), re.I):
        def _is_statute_definition(c: Dict[str, Any]) -> bool:
            b = (c.get("content") or "").lower()
            return bool(
                re.search(r"\bipc\s+section\s+\d{1,4}\b", b)
                and "punishment" in b
                and not any(n.lower() in b for n in needles)
            )

        non_statute = [c for c in chunks if not _is_statute_definition(c)]
        if non_statute:
            chunks = non_statute + [c for c in chunks if _is_statute_definition(c)]
            diag["stages"].append("statute_deprioritize")

    try:
        from backend.app.core.universal_kb import boost_chunks_by_doc_relevance

        chunks = boost_chunks_by_doc_relevance(chunks, query)
    except Exception:
        pass

    final = chunks[: max(_RERANK_TOP, min(k, 12))]
    diag["chunk_count"] = len(final)
    if final:
        diag["top_file"] = str((final[0].get("metadata") or {}).get("filename", ""))[:80]
        diag["top_score"] = float(
            final[0].get("final_score") or final[0].get("score") or 0
        )

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "H4",
            "kb_retrieval_coordinator.py:coordinated_retrieve",
            "coordinated_done",
            {
                "query": (query or "")[:80],
                "stages": diag.get("stages"),
                "confidence": diag.get("confidence"),
                "chunk_count": diag.get("chunk_count"),
                "top_file": diag.get("top_file"),
            },
            run_id="retrieval-v1",
        )
    except Exception:
        pass
    # endregion

    return final, diag
