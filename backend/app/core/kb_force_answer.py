"""
Guaranteed document-grounded KB answers when retrieval returned chunks.
Uses one scoped narrative segment — never dumps unrelated multi-case chunks.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

from backend.app.core.case_narrative_engine import (
    build_entity_document_answer,
    build_structured_case_answer,
    collect_text_from_chunks,
    filter_case_chunks,
    is_faq_or_boilerplate,
    select_best_case_segment,
)
from backend.app.core.case_entity_resolver import extract_case_needles


def _chunk_score(c: Dict[str, Any]) -> float:
    for key in ("final_score", "hybrid_score", "semantic_score"):
        if key in c:
            try:
                return float(c.get(key) or 0.0)
            except (TypeError, ValueError):
                pass
    sc = c.get("score")
    if sc is not None:
        try:
            return max(0.0, 1.0 - float(sc))
        except (TypeError, ValueError):
            pass
    return 0.0


def _query_terms(query: str) -> List[str]:
    stop = {
        "what", "when", "where", "which", "explain", "define", "about", "under",
        "indian", "india", "legal", "law", "the", "and", "for", "from", "with",
        "tell", "describe", "section", "article", "wife", "husband",
    }
    terms: List[str] = []
    for w in re.findall(r"[A-Za-z0-9]{3,}", (query or "").lower()):
        if w not in stop and w not in terms:
            terms.append(w)
    return terms[:12]


def _filter_answer_chunks(chunks: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    try:
        from kb_content_cleaner import is_index_meta_boilerplate
    except ImportError:
        is_index_meta_boilerplate = lambda _t: False  # noqa: E731

    ql = (query or "").lower()
    contract_q = bool(
        re.search(
            r"\b(termination|confidential|nda|agreement|disclosing party|receiving party|parties)\b",
            ql,
        )
    )
    out: List[Dict[str, Any]] = []
    for c in chunks:
        body = c.get("content") or ""
        if is_index_meta_boilerplate(body) or is_faq_or_boilerplate(body):
            continue
        if contract_q:
            bl = body.lower()
            if re.search(r"\bipc\s+section\s+\d", bl) and not re.search(
                r"\b(non[- ]?disclosure|disclosing party|confidential)\b",
                bl,
            ):
                continue
        out.append(c)
    return out or chunks


def guarantee_kb_answer(
    query: str,
    chunks: List[Dict[str, Any]],
    *,
    max_chars: int = 1400,
) -> str:
    """
    Build a minimal grounded answer — single case/contract segment, structured markdown.
    """
    if not chunks:
        return ""

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "PASTE",
            "kb_force_answer.py:guarantee_kb_answer",
            "entry",
            {"query": (query or "")[:80], "chunk_count": len(chunks)},
            run_id="anti-paste",
        )
    except Exception:
        pass
    # endregion

    entity_ans = build_entity_document_answer(query, chunks)
    if entity_ans and len(entity_ans.strip()) > 80:
        return entity_ans

    needles = extract_case_needles(query) or _query_terms(query)
    filtered = filter_case_chunks(_filter_answer_chunks(chunks, query), needles)
    combined = collect_text_from_chunks(filtered)
    if combined:
        narrative = select_best_case_segment(combined, needles, min_score=1.5)
        if narrative and len(narrative) > 80:
            structured = build_structured_case_answer(query, narrative)
            if structured:
                return structured[:max_chars]

    ranked = sorted(filtered or chunks, key=_chunk_score, reverse=True)
    for c in ranked[:2]:
        body = (c.get("content") or "").strip()
        if not body or is_faq_or_boilerplate(body):
            continue
        narrative = select_best_case_segment(body, needles, min_score=1.0)
        if narrative:
            meta = c.get("metadata") or {}
            fn = meta.get("filename") or meta.get("source_file") or "your document"
            title = "## Answer from your document"
            if re.search(r"\bvs\.?\b", narrative[:200], re.I):
                title = "## Case summary"
            return f"{title}\n\n{narrative[:max_chars]}\n\n**Source:** {fn}"

    return ""
