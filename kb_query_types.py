"""
Pre-retrieval query type classification for LegalEase KB.
Drives retrieval depth, document-wide scan, metadata filters, and answer shape.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from conversation_context import extract_sections_from_text
from kb_retrieval import extract_comparison_sections


class QueryType(str, Enum):
    ENTITY_LOOKUP = "entity_lookup"
    SECTION_LOOKUP = "section_lookup"
    SECTION_EXPLANATION = "section_explanation"
    COMPARISON = "comparison"
    SUMMARY = "summary"
    LIST_EXTRACTION = "list_extraction"
    PUNISHMENT_QUERY = "punishment_query"
    FOLLOW_UP = "follow_up"
    PAGE_LOOKUP = "page_lookup"
    TOPIC_QUERY = "topic_query"
    LAW_REPLACEMENT = "law_replacement"
    UNKNOWN = "unknown"


_COMPARE_RE = re.compile(
    r"\b(compare|comparison|difference|differences|differentiate|distinguish|between)\b",
    re.I,
)
_SUMMARY_RE = re.compile(
    r"\b(summarize|summarise|summary|overview|gist|in brief|key points|main points)\b",
    re.I,
)
_LIST_RE = re.compile(
    r"\b(list all|list the|enumerate|all\s+(?:ipc|bns|criminal)?\s*(?:sections?|offences?|offenses?|topics?)|"
    r"which\s+sections?|what\s+sections?)\b",
    re.I,
)
_PUNISH_RE = re.compile(
    r"\b(punishment|penalty|sentence|imprisonment|fine|maximum|minimum)\b",
    re.I,
)
_PAGE_RE = re.compile(
    r"\b(which page|what page|page number|on which page|page\s+\d+)\b",
    re.I,
)
_TOPIC_RE = re.compile(
    r"\b(topics?\s+(?:are\s+)?(?:discussed|covered)|themes?|subjects?\s+covered|what\s+topics?)\b",
    re.I,
)
_EXPLAIN_RE = re.compile(r"\b(explain|describe|walk me through|break down)\b", re.I)
_LOOKUP_RE = re.compile(r"\b(what is|what's|define|meaning of)\b", re.I)
_FOLLOW_UP_RE = re.compile(
    r"\b(explain it|simplify|more detail|elaborate|that section|this section|"
    r"the same|above|earlier|what about|also|does it|it carry|simply)\b",
    re.I,
)
_MULTI_NUM_RE = re.compile(
    r"\b(\d{1,4}[a-z]?)\s*(?:,|and|&|or)\s*(\d{1,4}[a-z]?)",
    re.I,
)
_MULTI_NUM_SPACE_RE = re.compile(
    r"\b(?:compare|comparison)\s+((?:\d{1,4}[a-z]?\s*){2,6})",
    re.I,
)
_REPLACE_RE = re.compile(
    r"\b(replac(?:e|ed|ing|ement)?|successor|new\s+law|became|equivalent|what\s+replaced|which\s+law)\b",
    re.I,
)
_BARE_SECTION_NUM_RE = re.compile(r"^(?:section\s+)?(\d{1,4}[a-z]?)$", re.I)
_BARE_SECTION_QUERY_RE = re.compile(
    r"^(?:"
    r"(?:section|sec\.?)\s*\d{1,4}[a-z]?|"
    r"\d{1,4}[a-z]?|"
    r"(?:ipc|bns|crpc|bnss|bsa)\s*\d{1,4}[a-z]?|"
    r"(?:ipc|bns|crpc|bnss|bsa)\s*(?:section|sec\.?)\s*\d{1,4}[a-z]?"
    r")$",
    re.I,
)
_ENTITY_LOOKUP_RE = re.compile(
    r"\b(parties? involved|who are the parties|name the parties|parties to|"
    r"confidential information|what is confidential|governing law|effective date|"
    r"after termination|upon termination|what happens.*termination|"
    r"sample\s+(?:non[- ]?disclosure|agreement|contract)|"
    r"(?:what is|what's|define|explain|describe|tell me about).*(?:nda|non[- ]?disclosure|agreement|contract))\b",
    re.I,
)
_CASE_QUERY_RE = re.compile(
    r"\b(?:case|judgment|judgement|verdict|ruling|petition|fir|hearing)\b|"
    r"\b(?:rg\s*karr?|rg\s*kar|nirbhaya|kesavananda|vishaka|navtej|"
    r"puttaswamy|shayara|maneka\s+gandhi)\b|"
    r"\b\w+(?:\s+\w+){0,6}\s+vs\.?\s+\w+(?:\s+\w+){0,8}\b",
    re.I,
)
_WH_FACT_RE = re.compile(
    r"\b(who|which|what|when)\b.+?\b(?:sought|filed|granted|obtained|awarded|"
    r"alleged|appointed|claimed|applied\s+for|petitioned)\b",
    re.I | re.S,
)
_UNDER_SECTION_RE = re.compile(r"\bunder\s+(\d{1,4}[a-z]?)\b", re.I)


def is_bare_section_query(query: str) -> bool:
    """Single-section lookup: 'section 300', 'ipc 307', '300'."""
    return bool(_BARE_SECTION_QUERY_RE.match((query or "").strip()))


def is_law_code_comparison_query(query: str) -> bool:
    """CrPC vs BNSS, Evidence Act vs BSA — not a case caption."""
    ql = (query or "").lower()
    if not re.search(r"\b(vs|versus)\b", ql):
        return False
    law_hits = re.findall(
        r"\b(ipc|bns|crpc|bnss|bsa|evidence act|indian evidence act)\b",
        ql,
        re.I,
    )
    return len(set(law_hits)) >= 2


def is_document_fact_query(query: str) -> bool:
    """Who sought custody / who filed FIR — answered from case narrative in KB PDFs."""
    q = (query or "").strip()
    if not q or len(q) > 160:
        return False
    try:
        from backend.app.core.universal_kb import is_statute_focused_query

        if is_statute_focused_query(q):
            return False
    except Exception:
        pass
    if is_case_query(q):
        return True
    if _WH_FACT_RE.search(q):
        return True
    if re.search(r"\bwho\b", q, re.I) and re.search(
        r"\b(?:custody|maintenance|bail|divorce|alimony|guardianship)\b", q, re.I
    ):
        return True
    return False


def is_case_query(query: str) -> bool:
    if is_law_code_comparison_query(query):
        return False
    if _CASE_QUERY_RE.search(query or ""):
        return True
    try:
        from backend.app.core.case_entity_resolver import is_case_style_query

        return is_case_style_query(query)
    except ImportError:
        return False


def _has_prior_assistant(messages: Optional[List[Dict]]) -> bool:
    if not messages:
        return False
    return any(m.get("role") == "assistant" for m in messages[-6:])


def _requested_laws(query: str) -> List[str]:
    ql = (query or "").lower()
    laws: List[str] = []
    if re.search(r"\b(ipc|indian penal code)\b", ql):
        laws.append("ipc")
    if re.search(r"\b(bns|bharatiya nyaya)\b", ql):
        laws.append("bns")
    if re.search(r"\b(it act|information technology|cyber|66[cd])\b", ql):
        laws.append("it_act")
    if re.search(r"\b(evidence act)\b", ql):
        laws.append("evidence")
    return laws


def is_section_mapping_followup(query: str) -> bool:
    """IPC 302 became what? / which BNS section maps to IPC 307 — not a section explain."""
    ql = (query or "").lower().strip()
    return bool(
        re.search(
            r"\b(?:became|replaced|maps?\s+to|equivalent|correspond(?:s|ing)?)\s+(?:what|which)\b",
            ql,
        )
        or re.search(r"\bwhat\s+did\s+ipc\s+\d+\s+(?:become|map)\b", ql)
    )


def is_section_focus_query(query: str) -> bool:
    """True when the user wants one section explained — not a law-replacement chart answer."""
    ql = (query or "").lower().strip()
    if not ql:
        return False
    if is_section_mapping_followup(query):
        return False
    try:
        from backend.app.services.legal_query_parser import parse_legal_query

        if parse_legal_query(query):
            return True
    except ImportError:
        pass
    try:
        from kb_legal_query_rewrite import is_law_replacement_query

        if is_law_replacement_query(query):
            return False
    except Exception:
        pass
    secs = primary_sections_from_query(query)
    if not secs:
        return False
    if re.search(
        r"\b(?:explain|meaning|define|what is|simple language|tell me about|punishment for|"
        r"punishment under|offence under|offense under)\b",
        ql,
    ):
        return True
    if len(secs) == 1 and re.search(r"\b(?:ipc|bns|section)\s*\d", ql):
        if not re.search(r"\b(?:replaced|replacement|mapped|equivalent|what replaced|became)\b", ql):
            return True
    return False


def primary_sections_from_query(query: str) -> List[str]:
    """Section numbers explicitly named in the current user message only."""
    try:
        from backend.app.services.legal_query_parser import section_numbers_from_query

        return section_numbers_from_query(query)
    except ImportError:
        pass
    q = (query or "").strip()
    if not q:
        return []
    found: List[str] = []
    for pat in (
        re.compile(r"\b(?:section|sec\.?)\s*(\d{1,4}[a-z]?)\b", re.I),
        re.compile(r"\b(?:ipc|bns|crpc)\s*(\d{1,4}[a-z]?)\b", re.I),
        re.compile(r"^(?:section|sec\.?)?\s*(\d{1,4}[a-z]?)$", re.I),
        re.compile(r"\b(\d{1,4}[a-z]?)\s*ipc\b", re.I),
    ):
        for m in pat.finditer(q):
            found.append(m.group(1).lower())
    em = re.search(r"\bexplain\s+(\d{1,4}[a-z]?)\b", q, re.I)
    if em:
        found.append(em.group(1).lower())
    dedup: List[str] = []
    seen: set = set()
    for s in found:
        if s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup


def query_has_explicit_section(query: str) -> bool:
    return bool(primary_sections_from_query(query))


def extract_entities(query: str, history: Optional[List[Dict]] = None) -> Dict[str, Any]:
    """
    Unified entity + intent extraction for KB pipeline.

    Example:
      "Difference between IPC 300 and 307" ->
        {intent: COMPARISON, entities: ["300", "307"], laws: ["ipc"]}
    """
    q = (query or "").strip()
    ql = q.lower()
    intent = detect_query_type(q, history)
    entities: List[str] = []

    if intent == QueryType.COMPARISON:
        cmp_secs = extract_comparison_sections(q)
        typed = _extract_typed_entities_safe(q)
        if len(cmp_secs) >= 2:
            entities = cmp_secs
        elif len(typed) >= 2:
            entities = [e.get("section", "") for e in typed if e.get("section")]
        else:
            entities = cmp_secs
        if len(entities) < 2:
            for m in _MULTI_NUM_RE.finditer(q):
                for g in m.groups():
                    if g and g.lower() not in entities:
                        entities.append(g.lower())
        if len(entities) < 2:
            cm = _MULTI_NUM_SPACE_RE.search(q)
            if cm:
                for n in re.findall(r"\d{1,4}[a-z]?", cm.group(1), re.I):
                    nl = n.lower()
                    if nl not in entities:
                        entities.append(nl)
    else:
        explicit = primary_sections_from_query(q)
        if explicit:
            entities = explicit
        else:
            entities = extract_sections_from_text(q)
            for m in _UNDER_SECTION_RE.finditer(q):
                entities.append(m.group(1).lower())
            m_bare = _BARE_SECTION_NUM_RE.match(q.strip())
            if m_bare:
                entities.append(m_bare.group(1).lower())
            em = re.search(r"\bexplain\s+(\d{1,4}[a-z]?)\b", ql)
            if em:
                entities.append(em.group(1).lower())

    if intent == QueryType.PUNISHMENT_QUERY and not entities:
        if re.search(r"\bmurder\b", ql):
            entities = ["302"]
        elif re.search(r"\bcheating\b", ql):
            entities = ["420"]
        elif re.search(r"\battempt\b", ql):
            entities = ["307"]

    if intent == QueryType.FOLLOW_UP and history and not query_has_explicit_section(q):
        current = extract_sections_from_text(q)
        if len(current) == 1 and is_bare_section_query(q):
            entities = current
        elif not current:
            for msg in reversed(history[-6:]):
                if msg.get("role") == "user":
                    prior = extract_sections_from_text(msg.get("content") or "")
                    if prior:
                        entities = prior + [e for e in entities if e not in prior]
                        break

    dedup: List[str] = []
    seen = set()
    for e in entities:
        el = e.lower()
        if el not in seen:
            seen.add(el)
            dedup.append(el)

    return {
        "intent": intent,
        "entities": dedup,
        "laws": _requested_laws(q),
        "typed_entities": _extract_typed_entities_safe(q),
    }


def _extract_typed_entities_safe(q: str) -> List[Dict[str, str]]:
    try:
        from kb_compare_engine import extract_typed_entities

        return extract_typed_entities(q)
    except Exception:
        return []


def detect_query_type(
    query: str,
    history: Optional[List[Dict]] = None,
) -> QueryType:
    q = (query or "").strip()
    ql = q.lower()
    sections = extract_sections_from_text(q)
    word_count = len(ql.split())

    if _ENTITY_LOOKUP_RE.search(ql):
        return QueryType.ENTITY_LOOKUP

    if _PAGE_RE.search(ql):
        return QueryType.PAGE_LOOKUP

    if is_case_query(q):
        return QueryType.TOPIC_QUERY

    if is_document_fact_query(q):
        return QueryType.TOPIC_QUERY

    try:
        from backend.app.core.constitutional_concept_map import is_constitutional_query

        if is_constitutional_query(q):
            return QueryType.TOPIC_QUERY
    except ImportError:
        pass

    # --- PRIORITY: legal section entities always beat replacement routing ---
    try:
        from backend.app.services.legal_query_parser import (
            has_legal_section_entities,
            is_cross_law_comparison_query,
            route_legal_query,
            section_numbers_from_query,
        )

        if has_legal_section_entities(q):
            route = route_legal_query(q)
            nums = section_numbers_from_query(q)
            if route == "comparison" or is_cross_law_comparison_query(q) or (
                len(nums) >= 2 and _COMPARE_RE.search(ql)
            ):
                return QueryType.COMPARISON
            if route == "punishment" or _PUNISH_RE.search(ql):
                return QueryType.PUNISHMENT_QUERY
            if route == "section_explanation" or _EXPLAIN_RE.search(ql):
                return QueryType.SECTION_EXPLANATION
            if is_bare_section_query(q):
                return QueryType.SECTION_LOOKUP
            return QueryType.SECTION_EXPLANATION
    except ImportError:
        pass

    if is_bare_section_query(q):
        return QueryType.SECTION_LOOKUP

    if is_law_code_comparison_query(q):
        return QueryType.COMPARISON

    compare_cue = bool(
        _COMPARE_RE.search(ql)
        or _MULTI_NUM_SPACE_RE.search(ql)
        or _MULTI_NUM_RE.search(ql)
        or re.search(r"\b\d{1,4}\b.*\b(?:and|vs|versus|between)\b.*\b\d{1,4}\b", ql)
    )
    if compare_cue:
        sections = extract_comparison_sections(q) or sections

    if _has_prior_assistant(history) and (
        word_count <= 12
        or _FOLLOW_UP_RE.search(ql)
        or (not sections and re.search(r"\b(it|this|that|same)\b", ql))
    ) and not is_bare_section_query(q) and not is_case_query(q):
        if not query_has_explicit_section(q):
            return QueryType.FOLLOW_UP

    if _REPLACE_RE.search(ql) and re.search(
        r"\b(ipc|crpc|evidence act|indian penal|bns|bnss|bsa|criminal procedure)\b", ql
    ):
        try:
            from backend.app.services.legal_query_parser import has_legal_section_entities

            if not has_legal_section_entities(q):
                return QueryType.LAW_REPLACEMENT
        except ImportError:
            return QueryType.LAW_REPLACEMENT

    if re.search(r"\bwhat\s+changed\b.*\b(?:criminal|law|bns|ipc)\b", ql):
        try:
            from backend.app.services.legal_query_parser import has_legal_section_entities

            if not has_legal_section_entities(q):
                return QueryType.LAW_REPLACEMENT
        except ImportError:
            return QueryType.LAW_REPLACEMENT

    if compare_cue:
        cmp_secs = extract_comparison_sections(q)
        if len(cmp_secs) >= 2 or _MULTI_NUM_RE.search(ql) or _MULTI_NUM_SPACE_RE.search(ql):
            return QueryType.COMPARISON
        try:
            from kb_compare_engine import extract_typed_entities

            typed = extract_typed_entities(q)
            if len(typed) >= 2:
                return QueryType.COMPARISON
        except Exception:
            pass
        try:
            from backend.app.core.legal_offence_resolver import is_conceptual_comparison_query

            if is_conceptual_comparison_query(q):
                return QueryType.COMPARISON
        except Exception:
            pass
        if _COMPARE_RE.search(ql) and re.search(
            r"\b(ipc|bns|crpc|bnss|bsa|evidence act)\b.*\b(ipc|bns|crpc|bnss|bsa|evidence act)\b",
            ql,
        ):
            return QueryType.COMPARISON
        if re.search(r"\b(vs|versus)\b", ql):
            law_hits = re.findall(
                r"\b(ipc|bns|crpc|bnss|bsa|evidence act|indian evidence act)\b",
                ql,
                re.I,
            )
            if len(set(law_hits)) >= 2:
                return QueryType.COMPARISON

    if _PUNISH_RE.search(ql) and (
        sections
        or re.search(
            r"\b(murder|cheating|theft|robbery|rape|fraud|attempt|culpable homicide|homicide)\b",
            ql,
        )
    ):
        return QueryType.PUNISHMENT_QUERY

    if re.search(
        r"\b(name\s+(?:five|5)\s+.*rights|constitutional rights?|five constitutional rights?)\b",
        ql,
    ):
        return QueryType.LIST_EXTRACTION

    if _LIST_RE.search(ql) or (
        _SUMMARY_RE.search(ql)
        and re.search(r"\b(all|every|each)\b.*\b(section|ipc|bns|offence|offenses?|topic|criminal)\b", ql)
    ):
        return QueryType.LIST_EXTRACTION

    if _SUMMARY_RE.search(ql) or re.search(
        r"\b(all|every)\b.*\b(criminal\s+)?(offences?|offenses?|sections?|topics?)\b", ql
    ):
        return QueryType.SUMMARY

    if _TOPIC_RE.search(ql):
        return QueryType.TOPIC_QUERY

    if not sections:
        for m in _UNDER_SECTION_RE.finditer(q):
            sections.append(m.group(1).lower())
        m_bare = _BARE_SECTION_NUM_RE.match(q.strip())
        if m_bare:
            sections.append(m_bare.group(1).lower())
        em = re.search(r"\bexplain\s+(\d{1,4}[a-z]?)\b", ql)
        if em:
            sections.append(em.group(1).lower())

    if sections and _PUNISH_RE.search(ql):
        return QueryType.PUNISHMENT_QUERY

    if sections and _EXPLAIN_RE.search(ql):
        return QueryType.SECTION_EXPLANATION

    if sections and (_LOOKUP_RE.search(ql) or word_count <= 10):
        return QueryType.SECTION_LOOKUP

    if _PUNISH_RE.search(ql) and sections:
        return QueryType.PUNISHMENT_QUERY

    if _EXPLAIN_RE.search(ql):
        if sections:
            return QueryType.SECTION_EXPLANATION
        if _has_prior_assistant(history):
            return QueryType.FOLLOW_UP
        return QueryType.UNKNOWN

    if sections and word_count <= 6:
        return QueryType.SECTION_LOOKUP

    if _LOOKUP_RE.search(ql):
        try:
            from document_classifier import is_contract_topic_query

            if is_contract_topic_query(q):
                return QueryType.ENTITY_LOOKUP
        except ImportError:
            pass
        return QueryType.SECTION_LOOKUP

    return QueryType.UNKNOWN


def retrieval_k_for_type(query_type: QueryType, profile_k: int = 10) -> int:
    mapping = {
        QueryType.SECTION_LOOKUP: 6,
        QueryType.SECTION_EXPLANATION: 6,
        QueryType.COMPARISON: 10,
        QueryType.SUMMARY: 12,
        QueryType.LIST_EXTRACTION: 12,
        QueryType.PUNISHMENT_QUERY: 6,
        QueryType.FOLLOW_UP: 8,
        QueryType.PAGE_LOOKUP: 8,
        QueryType.TOPIC_QUERY: 10,
        QueryType.LAW_REPLACEMENT: 8,
        QueryType.UNKNOWN: 8,
    }
    cap = mapping.get(query_type, 8)
    return min(cap, profile_k or cap, 12)


def needs_document_wide_scan(query_type: QueryType, query: str) -> bool:
    if query_type == QueryType.ENTITY_LOOKUP:
        try:
            from document_classifier import is_contract_topic_query

            if is_contract_topic_query(query):
                return True
        except ImportError:
            pass
    if query_type in {
        QueryType.LIST_EXTRACTION,
        QueryType.TOPIC_QUERY,
        QueryType.SUMMARY,
    }:
        return True
    ql = (query or "").lower()
    if re.search(
        r"\b(all|every|each)\b.*\b(section|ipc|bns|offence|offenses?|topic|criminal)\b",
        ql,
    ):
        return True
    if re.search(r"\b(criminal\s+)?(offences?|offenses?)\s+(discussed|mentioned|covered)\b", ql):
        return True
    return False


def query_type_signals(query_type: QueryType, query: str) -> Dict[str, Any]:
    ent = extract_entities(query)
    return {
        "query_type": query_type.value,
        "requested_laws": ent["laws"],
        "sections": ent["entities"],
        "entities": ent["entities"],
    }
