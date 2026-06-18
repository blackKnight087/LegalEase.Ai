"""
Post-generation answer validation — reject hallucinations and wrong-law drift.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from kb_query_types import QueryType
from kb_rag_decision import extract_query_sections
from kb_response_state import KB_NOT_FOUND_MESSAGE, contains_not_found_phrase

_CLAIM_SECTION_RE = re.compile(
    r"\b(?:section|ipc|bns|crpc|article)\s+(\d{1,4}[a-z]?)\b", re.I
)
_CLAIM_AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)\s*[\d,]+(?:\.\d+)?|\b\d{1,3}(?:,\d{3})+\s*(?:rupees|lakh|crore)\b",
    re.I,
)
_CLAIM_DATE_RE = re.compile(
    r"\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
    re.I,
)
_CLAIM_PERCENT_RE = re.compile(r"\b\d{1,3}(?:\.\d+)?\s*%")
_CLAIM_DEADLINE_RE = re.compile(
    r"\b\d+\s+(?:days?|months?|years?)\s+(?:from|after|within)\b", re.I
)


def _answer_mentions_section(answer: str, section: str) -> bool:
    if not section:
        return True
    al = (answer or "").lower()
    sec = section.lower()
    return bool(
        re.search(rf"\b{re.escape(sec)}\b", al)
        or re.search(rf"\bsection\s*{re.escape(sec)}\b", al, re.I)
        or re.search(rf"\bipc\s*{re.escape(sec)}\b", al, re.I)
        or re.search(rf"\bbns\s*{re.escape(sec)}\b", al, re.I)
    )


def _chunks_support_answer(chunks: List[Dict], answer: str) -> bool:
    if not chunks:
        return False
    joined = "\n".join((c.get("content") or "") for c in chunks[:8]).lower()
    al = (answer or "").lower()
    if len(joined) < 50:
        return False
    # Section-specific: chunk must mention the section from the answer
    for m in re.finditer(r"\b(?:ipc|bns|section)\s+(\d{1,4}[a-z]?)\b", al, re.I):
        sec = m.group(1).lower()
        if re.search(
            rf"\b(?:section\s*{re.escape(sec)}|ipc\s*{re.escape(sec)}|bns\s*{re.escape(sec)})\b",
            joined,
            re.I,
        ):
            return True
    tokens = set(re.findall(r"[a-z]{5,}", joined)) - {
        "section", "indian", "penal", "punishment", "offence", "offense",
    }
    hits = sum(1 for t in list(tokens)[:40] if t in al)
    return hits >= 2


def _context_blob(chunks: List[Dict]) -> str:
    return "\n".join((c.get("content") or "") for c in chunks[:10]).lower()


def extract_factual_claims(answer: str) -> Dict[str, List[str]]:
    """Numbers, dates, amounts, sections cited in the answer."""
    text = answer or ""
    claims: Dict[str, List[str]] = {
        "sections": [],
        "amounts": [],
        "dates": [],
        "percents": [],
        "deadlines": [],
    }
    for m in _CLAIM_SECTION_RE.finditer(text):
        sec = m.group(1).lower()
        if sec not in claims["sections"]:
            claims["sections"].append(sec)
    for m in _CLAIM_AMOUNT_RE.finditer(text):
        val = m.group(0).strip().lower()
        if val not in claims["amounts"]:
            claims["amounts"].append(val)
    for m in _CLAIM_DATE_RE.finditer(text):
        val = m.group(0).strip().lower()
        if val not in claims["dates"]:
            claims["dates"].append(val)
    for m in _CLAIM_PERCENT_RE.finditer(text):
        val = m.group(0).strip().lower()
        if val not in claims["percents"]:
            claims["percents"].append(val)
    for m in _CLAIM_DEADLINE_RE.finditer(text):
        val = m.group(0).strip().lower()
        if val not in claims["deadlines"]:
            claims["deadlines"].append(val)
    return claims


def verify_claims_grounded(answer: str, chunks: List[Dict]) -> Tuple[bool, str]:
    """
    Sentence/claim-level grounding: reject unsupported sections, amounts, dates.
    """
    if not chunks or not (answer or "").strip():
        return True, "no_claims"
    ctx = _context_blob(chunks)
    claims = extract_factual_claims(answer)
    for sec in claims["sections"]:
        if not re.search(
            rf"\b(?:section\s*{re.escape(sec)}|ipc\s*{re.escape(sec)}|bns\s*{re.escape(sec)})\b",
            ctx,
            re.I,
        ):
            return False, f"unsupported_section:{sec}"
    for amt in claims["amounts"]:
        digits = re.sub(r"[^\d]", "", amt)
        if digits and digits not in re.sub(r"[^\d]", "", ctx):
            return False, f"unsupported_amount:{amt[:24]}"
    for dt in claims["dates"]:
        if dt not in ctx and not any(part in ctx for part in dt.split() if len(part) > 2):
            return False, f"unsupported_date:{dt[:24]}"
    for pct in claims["percents"]:
        if pct.replace(" ", "") not in ctx.replace(" ", ""):
            num = re.search(r"\d", pct)
            if num and num.group(0) not in ctx:
                return False, f"unsupported_percent:{pct}"
    for dl in claims["deadlines"]:
        nums = re.findall(r"\d+", dl)
        if nums and not all(n in ctx for n in nums):
            return False, f"unsupported_deadline:{dl[:24]}"

    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", answer)
        if len(s.strip()) > 40 and re.search(r"[a-z]{4,}", s, re.I)
    ]
    if len(sentences) > 1:
        unsupported = 0
        for sent in sentences[:12]:
            words = set(re.findall(r"[a-z]{5,}", sent.lower()))
            words -= {"section", "indian", "penal", "punishment", "offence", "offense", "therefore"}
            if not words:
                continue
            hits = sum(1 for w in list(words)[:12] if w in ctx)
            if hits < max(1, len(words) // 4):
                unsupported += 1
        if unsupported >= 2:
            return False, "unsupported_sentences"
    return True, "claims_ok"


def _wrong_law_in_answer(answer: str, query: str, query_type: QueryType) -> bool:
    ql = (query or "").lower()
    al = (answer or "").lower()
    wants_ipc = bool(re.search(r"\b(ipc|indian penal code)\b", ql)) or query_type == QueryType.LIST_EXTRACTION
    if not wants_ipc:
        return False
    has_ipc = bool(re.search(r"\b(ipc|indian penal code|section\s+\d{2,3})\b", al))
    has_cyber_only = bool(
        re.search(r"\b(66c|66d|it act|cyber law|information technology)\b", al)
    ) and not has_ipc
    return has_cyber_only


def validate_answer(
    answer: str,
    query: str,
    chunks: List[Dict],
    query_type: QueryType,
    *,
    profile_sections: Optional[List[str]] = None,
    entity_count: int = 0,
) -> Tuple[bool, str]:
    """
    Returns (ok, reason). If not ok, caller should retry retrieval or return NOT_FOUND.
    """
    text = (answer or "").strip()
    if not text or contains_not_found_phrase(text):
        return True, "not_found_ok"

    if _is_low_info(text):
        return False, "empty_or_garbage"

    from kb_retrieval import extract_comparison_sections, is_comparison_query

    sections = profile_sections or extract_query_sections(query)
    if is_comparison_query(query):
        cmp_secs = extract_comparison_sections(query)
        if len(cmp_secs) >= 2:
            sections = cmp_secs

    if query_type in {QueryType.SUMMARY, QueryType.LIST_EXTRACTION, QueryType.TOPIC_QUERY}:
        if entity_count >= 3:
            return True, "ok_entities"
        listed = len(re.findall(r"\b(?:IPC|IT Act|Section)\s+[\dA-Z]+", text, re.I))
        if entity_count >= 4 and listed < 3:
            return False, "summary_too_few_offences"
        if entity_count >= 2 and listed >= 2:
            return True, "ok_summary"

    if query_type == QueryType.COMPARISON and len(sections) >= 2:
        missing = [s for s in sections if not _answer_mentions_section(text, s)]
        if missing:
            return False, f"comparison_missing_sections:{','.join(missing)}"

    if query_type in {
        QueryType.SECTION_LOOKUP,
        QueryType.SECTION_EXPLANATION,
        QueryType.PUNISHMENT_QUERY,
        QueryType.PAGE_LOOKUP,
    } and sections:
        try:
            from rag import _chunk_matches_strict_section

            if not any(
                _chunk_matches_strict_section(c.get("content", ""), sections[0])
                for c in (chunks or [])[:8]
            ):
                return False, f"wrong_section_chunks:{sections[0]}"
        except ImportError:
            pass
        if not _answer_mentions_section(text, sections[0]):
            return False, f"missing_section:{sections[0]}"
        wrong_secs = re.findall(r"\bipc\s*(?:section\s*)?(\d{1,4}[a-z]?)\b", text, re.I)
        if wrong_secs and sections[0].lower() not in {w.lower() for w in wrong_secs}:
            if len(wrong_secs) == 1 and wrong_secs[0].lower() != sections[0].lower():
                return False, f"answer_wrong_section:{wrong_secs[0]}"
        try:
            from backend.app.services.legal_query_parser import answer_satisfies_section_query

            if not answer_satisfies_section_query(query, text):
                return False, "law_replacement_only"
        except ImportError:
            pass

    if query_type == QueryType.LIST_EXTRACTION:
        if _wrong_law_in_answer(text, query, query_type):
            return False, "wrong_law_it_act_only"
        ipc_hits = len(re.findall(r"\b(?:IPC|Section)\s+\d{2,3}", text, re.I))
        if ipc_hits == 0 and re.search(r"\b(ipc|all sections)\b", query, re.I):
            return False, "list_no_ipc_sections"

    if query_type == QueryType.LAW_REPLACEMENT:
        try:
            from kb_legal_query_rewrite import chunk_matches_law_query

            if any(chunk_matches_law_query(c.get("content", ""), query) for c in chunks[:8]):
                if re.search(r"\b(ipc|bns|bnss|bsa|crpc|penal code|sanhita|sakshya)\b", text, re.I):
                    return True, "ok_law_replacement"
        except Exception:
            pass
        if re.search(r"\b(ipc|bns|bnss|bsa|crpc)\b", text, re.I):
            return True, "ok_law_replacement_keywords"

    if _wrong_law_in_answer(text, query, query_type):
        return False, "wrong_law_drift"

    if not _chunks_support_answer(chunks, text):
        return False, "unsupported_by_chunks"

    claims_ok, claim_reason = verify_claims_grounded(text, chunks)
    if not claims_ok:
        return False, claim_reason

    try:
        from backend.app.core.kb_claim_audit import (
            answer_has_legal_definition_leak,
            grounding_score,
            is_statute_explanation_query,
        )

        if answer_has_legal_definition_leak(text, chunks):
            return False, "statute_definition_hallucination"
        if is_statute_explanation_query(query) and grounding_score(text, chunks) < 0.65:
            return False, "low_grounding_score"
    except ImportError:
        pass

    # Duplicate line detection
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) != len(set(lines)) and len(lines) > 4:
        dup_ratio = 1 - (len(set(lines)) / len(lines))
        if dup_ratio > 0.25:
            return False, "duplicate_lines"

    return True, "ok"


def _is_low_info(text: str) -> bool:
    normalized = text.strip().lower()
    if len(normalized) < 12:
        return True
    if normalized in {"{}", "[]", "null", "none"}:
        return True
    return len(re.findall(r"[A-Za-z0-9]", normalized)) < 8
