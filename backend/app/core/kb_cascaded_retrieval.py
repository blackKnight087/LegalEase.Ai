"""
Cascaded KB retrieval — exact party/title → semantic → keyword → fuzzy.

Only return empty after all stages fail (unless min-accept score applies).
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

_DEFAULT_K = 12


def min_accept_score() -> float:
    raw = (os.getenv("RAG_MIN_ACCEPT_SCORE") or "0.50").strip()
    try:
        return max(0.0, min(float(raw), 1.0))
    except ValueError:
        return 0.50


def _chunk_score(c: Dict[str, Any]) -> float:
    return float(
        c.get("final_score") or c.get("hybrid_score") or c.get("score") or 0.0
    )


def apply_min_accept_guarantee(
    chunks: List[Dict[str, Any]],
    *,
    candidates: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """If top candidate meets min score, ensure at least one chunk is returned."""
    pool = list(chunks or [])
    if candidates:
        for c in candidates:
            key = (c.get("content") or "")[:80]
            if key and not any((p.get("content") or "")[:80] == key for p in pool):
                pool.append(c)
    if not pool:
        return []
    pool.sort(key=_chunk_score, reverse=True)
    top = pool[0]
    if _chunk_score(top) >= min_accept_score():
        return pool[: max(_DEFAULT_K, 8)]
    if _chunk_score(top) >= 0.35:
        return pool[:6]
    return list(chunks or [])[:3]


def lookup_paragraph_chunks(
    index_dir: Any,
    query: str,
    *,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    """Find docstore segments whose paragraphs contain query terms (in-document questions)."""
    from backend.app.core.kb_document_first import _query_terms

    terms = _query_terms(query)
    if len(terms) < 2:
        return []

    try:
        from rag import _load_docstore_only
    except ImportError:
        return []

    from pathlib import Path

    try:
        view = _load_docstore_only(Path(index_dir))
    except Exception:
        view = None
    if view is None:
        return []

    hits: List[tuple[float, Dict[str, Any]]] = []
    for doc_id in view.index_to_docstore_id.values():
        try:
            doc = view.docstore.search(doc_id)
        except Exception:
            continue
        content = (getattr(doc, "page_content", None) or "").strip()
        if not content:
            continue
        meta = dict(getattr(doc, "metadata", None) or {})
        for block in re.split(r"\n\s*\n", content):
            block = re.sub(r"\s+", " ", block).strip()
            if len(block) < 40:
                continue
            bl = block.lower()
            hit_count = sum(1 for t in terms if t in bl)
            if hit_count < max(1, (len(terms) + 1) // 2):
                continue
            score = 0.55 + 0.12 * hit_count
            if re.search(r"\bcase\s+\d+:", block, re.I):
                score += 0.2
            hits.append(
                (
                    score,
                    {
                        "content": block[:5000],
                        "metadata": meta,
                        "final_score": score,
                        "hybrid_score": score,
                        "retrieval_mode": "paragraph_lookup",
                    },
                )
            )
    hits.sort(key=lambda x: -x[0])
    return [c for _, c in hits[:top_k]]


def _fuzzy_docstore_scan(
    index_dir: Any,
    query: str,
    *,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Last resort: broad keyword scan on docstore."""
    try:
        from backend.app.core.kb_doc_scope import retrieve_scoped_docstore_chunks

        return retrieve_scoped_docstore_chunks(
            query, index_dir, {"strict": False}, top_k=top_k
        )
    except Exception:
        return []


