"""Docstore case lookup — shared by orchestrator, lock rescue, and cascaded retrieval."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List

from backend.app.core.kb_case_context_lock import normalize_case_query


def lookup_case_chunks_by_query(
    index_dir: Any,
    query: str,
    *,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    """Scan docstore for case narratives matching party/topic needles."""
    from backend.app.core.case_entity_resolver import (
        chunk_matches_case,
        extract_case_block,
        extract_case_needles,
    )

    clean_q = normalize_case_query(query)
    needles = extract_case_needles(clean_q)
    if not needles:
        return []

    try:
        from rag import _load_docstore_only
    except ImportError:
        return []

    try:
        view = _load_docstore_only(Path(index_dir))
    except Exception:
        view = None
    if view is None:
        return []

    hits: List[Dict[str, Any]] = []
    for doc_id in view.index_to_docstore_id.values():
        try:
            doc = view.docstore.search(doc_id)
        except Exception:
            continue
        content = (getattr(doc, "page_content", None) or "").strip()
        if not content:
            continue
        hc = {
            "content": content,
            "metadata": dict(getattr(doc, "metadata", None) or {}),
            "final_score": 0.5,
            "hybrid_score": 0.5,
        }
        if not chunk_matches_case(hc, needles):
            continue
        isolated = extract_case_block(content, needles)
        try:
            from backend.app.core.case_narrative_engine import is_faq_or_boilerplate

            if is_faq_or_boilerplate(isolated):
                continue
        except ImportError:
            if "(cid:127)" in isolated:
                continue
        score = 0.92
        primary = [n for n in needles if n not in ("case",) and len(n) > 4]
        if primary and all(n in isolated.lower() for n in primary[:1]):
            score = 1.25
        if re.search(r"\bcase\s+\d+:", isolated, re.I):
            score += 0.15
        hits.append(
            {
                "content": isolated or content,
                "metadata": hc["metadata"],
                "final_score": score,
                "hybrid_score": score,
                "retrieval_mode": "case_docstore_lookup",
            }
        )
    hits.sort(key=lambda c: -float(c.get("final_score", 0)))
    return hits[:top_k]
