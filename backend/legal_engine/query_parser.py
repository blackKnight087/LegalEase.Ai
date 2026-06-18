"""
Legal Query Parser — extract structured legal meaning from user queries.

Replaces brittle regex-only routing with a unified parse object consumed by
KB pipeline, mode router, retrieval, and response formatter.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from conversation_context import (
    build_conversation_state,
    enrich_query_with_context,
    extract_law_from_text,
    extract_sections_from_text,
)
from kb_compare_engine import extract_typed_entities, is_compare_query
from kb_query_types import QueryType, detect_query_type, is_case_query

_LAW_ALIASES = {
    "ipc": "IPC",
    "indian penal code": "IPC",
    "bns": "BNS",
    "bharatiya nyaya": "BNS",
    "bharatiya nyaya sanhita": "BNS",
    "crpc": "CrPC",
    "bnss": "BNSS",
    "it act": "IT Act",
    "information technology act": "IT Act",
}

_SECTION_WITH_LAW_RE = re.compile(
    r"\b(IPC|BNS|CrPC|BNSS|BSA|Indian Penal Code|"
    r"Bharatiya Nyaya Sanhita|Code of Criminal Procedure)\s*"
    r"(?:Section|Sec\.?|S\.?)?\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
_BARE_SECTION_RE = re.compile(
    r"\b(?:Section|Sec\.?|S\.?)\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
_ARTICLE_RE = re.compile(r"\b(?:Article|Art\.?)\s*(\d{1,4}[a-z]?)\b", re.I)

_CASE_PATTERNS = (
    r"\b(?:explain|describe|summarize|summary of|what is|tell me about)\s+"
    r"(?:the\s+)?([A-Z][\w\s\-']+\s+(?:case|judgment|judgement|verdict))\b",
    r"\b([A-Z][\w\s\-']+)\s+(?:case|judgment|judgement|verdict|ruling)\b",
    r"\b(nirbhaya|kesavananda\s+bharati|maneka\s+gandhi|vishaka|navtej|"
    r"puttaswamy|shayara\s+bano|indira\s+gandhi|basic\s+structure|"
    r"rg\s*karr?|rg\s*kar)\b",
)

_FOLLOW_UP_CUES = (
    "explain in simple", "simple language", "what is punishment", "punishment?",
    "tell me more", "go deeper", "elaborate", "example", "compare with",
    "difference from", "previous law", "what about", "and what", "how about",
    "does it", "what does it", "more detail",
)

_CONCEPT_CUES = (
    "what is bail", "anticipatory bail", "culpable homicide", "murder and",
    "difference between murder", "fundamental rights", "writ petition",
    "limitation period", "cheating", "defamation", "contract",
)


def _normalize_law(token: str) -> str:
    t = (token or "").strip().lower()
    for key, val in _LAW_ALIASES.items():
        if key in t or t == key.replace(" ", ""):
            return val
    return token.upper() if token else ""


def _detect_law(query: str) -> str:
    ql = (query or "").lower()
    for key, val in _LAW_ALIASES.items():
        if re.search(rf"\b{re.escape(key)}\b", ql):
            return val
    return ""


def _is_follow_up(query: str, history: Optional[List[Dict]]) -> bool:
    q = (query or "").strip()
    ql = q.lower()
    if not history:
        return False
    try:
        from backend.app.services.followup_detector import is_new_legal_query

        if is_new_legal_query(q):
            return False
    except ImportError:
        pass
    try:
        from kb_query_types import is_bare_section_query, is_case_query

        if is_bare_section_query(q) or is_case_query(q):
            return False
    except ImportError:
        pass
    if extract_sections_from_text(q) and len(q.split()) > 12:
        return False
    if any(c in ql for c in _FOLLOW_UP_CUES):
        return True
    if len(q.split()) <= 8 and any(w in ql for w in ("it", "that", "this", "same", "above")):
        return True
    return detect_query_type(q, history) == QueryType.FOLLOW_UP


def _extract_case_name(query: str) -> str:
    q = (query or "").strip()
    for pat in _CASE_PATTERNS:
        m = re.search(pat, q, re.I)
        if m:
            name = (m.group(1) if m.lastindex else m.group(0)).strip()
            name = re.sub(r"\s+", " ", name)
            if len(name) > 3:
                return name.title()
    if re.search(r"\bcase\b|\bjudgment\b|\bverdict\b", q, re.I):
        cleaned = re.sub(
            r"(?i)\b(explain|describe|what is|tell me about|summarize|summary of)\b",
            "",
            q,
        ).strip(" ?.")
        if cleaned and len(cleaned) > 4:
            return cleaned.title()
    return ""


def _is_concept_query(query: str, kb_intent: QueryType) -> bool:
    ql = (query or "").lower()
    if extract_sections_from_text(query) or _SECTION_WITH_LAW_RE.search(query or ""):
        return False
    if kb_intent in {QueryType.COMPARISON, QueryType.PAGE_LOOKUP}:
        return False
    if any(c in ql for c in _CONCEPT_CUES):
        return True
    if re.search(r"\bwhat is\b|\bdefine\b|\bmeaning of\b|\bdifference between\b", ql):
        if not extract_sections_from_text(query):
            return True
    return kb_intent == QueryType.TOPIC_QUERY


@dataclass
class LegalQueryParse:
    """Structured legal query understanding."""

    raw_query: str = ""
    intent: str = "general"
    law: str = ""
    section: str = ""
    article: str = ""
    case_name: str = ""
    entities: List[Dict[str, str]] = field(default_factory=list)
    is_follow_up: bool = False
    resolved_query: str = ""
    kb_query_type: str = "unknown"
    retrieval_mode: str = "semantic"  # semantic | statute | comparison
    signals: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "law": self.law,
            "section": self.section,
            "article": self.article,
            "case_name": self.case_name,
            "entities": self.entities,
            "is_follow_up": self.is_follow_up,
            "resolved_query": self.resolved_query,
            "kb_query_type": self.kb_query_type,
            "retrieval_mode": self.retrieval_mode,
            "signals": self.signals,
        }


def parse_legal_query(
    query: str,
    history: Optional[List[Dict]] = None,
    *,
    session_state: Optional[Dict[str, Any]] = None,
) -> LegalQueryParse:
    """
    Parse user query into structured legal intent.

    Intents: section_lookup, comparison, case_explanation, concept_explanation,
    follow_up, general.
    """
    q = (query or "").strip()
    parse = LegalQueryParse(raw_query=q)
    kb_type = detect_query_type(q, history)
    parse.kb_query_type = kb_type.value

    follow_up = _is_follow_up(q, history)
    parse.is_follow_up = follow_up

    resolved = q
    if follow_up and history:
        resolved = enrich_query_with_context(q, history)
    elif session_state:
        try:
            from backend.app.core.conversation_memory import resolve_follow_up_query

            resolved = resolve_follow_up_query(q, session_state) or q
        except Exception:
            resolved = enrich_query_with_context(q, history)
    parse.resolved_query = resolved

    # Comparison
    if is_compare_query(q) or kb_type == QueryType.COMPARISON:
        typed = extract_typed_entities(q)
        if len(typed) >= 2:
            parse.intent = "comparison"
            parse.entities = [
                {"law": e.get("type", ""), "section": e.get("section", "")}
                for e in typed
            ]
            parse.retrieval_mode = "comparison"
            parse.signals["typed_entities"] = typed
            parse.signals["sections"] = [
                e.get("section", "") for e in typed if e.get("section")
            ]
            return parse

    # Section lookup — before follow-up so "section 300" stays a fresh lookup
    law = _detect_law(q) or _detect_law(resolved)
    sections = extract_sections_from_text(q) or extract_sections_from_text(resolved)
    m_law_sec = _SECTION_WITH_LAW_RE.search(q) or _SECTION_WITH_LAW_RE.search(resolved)
    if m_law_sec:
        law = _normalize_law(m_law_sec.group(1))
        sections = [m_law_sec.group(2).lower()] + [s for s in sections if s != m_law_sec.group(2).lower()]

    art_m = _ARTICLE_RE.search(q)
    if art_m:
        parse.article = art_m.group(1).lower()

    try:
        from kb_query_types import is_bare_section_query, is_case_query

        if is_bare_section_query(q) and sections:
            parse.intent = "section_lookup"
            parse.law = law or (session_state or {}).get("last_law", "") or "IPC"
            parse.section = sections[0]
            parse.retrieval_mode = "statute"
            parse.signals["sections"] = sections[:1]
            parse.signals["law"] = parse.law
            return parse
    except ImportError:
        pass

    if is_case_query(q):
        case = _extract_case_name(q)
        parse.intent = "case_explanation"
        parse.case_name = case or q.strip()
        parse.retrieval_mode = "semantic"
        return parse

    # General legal concept (before generic "what is" → section_lookup drift)
    if not sections and _is_concept_query(q, kb_type):
        parse.intent = "concept_explanation"
        parse.retrieval_mode = "semantic"
        return parse

    if sections or (
        kb_type in {
            QueryType.SECTION_LOOKUP,
            QueryType.SECTION_EXPLANATION,
            QueryType.PUNISHMENT_QUERY,
        }
        and (sections or _SECTION_WITH_LAW_RE.search(q) or re.search(r"\b(?:ipc|bns|crpc)\s*\d", q, re.I))
    ):
        parse.intent = "section_lookup"
        if kb_type == QueryType.PUNISHMENT_QUERY:
            parse.intent = "section_lookup"
        parse.law = law or (session_state or {}).get("last_law", "") or "IPC"
        parse.section = sections[0] if sections else ""
        parse.retrieval_mode = "statute"
        parse.signals["sections"] = sections
        parse.signals["law"] = parse.law
        return parse

    # Case law (skip bare concept questions like "what is bail")
    case = _extract_case_name(q)
    is_case_query = bool(
        case
        or (
            re.search(r"\bcase\b|\bjudgment\b|\bverdict\b|\bpetition\b", q, re.I)
            and not _is_concept_query(q, kb_type)
        )
    )
    if is_case_query:
        parse.intent = "case_explanation"
        parse.case_name = case or q.strip()
        parse.retrieval_mode = "semantic"
        return parse

    # Follow-up without section in current query
    if follow_up:
        state = build_conversation_state(history)
        if session_state:
            parse.law = session_state.get("last_law") or state.active_law.upper()
            parse.section = (session_state.get("last_section") or "").lower()
            if session_state.get("last_entities"):
                parse.entities = session_state["last_entities"]
        elif state.active_sections:
            parse.law = (state.active_law or "ipc").upper()
            parse.section = state.active_sections[0]
        parse.intent = "follow_up"
        if parse.section:
            parse.retrieval_mode = "statute"
            parse.signals["sections"] = [parse.section]
        return parse

    parse.intent = "general"
    parse.retrieval_mode = "semantic"
    return parse
