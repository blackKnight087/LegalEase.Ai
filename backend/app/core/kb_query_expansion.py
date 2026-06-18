"""
Query expansion for universal KB retrieval — improves recall on any document type.
"""
from __future__ import annotations

import re
from typing import List

from backend.app.core.universal_kb import is_statute_focused_query


def expand_query_for_retrieval(query: str, *, max_variants: int = 4) -> List[str]:
    """Return original query plus short variants for hybrid retrieval."""
    q = (query or "").strip()
    if not q:
        return []
    variants: List[str] = [q]
    ql = q.lower()

    if is_statute_focused_query(q):
        try:
            from kb_retrieval import build_section_retrieval_queries
            from kb_rag_decision import extract_query_sections

            secs = extract_query_sections(q)
            if secs:
                for eq in build_section_retrieval_queries(secs[:2], q)[:3]:
                    if eq not in variants:
                        variants.append(eq)
        except Exception:
            pass
        return variants[:max_variants]

    # Document / topic queries — add keyword-focused variants
    words = [w for w in re.findall(r"[A-Za-z0-9]{3,}", ql) if w not in _STOPWORDS]
    if len(words) >= 2:
        key_phrase = " ".join(words[:6])
        if key_phrase not in variants:
            variants.append(key_phrase)

    if "summarize" in ql or "summary" in ql:
        variants.append("main points key obligations terms conditions")
    if "obligation" in ql or "duty" in ql or "must" in ql:
        variants.append("obligations duties shall must party agreement")
    if "right" in ql or "article" in ql:
        variants.append("fundamental rights constitutional article equality liberty")
    if "punishment" in ql or "penalty" in ql:
        variants.append("punishment penalty sentence imprisonment fine maximum")

    try:
        from document_classifier import document_type_for_query

        dt = document_type_for_query(q)
        if dt == "constitutional":
            variants.append("fundamental rights constitution article")
        elif dt in ("contract", "nda", "agreement"):
            variants.append("parties agreement confidential termination indemnity")
        elif dt == "court_judgment":
            variants.append("court held petitioner respondent judgment ratio")
    except Exception:
        pass

    out: List[str] = []
    seen: set[str] = set()
    for v in variants:
        key = v.lower()[:80]
        if key not in seen:
            seen.add(key)
            out.append(v)
    return out[:max_variants]


_STOPWORDS = frozenset(
    {
        "what", "when", "where", "which", "explain", "define", "about", "under",
        "the", "and", "for", "from", "with", "this", "that", "your", "uploaded",
        "document", "documents", "tell", "describe", "please", "give", "does",
    }
)