def cascaded_retrieve(
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
    Stage 1: Party/title docstore exact
    Stage 2: Semantic (coordinated / base_chunks)
    Stage 3: Paragraph term match
    Stage 4: Keyword docstore fuzzy
    """
    scope = dict(scope or {})
    diag: Dict[str, Any] = {
        "query": (query or "")[:200],
        "stages": [],
        "mode": mode,
        "threshold_min_accept": min_accept_score(),
    }
    all_candidates: List[Dict[str, Any]] = []
    chunks: List[Dict[str, Any]] = []

    # Stage 1 — party / case title
    try:
        from backend.app.core.case_entity_resolver import extract_case_parties, is_case_style_query
        from backend.app.core.case_docstore_lookup import lookup_case_chunks_by_query
        from backend.app.core.case_topic_resolver import (
            extract_topic_case_needles,
            is_topic_case_query,
            lookup_topic_case_chunks,
        )

        if is_case_style_query(query):
            party_hits = lookup_case_chunks_by_query(index_dir, query, top_k=k)
            if party_hits:
                chunks = party_hits
                all_candidates.extend(party_hits)
                diag["stages"].append("party_docstore_exact")
        if is_topic_case_query(query) and not chunks:
            topics = extract_topic_case_needles(query)
            topic_hits = lookup_topic_case_chunks(index_dir, topics, top_k=k)
            if topic_hits:
                chunks = topic_hits
                all_candidates.extend(topic_hits)
                diag["stages"].append("topic_case_lookup")
        a, b = extract_case_parties(query)
        if a and b and not chunks:
            party_hits = lookup_case_chunks_by_query(index_dir, query, top_k=k)
            if party_hits:
                chunks = party_hits
                all_candidates.extend(party_hits)
                diag["stages"].append("party_names_docstore")
    except Exception:
        pass

    # Stage 2 — semantic / coordinator
    if base_chunks:
        seen = {(c.get("content") or "")[:80] for c in chunks}
        for c in base_chunks:
            key = (c.get("content") or "")[:80]
            if key and key not in seen:
                chunks.append(c)
                seen.add(key)
        all_candidates.extend(base_chunks)
        diag["stages"].append("base_chunks_merge")
    if not chunks or len(chunks) < 2:
        try:
            from backend.app.core.kb_retrieval_coordinator import coordinated_retrieve

            sem, coord_diag = coordinated_retrieve(
                query,
                index_dir,
                scope=scope,
                user_id=user_id,
                k=k,
                base_chunks=chunks or None,
                mode=mode or "cascaded",
            )
            diag["coordinator"] = coord_diag
            seen = {(c.get("content") or "")[:80] for c in chunks}
            for c in sem:
                key = (c.get("content") or "")[:80]
                if key and key not in seen:
                    chunks.append(c)
                    seen.add(key)
            all_candidates.extend(sem)
            if sem:
                diag["stages"].append("semantic_coordinated")
        except Exception:
            pass

    # Stage 3 — paragraph-level (in-document questions)
    if len(chunks) < 2:
        para = lookup_paragraph_chunks(index_dir, query, top_k=k)
        if para:
            seen = {(c.get("content") or "")[:80] for c in chunks}
            for c in para:
                key = (c.get("content") or "")[:80]
                if key and key not in seen:
                    chunks.append(c)
                    seen.add(key)
            all_candidates.extend(para)
            diag["stages"].append("paragraph_lookup")

    # Stage 4 — fuzzy docstore
    if not chunks:
        fuzzy = _fuzzy_docstore_scan(index_dir, query, top_k=k)
        if fuzzy:
            chunks = fuzzy
            all_candidates.extend(fuzzy)
            diag["stages"].append("fuzzy_docstore")

    chunks.sort(key=_chunk_score, reverse=True)
    diag["candidates_count"] = len(all_candidates)
    diag["top_score"] = _chunk_score(chunks[0]) if chunks else 0.0
    guaranteed = apply_min_accept_guarantee(chunks, candidates=all_candidates)
    if guaranteed:
        chunks = guaranteed[: max(k, 8)]
    elif chunks:
        chunks = chunks[:k]
    else:
        chunks = []

    diag["chunk_count"] = len(chunks)
    diag["candidates"] = [
        {
            "score": round(_chunk_score(c), 4),
            "source": str((c.get("metadata") or {}).get("filename", ""))[:60],
            "excerpt": (c.get("content") or "")[:100],
        }
        for c in all_candidates[:10]
    ]
    return chunks[: max(k, 8)], diag


def detect_potential_retrieval_failure(
    query: str,
    index_dir: Any,
    chunks: List[Dict[str, Any]],
) -> bool:
    """True when docstore contains query terms but pipeline returned no chunks."""
    if chunks:
        return False
    if not (query or "").strip() or index_dir is None:
        return False
    try:
        from rag import _load_docstore_only, _scan_docstore_generic
        from pathlib import Path

        view = _load_docstore_only(Path(index_dir))
        if view is None:
            return False
        hits = _scan_docstore_generic(view, query, top_k=3)
        return bool(hits)
    except Exception:
        return False
