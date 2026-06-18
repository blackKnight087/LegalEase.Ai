"""
Layered KB retrieval — used when primary vector/section search returns too little.
Keeps answers grounded in the indexed docstore after re-index.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _dedupe_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    out: List[Dict[str, Any]] = []
    for c in chunks:
        key = (c.get("content") or "")[:100]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _keyword_docstore_hits(
    query: str,
    index_dir: Any,
    *,
    top_k: int = 10,
    document_scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    try:
        from rag import _keyword_fallback_docstore_only

        return _keyword_fallback_docstore_only(
            query,
            index_dir,
            original_query=query,
            top_k=top_k,
            document_scope=document_scope,
        ) or []
    except Exception as exc:
        logger.debug("keyword docstore rescue failed: %s", exc)
        return []


_CRIMINAL_SKIP = re.compile(
    r"\b(?:ipc|bns)\s*(?:section\s*)?\d{1,4}\b|transition chart|old laws vs new",
    re.I,
)


def _constitutional_docstore_hits(
    query: str,
    index_dir: Any,
    *,
    top_k: int = 10,
) -> List[Dict[str, Any]]:
    """Scan indexed chunks for constitutional rights text (no orchestrator import)."""
    hits: List[Dict[str, Any]] = []
    try:
        from pathlib import Path

        from rag import _load_docstore_only

        vs = _load_docstore_only(Path(index_dir))
        if not vs:
            return []
        doc_dict = getattr(getattr(vs, "docstore", None), "_dict", None) or {}
    except Exception:
        return []

    ql = (query or "").lower()
    needles = ["constitutional rights", "fundamental rights", "right to equality", "article 14"]
    if "equality" in ql:
        needles.extend(["right to equality", "article 14", "equality before law"])
    if "freedom" in ql:
        needles.extend(["right to freedom", "article 19"])
    if "religion" in ql:
        needles.extend(["right to religion", "article 25"])
    if "life" in ql or "liberty" in ql:
        needles.extend(["right to life", "article 21", "personal liberty"])

    seen: set[str] = set()
    for doc in doc_dict.values():
        content = getattr(doc, "page_content", None) or str(doc)
        if _CRIMINAL_SKIP.search(content or ""):
            continue
        cl = (content or "").lower()
        if not any(n in cl for n in needles):
            continue
        key = content[:120]
        if key in seen:
            continue
        seen.add(key)
        meta = dict(getattr(doc, "metadata", None) or {})
        hits.append(
            {
                "content": content,
                "metadata": meta,
                "final_score": 2.3,
                "hybrid_score": 2.3,
                "retrieval_mode": "constitutional_docstore",
            }
        )
    hits.sort(key=lambda c: -len(c.get("content") or ""))
    return hits[:top_k]


def _section_hits(
    query: str,
    index_dir: Any,
    *,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    try:
        from backend.app.core.universal_kb import is_statute_focused_query

        if not is_statute_focused_query(query):
            return []
    except Exception:
        pass
    try:
        from kb_rag_decision import extract_query_sections
        from rag import exact_section_lookup

        sections = extract_query_sections(query)
        if not sections:
            return []
        law = "BNS" if re.search(r"\bbns\b", query, re.I) else "IPC"
        return exact_section_lookup(index_dir, sections[:3], law=law, top_k=top_k) or []
    except Exception as exc:
        logger.debug("section rescue failed: %s", exc)
        return []


def robust_kb_retrieve(
    query: str,
    index_dir: Any,
    *,
    scope: Optional[Dict[str, Any]] = None,
    k: int = 10,
    constitutional: bool = False,
) -> List[Dict[str, Any]]:
    """
    Multi-strategy retrieval merge: vector → exact section → keyword docstore.
  Constitutional queries also scan the docstore for rights/article text.
    """
    merged: List[Dict[str, Any]] = []
    scope = scope or {}

    search_q = query
    if constitutional:
        try:
            from backend.app.core.constitutional_concept_map import expand_constitutional_query

            search_q = expand_constitutional_query(query)
        except Exception:
            pass

    if not constitutional:
        try:
            from rag import query_kb

            vector_hits = query_kb(
                search_q,
                k=max(k, 8),
                index_dir=index_dir,
                document_scope=scope if scope.get("strict") else None,
            )
            merged.extend(vector_hits or [])
        except Exception as exc:
            logger.debug("robust vector pass failed: %s", exc)

    if constitutional:
        merged.extend(_constitutional_docstore_hits(search_q, index_dir, top_k=k))

    if not constitutional:
        try:
            from backend.app.core.universal_kb import is_statute_focused_query

            if is_statute_focused_query(query):
                merged.extend(_section_hits(query, index_dir, top_k=k))
        except Exception:
            merged.extend(_section_hits(query, index_dir, top_k=k))
    merged.extend(
        _keyword_docstore_hits(query, index_dir, top_k=k, document_scope=scope or None)
    )

    merged = _dedupe_chunks(merged)
    if constitutional and merged:
        try:
            from backend.app.core.legal_domain_router import LegalDomain, route_legal_domain
            from backend.app.core.legal_domain_router import filter_chunks_for_domain

            merged = filter_chunks_for_domain(merged, route_legal_domain(query))
        except Exception:
            merged = [
                c
                for c in merged
                if not re.search(r"\bipc\s+section\s+\d", (c.get("content") or ""), re.I)
            ]
    merged = _dedupe_chunks(merged)
    if scope.get("strict") and merged:
        try:
            from backend.app.core.kb_doc_scope import filter_chunks_by_scope

            scoped = filter_chunks_by_scope(merged, scope)
            if scoped:
                merged = scoped
        except Exception:
            pass

    return merged[: max(k, 10)]
