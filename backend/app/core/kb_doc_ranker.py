"""
Document-first ranking for multi-upload indexes.

Scores each indexed document before chunk retrieval to reduce cross-document leakage.
Memory-safe: samples at most one short preview per document from the docstore.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_PREVIEW_CHARS = 1200


def _preview_for_doc(index_dir: Any, doc_meta: Dict[str, str]) -> str:
    """First chunk text for a document (bounded)."""
    try:
        from pathlib import Path

        from rag import _load_docstore_only

        vs = _load_docstore_only(Path(index_dir))
        if not vs:
            return ""
        doc_dict = getattr(getattr(vs, "docstore", None), "_dict", None) or {}
        target_doc = (doc_meta.get("doc_id") or "").strip()
        target_file = (doc_meta.get("filename") or "").strip().lower()
        for doc in doc_dict.values():
            meta = getattr(doc, "metadata", None) or {}
            if target_doc and str(meta.get("doc_id") or "") == target_doc:
                return (getattr(doc, "page_content", None) or str(doc))[:_PREVIEW_CHARS]
            fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
            if target_file and (fn == target_file or target_file in fn):
                return (getattr(doc, "page_content", None) or str(doc))[:_PREVIEW_CHARS]
    except Exception as exc:
        logger.debug("doc preview failed: %s", exc)
    return ""


def score_document_for_query(
    query: str,
    doc: Dict[str, str],
    *,
    preview: str = "",
) -> float:
    """Higher = more likely source document for this query."""
    ql = (query or "").lower()
    score = 0.0
    fn = (doc.get("filename") or "").lower()
    dt = (doc.get("document_type") or "").lower()
    body = (preview or "").lower()
    combined = f"{fn} {dt} {body}"

    try:
        from backend.app.core.case_entity_resolver import extract_entity_needles

        for needle in extract_entity_needles(query):
            if needle in combined:
                score += 2.5
    except Exception:
        pass

    for term in re.findall(r"[A-Za-z]{4,}", ql):
        if term in combined:
            score += 0.6

    try:
        from backend.app.core.universal_kb import query_target_doc_types

        for hint in query_target_doc_types(query):
            if hint.lower() in dt or hint.lower() in fn:
                score += 1.2
    except Exception:
        pass

    try:
        from document_classifier import document_type_for_query

        wanted = document_type_for_query(query)
        if wanted and wanted == dt:
            score += 1.5
    except Exception:
        pass

    return score


def rank_documents_for_query(
    query: str,
    index_dir: Any,
    *,
    user_id: str = "",
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    Rank all documents in the index for the query.
    Returns [{doc_id, filename, document_type, score, rank}, ...].
    """
    from backend.app.core.kb_doc_scope import list_index_documents

    docs = list_index_documents(index_dir)
    if not docs:
        return []

    scored: List[Tuple[float, Dict[str, str]]] = []
    for doc in docs:
        preview = _preview_for_doc(index_dir, doc)
        s = score_document_for_query(query, doc, preview=preview)
        scored.append((s, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    out: List[Dict[str, Any]] = []
    for i, (s, doc) in enumerate(scored[: max(top_n, len(scored))]):
        if s <= 0 and i > 0:
            break
        out.append(
            {
                "doc_id": doc.get("doc_id") or "",
                "filename": doc.get("filename") or "",
                "document_type": doc.get("document_type") or "",
                "score": round(s, 3),
                "rank": i + 1,
            }
        )
    return out


def apply_document_ranking_to_scope(
    query: str,
    index_dir: Any,
    scope: Dict[str, Any],
    *,
    user_id: str = "",
    min_score_gap: float = 0.8,
) -> Dict[str, Any]:
    """
    Tighten scope when one document clearly wins (multi-doc indexes).
    """
    if scope.get("strict") or scope.get("doc_id") or scope.get("filename"):
        return scope

    ranked = rank_documents_for_query(query, index_dir, user_id=user_id, top_n=3)
    if len(ranked) < 2:
        return scope

    best = ranked[0]
    second = ranked[1] if len(ranked) > 1 else {"score": 0.0}
    if best["score"] <= 0:
        return scope

    gap = float(best["score"]) - float(second.get("score") or 0)
    if gap >= min_score_gap or (best["score"] >= 2.5 and gap >= 0.5):
        scope = dict(scope)
        scope.update(
            {
                "doc_id": best.get("doc_id") or "",
                "filename": best.get("filename") or "",
                "document_type": best.get("document_type") or scope.get("document_type") or "",
                "strict": True,
                "reason": "document_rank_winner",
                "document_rank": ranked,
            }
        )
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "H3",
                "kb_doc_ranker.py:apply_document_ranking_to_scope",
                "scoped_by_doc_rank",
                {
                    "query": (query or "")[:80],
                    "winner": (best.get("filename") or "")[:50],
                    "score": best.get("score"),
                    "gap": round(gap, 2),
                },
                run_id="retrieval-v1",
            )
        except Exception:
            pass
        # endregion
    elif ranked:
        scope = dict(scope)
        scope["document_rank"] = ranked

    return scope
