"""
Strict KB retrieval decision tree — FOUND or NOT_FOUND, never both.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from kb_response_state import KB_NOT_FOUND_MESSAGE

logger = logging.getLogger(__name__)

MIN_RETRIEVAL_THRESHOLD = float(
    __import__("os").getenv("RAG_MIN_RETRIEVAL_THRESHOLD", "0.28")
)

_OFF_TOPIC_GENERAL_PATTERNS = (
    re.compile(r"\bcapital of\b", re.I),
    re.compile(r"\bpopulation of\b", re.I),
    re.compile(r"\bwho (?:is|was) the president of\b", re.I),
    re.compile(r"\bhow many countries\b", re.I),
    re.compile(r"\bwhat is the largest\b", re.I),
    re.compile(r"\bwho invented\b", re.I),
    re.compile(r"\bweather in\b", re.I),
)

_LEGAL_TOPIC_MARKERS = re.compile(
    r"\b(ipc|bns|crpc|bnss|section|article|court|case|witness|contract|statute|"
    r"fundamental|constitutional|punishment|bail|fir|petition|agreement|nda|"
    r"legal|law|judgment|hearing|evidence|plaintiff|defendant)\b",
    re.I,
)


def is_off_topic_general_knowledge(query: str) -> bool:
    """True for general-world questions that must not be answered from LLM memory in KB mode."""
    q = (query or "").strip()
    if not q:
        return False
    if _LEGAL_TOPIC_MARKERS.search(q):
        return False
    return any(p.search(q) for p in _OFF_TOPIC_GENERAL_PATTERNS)

_CRIMINAL_CONTAMINATION = re.compile(
    r"\b(ipc|bns|criminal conspiracy|unlawful assembly|rioting)\b",
    re.I,
)

# Type-specific floors — legal PDFs score lower due to OCR/chunking variance
_THRESHOLD_BY_TYPE = {
    "law_replacement": 0.22,
    "law_mapping": 0.22,
    "section_lookup": 0.25,
    "section_explanation": 0.25,
    "punishment_query": 0.25,
    "exact_identifier": 0.24,
    "comparison": 0.26,
    "follow_up": 0.26,
    "topic_query": 0.20,
    "summary": 0.20,
    "unknown": 0.20,
    "general": 0.20,
    "document_qa": 0.18,
}


def threshold_for_query(query: str, query_type: Optional[str] = None) -> float:
    """Adaptive retrieval threshold by query type; never block valid law-mapping hits."""
    qt = (query_type or "").lower()
    if qt in _THRESHOLD_BY_TYPE:
        return min(MIN_RETRIEVAL_THRESHOLD, _THRESHOLD_BY_TYPE[qt])
    try:
        from kb_legal_query_rewrite import is_law_replacement_query

        if is_law_replacement_query(query):
            return min(MIN_RETRIEVAL_THRESHOLD, 0.22)
    except Exception:
        pass
    try:
        from kb_retrieval import is_comparison_query

        if is_comparison_query(query):
            return min(MIN_RETRIEVAL_THRESHOLD, 0.26)
    except Exception:
        pass
    return MIN_RETRIEVAL_THRESHOLD

# Re-export for compatibility
NOT_FOUND_PHRASE = KB_NOT_FOUND_MESSAGE


def extract_query_sections(query: str) -> List[str]:
    q = (query or "").strip()
    found: List[str] = []
    for pat in (
        re.compile(r"\b(?:section|sec\.?)\s*(\d{1,4}[a-z]?)\b", re.I),
        re.compile(r"\b(?:ipc|bns|crpc)\s*(\d{1,4}[a-z]?)\b", re.I),
        re.compile(r"^(?:section|sec\.?)?\s*(\d{1,4}[a-z]?)$", re.I),
    ):
        for m in pat.finditer(q):
            found.append(m.group(1).lower())
    dedup: List[str] = []
    seen = set()
    for s in found:
        if s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup


def chunk_matches_section(content: str, section: str) -> bool:
    text = (content or "").lower()
    sec = section.lower()
    if re.search(rf"\bsection\s*{re.escape(sec)}\b", text):
        return True
    if re.search(
        rf"\b(?:ipc|bns|crpc|bnss|indian penal code)\s*(?:section\s*)?{re.escape(sec)}\b",
        text,
    ):
        return True
    if re.search(rf"\b{re.escape(sec)}\s*(?:ipc|bns)\b", text):
        return True
    if re.search(rf"\b{re.escape(sec)}\b", text) and re.search(
        r"\b(?:ipc|bns|section|penal code|offence|offense|punishment)\b", text
    ):
        return True
    return False


def best_chunk_score(chunks: List[Dict]) -> float:
    if not chunks:
        return 0.0
    scores = []
    for c in chunks:
        if "final_score" in c:
            scores.append(float(c.get("final_score", 0.0)))
        else:
            sc = float(c.get("score", 2.5))
            scores.append(max(0.0, 1.0 - sc))
    return max(scores) if scores else 0.0


def section_match_in_chunks(chunks: List[Dict], sections: List[str]) -> bool:
    if not sections:
        return False
    for ch in chunks[:6]:
        body = ch.get("content") or ""
        if any(chunk_matches_section(body, sec) for sec in sections):
            return True
    return False


def law_mapping_match_in_chunks(chunks: List[Dict], query: str) -> bool:
    try:
        from kb_query_types import is_section_focus_query

        if is_section_focus_query(query):
            return False
        from kb_legal_query_rewrite import chunk_matches_law_query

        return any(chunk_matches_law_query(ch.get("content", ""), query) for ch in chunks[:8])
    except Exception:
        return False


def _query_terms_in_chunk(query: str, chunk_text: str) -> bool:
    """Require substantive query terms in top chunk for general (non-section) questions."""
    q = (query or "").lower()
    body = (chunk_text or "").lower()
    if not q or not body:
        return False
    stop = {
        "what", "when", "where", "which", "explain", "define", "definition",
        "about", "under", "indian", "india", "legal", "law", "case", "simple",
        "language", "requirements", "requirement", "tell", "describe",
    }
    terms = [
        w.strip("?.!,;:'\"()[]")
        for w in q.split()
        if len(w) > 3 and w.lower() not in stop
    ]
    if len(terms) < 2:
        return True
    hits = sum(1 for t in terms if t in body)
    return hits >= max(1, len(terms) // 2)


def evaluate_retrieval(
    query: str,
    chunks: List[Dict],
    *,
    threshold: float = MIN_RETRIEVAL_THRESHOLD,
    entities: Optional[List[str]] = None,
    query_type: Optional[str] = None,
    extracted_count: int = 0,
) -> Tuple[bool, float, str, Dict[str, Any]]:
    from kb_retrieval import extract_comparison_sections, is_comparison_query

    sections = entities or extract_query_sections(query)
    if is_comparison_query(query):
        cmp_secs = extract_comparison_sections(query)
        if len(cmp_secs) >= 2:
            sections = cmp_secs

    debug: Dict[str, Any] = {
        "query": query,
        "chunk_count": len(chunks),
        "sections": sections,
        "threshold": threshold,
        "query_type": query_type,
    }

    if is_off_topic_general_knowledge(query):
        debug["decision"] = "NOT_FOUND"
        debug["reason"] = "off_topic_general_knowledge"
        _log_decision(debug)
        return False, best_chunk_score(chunks), "NOT_FOUND", debug

    if query_type == "entity_lookup" and chunks:
        from document_classifier import is_contract_family

        body = (chunks[0].get("content") or "")[:800]
        meta = chunks[0].get("metadata") or {}
        if is_contract_family(meta.get("document_type")) and not _CRIMINAL_CONTAMINATION.search(body):
            debug["decision"] = "FOUND"
            debug["reason"] = "entity_lookup_contract"
            _log_decision(debug)
            return True, best_chunk_score(chunks), "FOUND", debug

    if not chunks:
        if query_type == "entity_lookup":
            debug["decision"] = "NOT_FOUND"
            debug["reason"] = "entity_lookup_no_chunks"
            _log_decision(debug)
            return False, 0.0, "NOT_FOUND", debug
        if extracted_count >= 3:
            debug["decision"] = "FOUND"
            debug["reason"] = "entities_without_chunks"
            _log_decision(debug)
            return True, threshold, "FOUND", debug
        debug["decision"] = "NOT_FOUND"
        debug["reason"] = "no_chunks"
        _log_decision(debug)
        return False, 0.0, "NOT_FOUND", debug

    best = best_chunk_score(chunks)
    debug["best_score"] = round(best, 4)
    debug["top_excerpt"] = (chunks[0].get("content") or "")[:120].replace("\n", " ")

    if is_comparison_query(query) and chunks:
        try:
            from kb_compare_engine import extract_typed_entities, _entity_in_chunk

            typed = extract_typed_entities(query)
            if len(typed) >= 2:
                typed_matched = sum(
                    1
                    for ent in typed[:2]
                    if any(_entity_in_chunk(c.get("content", ""), ent) for c in chunks)
                )
                debug["typed_entities_matched"] = typed_matched
                if typed_matched >= 2:
                    debug["decision"] = "FOUND"
                    debug["reason"] = "typed_comparison_both"
                    _log_decision(debug)
                    return True, max(best, threshold), "FOUND", debug
                if typed_matched >= 1 and best >= 0.30 and len(typed) >= 2:
                    laws = {str(e.get("type", "")).upper() for e in typed[:2]}
                    if len(laws) >= 2:
                        debug["decision"] = "FOUND"
                        debug["reason"] = "typed_comparison_partial"
                        _log_decision(debug)
                        return True, max(best, threshold), "FOUND", debug
        except Exception:
            pass

    if extracted_count >= 3 and query_type in {
        "summary",
        "list_extraction",
        "topic_query",
    }:
        debug["decision"] = "FOUND"
        debug["reason"] = "document_entities"
        _log_decision(debug)
        return True, max(best, threshold), "FOUND", debug

    if any(str(c.get("source", "")) == "document_scan" for c in chunks[:12]):
        if len(chunks) >= 1 and (extracted_count >= 2 or best >= 0.35):
            debug["decision"] = "FOUND"
            debug["reason"] = "document_scan"
            _log_decision(debug)
            return True, max(best, threshold), "FOUND", debug

    if sections and not section_match_in_chunks(chunks, sections):
        qt = (query_type or "").lower()
        if qt in {
            "exact_identifier",
            "section_lookup",
            "section_explanation",
            "punishment_query",
            "page_lookup",
        }:
            if best >= max(threshold, 0.32) and any(
                re.search(rf"\b{re.escape(sec)}\b", c.get("content", ""), re.I)
                for c in chunks[:10]
                for sec in sections
            ):
                debug["decision"] = "FOUND"
                debug["reason"] = "section_number_in_high_score_chunk"
                _log_decision(debug)
                return True, best, "FOUND", debug
            debug["decision"] = "NOT_FOUND"
            debug["reason"] = "section_not_in_chunks"
            _log_decision(debug)
            return False, best, "NOT_FOUND", debug

    if len(sections) >= 2:
        matched = sum(
            1 for sec in sections[:6] if section_match_in_chunks(chunks, [sec])
        )
        debug["sections_matched"] = matched
        if matched >= 2:
            debug["decision"] = "FOUND"
            debug["reason"] = "comparison_all_sections"
            _log_decision(debug)
            return True, max(best, threshold), "FOUND", debug
        if matched == 1:
            try:
                from kb_compare_engine import extract_typed_entities

                typed = extract_typed_entities(query)
                if (
                    len(typed) >= 2
                    and typed[0].get("type") != typed[1].get("type")
                    and best >= 0.24
                ):
                    debug["decision"] = "FOUND"
                    debug["reason"] = "typed_comparison_partial"
                    _log_decision(debug)
                    return True, max(best, threshold), "FOUND", debug
            except Exception:
                pass
        if matched == 1:
            debug["decision"] = "NOT_FOUND"
            debug["reason"] = "comparison_incomplete"
            _log_decision(debug)
            return False, best, "NOT_FOUND", debug

    if sections and section_match_in_chunks(chunks, sections):
        debug["decision"] = "FOUND"
        debug["reason"] = "section_match"
        _log_decision(debug)
        return True, max(best, threshold), "FOUND", debug

    if law_mapping_match_in_chunks(chunks, query):
        debug["decision"] = "FOUND"
        debug["reason"] = "law_mapping_match"
        _log_decision(debug)
        return True, max(best, threshold), "FOUND", debug

    try:
        from kb_legal_query_rewrite import is_law_replacement_query

        if is_law_replacement_query(query) and best >= 0.22:
            debug["decision"] = "FOUND"
            debug["reason"] = "law_replacement_low_bar"
            _log_decision(debug)
            return True, max(best, threshold), "FOUND", debug
    except Exception:
        pass

    if best >= threshold:
        try:
            from backend.app.core.universal_kb import is_statute_focused_query

            statute_q = is_statute_focused_query(query)
        except Exception:
            statute_q = bool(sections)

        if sections and not section_match_in_chunks(chunks, sections) and statute_q:
            if best >= max(threshold, 0.32) and any(
                re.search(rf"\b{re.escape(sec)}\b", c.get("content", ""), re.I)
                for c in chunks[:10]
                for sec in sections
            ):
                debug["decision"] = "FOUND"
                debug["reason"] = "section_number_in_high_score_chunk"
                _log_decision(debug)
                return True, best, "FOUND", debug
            debug["decision"] = "NOT_FOUND"
            debug["reason"] = "score_without_section_match"
            _log_decision(debug)
            return False, best, "NOT_FOUND", debug
        if not sections and best < 0.45 and not _query_terms_in_chunk(query, chunks[0].get("content", "")):
            qt = (query_type or "").lower()
            topic_qt = qt in {
                "topic_query",
                "summary",
                "unknown",
                "general",
                "constitutional",
                "document_qa",
            }
            try:
                from backend.app.core.universal_kb import chunks_overlap_query

                if chunks_overlap_query(query, chunks):
                    debug["decision"] = "FOUND"
                    debug["reason"] = "document_term_overlap"
                    _log_decision(debug)
                    return True, best, "FOUND", debug
            except Exception:
                pass
            if topic_qt and best >= threshold:
                debug["decision"] = "FOUND"
                debug["reason"] = "topic_query_above_threshold"
                _log_decision(debug)
                return True, best, "FOUND", debug
            debug["decision"] = "NOT_FOUND"
            debug["reason"] = "weak_term_overlap"
            _log_decision(debug)
            return False, best, "NOT_FOUND", debug
        debug["decision"] = "FOUND"
        debug["reason"] = "score_above_threshold"
        _log_decision(debug)
        return True, best, "FOUND", debug

    if chunks and best >= 0.18:
        body = (chunks[0].get("content") or "")
        if len(body) > 50:
            debug["decision"] = "FOUND"
            debug["reason"] = "minimum_score_with_substantive_chunk"
            _log_decision(debug)
            return True, best, "FOUND", debug

    try:
        from backend.app.core.universal_kb import chunks_overlap_query, is_statute_focused_query

        if chunks and not is_statute_focused_query(query) and chunks_overlap_query(query, chunks):
            body = (chunks[0].get("content") or "")
            if len(body) > 40:
                debug["decision"] = "FOUND"
                debug["reason"] = "universal_overlap_substantive"
                _log_decision(debug)
                return True, max(best, 0.15), "FOUND", debug
    except Exception:
        pass

    debug["decision"] = "NOT_FOUND"
    debug["reason"] = "below_threshold"
    _log_decision(debug)
    return False, best, "NOT_FOUND", debug


def _log_decision(debug: Dict[str, Any]) -> None:
    try:
        from backend.app.core.kb_pipeline_log import kb_log

        kb_log(
            "RAG_DECISION",
            query=debug.get("query"),
            decision=debug.get("decision"),
            reason=debug.get("reason"),
            best_score=debug.get("best_score"),
            threshold=debug.get("threshold"),
            sections=debug.get("sections"),
            chunks=debug.get("chunk_count"),
            excerpt=debug.get("top_excerpt"),
        )
    except Exception:
        pass
    logger.info(
        "[KB RAG] Query=%r | Decision=%s | Score=%s | Threshold=%s | Sections=%s | Chunks=%s",
        debug.get("query"),
        debug.get("decision"),
        debug.get("best_score"),
        debug.get("threshold"),
        debug.get("sections"),
        debug.get("chunk_count"),
    )


def strip_false_not_found(text: str, chunks: List[Dict]) -> str:
    from kb_response_state import enforce_single_state

    return enforce_single_state(text, found=True) if chunks else text


def contains_not_found_phrase(text: str) -> bool:
    from kb_response_state import contains_not_found_phrase as _c

    return _c(text)
