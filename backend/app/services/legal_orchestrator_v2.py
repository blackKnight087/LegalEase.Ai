"""
Legal Orchestrator V2 — master controller for KB query → answer.

NO retrieval before orchestration. NO semantic-first answering.
Pipeline: parse → classify → entities → retrieval plan → execute → generate → validate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from intent_engine import IntentProfile, QueryIntent, classify_intent
from kb_query_types import QueryType

_last_kb_synthesis_meta: Dict[str, Any] = {}


def reset_kb_synthesis_meta() -> None:
    global _last_kb_synthesis_meta
    _last_kb_synthesis_meta = {"ollama_invoked": False}


def get_last_kb_synthesis_meta() -> Dict[str, Any]:
    return dict(_last_kb_synthesis_meta)


class QueryClass(str, Enum):
    SINGLE_SECTION = "single_section"
    SECTION_PUNISHMENT = "section_punishment"
    MULTI_SECTION = "multi_section"
    SAME_LAW_COMPARISON = "same_law_comparison"
    LAW_MAPPING = "law_mapping"
    CONSTITUTIONAL = "constitutional"
    GENERAL_LEGAL = "general_legal"
    DOCUMENT_QA = "document_qa"
    CASE_LAW = "case_law"
    ENTITY_LOOKUP = "entity_lookup"


_COMPARE_RE = re.compile(
    r"\b(compare|comparison|difference|differences|differentiate|distinguish|"
    r"between|table\s+format)\b",
    re.I,
)
_PUNISH_RE = re.compile(
    r"\b(punishment|penalty|sentence|imprisonment|jail|fine|jail\s+term)\b",
    re.I,
)
_EXPLAIN_RE = re.compile(
    r"\b(explain|describe|walk me through|break down|tell me about|what is|what's|define|meaning of)\b",
    re.I,
)
_MAPPING_RE = re.compile(
    r"\b(equivalent|counterpart|correspond|mapped|mapping|replace|replaced|successor|"
    r"old\s+vs\s+new|bns\s+equivalent|what replaced|which law replaced|new law)\b",
    re.I,
)
_ARTICLE_RE = re.compile(r"\b(?:article|art\.?)\s*(\d{1,4}[a-z]?)\b", re.I)
_MULTI_JOIN_RE = re.compile(r"\b(?:and|&|,)\b", re.I)

_CONSTITUTIONAL_KEYWORDS = (
    "fundamental rights",
    "constitutional rights",
    "constitutional remedy",
    "constitution",
    "article ",
    "right to equality",
    "right to freedom",
    "right against exploitation",
    "right to religion",
    "right to life",
    "equality",
    "freedom of speech",
    "freedom of religion",
    "personal liberty",
    "religion",
)

_RIGHT_TO_ARTICLE: Dict[str, str] = {
    "right to equality": "14",
    "equality": "14",
    "right to freedom of speech": "19",
    "right to freedom": "19",
    "freedom of speech": "19",
    "freedom": "19",
    "right against exploitation": "23",
    "exploitation": "23",
    "right to freedom of religion": "25",
    "right to religion": "25",
    "religion": "25",
    "right to life": "21",
    "personal liberty": "21",
    "right to life and personal liberty": "21",
}

_BNS_FORBIDDEN_IN_ANSWER = re.compile(
    r"\bcorresponds to bns\b|\bmapping in your document\b|"
    r"\bipc\s+section\s+\d+.*\bbns\s+section\b|\btransition chart\b|"
    r"\bold laws vs new\b",
    re.I,
)
_CRIMINAL_CHUNK_RE = re.compile(
    r"\b(?:ipc|bns|crpc|bnss)\s*(?:section\s*)?\d{1,4}\b|"
    r"transition chart|old laws vs new|indian penal code.*replaced",
    re.I,
)


@dataclass
class ParsedQuery:
    raw: str
    normalized: str
    query_class: QueryClass
    law_systems: List[str] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)
    articles: List[str] = field(default_factory=list)
    typed_entities: List[Dict[str, str]] = field(default_factory=list)
    mapping_mode: bool = False
    constitutional_topic: str = ""
    constitutional_article: str = ""


@dataclass
class RetrievalPlan:
    query_class: QueryClass
    steps: List[str] = field(default_factory=list)
    per_section: bool = False
    allow_bns: bool = False
    law: str = "IPC"
    sections: List[str] = field(default_factory=list)
    typed_entities: List[Dict[str, str]] = field(default_factory=list)
    constitutional_terms: List[str] = field(default_factory=list)


@dataclass
class OrchestratorDiag:
    query_class: str = ""
    retrieval_mode: str = ""
    mapping_mode: bool = False
    validation: Dict[str, Any] = field(default_factory=dict)
    sections_requested: List[str] = field(default_factory=list)
    retried: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "orchestrator": "v2",
            "query_class": self.query_class,
            "mode": self.retrieval_mode,
            "retrieval_mode": self.retrieval_mode,
            "mapping_mode": self.mapping_mode,
            "validation": self.validation,
            "sections_requested": self.sections_requested,
            "retried": self.retried,
        }


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", (query or "").strip())


def _detect_law_systems(query: str) -> List[str]:
    ql = query.lower()
    found: List[str] = []
    for key, label in (
        ("ipc", "IPC"),
        ("indian penal", "IPC"),
        ("bns", "BNS"),
        ("bharatiya nyaya", "BNS"),
        ("crpc", "CrPC"),
        ("bnss", "BNSS"),
    ):
        if re.search(rf"\b{re.escape(key)}\b", ql) and label not in found:
            found.append(label)
    try:
        from backend.app.core.constitutional_concept_map import is_constitutional_query

        if is_constitutional_query(query):
            return found
    except Exception:
        pass
    if not found and _extract_section_numbers(query) and not _is_constitutional_text(query):
        found.append("IPC")
    return found


def _extract_section_numbers(query: str) -> List[str]:
    try:
        from backend.app.services.legal_query_parser import section_numbers_from_query

        nums = section_numbers_from_query(query)
        if nums:
            return nums
    except Exception:
        pass
    m = re.search(
        r"\b(\d{1,4}[a-z]?)\s+(?:punishment|penalty|sentence|fine|imprisonment)\b",
        query,
        re.I,
    )
    if m:
        return [m.group(1).lower()]
    m2 = re.search(
        r"\b(?:punishment|penalty|sentence|fine|imprisonment)\s+(?:for|under|of)?\s*(\d{1,4}[a-z]?)\b",
        query,
        re.I,
    )
    if m2:
        return [m2.group(1).lower()]
    ql = query.lower()
    if _EXPLAIN_RE.search(ql) and _MULTI_JOIN_RE.search(ql):
        out: List[str] = []
        seen: set[str] = set()
        for m in re.finditer(r"\b(\d{1,4}[a-z]?)\b", query):
            n = m.group(1).lower()
            if n not in seen and n.isdigit() and 1 <= int(n) <= 599:
                seen.add(n)
                out.append(n)
        if len(out) >= 2:
            return out
    from kb_retrieval import extract_comparison_sections

    return extract_comparison_sections(query) or []


def _mapping_mode_explicit(query: str, law_systems: List[str]) -> bool:
    ql = query.lower()
    if _MAPPING_RE.search(ql):
        return True
    try:
        from kb_legal_query_rewrite import is_law_replacement_query

        if is_law_replacement_query(query):
            return True
    except Exception:
        pass
    old = {"IPC", "CrPC", "Evidence Act"} & set(law_systems)
    new = {"BNS", "BNSS", "BSA"} & set(law_systems)
    return bool(old and new)


def _is_constitutional_text(query: str) -> bool:
    try:
        from kb_query_types import is_case_query

        if is_case_query(query):
            return False
    except ImportError:
        if re.search(r"\b\w+(?:\s+\w+){0,6}\s+vs\.?\s+\w+", query or "", re.I):
            return False
    ql = query.lower()
    if any(k in ql for k in _CONSTITUTIONAL_KEYWORDS):
        return True
    if _ARTICLE_RE.search(query):
        return True
    if re.search(r"\bright to\b", ql):
        return True
    return False


def _infer_section_from_topic(query: str) -> str:
    """Map offence topics to IPC sections when punishment is asked without a number."""
    ql = (query or "").lower()
    if re.search(r"\battempt\s+to\s+murder\b", ql):
        return "307"
    if re.search(r"\bmurder\b", ql):
        return "302"
    if re.search(r"\bcheat(?:ing)?\b", ql):
        return "420"
    if re.search(r"\btheft\b", ql):
        return "378"
    return ""


def _case_lookup(index_dir: Any, parsed: ParsedQuery, *, top_k: int = 10) -> List[Dict[str, Any]]:
    """Docstore scan for case paragraphs — party names, landmarks, or 'vs' style."""
    from backend.app.core.case_entity_resolver import (
        chunk_matches_case,
        extract_case_block,
        extract_case_needles,
    )

    needles = extract_case_needles(parsed.raw)
    if not needles:
        return []
    try:
        from rag import _load_docstore_only

        view = _load_docstore_only(Path(index_dir))
        if view is None:
            return []
    except Exception:
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
        except Exception:
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
                "retrieval_mode": "case_lookup",
            }
        )
    hits.sort(key=lambda c: -float(c.get("final_score", 0)))
    return hits[:top_k]


def _constitutional_topic(query: str) -> Tuple[str, str]:
    ql = query.lower().strip()
    for phrase, art in sorted(_RIGHT_TO_ARTICLE.items(), key=lambda x: -len(x[0])):
        if phrase in ql:
            return phrase, art
    for m in _ARTICLE_RE.finditer(query):
        return f"article {m.group(1)}", m.group(1).lower()
    if "fundamental rights" in ql or "constitutional rights" in ql:
        return "constitutional rights", ""
    return "", ""


def parse_query(query: str) -> ParsedQuery:
    raw = (query or "").strip()
    normalized = normalize_query(raw)

    try:
        from backend.app.core.legal_domain_router import LegalDomain, route_legal_domain

        domain_route = route_legal_domain(normalized)
    except Exception:
        domain_route = None

    try:
        from kb_query_types import is_case_query

        if is_case_query(normalized):
            # region agent log
            try:
                from backend.app.core.debug_kb_session import dbg_kb

                dbg_kb(
                    "H1",
                    "legal_orchestrator_v2.py:parse_query",
                    "classified_case_law_before_constitution",
                    {"query": normalized[:120]},
                )
            except Exception:
                pass
            # endregion
            return ParsedQuery(
                raw=raw,
                normalized=normalized,
                query_class=QueryClass.CASE_LAW,
                law_systems=[],
                sections=[],
            )
    except Exception:
        pass

    if domain_route and domain_route.domain == LegalDomain.CONSTITUTION:
        const_art = domain_route.article or _constitutional_topic(normalized)[1]
        const_topic = domain_route.constitutional_topic or _constitutional_topic(normalized)[0]
        return ParsedQuery(
            raw=raw,
            normalized=normalized,
            query_class=QueryClass.CONSTITUTIONAL,
            law_systems=[],
            sections=[],
            articles=[const_art] if const_art else [],
            mapping_mode=False,
            constitutional_topic=const_topic,
            constitutional_article=const_art,
        )

    laws = _detect_law_systems(normalized)
    sections = _extract_section_numbers(normalized)
    articles = [m.group(1).lower() for m in _ARTICLE_RE.finditer(normalized)]
    mapping_mode = _mapping_mode_explicit(normalized, laws)
    const_topic, const_art = _constitutional_topic(normalized)

    # Strict classification — no fallback guessing
    qclass = QueryClass.GENERAL_LEGAL

    try:
        from kb_query_types import QueryType as QT, detect_query_type

        if detect_query_type(normalized) == QT.ENTITY_LOOKUP:
            qclass = QueryClass.ENTITY_LOOKUP
            return ParsedQuery(
                raw=raw,
                normalized=normalized,
                query_class=qclass,
                law_systems=laws,
                sections=sections,
                articles=articles,
            )
    except Exception:
        pass

    try:
        from kb_query_types import is_case_query

        if is_case_query(normalized):
            qclass = QueryClass.CASE_LAW
            return ParsedQuery(
                raw=raw,
                normalized=normalized,
                query_class=qclass,
                law_systems=laws,
                sections=[],
            )
    except Exception:
        pass

    try:
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(normalized):
            qclass = QueryClass.DOCUMENT_QA
            return ParsedQuery(
                raw=raw,
                normalized=normalized,
                query_class=qclass,
                law_systems=[],
                sections=[],
            )
    except Exception:
        pass

    if _is_constitutional_text(normalized) and not sections and not (
        sections and _COMPARE_RE.search(normalized) and not mapping_mode
    ):
        try:
            from kb_query_types import is_case_query

            if is_case_query(normalized):
                return ParsedQuery(
                    raw=raw,
                    normalized=normalized,
                    query_class=QueryClass.CASE_LAW,
                    law_systems=laws,
                    sections=[],
                )
        except ImportError:
            pass
        qclass = QueryClass.CONSTITUTIONAL
        return ParsedQuery(
            raw=raw,
            normalized=normalized,
            query_class=qclass,
            law_systems=[],
            sections=[],
            articles=articles,
            mapping_mode=False,
            constitutional_topic=const_topic,
            constitutional_article=const_art,
        )

    conceptual_typed: List[Dict[str, str]] = []
    try:
        from backend.app.core.legal_offence_resolver import extract_conceptual_comparison_entities

        conceptual_typed = extract_conceptual_comparison_entities(normalized)
    except Exception:
        conceptual_typed = []

    typed: List[Dict[str, str]] = []

    if mapping_mode and sections:
        qclass = QueryClass.LAW_MAPPING
    elif _COMPARE_RE.search(normalized) and len(conceptual_typed) >= 2:
        qclass = QueryClass.SAME_LAW_COMPARISON
        sections = [e.get("section", "") for e in conceptual_typed if e.get("section")]
        typed = conceptual_typed
    elif _COMPARE_RE.search(normalized) and len(sections) >= 2:
        qclass = QueryClass.SAME_LAW_COMPARISON if not mapping_mode else QueryClass.LAW_MAPPING
    elif (
        len(sections) >= 2
        and _EXPLAIN_RE.search(normalized.lower())
        and _MULTI_JOIN_RE.search(normalized)
        and not _COMPARE_RE.search(normalized)
    ):
        qclass = QueryClass.MULTI_SECTION
    elif _PUNISH_RE.search(normalized.lower()) and not sections:
        topic_sec = _infer_section_from_topic(normalized)
        if topic_sec:
            sections = [topic_sec]
            qclass = QueryClass.SECTION_PUNISHMENT
    elif sections:
        if _PUNISH_RE.search(normalized.lower()):
            qclass = QueryClass.SECTION_PUNISHMENT
        else:
            qclass = QueryClass.SINGLE_SECTION
    elif mapping_mode:
        qclass = QueryClass.LAW_MAPPING
    else:
        try:
            from kb_legal_query_rewrite import is_law_replacement_query

            if is_law_replacement_query(normalized) and not sections:
                qclass = QueryClass.LAW_MAPPING
                mapping_mode = True
        except Exception:
            pass

    if qclass in (QueryClass.SAME_LAW_COMPARISON, QueryClass.LAW_MAPPING) and len(typed) < 2:
        typed = _build_comparison_entities(normalized, sections, laws, mapping_mode)

    from backend.app.services.legal_query_engine import _sections_from_multi_explain

    multi_secs = _sections_from_multi_explain(normalized)
    if (
        len(multi_secs) >= 2
        and _EXPLAIN_RE.search(normalized.lower())
        and not _COMPARE_RE.search(normalized)
        and not mapping_mode
    ):
        qclass = QueryClass.MULTI_SECTION
        sections = multi_secs
        typed = []

    if qclass == QueryClass.GENERAL_LEGAL:
        try:
            from backend.app.core.case_entity_resolver import is_entity_focus_query

            if is_entity_focus_query(normalized):
                qclass = QueryClass.CASE_LAW
            else:
                from backend.app.core.universal_kb import is_statute_focused_query

                if not is_statute_focused_query(normalized):
                    qclass = QueryClass.DOCUMENT_QA
        except Exception:
            qclass = QueryClass.DOCUMENT_QA

    return ParsedQuery(
        raw=raw,
        normalized=normalized,
        query_class=qclass,
        law_systems=laws,
        sections=sections,
        articles=articles,
        typed_entities=typed,
        mapping_mode=mapping_mode,
        constitutional_topic=const_topic,
        constitutional_article=const_art,
    )


def _enrich_parsed_from_context(
    parsed: ParsedQuery,
    *,
    original_query: str,
    search_q: str,
    history: Optional[List[Dict]] = None,
    session_id: Optional[str] = None,
) -> ParsedQuery:
    """Restore section/topic on meta follow-ups only (e.g. 'explain in simple language' after IPC 420)."""
    # Fresh topics must not inherit prior section/topic from session or history.
    try:
        from backend.app.services.followup_detector import requires_fresh_retrieval

        if requires_fresh_retrieval(original_query):
            return parsed
    except ImportError:
        pass

    protected_classes = {
        QueryClass.CASE_LAW,
        QueryClass.CONSTITUTIONAL,
        QueryClass.DOCUMENT_QA,
        QueryClass.ENTITY_LOOKUP,
        QueryClass.LAW_MAPPING,
    }
    if parsed.query_class in protected_classes and parsed.sections:
        return parsed
    if parsed.query_class in protected_classes and not parsed.sections:
        return parsed

    sections = list(parsed.sections)
    laws = list(parsed.law_systems)
    qclass = parsed.query_class

    try:
        from conversation_context import (
            build_conversation_state,
            extract_law_from_text,
            extract_sections_from_text,
            is_meta_follow_up,
        )
    except ImportError:
        return parsed

    meta = is_meta_follow_up(original_query)
    if not meta:
        return parsed

    if meta and session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            mem = get_session_legal_memory(session_id)
            last_q = str(mem.get("last_user_query") or "").strip()
            last_domain = str(mem.get("last_domain") or "")
            if last_q and not extract_sections_from_text(original_query):
                topic_q = str(mem.get("last_topic") or last_q)
                if last_domain == "constitution" or re.search(
                    r"\b(?:fundamental|constitutional|nda|agreement|contract|witness|"
                    r"medical|blood pressure|report|policy)\b",
                    last_q,
                    re.I,
                ):
                    return ParsedQuery(
                        raw=parsed.raw,
                        normalized=f"{original_query} — {topic_q}",
                        query_class=QueryClass.DOCUMENT_QA,
                        law_systems=[],
                        sections=[],
                        articles=parsed.articles,
                        typed_entities=parsed.typed_entities,
                        mapping_mode=parsed.mapping_mode,
                        constitutional_topic=parsed.constitutional_topic
                        or topic_q,
                        constitutional_article=parsed.constitutional_article,
                    )
        except Exception:
            pass

    if meta and session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            mem = get_session_legal_memory(session_id)
            last_case = str(mem.get("last_case") or "").strip()
            if last_case:
                return ParsedQuery(
                    raw=parsed.raw,
                    normalized=parsed.normalized,
                    query_class=QueryClass.CASE_LAW,
                    law_systems=[],
                    sections=[],
                    articles=parsed.articles,
                    typed_entities=parsed.typed_entities,
                    mapping_mode=parsed.mapping_mode,
                    constitutional_topic=parsed.constitutional_topic,
                    constitutional_article=parsed.constitutional_article,
                )
        except Exception:
            pass

    if not sections:
        sections = extract_sections_from_text(search_q) or extract_sections_from_text(
            original_query
        )
    if not sections and history:
        state = build_conversation_state(history)
        sections = list(state.active_sections[:3])
        if not laws and state.active_law:
            laws = [state.active_law]
    if not sections and session_id:
        try:
            from backend.app.core.conversation_memory import get_session_legal_memory

            mem = get_session_legal_memory(session_id)
            if mem.get("last_case"):
                return ParsedQuery(
                    raw=parsed.raw,
                    normalized=parsed.normalized,
                    query_class=QueryClass.CASE_LAW,
                    law_systems=[],
                    sections=[],
                    articles=parsed.articles,
                    typed_entities=parsed.typed_entities,
                    mapping_mode=parsed.mapping_mode,
                    constitutional_topic=parsed.constitutional_topic,
                    constitutional_article=parsed.constitutional_article,
                )
            if mem.get("last_section"):
                sections = [str(mem["last_section"])]
            if not laws and mem.get("last_law"):
                laws = [str(mem["last_law"]).lower()]
        except Exception:
            pass

    if sections and qclass in (
        QueryClass.GENERAL_LEGAL,
        QueryClass.DOCUMENT_QA,
    ):
        if _PUNISH_RE.search((original_query or "").lower()):
            qclass = QueryClass.SECTION_PUNISHMENT
        else:
            qclass = QueryClass.SINGLE_SECTION
    elif meta and sections and qclass not in protected_classes:
        qclass = QueryClass.SINGLE_SECTION

    if not laws and sections:
        law = extract_law_from_text(search_q) or extract_law_from_text(original_query)
        if law:
            laws = [law]

    if sections == parsed.sections and qclass == parsed.query_class and laws == parsed.law_systems:
        return parsed

    return ParsedQuery(
        raw=parsed.raw,
        normalized=parsed.normalized,
        query_class=qclass,
        law_systems=laws or parsed.law_systems,
        sections=sections,
        articles=parsed.articles,
        typed_entities=parsed.typed_entities,
        mapping_mode=parsed.mapping_mode,
        constitutional_topic=parsed.constitutional_topic,
        constitutional_article=parsed.constitutional_article,
    )


def classify_intent(parsed: ParsedQuery) -> QueryClass:
    return parsed.query_class


def extract_entities(parsed: ParsedQuery) -> Dict[str, Any]:
    mapping = {
        QueryClass.SINGLE_SECTION: QueryType.SECTION_EXPLANATION,
        QueryClass.SECTION_PUNISHMENT: QueryType.PUNISHMENT_QUERY,
        QueryClass.MULTI_SECTION: QueryType.SECTION_EXPLANATION,
        QueryClass.SAME_LAW_COMPARISON: QueryType.COMPARISON,
        QueryClass.LAW_MAPPING: QueryType.COMPARISON,
        QueryClass.CONSTITUTIONAL: QueryType.TOPIC_QUERY,
        QueryClass.GENERAL_LEGAL: QueryType.UNKNOWN,
        QueryClass.DOCUMENT_QA: QueryType.TOPIC_QUERY,
        QueryClass.CASE_LAW: QueryType.TOPIC_QUERY,
        QueryClass.ENTITY_LOOKUP: QueryType.ENTITY_LOOKUP,
    }
    return {
        "intent": mapping.get(parsed.query_class, QueryType.UNKNOWN),
        "entities": parsed.sections,
        "typed_entities": parsed.typed_entities,
        "laws": [x.lower() for x in parsed.law_systems],
        "mapping_mode": parsed.mapping_mode,
    }


def _build_comparison_entities(
    query: str,
    sections: List[str],
    laws: List[str],
    mapping_mode: bool,
) -> List[Dict[str, str]]:
    primary = laws[0] if laws else "IPC"
    if not mapping_mode and len(sections) >= 2:
        return [{"type": primary, "section": s} for s in sections[:4]]
    if mapping_mode:
        try:
            from kb_compare_engine import extract_typed_entities

            typed = extract_typed_entities(query)
            if len(typed) >= 2:
                return typed
        except Exception:
            pass
    try:
        from kb_compare_engine import extract_all_comparison_entities

        typed = extract_all_comparison_entities(query)
        if len(typed) >= 2 and mapping_mode:
            return typed
        if len(typed) >= 2:
            laws_set = {e.get("type", primary) for e in typed}
            if len(laws_set) == 1:
                return typed
    except Exception:
        pass
    if len(sections) >= 2:
        return [{"type": primary, "section": s} for s in sections[:4]]
    return []


def build_retrieval_plan(parsed: ParsedQuery) -> RetrievalPlan:
    law = parsed.law_systems[0] if parsed.law_systems else "IPC"
    allow_bns = parsed.mapping_mode
    terms: List[str] = []
    if parsed.query_class == QueryClass.CONSTITUTIONAL:
        if parsed.constitutional_topic:
            terms.append(parsed.constitutional_topic)
        if parsed.constitutional_article:
            terms.append(f"Article {parsed.constitutional_article}")
        terms.extend(["constitutional rights", "fundamental rights", "Article"])

    steps = ["exact_metadata", "section_lookup", "constitutional_lookup", "vector_search", "fallback"]

    if parsed.query_class == QueryClass.CONSTITUTIONAL:
        steps = ["constitutional_lookup", "exact_metadata", "vector_search"]

    return RetrievalPlan(
        query_class=parsed.query_class,
        steps=steps,
        per_section=parsed.query_class
        in (QueryClass.MULTI_SECTION, QueryClass.SAME_LAW_COMPARISON),
        allow_bns=allow_bns,
        law=law,
        sections=list(parsed.sections),
        typed_entities=list(parsed.typed_entities),
        constitutional_terms=terms,
    )


def _is_criminal_chunk(content: str) -> bool:
    return bool(_CRIMINAL_CHUNK_RE.search(content or ""))


def _chunk_allowed_by_scope(meta: Dict[str, Any], scope: Optional[Dict[str, Any]]) -> bool:
    if not scope:
        return True
    allowed_names = scope.get("allowed_filenames") or []
    allowed_ids = scope.get("allowed_doc_ids") or []
    if not allowed_names and not allowed_ids:
        return True
    fn = str(meta.get("filename") or meta.get("source_file") or "").lower()
    did = str(meta.get("doc_id") or "")
    if allowed_ids and did in allowed_ids:
        return True
    if allowed_names:
        allowed_lower = {str(n).lower() for n in allowed_names}
        if fn in allowed_lower or any(a in fn for a in allowed_lower):
            return True
    return False


def _constitutional_lookup(
    index_dir: Any,
    parsed: ParsedQuery,
    *,
    top_k: int = 10,
    scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Docstore scan for constitutional text — never criminal-transition chunks."""
    hits: List[Dict[str, Any]] = []
    try:
        from rag import _load_docstore_only

        vs = _load_docstore_only(index_dir)
        if not vs:
            return []
        store = getattr(vs, "docstore", None)
        doc_dict = getattr(store, "_dict", None) or {}
    except Exception:
        return []

    needles: List[str] = []
    if parsed.constitutional_topic:
        needles.append(parsed.constitutional_topic)
    if parsed.constitutional_article:
        needles.extend(
            [
                f"article {parsed.constitutional_article}",
                f"article {parsed.constitutional_article.upper()}",
            ]
        )
    ql = parsed.normalized.lower()
    if "rights" in ql or "constitutional" in ql or "fundamental" in ql:
        needles.extend(
            [
                "constitutional rights",
                "fundamental rights",
                "right to equality",
                "right to freedom",
                "article 14",
                "article 19",
                "article 21",
                "article 23",
                "article 25",
            ]
        )
    if not needles:
        needles = ["constitutional rights", "article"]

    seen: set[str] = set()
    for doc in doc_dict.values():
        content = getattr(doc, "page_content", None) or str(doc)
        if _is_criminal_chunk(content):
            continue
        meta = dict(getattr(doc, "metadata", None) or {})
        if not _chunk_allowed_by_scope(meta, scope):
            continue
        cl = content.lower()
        if not any(n.lower() in cl for n in needles):
            continue
        key = content[:120]
        if key in seen:
            continue
        seen.add(key)
        hits.append(
            {
                "content": content,
                "metadata": meta,
                "final_score": 2.4,
                "hybrid_score": 2.4,
                "retrieval_mode": "constitutional_lookup",
            }
        )
    hits.sort(key=lambda c: -len(c.get("content") or ""))
    return hits[:top_k]


def _prefer_constitutional_chunks(
    query: str,
    chunks: List[Dict[str, Any]],
    *,
    index_dir: Any = None,
    parsed: Optional[ParsedQuery] = None,
    scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Re-rank or rescue chunks so fundamental/constitutional queries never use IPC-only hits."""
    ql = (query or "").lower()
    if not any(k in ql for k in ("fundamental", "constitutional", "article")):
        return chunks
    try:
        from answer_orchestrator import _rank_constitutional_chunks

        ranked = _rank_constitutional_chunks(chunks or [])
    except Exception:
        ranked = list(chunks or [])

    combined = " ".join((c.get("content") or "")[:600].lower() for c in ranked[:6])
    has_rights = bool(
        re.search(
            r"\b(?:fundamental\s+rights|constitutional\s+rights|right\s+to\s+)"
            r"|article\s+(?:1[2-9]|[2-3]\d)\b",
            combined,
            re.I,
        )
    )
    if has_rights:
        return ranked

    if index_dir is not None and parsed is not None:
        rescued = _constitutional_lookup(
            index_dir, parsed, top_k=10, scope=scope or {}
        )
        if rescued:
            seen: set[str] = set()
            out: List[Dict[str, Any]] = []
            for c in rescued + ranked:
                key = (c.get("content") or "")[:100]
                if key and key not in seen:
                    seen.add(key)
                    out.append(c)
            return out
    return ranked


def _section_lookup_exact(
    index_dir: Any,
    section: str,
    law: str = "IPC",
    *,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    try:
        from rag import exact_section_lookup

        hits = exact_section_lookup(index_dir, [section], law=law, top_k=top_k)
        for h in hits:
            h["entity"] = section
            h["retrieval_mode"] = "exact_section"
        return hits
    except Exception:
        return []


def _law_replacement_retrieve(
    index_dir: Any,
    query: str,
    *,
    scope: Optional[Dict[str, Any]] = None,
    k: int = 12,
) -> List[Dict[str, Any]]:
    """Retrieve IPC→BNS replacement chart rows — not generic section-explanation chunks."""
    hits: List[Dict[str, Any]] = []
    try:
        from rag import _load_docstore_only

        view = _load_docstore_only(Path(index_dir))
        if view is not None:
            from kb_legal_query_rewrite import keyword_fallback_from_vectorstore

            hits = keyword_fallback_from_vectorstore(view, query, top_k=k)
    except Exception:
        pass
    if not hits:
        hits = _vector_search_last(
            index_dir,
            "IPC replaced by BNS Bharatiya Nyaya Sanhita 2023",
            k=k,
            scope=scope,
            exclude_bns=False,
            filter_criminal=False,
        )
    if not hits:
        hits = _vector_search_last(
            index_dir,
            query,
            k=k,
            scope=scope,
            exclude_bns=False,
            filter_criminal=False,
        )
    filtered: List[Dict[str, Any]] = []
    try:
        from kb_legal_query_rewrite import chunk_matches_law_query, is_law_mapping_chunk
        from kb_content_cleaner import is_kb_test_boilerplate

        for h in hits:
            body = h.get("content") or ""
            if is_kb_test_boilerplate(body):
                continue
            if chunk_matches_law_query(body, query) or is_law_mapping_chunk(body):
                filtered.append(h)
            elif re.search(r"\b(bns|bharatiya nyaya|replaced|successor)\b", body, re.I) and re.search(
                r"\bipc\b", body, re.I
            ):
                filtered.append(h)
    except Exception:
        filtered = list(hits)
    return filtered or hits


def _vector_search_last(
    index_dir: Any,
    query: str,
    *,
    k: int = 6,
    scope: Optional[Dict[str, Any]] = None,
    exclude_bns: bool = True,
    filter_criminal: bool = True,
) -> List[Dict[str, Any]]:
    try:
        from rag import query_kb

        scope_arg = scope if scope and scope.get("strict") else None
        hits = query_kb(query, k=max(k, 8), index_dir=index_dir, document_scope=scope_arg)
        if exclude_bns:
            filtered = []
            for h in hits:
                body = (h.get("content") or "").lower()
                if re.search(r"\bbns\s*section\s*\d", body) and "ipc" not in query.lower():
                    if not re.search(r"\bbns\b", query.lower()):
                        continue
                filtered.append(h)
            hits = filtered
        if len(hits) >= 3:
            return hits[:k]
        from backend.app.core.kb_retrieval_robust import robust_kb_retrieve

        broad = robust_kb_retrieve(
            query,
            index_dir,
            scope=scope or {},
            k=max(k, 10),
            constitutional=_is_constitutional_text(query),
        )
        if broad:
            merged = list(hits)
            seen = {(c.get("content") or "")[:80] for c in merged}
            for c in broad:
                key = (c.get("content") or "")[:80]
                if key and key not in seen:
                    merged.append(c)
                    seen.add(key)
            return merged[: max(k, 10)]
        return hits
    except Exception:
        try:
            from backend.app.core.kb_retrieval_robust import robust_kb_retrieve

            return robust_kb_retrieve(
                query,
                index_dir,
                scope=scope or {},
                k=max(k, 10),
                constitutional=_is_constitutional_text(query),
            )
        except Exception:
            return []


def execute_retrieval(
    plan: RetrievalPlan,
    parsed: ParsedQuery,
    index_dir: Any,
    *,
    scope: Optional[Dict[str, Any]] = None,
    retry: bool = False,
) -> Tuple[List[Dict[str, Any]], str]:
    chunks: List[Dict[str, Any]] = []
    mode = ""

    if plan.query_class == QueryClass.DOCUMENT_QA:
        try:
            from backend.app.core.universal_kb import universal_retrieve

            chunks = universal_retrieve(
                parsed.normalized or parsed.raw,
                index_dir,
                scope=scope,
                k=12 if retry else 10,
            )
            mode = "universal_document"
            if not chunks:
                chunks = _vector_search_last(
                    index_dir,
                    parsed.normalized,
                    k=10,
                    scope=scope,
                    exclude_bns=False,
                    filter_criminal=False,
                )
                mode = "universal_vector_fallback"
            return chunks, mode
        except Exception:
            pass

    if plan.query_class == QueryClass.CASE_LAW:
        from backend.app.core.case_entity_resolver import (
            extract_case_needles,
            extract_case_parties,
        )
        from backend.app.core.case_narrative_engine import filter_case_chunks, is_faq_or_boilerplate

        party_a, party_b = extract_case_parties(parsed.raw)
        if party_a and party_b:
            party_first = _case_lookup(index_dir, parsed, top_k=12 if retry else 10)
            if party_first:
                return party_first, "case_lookup_party_first"

        try:
            from backend.app.core.case_topic_resolver import (
                extract_topic_case_needles,
                is_topic_case_query,
                is_statute_stub_chunk,
                lookup_topic_case_chunks,
            )

            if is_topic_case_query(parsed.raw):
                topics = extract_topic_case_needles(parsed.raw)
                topic_chunks = lookup_topic_case_chunks(
                    index_dir, topics, top_k=12 if retry else 8
                )
                if topic_chunks:
                    return topic_chunks, "topic_case_lookup"
        except ImportError:
            pass

        chunks = _case_lookup(index_dir, parsed, top_k=12 if retry else 10)
        mode = "case_lookup"
        needles = extract_case_needles(parsed.raw)
        if chunks and needles:
            chunks = filter_case_chunks(chunks, needles)
        if not chunks and needles:
            try:
                from rag import query_kb

                search_q = " ".join(
                    dict.fromkeys([parsed.raw] + [n for n in needles if n != "case"])
                )
                chunks = query_kb(
                    search_q,
                    k=12,
                    index_dir=index_dir,
                    document_scope=scope if scope.get("strict") else None,
                )
                from backend.app.core.case_entity_resolver import chunk_matches_case

                chunks = filter_case_chunks(
                    [c for c in chunks if chunk_matches_case(c, needles)],
                    needles,
                )
                mode = "case_vector_party"
            except Exception:
                pass
        if not chunks:
            chunks = _vector_search_last(
                index_dir,
                parsed.normalized,
                k=10,
                scope=scope,
                exclude_bns=True,
                filter_criminal=False,
            )
            if needles:
                from backend.app.core.case_entity_resolver import chunk_matches_case

                filtered = filter_case_chunks(
                    [c for c in chunks if chunk_matches_case(c, needles)],
                    needles,
                )
                if filtered:
                    chunks = filtered
            try:
                from backend.app.core.case_topic_resolver import is_statute_stub_chunk

                _is_stub = is_statute_stub_chunk
            except ImportError:
                _is_stub = lambda _t: False  # noqa: E731
            chunks = [
                c
                for c in chunks
                if not is_faq_or_boilerplate(c.get("content") or "")
                and not _is_stub(c.get("content") or "")
                and "suggested questions" not in (c.get("content") or "").lower()
            ]
            if needles:
                chunks = filter_case_chunks(chunks, needles) or chunks
            mode = "case_vector_fallback"
        return chunks, mode

    if plan.query_class == QueryClass.CONSTITUTIONAL:
        try:
            from backend.app.core.legal_domain_router import LegalDomain, route_legal_domain
            from backend.app.core.legal_domain_router import filter_chunks_for_domain

            dr = route_legal_domain(parsed.raw)
            if dr.expanded_query:
                parsed = ParsedQuery(
                    raw=parsed.raw,
                    normalized=dr.expanded_query,
                    query_class=parsed.query_class,
                    law_systems=[],
                    sections=[],
                    articles=parsed.articles,
                    mapping_mode=False,
                    constitutional_topic=dr.constitutional_topic or parsed.constitutional_topic,
                    constitutional_article=dr.article or parsed.constitutional_article,
                )
        except Exception:
            dr = None
        chunks = _constitutional_lookup(
            index_dir, parsed, top_k=12 if retry else 10, scope=scope
        )
        chunks = filter_chunks_for_domain(chunks, dr) if dr else chunks
        mode = "constitutional_lookup"
        if re.search(r"\b(?:five|5|name|list)\b.*\b(?:rights?)\b", parsed.raw, re.I):
            try:
                from rag import _load_docstore_only

                view = _load_docstore_only(Path(index_dir))
                if view is not None:
                    rights_parts: List[str] = []
                    for doc_id in view.index_to_docstore_id.values():
                        doc = view.docstore.search(doc_id)
                        body = (getattr(doc, "page_content", None) or "")
                        if re.search(
                            r"\b(?:Right to|Five Constitutional Rights|Article\s+\d+)\b",
                            body,
                            re.I,
                        ):
                            rights_parts.append(body)
                    if rights_parts:
                        merged = "\n".join(rights_parts)
                        meta = dict(getattr(doc, "metadata", None) or {}) if view else {}
                        extra = {
                            "content": merged,
                            "metadata": meta,
                            "final_score": 0.95,
                            "hybrid_score": 0.95,
                            "retrieval_mode": "constitutional_rights_block",
                        }
                        chunks = [extra] + [
                            c
                            for c in chunks
                            if (c.get("content") or "")[:80] != merged[:80]
                        ]
            except Exception:
                pass
        mode = "constitutional_lookup"
        if not chunks:
            try:
                from backend.app.core.kb_retrieval_robust import robust_kb_retrieve

                chunks = robust_kb_retrieve(
                    parsed.normalized,
                    index_dir,
                    scope=scope or {},
                    k=12,
                    constitutional=True,
                )
                if chunks:
                    mode = "constitutional_robust"
            except Exception:
                pass
        if not chunks and parsed.constitutional_article:
            chunks = _constitutional_lookup(
                index_dir,
                ParsedQuery(
                    raw=parsed.raw,
                    normalized=f"Article {parsed.constitutional_article} Constitution",
                    query_class=QueryClass.CONSTITUTIONAL,
                    constitutional_article=parsed.constitutional_article,
                    constitutional_topic=parsed.constitutional_topic,
                ),
                top_k=8,
                scope=scope,
            )
            if chunks:
                mode = "constitutional_article_exact"
        if not chunks:
            try:
                from backend.app.core.legal_domain_router import route_legal_domain, filter_chunks_for_domain

                dr = route_legal_domain(parsed.raw)
                chunks = _vector_search_last(
                    index_dir,
                    dr.expanded_query or parsed.normalized,
                    k=8,
                    scope=scope,
                    exclude_bns=True,
                )
                chunks = filter_chunks_for_domain(chunks, dr)
            except Exception:
                chunks = []
            chunks = [c for c in chunks if not _is_criminal_chunk(c.get("content", ""))]
            mode = "constitutional_vector_fallback"
        return chunks, mode

    if plan.query_class in (QueryClass.MULTI_SECTION,):
        from backend.app.core.kb_strict_retrieval import strict_retrieve_statute_sections

        for sec in plan.sections[:4]:
            sec_hits, _, _ = strict_retrieve_statute_sections(
                index_dir,
                query=parsed.raw,
                sections=[sec],
                law=plan.law,
                scope=scope,
                top_k=4,
                allow_vector_fallback=False,
            )
            chunks.extend(sec_hits)
        return chunks, "multi_section_strict"

    if plan.query_class in (QueryClass.SAME_LAW_COMPARISON, QueryClass.LAW_MAPPING):
        entities = plan.typed_entities
        if plan.query_class == QueryClass.SAME_LAW_COMPARISON:
            for ent in entities[:4]:
                sec = ent.get("section", "")
                law = ent.get("type", plan.law)
                if sec:
                    chunks.extend(_section_lookup_exact(index_dir, sec, law, top_k=5))
            mode = "comparison_exact_per_entity"
            if len(entities) >= 2:
                from kb_compare_engine import ComparisonBundle, _entity_key, _entity_in_chunk

                bundle = ComparisonBundle(entities=entities)
                for ent in entities:
                    key = _entity_key(ent)
                    bundle.entity_chunks[key] = [
                        c
                        for c in chunks
                        if _entity_in_chunk(c.get("content", ""), ent)
                    ]
                if not all(
                    bundle.entity_chunks.get(_entity_key(e)) for e in entities[:2]
                ):
                    try:
                        from kb_compare_engine import retrieve_comparison_bundle

                        bundle_fb = retrieve_comparison_bundle(
                            entities, index_dir, k_per_entity=8
                        )
                        if bundle_fb.all_chunks:
                            chunks = bundle_fb.all_chunks
                            mode = "comparison_bundle_fallback"
                    except Exception:
                        pass
                if retry and not all(
                    bundle.entity_chunks.get(_entity_key(e)) for e in entities[:2]
                ):
                    extra: List[Dict[str, Any]] = []
                    for ent in entities[:4]:
                        sec = ent.get("section", "")
                        law = ent.get("type", plan.law)
                        if sec:
                            extra.extend(
                                _section_lookup_exact(index_dir, sec, law, top_k=6)
                            )
                    if extra:
                        chunks = extra
                        mode = "comparison_retry_exact"
                return chunks, mode
        else:
            from kb_legal_query_rewrite import is_law_replacement_query

            if is_law_replacement_query(parsed.normalized) and len(entities) < 2:
                chunks = _law_replacement_retrieve(index_dir, parsed.raw, scope=scope)
                return chunks, "law_replacement_retrieve"

            from kb_compare_engine import retrieve_comparison_bundle, enrich_entities_with_mapping

            typed = enrich_entities_with_mapping(entities)
            bundle = retrieve_comparison_bundle(typed, index_dir, k_per_entity=8)
            return bundle.all_chunks, "law_mapping_bundle"
        return chunks, mode

    if plan.sections:
        from backend.app.core.kb_strict_retrieval import strict_retrieve_statute_sections

        chunks, mode, _ = strict_retrieve_statute_sections(
            index_dir,
            query=parsed.raw,
            sections=plan.sections[:4],
            law=plan.law,
            scope=scope,
            top_k=8 if retry else 10,
            allow_vector_fallback=False,
        )
        return chunks, mode

    chunks = _vector_search_last(
        index_dir,
        parsed.normalized,
        k=8,
        scope=scope,
        exclude_bns=not plan.allow_bns,
    )
    if not chunks:
        from backend.app.core.kb_retrieval_robust import robust_kb_retrieve

        chunks = robust_kb_retrieve(
            parsed.normalized,
            index_dir,
            scope=scope or {},
            k=12,
            constitutional=parsed.query_class == QueryClass.CONSTITUTIONAL,
        )
        return chunks, "robust_retrieval_fallback"
    return chunks, "vector_general"


def _extract_punishment_line(text: str) -> str:
    try:
        from kb_content_cleaner import extract_punishment_from_block

        pun = extract_punishment_from_block(text or "")
        if pun:
            return pun[:400]
    except ImportError:
        pass
    for raw in re.split(r"[\n.!?]+", text or ""):
        sent = re.sub(r"^#+\s*", "", raw).strip()
        if not sent or sent.endswith("?"):
            continue
        if re.match(r"^Meaning:\s*", sent, re.I):
            sent = re.sub(r"^Meaning:\s*", "", sent, flags=re.I).strip()
        if not sent:
            continue
        if re.match(r"^(?:IPC|BNS)\s*$", sent, re.I):
            continue
        if re.match(r"^(?:IPC|BNS)\s+Section\s+\d", sent, re.I) and not re.search(
            r"\b(imprison|punish|death|life|fine|years)\b", sent, re.I
        ):
            continue
        if re.search(r"\b(imprison|punish|death|life|fine|years|extend)\b", sent, re.I):
            return sent[:400]
    return ""


def _format_section_block(
    section: str,
    chunks: List[Dict[str, Any]],
    law: str,
    *,
    punishment_only: bool = False,
) -> str:
    from kb_preprocess import filter_chunks_for_section
    from answer_orchestrator import format_statute_section_answer

    law_l = (law or "IPC").lower()
    scoped = filter_chunks_for_section(chunks, section, law=law_l)
    body = format_statute_section_answer("", scoped or chunks, section, law_l)

    if punishment_only:
        if body and len(body.strip()) >= 40:
            pun = _extract_punishment_line(body)
            law_u = "BNS" if law_l == "bns" else "IPC"
            try:
                from answer_orchestrator import SECTION_SUBTITLES

                subtitle = SECTION_SUBTITLES.get(section.lower(), "")
            except Exception:
                subtitle = ""
            header = f"## {law_u} Section {section.upper()}"
            if subtitle:
                header += f" — {subtitle}"
            if pun:
                return f"{header}\n\n**Punishment:** {pun}"
            return body.strip()
        excerpt = " ".join((c.get("content") or "")[:400] for c in (scoped or chunks)[:2]).strip()
        if len(excerpt) < 40:
            return ""
        law_u = "BNS" if law_l == "bns" else "IPC"
        try:
            from answer_orchestrator import SECTION_SUBTITLES

            subtitle = SECTION_SUBTITLES.get(section.lower(), "")
        except Exception:
            subtitle = ""
        header = f"## {law_u} Section {section.upper()}"
        if subtitle:
            header += f" — {subtitle}"
        body = f"{header}\n\n{excerpt[:900]}"
        pun = _extract_punishment_line(body)
        if pun:
            return f"{header}\n\n**Punishment:** {pun}"
        return body

    # format_statute_section_answer already builds a full card — do not re-parse lines
    # (naive line split turns "IPC Section 300 Meaning: Murder…" into Meaning: IPC).
    if body and len(body.strip()) >= 60 and re.search(
        rf"\bsection\s*{re.escape(section)}\b", body, re.I
    ):
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "FMT",
                "legal_orchestrator_v2.py:_format_section_block",
                "using_statute_formatter_body",
                {"section": section, "body_len": len(body), "preview": body[:160]},
                run_id="post-fix2",
            )
        except Exception:
            pass
        # endregion
        return body.strip()

    if not body:
        try:
            from kb_preprocess import extract_section_content

            parts: List[str] = []
            for ch in (scoped or chunks)[:4]:
                isolated = extract_section_content(ch.get("content") or "", section)
                if isolated and len(isolated) > 40:
                    parts.append(isolated.strip())
            if parts:
                from answer_orchestrator import SECTION_SUBTITLES

                law_u = "BNS" if law_l == "bns" else "IPC"
                subtitle = SECTION_SUBTITLES.get(section.lower(), "")
                header = f"## {law_u} Section {section.upper()}"
                if subtitle:
                    header += f" — {subtitle}"
                body = f"{header}\n\n{parts[0][:1200]}"
                return body.strip()
        except Exception:
            pass
        excerpt = " ".join((c.get("content") or "")[:400] for c in (scoped or chunks)[:2]).strip()
        if len(excerpt) < 40:
            return ""
        law_u = "BNS" if law_l == "bns" else "IPC"
        try:
            from answer_orchestrator import statute_section_heading

            body = f"{statute_section_heading(section, law_u)}\n\n{excerpt[:900]}"
        except ImportError:
            body = f"## {law_u} Section {section.upper()}\n\n{excerpt[:900]}"
        return body.strip()

    law_u = "BNS" if law_l == "bns" else "IPC"
    try:
        from kb_content_cleaner import format_statute_section_fields

        raw_block = "\n\n".join(
            (c.get("content") or "")[:1400] for c in (scoped or chunks)[:3]
        ).strip()
        if raw_block:
            formatted = format_statute_section_fields(
                raw_block, section=section, law=law_u
            )
            if formatted and re.search(rf"\bsection\s*{re.escape(section)}\b", formatted, re.I):
                return formatted.strip()
    except Exception:
        pass

    title_m = re.search(
        rf"(?:{law_u}|IPC|BNS)\s+Section\s+{re.escape(section)}\s*[—–\-]\s*(.+)$",
        body,
        re.I | re.M,
    )
    title_suffix = f" — {title_m.group(1).strip()}" if title_m else ""
    meaning = ""
    pun = ""
    for line in body.split("\n"):
        ll = line.lower()
        if "punishment" in ll or "imprison" in ll:
            pun = line.strip()
        elif line.strip() and not line.startswith("#"):
            if not meaning:
                meaning = line.strip()
    text = f"## {law_u} Section {section.upper()}{title_suffix}\n\n"
    if meaning:
        text += f"**Meaning:** {meaning}\n\n"
    if pun:
        text += f"**Punishment:** {pun}\n"
    elif _extract_punishment_line(body):
        text += f"**Punishment:** {_extract_punishment_line(body)}\n"
    else:
        text += body.split("\n", 1)[-1] if "\n" in body else body
    return text.strip()


def _expand_section_with_llm(
    parsed: ParsedQuery,
    chunks: List[Dict[str, Any]],
    plan: RetrievalPlan,
    *,
    user_id: str = "",
) -> str:
    """Long-form statute answer from retrieved chunks (Ollama / local generator)."""
    if not chunks or not parsed.sections:
        return ""
    try:
        from backend.app.core.kb_claim_audit import (
            chunk_defines_section,
            try_statute_safe_answer,
        )

        if not chunk_defines_section(chunks, parsed.sections[0]):
            safe = try_statute_safe_answer(parsed.raw or "", chunks)
            if safe:
                return safe
            return ""
    except ImportError:
        pass
    try:
        from answer_orchestrator import synthesize_from_chunks
        from intent_engine import IntentProfile

        sec = parsed.sections[0].upper()
        law_u = (plan.law or "IPC").upper()
        question = (
            f"Explain {law_u} Section {sec} comprehensively using ONLY the excerpts below. "
            f"Structure with headings: Overview, Meaning, Legal Ingredients or Elements, "
            f"Punishment (if stated), Important Elements, Examples, Difference from Related "
            f"Sections (if in excerpts), Practical Interpretation, Source. "
            f"Target 300–600 words when the excerpts support it. Do not invent facts."
        )
        tok = _kb_ollama_max_tokens()
        profile = IntentProfile(
            intent="section_explain",
            complexity="deep",
            max_answer_tokens=tok,
            signals={
                "law": law_u,
                "original_query": parsed.raw,
                "kb_synthesis": True,
                "kb_ollama_instruction": _kb_ollama_instruction_for_class(parsed),
            },
            expanded_query=question,
        )
        return (synthesize_from_chunks(
            question, chunks[:8], profile, user_id=user_id, max_tokens=tok
        ) or "").strip()
    except Exception:
        return ""


def _kb_ollama_max_tokens() -> int:
    import os

    return int(os.getenv("KB_OLLAMA_MAX_TOKENS", "2048"))


def _kb_ollama_instruction_for_class(parsed: "ParsedQuery") -> str:
    """Extra synthesis guidance per query type — legalease-tuned structured output."""
    qc = parsed.query_class
    if qc == QueryClass.SAME_LAW_COMPARISON:
        secs = ", ".join(parsed.sections[:4]) if parsed.sections else "each provision"
        return (
            f"Compare {secs} using a markdown table (columns: Aspect | First | Second) "
            "then ### Key Differences with specific distinctions from the documents."
        )
    if qc == QueryClass.CONSTITUTIONAL:
        return (
            "Explain constitutional/fundamental rights from the excerpts with ## headings. "
            "List each right with its Article number and a clear 1–3 sentence explanation."
        )
    if qc == QueryClass.SINGLE_SECTION and parsed.sections:
        law = (parsed.law_systems[0] if parsed.law_systems else "IPC").upper()
        sec = parsed.sections[0].upper()
        return (
            f"Full {law} Section {sec} analysis: ## Overview, ### Meaning, ### Legal ingredients, "
            "### Punishment, ### Examples, ### Key legal point — all from excerpts only."
        )
    if qc == QueryClass.CASE_LAW:
        return (
            "Case answer: ## Case summary, ### Parties, ### Facts, ### Legal issue, "
            "### Outcome — grounded in the document excerpts."
        )
    if qc == QueryClass.DOCUMENT_QA:
        return (
            "Document-focused answer with ## title and ### subsections; "
            "extract parties, obligations, and key terms from the excerpts."
        )
    if qc == QueryClass.MULTI_SECTION:
        return "Answer each requested section in separate ### blocks with clear headings."
    return ""


def _enrich_comparison_narrative(
    question: str,
    table_answer: str,
    chunks: List[Dict[str, Any]],
    *,
    user_id: str = "",
) -> str:
    """Ollama narrative for Key Difference when deterministic text is thin."""
    m = re.search(r"## Key Difference\s*\n+(.*?)(?:\n##|\Z)", table_answer, re.S)
    diff = (m.group(1).strip() if m else "")
    if len(diff) >= 120:
        return table_answer
    try:
        from answer_orchestrator import NOT_FOUND, synthesize_from_chunks
        from intent_engine import classify_intent

        profile = classify_intent(question, None)
        tok = _kb_ollama_max_tokens()
        profile.complexity = "deep"
        profile.max_answer_tokens = tok
        profile.signals = dict(profile.signals or {})
        profile.signals["original_query"] = question
        profile.signals["kb_synthesis"] = True
        prompt_q = (
            f"Using ONLY the document excerpts, explain the key legal difference "
            f"for this comparison. User question: {question}"
        )
        global _last_kb_synthesis_meta
        _last_kb_synthesis_meta["ollama_invoked"] = True
        narrative = (
            synthesize_from_chunks(
                prompt_q,
                chunks[:8],
                profile,
                user_id=user_id,
                max_tokens=tok,
            )
            or ""
        ).strip()
        if not narrative or narrative == NOT_FOUND or len(narrative) < len(diff) + 40:
            return table_answer
        return re.sub(
            r"(## Key Difference\s*\n+)(.*?)(?=\n##|\Z)",
            rf"\1{narrative}\n",
            table_answer,
            count=1,
            flags=re.S,
        )
    except Exception:
        return table_answer


def _ollama_kb_answer(
    parsed: ParsedQuery,
    plan: RetrievalPlan,
    chunks: List[Dict[str, Any]],
    *,
    user_id: str = "",
    history: Optional[List[Dict]] = None,
    search_q: str = "",
    force_explanation_mode: bool = False,
) -> str:
    """Primary KB synthesis — Ollama legalease-tuned (highest priority, structured, detailed)."""
    import os

    try:
        from backend.app.core.kb_dense_document import (
            ollama_synthesis_mode,
            should_invoke_ollama,
            should_ollama_polish_only,
            try_dense_document_answer,
        )

        if not should_invoke_ollama():
            return ""
        if should_ollama_polish_only():
            extractive = try_dense_document_answer(
                (parsed.raw or search_q or "").strip(),
                chunks,
            )
            if extractive:
                if not force_explanation_mode:
                    return extractive
            elif force_explanation_mode:
                return ""
    except ImportError:
        mode = (os.getenv("KB_USE_OLLAMA_SYNTHESIS") or "0").lower()
        if mode not in {"1", "true", "yes", "hybrid", "polish"}:
            return ""
    if not chunks:
        return ""
    try:
        from answer_orchestrator import NOT_FOUND, synthesize_from_chunks
        from intent_engine import classify_intent

        question = (parsed.raw or search_q or "").strip()
        profile = classify_intent(question, history)
        profile.complexity = "deep"
        tok_cap = _kb_ollama_max_tokens()
        if force_explanation_mode:
            tok_cap = min(max(tok_cap, 768), 1024)
        profile.max_answer_tokens = max(int(profile.max_answer_tokens or 0), tok_cap)
        signals = dict(profile.signals or {})
        signals["original_query"] = parsed.raw
        try:
            from backend.app.core.kb_dense_document import (
                should_ollama_polish_only,
                try_dense_document_answer,
            )

            if should_ollama_polish_only():
                pre = try_dense_document_answer(question, chunks)
                if pre:
                    signals["kb_extractive_prefill"] = pre[:3500]
                    signals["kb_ollama_instruction"] = (
                        "Polish the EXTRACTIVE PREFILL below using ONLY that text. "
                        "Do not add statutes, cases, or facts not in the prefill."
                    )
        except ImportError:
            pass
        try:
            from backend.app.core.kb_strict_policy import prepare_kb_synthesis_signals

            signals = prepare_kb_synthesis_signals(signals)
        except ImportError:
            signals["kb_synthesis"] = True
        try:
            from backend.app.core.kb_explanation_mode import (
                apply_explanation_signals,
                explanation_mode_active,
            )

            if force_explanation_mode or explanation_mode_active(question):
                qclass = parsed.query_class.value if parsed.query_class else ""
                signals = apply_explanation_signals(
                    signals, question, query_class=qclass
                )
            else:
                signals["kb_ollama_instruction"] = _kb_ollama_instruction_for_class(parsed)
        except ImportError:
            signals["kb_ollama_instruction"] = _kb_ollama_instruction_for_class(parsed)
        if parsed.sections:
            signals["sections"] = list(parsed.sections)
        if plan.law:
            signals["law"] = (plan.law or "IPC").upper()
        try:
            from backend.app.core.kb_request_classifier import classify_kb_request

            signals["kb_classification"] = classify_kb_request(question)
        except Exception:
            pass
        profile.signals = signals

        global _last_kb_synthesis_meta
        _last_kb_synthesis_meta["ollama_invoked"] = True
        try:
            from backend.app.core.kb_strict_policy import kb_llm_temperature

            kb_temp = kb_llm_temperature()
        except ImportError:
            kb_temp = 0.0
        raw = synthesize_from_chunks(
            question,
            chunks[:10],
            profile,
            user_id=user_id,
            temperature=kb_temp if force_explanation_mode else kb_temp,
            max_tokens=tok_cap,
        )
        raw = (raw or "").strip()
        if force_explanation_mode and raw:
            try:
                from backend.app.core.kb_explanation_mode import sanitize_explanation_answer

                raw = sanitize_explanation_answer(raw, chunks) or raw
            except ImportError:
                pass
        try:
            from llms import is_ollama_error_response

            if is_ollama_error_response(raw):
                raw = ""
        except ImportError:
            pass
        if not raw or raw == NOT_FOUND:
            # AWS-only fallback when Ollama is not on the server (CLOUD_GEMINI_KB=1). Local dev uses Ollama only.
            try:
                from backend.app.core.cloud_kb_gemini import (
                    cloud_kb_gemini_enabled,
                    synthesize_kb_cloud_gemini,
                )

                if cloud_kb_gemini_enabled():
                    cloud = synthesize_kb_cloud_gemini(
                        question,
                        chunks,
                        user_id=user_id,
                        max_tokens=tok_cap,
                    )
                    if (cloud or "").strip():
                        return cloud.strip()
            except Exception:
                pass
            return ""
        low = raw.lower()
        if "couldn't find" in low[:220] or "not found in" in low[:220]:
            return ""
        if raw.startswith("❌"):
            return ""
        try:
            from backend.app.core.kb_strict_policy import (
                answer_has_outside_knowledge_bleed,
                chunks_support_query_topic,
            )

            if answer_has_outside_knowledge_bleed(raw):
                return ""
            if not chunks_support_query_topic(question, chunks):
                return ""
        except ImportError:
            pass
        return raw
    except Exception:
        return ""


def generate_answer(
    parsed: ParsedQuery,
    plan: RetrievalPlan,
    chunks: List[Dict[str, Any]],
    *,
    user_id: str = "",
    index_dir: Any = None,
    history: Optional[List[Dict]] = None,
    search_q: str = "",
) -> str:
    from kb_response_state import enforce_single_state

    reset_kb_synthesis_meta()

    if not chunks and parsed.query_class != QueryClass.GENERAL_LEGAL:
        return ""

    expl_question = (search_q or parsed.raw or "").strip()

    if chunks and expl_question:
        try:
            from backend.app.core.kb_question_aware import generate_question_aware_answer

            qa_ans = generate_question_aware_answer(
                expl_question,
                chunks,
                index_dir=index_dir,
            )
            if qa_ans:
                return enforce_single_state(qa_ans, found=True)
        except ImportError:
            pass

    try:
        from backend.app.core.kb_case_context_lock import (
            is_case_locked_query,
            strip_query_context_suffix,
        )

        case_locked = (
            parsed.query_class == QueryClass.CASE_LAW
            or is_case_locked_query(expl_question)
        )
        clean_case_q = strip_query_context_suffix(expl_question)
    except ImportError:
        case_locked = parsed.query_class == QueryClass.CASE_LAW
        clean_case_q = expl_question

    if case_locked and chunks:
        from answer_orchestrator import format_case_topic_answer

        try:
            from backend.app.core.kb_landmark_case import is_landmark_case_query

            if is_landmark_case_query(clean_case_q):
                from backend.app.core.kb_landmark_case import build_landmark_case_answer

                landmark_ans = build_landmark_case_answer(clean_case_q, chunks)
                if landmark_ans:
                    return enforce_single_state(landmark_ans, found=True)
                from kb_response_state import KB_NOT_FOUND_MESSAGE

                return enforce_single_state(KB_NOT_FOUND_MESSAGE, found=False)
        except ImportError:
            pass

        try:
            from backend.app.core.kb_case_context_lock import lock_chunks_to_query

            chunks = lock_chunks_to_query(
                clean_case_q, chunks, index_dir=index_dir
            )
        except ImportError:
            pass

        case_ans = format_case_topic_answer(clean_case_q, chunks)
        if case_ans:
            # region agent log
            try:
                from backend.app.core.debug_session_log import debug_log

                debug_log(
                    "H3",
                    "legal_orchestrator_v2.py:generate_answer",
                    "case_locked_answer",
                    {
                        "query": clean_case_q[:100],
                        "answer_len": len(case_ans),
                        "preview": case_ans[:180],
                    },
                )
            except Exception:
                pass
            # endregion
            return enforce_single_state(case_ans, found=True)

        try:
            from kb_response_state import KB_NOT_FOUND_MESSAGE

            return enforce_single_state(KB_NOT_FOUND_MESSAGE, found=False)
        except ImportError:
            return ""

    if not case_locked:
        try:
            from backend.app.core.kb_dense_document import try_dense_document_answer

            dense_ans = try_dense_document_answer(
                expl_question,
                chunks,
                index_dir=index_dir,
            )
            if dense_ans:
                return enforce_single_state(dense_ans, found=True)
        except ImportError:
            pass
        try:
            from kb_legal_query_rewrite import (
                extract_law_mapping_answer,
                is_law_replacement_query,
            )
            from citation_formatter import polish_kb_response

            if is_law_replacement_query(expl_question):
                mapped = extract_law_mapping_answer(expl_question, chunks)
                if mapped:
                    return enforce_single_state(
                        polish_kb_response(mapped, chunks), found=True
                    )
        except ImportError:
            pass
        try:
            from backend.app.core.kb_document_first import try_statute_section_lookup_answer

            statute_ans = try_statute_section_lookup_answer(expl_question, chunks)
            if statute_ans:
                return enforce_single_state(statute_ans, found=True)
        except ImportError:
            pass
        try:
            from backend.app.core.constitutional_concept_map import (
                is_constitutional_rights_list_query,
            )
            from answer_orchestrator import format_constitutional_rights_answer

            if is_constitutional_rights_list_query(expl_question):
                scoped = chunks
                try:
                    from backend.app.core.legal_domain_router import (
                        filter_chunks_for_domain,
                        route_legal_domain,
                    )

                    dr = route_legal_domain(expl_question)
                    scoped = filter_chunks_for_domain(chunks, dr)
                except Exception:
                    pass
                const_ans = format_constitutional_rights_answer(expl_question, scoped)
                if const_ans:
                    return enforce_single_state(const_ans, found=True)
        except ImportError:
            pass
        try:
            from backend.app.core.kb_claim_audit import try_statute_safe_answer

            statute_safe = try_statute_safe_answer(expl_question, chunks)
            if statute_safe:
                return enforce_single_state(statute_safe, found=True)
        except ImportError:
            pass
        try:
            from backend.app.core.kb_document_first import build_document_first_answer

            doc_first = build_document_first_answer(expl_question, chunks)
            if doc_first:
                return enforce_single_state(doc_first, found=True)
        except ImportError:
            pass
    try:
        from backend.app.core.kb_explanation_mode import (
            explanation_mode_active,
            looks_like_chunk_dump,
        )

        if (
            chunks
            and explanation_mode_active(expl_question)
            and parsed.query_class != QueryClass.CONSTITUTIONAL
        ):
            try:
                from backend.app.core.kb_claim_audit import try_statute_safe_answer

                statute_safe = try_statute_safe_answer(expl_question, chunks)
                if statute_safe:
                    return enforce_single_state(statute_safe, found=True)
            except ImportError:
                pass

            from backend.app.core.kb_explanation_mode import build_explanation_from_chunks
            from backend.app.core.kb_strict_policy import chunks_support_query_topic

            if not chunks_support_query_topic(expl_question, chunks):
                strict_fb = build_explanation_from_chunks(
                    expl_question, chunks, strict=True
                )
                if strict_fb:
                    return enforce_single_state(strict_fb, found=True)

            ollama_ans = _ollama_kb_answer(
                parsed,
                plan,
                chunks,
                user_id=user_id,
                history=history,
                search_q=search_q,
                force_explanation_mode=True,
            )
            try:
                from backend.app.core.kb_strict_policy import answer_has_outside_knowledge_bleed

                if answer_has_outside_knowledge_bleed(ollama_ans):
                    ollama_ans = ""
            except ImportError:
                pass
            if ollama_ans and not looks_like_chunk_dump(ollama_ans) and len(ollama_ans.strip()) > 120:
                # region agent log
                try:
                    from backend.app.core.debug_kb_session import dbg_kb

                    dbg_kb(
                        "H5",
                        "legal_orchestrator_v2.py:generate_answer",
                        "explanation_mode_ollama",
                        {
                            "query": expl_question[:100],
                            "answer_len": len(ollama_ans),
                            "qclass": parsed.query_class.value,
                        },
                        run_id="post-fix",
                    )
                except Exception:
                    pass
                # endregion
                return enforce_single_state(ollama_ans, found=True)
            fallback = build_explanation_from_chunks(expl_question, chunks, strict=True)
            if fallback and len(fallback.strip()) > 150:
                return enforce_single_state(fallback, found=True)
    except Exception:
        pass

    meta_fu = False
    try:
        from conversation_context import is_meta_follow_up

        meta_fu = is_meta_follow_up(parsed.raw or "")
    except ImportError:
        pass
    if meta_fu and parsed.sections and parsed.query_class in (
        QueryClass.GENERAL_LEGAL,
        QueryClass.DOCUMENT_QA,
        QueryClass.CASE_LAW,
    ):
        parsed = ParsedQuery(
            raw=parsed.raw,
            normalized=parsed.normalized,
            query_class=QueryClass.SINGLE_SECTION,
            law_systems=parsed.law_systems,
            sections=parsed.sections,
            articles=parsed.articles,
            typed_entities=parsed.typed_entities,
            mapping_mode=parsed.mapping_mode,
            constitutional_topic=parsed.constitutional_topic,
            constitutional_article=parsed.constitutional_article,
        )

    skip_document_qa = meta_fu and bool(parsed.sections)
    if (
        parsed.query_class in (QueryClass.GENERAL_LEGAL, QueryClass.DOCUMENT_QA)
        and chunks
        and not skip_document_qa
    ):
        try:
            from backend.app.core.case_narrative_engine import build_entity_document_answer

            entity_ans = build_entity_document_answer(parsed.raw, chunks)
            if entity_ans and "(cid:" not in entity_ans:
                return enforce_single_state(entity_ans, found=True)
        except Exception:
            pass
        try:
            from backend.app.core.universal_kb import universal_document_answer

            ans = universal_document_answer(
                parsed.raw,
                chunks,
                user_id=user_id,
                use_llm=True,
            )
            if ans and "From your uploaded documents" not in ans[:80]:
                return enforce_single_state(ans, found=True)
            if ans and len(ans) < 900:
                return enforce_single_state(ans, found=True)
        except Exception:
            pass
        try:
            from backend.app.core.case_narrative_engine import build_entity_document_answer

            entity_ans = build_entity_document_answer(parsed.raw, chunks)
            if entity_ans:
                return enforce_single_state(entity_ans, found=True)
        except Exception:
            pass
        try:
            from backend.app.core.kb_force_answer import guarantee_kb_answer

            ans = guarantee_kb_answer(parsed.raw, chunks)
            if ans:
                return enforce_single_state(ans, found=True)
        except Exception:
            pass

    if parsed.query_class == QueryClass.CONSTITUTIONAL:
        ql = parsed.normalized.lower()
        try:
            from backend.app.core.constitutional_concept_map import (
                format_article_answer,
                list_rights_answer,
            )
            from backend.app.core.legal_domain_router import filter_chunks_for_domain, route_legal_domain

            dr = route_legal_domain(parsed.raw)
            chunks = filter_chunks_for_domain(chunks, dr)
        except Exception:
            format_article_answer = None  # type: ignore
            list_rights_answer = None  # type: ignore

        try:
            from backend.app.core.kb_explanation_mode import explanation_mode_active

            skip_list_formatter = (
                explanation_mode_active(parsed.raw or "")
                and not re.search(r"\bexplain\b", ql)
            )
        except ImportError:
            skip_list_formatter = bool(re.search(r"\bexplain\b", ql)) is False

        if not skip_list_formatter and (
            re.search(
                r"\b(?:what are|name|list|enumerate|five|5)\b.*\b(?:rights?)\b", ql
            )
            or re.search(r"\b(?:fundamental|constitutional)\s+rights?\b", ql)
        ):
            from answer_orchestrator import format_constitutional_rights_answer

            ans = format_constitutional_rights_answer(parsed.raw, chunks)
            if not ans and list_rights_answer:
                ans = list_rights_answer(chunks)
            if ans and len(ans) > 120:
                return enforce_single_state(ans, found=True)

        art = parsed.constitutional_article
        topic = parsed.constitutional_topic
        if art or (
            topic and topic not in ("constitutional rights", "fundamental rights")
        ):
            combined = "\n".join((c.get("content") or "") for c in chunks)
            snippet = ""
            try:
                from backend.app.core.constitutional_concept_map import extract_article_snippet

                for line in combined.split("\n"):
                    if _is_criminal_chunk(line):
                        continue
                    isolated = extract_article_snippet(line, art or "", topic=topic) if art else ""
                    if isolated:
                        snippet = isolated
                        break
            except ImportError:
                extract_article_snippet = None  # type: ignore

            if not snippet:
                for line in combined.split("\n"):
                    ll = line.lower()
                    if _is_criminal_chunk(line):
                        continue
                    if topic and topic in ll:
                        snippet = line.strip()
                        break
                    if art and re.search(rf"\barticle\s*{re.escape(art)}\b", ll, re.I):
                        snippet = line.strip()
                        break
            if snippet and art:
                try:
                    from backend.app.core.constitutional_concept_map import extract_article_snippet

                    snippet = extract_article_snippet(snippet, art, topic=topic) or snippet
                except ImportError:
                    pass
            if format_article_answer and art:
                body = format_article_answer(
                    art,
                    topic=topic,
                    doc_snippet=snippet,
                    chunks=chunks,
                )
                return enforce_single_state(body, found=True)
            if snippet:
                from answer_orchestrator import polish_kb_response

                title = f"Article {art.upper()}" if art else (topic.title() if topic else "Constitutional Right")
                return enforce_single_state(
                    polish_kb_response(f"## {title}\n\n{snippet}", chunks), found=True
                )
        if not skip_list_formatter:
            from answer_orchestrator import format_constitutional_rights_answer

            ans = format_constitutional_rights_answer(parsed.raw, chunks)
            if not ans and list_rights_answer:
                ans = list_rights_answer(chunks)
            if ans:
                return enforce_single_state(ans, found=True)
        if format_article_answer and parsed.constitutional_article:
            return enforce_single_state(
                format_article_answer(
                    parsed.constitutional_article,
                    topic=topic,
                    chunks=chunks,
                ),
                found=True,
            )
        return ""

    if parsed.query_class == QueryClass.MULTI_SECTION:
        blocks: List[str] = []
        for sec in parsed.sections[:4]:
            sec_chunks = [
                c
                for c in chunks
                if re.search(rf"\b{re.escape(sec)}\b", c.get("content", ""), re.I)
            ]
            if not sec_chunks and index_dir:
                sec_chunks = _section_lookup_exact(index_dir, sec, plan.law, top_k=4)
            block = _format_section_block(
                sec, sec_chunks or chunks, plan.law, punishment_only=False
            )
            if block:
                blocks.append(block)
        if blocks:
            from citation_formatter import polish_kb_response

            combined = "\n\n---\n\n".join(blocks)
            return enforce_single_state(polish_kb_response(combined, chunks), found=True)
        return ""

    if parsed.query_class == QueryClass.LAW_MAPPING:
        try:
            from kb_legal_query_rewrite import (
                build_baseline_law_answer,
                extract_law_mapping_answer,
                is_law_replacement_query,
            )
            from citation_formatter import polish_kb_response

            if is_law_replacement_query(parsed.raw) and len(plan.typed_entities) < 2:
                ans = extract_law_mapping_answer(parsed.raw, chunks) or build_baseline_law_answer(
                    parsed.raw
                )
                if ans:
                    return enforce_single_state(polish_kb_response(ans, chunks), found=True)

            if len(plan.typed_entities) >= 2:
                from kb_compare_engine import format_comparison_pro

                ans = format_comparison_pro(
                    parsed.raw,
                    chunks,
                    plan.typed_entities,
                    mapping_mode=parsed.mapping_mode,
                )
                cleaned = enforce_single_state(ans, found=True)
                if cleaned:
                    return cleaned
                ans = extract_law_mapping_answer(parsed.raw, chunks) or build_baseline_law_answer(
                    parsed.raw
                )
                if ans:
                    return enforce_single_state(polish_kb_response(ans, chunks), found=True)
            else:
                ans = extract_law_mapping_answer(parsed.raw, chunks) or build_baseline_law_answer(
                    parsed.raw
                )
                if ans:
                    return enforce_single_state(polish_kb_response(ans, chunks), found=True)
        except Exception:
            pass
        return ""

    if parsed.query_class == QueryClass.SAME_LAW_COMPARISON:
        from kb_compare_engine import format_comparison_pro

        typed = plan.typed_entities
        ans = format_comparison_pro(
            parsed.raw,
            chunks,
            typed,
            mapping_mode=parsed.mapping_mode,
        )
        if ans:
            ans = _enrich_comparison_narrative(
                parsed.raw, ans, chunks, user_id=user_id
            )
            return enforce_single_state(ans, found=True)
        return ""

    if parsed.query_class == QueryClass.SECTION_PUNISHMENT and parsed.sections:
        block = _format_section_block(
            parsed.sections[0], chunks, plan.law, punishment_only=True
        )
        if block:
            return enforce_single_state(block, found=True)

    if parsed.query_class == QueryClass.SINGLE_SECTION and parsed.sections:
        if not chunks:
            return ""
        block = _format_section_block(parsed.sections[0], chunks, plan.law)
        if block:
            try:
                from backend.app.core.kb_strict_retrieval import (
                    attach_retrieval_debug_footer,
                    wants_detailed_section_answer,
                )

                detail_q = (search_q or parsed.raw or "").strip()
                need_expand = _kb_section_llm_expand_enabled() and (
                    wants_detailed_section_answer(detail_q)
                    or len(block.strip()) < 600
                )
                if need_expand:
                    expanded = _expand_section_with_llm(
                        parsed, chunks, plan, user_id=user_id
                    )
                    if expanded and len(expanded.strip()) > len(block.strip()):
                        block = expanded
                block = attach_retrieval_debug_footer(block, chunks)
            except Exception:
                pass
            return enforce_single_state(block, found=True)
        try:
            from backend.app.core.kb_force_answer import guarantee_kb_answer

            forced = guarantee_kb_answer(parsed.raw, chunks)
            if forced:
                return enforce_single_state(forced, found=True)
        except Exception:
            pass

    if parsed.query_class == QueryClass.CASE_LAW:
        from answer_orchestrator import format_case_topic_answer

        ans = format_case_topic_answer(
            (search_q or parsed.raw or "").strip(),
            chunks,
        )
        # region agent log
        try:
            from backend.app.core.debug_kb_session import dbg_kb

            dbg_kb(
                "H3",
                "legal_orchestrator_v2.py:generate_answer",
                "case_law_answer",
                {
                    "query": (parsed.raw or "")[:80],
                    "answer_len": len(ans or ""),
                    "preview": (ans or "")[:200],
                },
            )
        except Exception:
            pass
        # endregion
        if ans:
            return enforce_single_state(ans, found=True)

    if parsed.query_class == QueryClass.ENTITY_LOOKUP and index_dir is not None:
        from kb_pipeline import _try_entity_lookup_answer

        scope_hint: Dict[str, Any] = {}
        ans = _try_entity_lookup_answer(
            user_id,
            parsed.raw,
            scope_hint,
            index_dir,
            chunks=chunks,
        )
        if ans:
            return enforce_single_state(ans, found=True)

    if parsed.query_class == QueryClass.LAW_MAPPING and not plan.typed_entities:
        try:
            from kb_legal_query_rewrite import extract_law_mapping_answer, build_baseline_law_answer
            from citation_formatter import polish_kb_response

            ans = extract_law_mapping_answer(parsed.raw, chunks) or build_baseline_law_answer(
                parsed.raw
            )
            if ans:
                return enforce_single_state(polish_kb_response(ans, chunks), found=True)
        except Exception:
            pass

    # Ollama only after fast deterministic paths — skip duplicate pass for explanation queries.
    try:
        from backend.app.core.kb_explanation_mode import explanation_mode_active

        if explanation_mode_active((search_q or parsed.raw or "").strip()):
            return ""
    except ImportError:
        pass

    ollama_ans = _ollama_kb_answer(
        parsed,
        plan,
        chunks,
        user_id=user_id,
        history=history,
        search_q=search_q,
    )
    if ollama_ans:
        return enforce_single_state(ollama_ans, found=True)

    return ""


def _kb_section_llm_expand_enabled() -> bool:
    """Skip extra Ollama pass on section cards when KB_FAST_SECTION=1 (default)."""
    import os

    if os.getenv("KB_SECTION_LLM_EXPAND", "0").lower() in {"1", "true", "yes"}:
        return True
    return os.getenv("KB_FAST_SECTION", "1").lower() not in {"1", "true", "yes"}


def validate_response(parsed: ParsedQuery, answer: str) -> Tuple[bool, str]:
    text = (answer or "").strip()
    if not text:
        return False, "empty_answer"

    al = text.lower()

    if not parsed.mapping_mode and _BNS_FORBIDDEN_IN_ANSWER.search(al):
        return False, "unwanted_bns_or_mapping"

    if parsed.query_class == QueryClass.CONSTITUTIONAL:
        if re.search(r"\bipc\s+section\s+\d{1,4}\b", al) and not re.search(
            r"\barticle\s+\d", al
        ):
            return False, "ipc_drift_in_constitutional"
        if _CRIMINAL_CHUNK_RE.search(al) and not parsed.sections:
            if "article" not in al and "right" not in al:
                return False, "criminal_drift"
        if parsed.constitutional_article and parsed.constitutional_article not in al:
            if "equality" not in al and parsed.constitutional_article == "14":
                pass
            elif f"article {parsed.constitutional_article}" not in al.replace("  ", " "):
                if parsed.constitutional_topic and parsed.constitutional_topic.split()[-1] not in al:
                    return False, f"missing_article_{parsed.constitutional_article}"

    if parsed.query_class == QueryClass.MULTI_SECTION:
        for sec in parsed.sections[:4]:
            if not re.search(rf"\b{re.escape(sec)}\b", al):
                return False, f"missing_section_{sec}"

    if parsed.query_class in (QueryClass.SAME_LAW_COMPARISON,):
        for sec in parsed.sections[:4]:
            if sec and not re.search(rf"\b{re.escape(sec)}\b", al):
                return False, f"missing_compare_section_{sec}"

    if parsed.query_class == QueryClass.SECTION_PUNISHMENT and parsed.sections:
        sec = parsed.sections[0]
        wrong = re.findall(r"\bipc\s*(?:section\s*)?(\d{1,4})\b", al, re.I)
        for w in wrong:
            if w != sec:
                return False, f"wrong_section_{w}"
        if sec not in al:
            return False, f"missing_section_{sec}"

    if parsed.query_class == QueryClass.SINGLE_SECTION and parsed.sections:
        sec = parsed.sections[0].lower()
        if sec not in al:
            return False, f"missing_section_{sec}"
        wrong_ipc = re.findall(r"\b(?:ipc|bns)\s*(?:section\s*)?(\d{1,4}[a-z]?)\b", al, re.I)
        for w in wrong_ipc:
            if w.lower() != sec:
                return False, f"wrong_section_{w}"

    return True, "ok"


class LegalOrchestratorV2:
    """Master KB controller — no retrieval before orchestration completes."""

    def run(
        self,
        user_id: str,
        query: str,
        history: Optional[List[Dict]] = None,
        index_dir: Any = None,
        thread_id: Optional[str] = None,
        session_id: Optional[str] = None,
        retrieval_query: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        from backend.app.core.resource_scheduler import Priority, acquire

        with acquire(Priority.KB_ANSWER, "kb_orchestrator") as slot:
            if not slot.get("ok"):
                pass  # still attempt answer — never hard-fail chat for scheduler
            return self._run_inner(
                user_id,
                query,
                history=history,
                index_dir=index_dir,
                thread_id=thread_id,
                session_id=session_id,
                retrieval_query=retrieval_query,
            )

    def _run_inner(
        self,
        user_id: str,
        query: str,
        history: Optional[List[Dict]] = None,
        index_dir: Any = None,
        thread_id: Optional[str] = None,
        session_id: Optional[str] = None,
        retrieval_query: Optional[str] = None,
    ) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
        from app import get_user_index_dir
        from kb_response_state import KB_NOT_FOUND_MESSAGE

        if index_dir is None:
            try:
                from app import resolve_rag_index_dir

                index_dir = resolve_rag_index_dir(user_id)
            except Exception:
                index_dir = get_user_index_dir(user_id)

        diag = OrchestratorDiag()
        from backend.app.core.kb_pipeline_trace import PipelineTracer, bypass_retrieval_filters

        trace = PipelineTracer(query)
        trace.stage("query_received", ok=True, detail={"query": (query or "")[:120]})
        try:
            from backend.app.core.kb_query_clean import strip_chat_routing_prefix

            query = strip_chat_routing_prefix(query) or query
        except Exception:
            pass
        search_q = (retrieval_query or query or "").strip() or query
        try:
            from backend.app.core.kb_query_clean import strip_chat_routing_prefix

            search_q = strip_chat_routing_prefix(search_q) or search_q
        except Exception:
            pass
        try:
            from conversation_context import is_meta_follow_up

            if is_meta_follow_up(query or "") and session_id:
                from backend.app.core.conversation_memory import get_session_legal_memory

                mem = get_session_legal_memory(session_id)
                last_q = str(mem.get("last_user_query") or "").strip()
                if last_q and len((query or "").split()) <= 4:
                    search_q = f"{query} {last_q}".strip()
        except Exception:
            pass
        try:
            from backend.app.core.kb_strict_retrieval import (
                enrich_query_sections_from_history,
                parse_structured_query,
            )

            search_q = enrich_query_sections_from_history(
                query, history, session_id
            ) or search_q
        except Exception:
            pass
        parsed = parse_query(search_q)
        try:
            from backend.app.core.kb_strict_retrieval import parse_structured_query

            structured_orig = parse_structured_query(query)
            structured_search = parse_structured_query(search_q)
            structured = (
                structured_orig
                if structured_orig.sections
                else structured_search
            )
            try:
                from backend.app.services.followup_detector import requires_fresh_retrieval

                if requires_fresh_retrieval(query):
                    structured = structured_orig
            except ImportError:
                pass
            if structured.sections:
                if not parsed.sections:
                    parsed = ParsedQuery(
                        raw=query,
                        normalized=parsed.normalized,
                        query_class=parsed.query_class,
                        law_systems=[structured.legal_code.lower()],
                        sections=structured.sections,
                        articles=parsed.articles,
                        typed_entities=parsed.typed_entities,
                        mapping_mode=parsed.mapping_mode,
                        constitutional_topic=parsed.constitutional_topic,
                        constitutional_article=parsed.constitutional_article,
                    )
                if (
                    parsed.query_class in (
                        QueryClass.GENERAL_LEGAL,
                        QueryClass.DOCUMENT_QA,
                        QueryClass.CASE_LAW,
                    )
                    and structured_orig.sections
                ):
                    qclass = (
                        QueryClass.SECTION_PUNISHMENT
                        if _PUNISH_RE.search((query or "").lower())
                        else QueryClass.SINGLE_SECTION
                    )
                    parsed = ParsedQuery(
                        raw=query,
                        normalized=parsed.normalized,
                        query_class=qclass,
                        law_systems=[structured.legal_code.lower()],
                        sections=structured_orig.sections,
                        articles=parsed.articles,
                        typed_entities=parsed.typed_entities,
                        mapping_mode=parsed.mapping_mode,
                        constitutional_topic=parsed.constitutional_topic,
                        constitutional_article=parsed.constitutional_article,
                    )
        except Exception:
            pass
        parsed = _enrich_parsed_from_context(
            parsed,
            original_query=query,
            search_q=search_q,
            history=history,
            session_id=session_id,
        )
        try:
            from backend.app.services.followup_detector import requires_fresh_retrieval

            if requires_fresh_retrieval(query):
                diag.validation["context_reset"] = True
        except Exception:
            pass
        parsed = ParsedQuery(
            raw=query,
            normalized=parsed.normalized,
            query_class=parsed.query_class,
            law_systems=parsed.law_systems,
            sections=parsed.sections,
            articles=parsed.articles,
            typed_entities=parsed.typed_entities,
            mapping_mode=parsed.mapping_mode,
            constitutional_topic=parsed.constitutional_topic,
            constitutional_article=parsed.constitutional_article,
        )
        try:
            from conversation_context import is_meta_follow_up

            meta_fu_early = is_meta_follow_up(query or "")
            if meta_fu_early and not parsed.sections and session_id:
                from backend.app.core.conversation_memory import get_session_legal_memory

                mem = get_session_legal_memory(session_id)
                if mem.get("last_case"):
                    parsed = ParsedQuery(
                        raw=query,
                        normalized=parsed.normalized,
                        query_class=QueryClass.CASE_LAW,
                        law_systems=[],
                        sections=[],
                        articles=parsed.articles,
                        typed_entities=parsed.typed_entities,
                        mapping_mode=parsed.mapping_mode,
                        constitutional_topic=parsed.constitutional_topic,
                        constitutional_article=parsed.constitutional_article,
                    )
                elif mem.get("last_section"):
                    parsed = ParsedQuery(
                        raw=query,
                        normalized=parsed.normalized,
                        query_class=QueryClass.SINGLE_SECTION,
                        law_systems=[
                            str(mem.get("last_law") or "ipc").lower()
                        ],
                        sections=[str(mem["last_section"]).lower()],
                        articles=parsed.articles,
                        typed_entities=parsed.typed_entities,
                        mapping_mode=parsed.mapping_mode,
                        constitutional_topic=parsed.constitutional_topic,
                        constitutional_article=parsed.constitutional_article,
                    )
        except Exception:
            meta_fu_early = False
        # region agent log
        try:
            from backend.app.core.kb_runtime_debug import kb_runtime_log
            from conversation_context import is_meta_follow_up

            kb_runtime_log(
                "B",
                "legal_orchestrator_v2.py:_run_inner",
                "kb_query_resolved",
                {
                    "user_query": (query or "")[:80],
                    "search_q": (search_q or "")[:160],
                    "is_meta_follow_up": bool(is_meta_follow_up(query or "")),
                    "query_class": parsed.query_class.value,
                    "sections": list(parsed.sections)[:3],
                },
            )
        except Exception:
            pass
        # endregion
        diag.query_class = parsed.query_class.value
        diag.mapping_mode = parsed.mapping_mode
        diag.sections_requested = list(parsed.sections)
        trace.stage(
            "mode_selection",
            ok=True,
            detail={
                "query_class": parsed.query_class.value,
                "retrieval_mode_planned": "constitutional_lookup"
                if parsed.query_class == QueryClass.CONSTITUTIONAL
                else "statute"
                if parsed.sections
                else "general",
            },
        )

        try:
            from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
            from backend.app.core.kb_doc_scope import list_unlinked_only_index_documents

            vec_count = count_index_vectors(index_dir) if index_exists(index_dir) else 0
            unlinked_docs = list_unlinked_only_index_documents(user_id, index_dir)
            trace.set_index_stats(
                documents=len(unlinked_docs),
                chunks=vec_count,
                vectors=vec_count,
                index_path=str(index_dir),
                unlinked_documents=len(unlinked_docs),
            )
        except Exception:
            pass

        entity_info = extract_entities(parsed)
        plan = build_retrieval_plan(parsed)

        scope: Dict[str, Any] = {}
        try:
            from backend.app.core.kb_doc_scope import resolve_document_scope
            from backend.app.core.kb_doc_ranker import apply_document_ranking_to_scope
            from backend.app.core.kb_strict_retrieval import apply_follow_up_scope_pin
            from conversation_context import is_meta_follow_up

            scope = resolve_document_scope(
                user_id, search_q, index_dir, thread_id=thread_id, history=history
            )
            meta_fu = is_meta_follow_up(query or "")
            if meta_fu:
                scope = apply_follow_up_scope_pin(
                    scope, query=query, session_id=session_id, history=history
                )
            else:
                scope = apply_document_ranking_to_scope(
                    search_q, index_dir, scope, user_id=str(user_id)
                )
            # region agent log
            try:
                from backend.app.core.kb_runtime_debug import kb_runtime_log

                kb_runtime_log(
                    "C",
                    "legal_orchestrator_v2.py:_run_inner",
                    "kb_scope",
                    {
                        "meta_follow_up": meta_fu,
                        "scope_filename": str(scope.get("filename") or "")[:80],
                        "strict": bool(scope.get("strict")),
                        "pinned_reason": str(scope.get("pinned_reason") or ""),
                    },
                )
            except Exception:
                pass
            # endregion
        except Exception:
            pass

        try:
            from backend.app.core.kb_doc_scope import apply_unlinked_only_scope

            scope = apply_unlinked_only_scope(user_id, scope, index_dir)
        except Exception:
            pass
        trace.stage(
            "scope_resolved",
            ok=True,
            detail={
                "strict": bool(scope.get("strict")),
                "reason": scope.get("reason") or "",
                "filename": str(scope.get("filename") or "")[:80],
                "unlinked_only": bool(scope.get("unlinked_only")),
                "allowed_count": len(scope.get("allowed_filenames") or []),
            },
        )

        if parsed.query_class == QueryClass.ENTITY_LOOKUP:
            from kb_pipeline import _try_entity_lookup_answer

            ans = _try_entity_lookup_answer(user_id, query, scope, index_dir)
            if ans:
                return ans, [], {
                    **diag.to_dict(),
                    "found": True,
                    "found_reason": "entity_lookup",
                    "document_scope": scope,
                }

        chunks, mode = execute_retrieval(plan, parsed, index_dir, scope=scope)
        raw_after_retrieve = len(chunks or [])
        trace.stage(
            "retriever_invoked",
            ok=raw_after_retrieve > 0,
            detail={
                "mode": mode,
                "chunks_raw": raw_after_retrieve,
                "top_file": str((chunks[0].get("metadata") or {}).get("filename", ""))[:80]
                if chunks
                else "",
                "top_score": float(
                    (chunks[0].get("final_score") or chunks[0].get("score") or 0)
                )
                if chunks
                else 0,
            },
        )

        section_classes = {
            QueryClass.SINGLE_SECTION,
            QueryClass.SECTION_PUNISHMENT,
            QueryClass.MULTI_SECTION,
        }
        if parsed.query_class not in section_classes:
            try:
                from backend.app.core.kb_cascaded_retrieval import cascaded_retrieve

                chunks, coord_diag = cascaded_retrieve(
                    search_q,
                    index_dir,
                    scope=scope,
                    user_id=str(user_id),
                    k=12,
                    base_chunks=chunks,
                    mode=mode,
                )
                diag.validation["retrieval_coordinator"] = coord_diag
                diag.validation["retrieval_threshold"] = coord_diag.get(
                    "threshold_min_accept"
                )
                diag.validation["retrieval_candidates"] = coord_diag.get("candidates")
            except Exception:
                try:
                    from backend.app.core.kb_retrieval_coordinator import coordinated_retrieve

                    chunks, coord_diag = coordinated_retrieve(
                        search_q,
                        index_dir,
                        scope=scope,
                        user_id=str(user_id),
                        base_chunks=chunks,
                        mode=mode,
                    )
                    diag.validation["retrieval_coordinator"] = coord_diag
                except Exception:
                    pass
        elif parsed.sections:
            try:
                from backend.app.core.kb_strict_retrieval import validate_section_chunks

                chunks = validate_section_chunks(
                    chunks, parsed.sections, plan.law
                )
            except Exception:
                pass

        if parsed.query_class == QueryClass.ENTITY_LOOKUP:
            from kb_pipeline import _try_entity_lookup_answer

            ans = _try_entity_lookup_answer(
                user_id, query, scope, index_dir, chunks=chunks or None
            )
            if ans:
                return ans, chunks or [], {
                    **diag.to_dict(),
                    "found": True,
                    "found_reason": "entity_lookup_post_retrieve",
                    "document_scope": scope,
                    "retrieval_mode": mode,
                }
        diag.retrieval_mode = mode

        pre_unlinked = list(chunks or [])
        try:
            from backend.app.core.kb_doc_scope import filter_chunks_unlinked_only

            before = len(chunks or [])
            if not bypass_retrieval_filters():
                filtered = filter_chunks_unlinked_only(
                    user_id, chunks or [], index_dir=index_dir
                )
                if before > len(filtered):
                    filtered_keys = {
                        (c.get("content") or "")[:80] for c in filtered
                    }
                    for ch in pre_unlinked:
                        if (ch.get("content") or "")[:80] not in filtered_keys:
                            meta = ch.get("metadata") or {}
                            trace.log_rejection(
                                ch,
                                "linked_matter_document_excluded",
                                score=float(
                                    ch.get("final_score") or ch.get("score") or 0
                                ),
                            )
                chunks = filtered
            if before and not chunks:
                diag.validation["unlinked_filter"] = "linked_matter_docs_excluded"
        except Exception:
            pass

        trace.stage(
            "chunks_after_filter",
            ok=bool(chunks),
            detail={
                "count": len(chunks or []),
                "rejected": len(trace.rejection_log),
                "bypass_filters": bypass_retrieval_filters(),
            },
        )

        if not chunks and not bypass_retrieval_filters():
            try:
                from backend.app.core.kb_pipeline_trace import rescue_top_chunks

                rescued = rescue_top_chunks(
                    index_dir, search_q or query, k=5, scope=scope
                )
                if rescued:
                    chunks = rescued
                    mode = f"{mode}+rescue_top5"
                    diag.retrieval_mode = mode
                    diag.validation["rescue"] = "top5_bypass_threshold"
            except Exception:
                pass

        if not chunks and bypass_retrieval_filters():
            try:
                from backend.app.core.kb_pipeline_trace import rescue_top_chunks

                chunks = rescue_top_chunks(index_dir, search_q or query, k=5, scope=scope)
                if chunks:
                    mode = f"{mode}+bypass_rescue"
                    diag.retrieval_mode = mode
            except Exception:
                pass

        try:
            from kb_rag_decision import is_off_topic_general_knowledge

            if is_off_topic_general_knowledge(query) and not chunks:
                return (
                    "NOT_FOUND_IN_KB",
                    [],
                    {
                        **diag.to_dict(),
                        "found": False,
                        "found_reason": "off_topic_general_knowledge",
                        "retrieval_mode": mode,
                    },
                )
        except Exception:
            pass

        # Gemini must never modify KB retrieval (see kb_strict_policy / kb_gemini_safety).

        if (
            parsed.sections
            and parsed.query_class
            in (
                QueryClass.SINGLE_SECTION,
                QueryClass.SECTION_PUNISHMENT,
                QueryClass.MULTI_SECTION,
            )
            and not chunks
        ):
            return (
                "Section not found in the uploaded knowledge base. "
                "Upload the relevant statute PDF and run **Re-index**, then ask again.",
                [],
                {
                    **diag.to_dict(),
                    "found": False,
                    "found_reason": "strict_section_not_in_kb",
                    "retrieval_mode": mode,
                },
            )

        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "A",
                "legal_orchestrator_v2.py:post_retrieve",
                "retrieval_result",
                {
                    "query": query[:120],
                    "query_class": parsed.query_class.value,
                    "mapping_mode": parsed.mapping_mode,
                    "sections": parsed.sections[:4],
                    "chunk_count": len(chunks or []),
                    "mode": mode,
                    "index_dir": str(index_dir),
                    "scope_strict": bool(scope.get("strict")),
                    "top_score": float((chunks[0].get("final_score") or chunks[0].get("score") or 0))
                    if chunks
                    else 0,
                    "top_file": str((chunks[0].get("metadata") or {}).get("filename", ""))
                    if chunks
                    else "",
                    "top_chunks": [
                        {
                            "score": round(
                                float(c.get("final_score") or c.get("score") or 0), 4
                            ),
                            "source": str(
                                (c.get("metadata") or {}).get("filename") or ""
                            )[:80],
                            "excerpt": (c.get("content") or "")[:100],
                        }
                        for c in (chunks or [])[:10]
                    ],
                },
            )
        except Exception:
            pass
        # endregion

        if not chunks:
            try:
                from backend.app.core.universal_kb import is_statute_focused_query, universal_retrieve
                from kb_legal_query_rewrite import is_law_replacement_query

                if parsed.query_class == QueryClass.LAW_MAPPING and is_law_replacement_query(
                    query
                ):
                    chunks = _law_replacement_retrieve(index_dir, query, scope=scope, k=12)
                    if chunks:
                        diag.retrieval_mode = "law_replacement_retrieve_fallback"
                elif parsed.query_class == QueryClass.DOCUMENT_QA or not is_statute_focused_query(
                    query
                ):
                    try:
                        from conversation_context import is_meta_follow_up

                        meta_no_chunks = is_meta_follow_up(query or "")
                    except ImportError:
                        meta_no_chunks = False
                    if meta_no_chunks and parsed.sections:
                        from backend.app.core.kb_strict_retrieval import (
                            strict_retrieve_statute_sections,
                        )

                        chunks, mode, _ = strict_retrieve_statute_sections(
                            index_dir,
                            query=search_q or query,
                            sections=parsed.sections[:4],
                            law=plan.law,
                            scope=scope,
                            top_k=12,
                            allow_vector_fallback=False,
                        )
                        if chunks:
                            diag.retrieval_mode = "meta_follow_up_strict"
                    else:
                        chunks = universal_retrieve(
                            query, index_dir, scope=scope or {}, k=12
                        )
                        if chunks:
                            diag.retrieval_mode = "universal_retrieval_primary"
                else:
                    from backend.app.core.kb_retrieval_robust import robust_kb_retrieve

                    chunks = robust_kb_retrieve(
                        query,
                        index_dir,
                        scope=scope or {},
                        k=12,
                        constitutional=parsed.query_class == QueryClass.CONSTITUTIONAL,
                    )
                    if chunks:
                        diag.retrieval_mode = "robust_retrieval_primary"
            except Exception:
                pass

        if (
            not chunks
            and parsed.sections
            and parsed.query_class != QueryClass.CONSTITUTIONAL
        ):
            chunks = _section_lookup_exact(
                index_dir, parsed.sections[0], plan.law, top_k=12
            )
            if chunks:
                diag.retrieval_mode = "late_exact_section_no_scope"

        raw_chunks = list(chunks)
        try:
            from conversation_context import is_meta_follow_up

            meta_fu_scope = is_meta_follow_up(query or "")
        except ImportError:
            meta_fu_scope = False
        if scope.get("strict") and chunks:
            try:
                from backend.app.core.kb_doc_scope import (
                    filter_chunks_by_scope,
                    reject_cross_document_contamination,
                )

                scoped = filter_chunks_by_scope(chunks, scope)
                ok, reason = reject_cross_document_contamination(query, scoped, scope)
                if ok and scoped:
                    chunks = scoped
                elif not scoped and raw_chunks and not meta_fu_scope:
                    relaxed = dict(scope)
                    relaxed["strict"] = False
                    scope = relaxed
                    chunks = raw_chunks
                    diag.validation["scope_relaxed"] = "multi_document_or_empty_scope"
                elif not scoped and raw_chunks and meta_fu_scope and parsed.sections:
                    try:
                        from backend.app.core.kb_strict_retrieval import (
                            validate_section_chunks,
                        )

                        section_only = validate_section_chunks(
                            raw_chunks, parsed.sections, plan.law
                        )
                        chunks = section_only or raw_chunks
                        diag.validation["scope_relaxed"] = "meta_follow_up_section_filter"
                    except Exception:
                        chunks = raw_chunks
                elif not ok and not meta_fu_scope:
                    relaxed = dict(scope)
                    relaxed["strict"] = False
                    scope = relaxed
                    chunks = raw_chunks
                    diag.validation["contamination"] = f"ignored:{reason}"
            except Exception:
                pass

        try:
            from backend.app.core.kb_case_context_lock import (
                is_case_locked_query,
                pin_party_matched_chunks,
            )
            from kb_query_types import is_case_query

            if is_case_query(query or "") or is_case_locked_query(query or ""):
                chunks = pin_party_matched_chunks(query, raw_chunks, chunks or [])
        except Exception:
            pass

        # Soft-fail: extra retrieval before giving up (no LLM without chunks)
        if not chunks:
            try:
                from backend.app.core.kb_retrieval_robust import robust_kb_retrieve
                from backend.app.core.kb_pipeline_trace import rescue_top_chunks
                from backend.app.core.universal_kb import (
                    is_statute_focused_query,
                    universal_retrieve,
                )

                rescued = robust_kb_retrieve(
                    search_q or query,
                    index_dir,
                    scope=scope or {},
                    k=12,
                    constitutional=parsed.query_class == QueryClass.CONSTITUTIONAL,
                )
                if rescued:
                    chunks = rescued
                    mode = f"{mode}+soft_robust"
                    diag.retrieval_mode = mode
                    diag.validation["soft_rescue"] = "robust_kb_retrieve"
                if not chunks:
                    rescued = rescue_top_chunks(
                        index_dir, search_q or query, k=8, scope=scope
                    )
                    if rescued:
                        chunks = rescued
                        mode = f"{mode}+soft_rescue"
                        diag.retrieval_mode = mode
                        diag.validation["soft_rescue"] = "rescue_top8"
                if not chunks and (
                    parsed.query_class == QueryClass.DOCUMENT_QA
                    or not is_statute_focused_query(query)
                ):
                    uni = universal_retrieve(
                        query, index_dir, scope=scope or {}, k=12
                    )
                    if uni:
                        chunks = uni
                        mode = f"{mode}+soft_universal"
                        diag.retrieval_mode = mode
                        diag.validation["soft_rescue"] = "universal_retrieve"
            except Exception:
                pass

        if not chunks:
            trace.stage("chunk_validation", ok=False, detail={"reason": "zero_chunks"})
            trace.stage("context_assembly", ok=False, detail={"context_length": 0})
            trace.stage("prompt_construction", ok=False, detail={"tokens": 0})
            trace.stage(
                "llm_call",
                ok=False,
                detail={"skipped": True, "ollama_invoked": False},
            )
            trace_payload = trace.finalize()
            try:
                from conversation_context import is_meta_follow_up
                from backend.app.core.conversation_memory import get_session_legal_memory
                from backend.app.core.kb_retrieval_debug import (
                    build_retrieval_debug_report,
                    record_retrieval_debug,
                )

                session_mem_dbg = get_session_legal_memory(session_id) if session_id else {}
                debug_report = build_retrieval_debug_report(
                    original_query=query,
                    expanded_query=search_q,
                    retrieval_mode=diag.retrieval_mode or mode,
                    chunks=[],
                    session_mem=session_mem_dbg,
                    scope=scope if isinstance(scope, dict) else {},
                    follow_up_detected=is_meta_follow_up(query or ""),
                    memory_used=False,
                    context_passed_to_llm=False,
                    prompt_preview="",
                    prompt_token_estimate=0,
                    index_dir=str(index_dir),
                    pipe_diag={**diag.to_dict(), "pipeline_trace": trace_payload},
                    linked_doc_leak=bool(diag.validation.get("unlinked_filter")),
                )
                debug_report["pipeline_trace"] = trace_payload
                debug_report["rejections"] = trace.rejection_log[:20]
                debug_report["index_stats"] = trace.index_stats
                record_retrieval_debug(debug_report)
            except Exception:
                pass
            no_chunk_msg = (
                "No relevant chunks found in the uploaded knowledge base for this query. "
                "Check the Debug Retrieval panel for rejection reasons."
            )
            if scope.get("reason") == "no_unlinked_documents":
                no_chunk_msg = (
                    "No unlinked documents are available for Knowledge Base search. "
                    "Upload statute/reference PDFs as unlinked documents, or select a matter "
                    "to search matter-linked files."
                )
            return (
                no_chunk_msg,
                [],
                {
                    **diag.to_dict(),
                    "found": False,
                    "found_reason": "hard_fail_zero_chunks",
                    "retrieval_mode": mode,
                    "pipeline_trace": trace_payload,
                },
            )

        trace.stage(
            "chunk_validation",
            ok=True,
            detail={"count": len(chunks), "top_score": float(chunks[0].get("final_score") or 0)},
        )

        try:
            from conversation_context import is_meta_follow_up
            from backend.app.core.conversation_memory import get_session_legal_memory
            from backend.app.core.kb_retrieval_debug import (
                build_retrieval_debug_report,
                record_retrieval_debug,
            )

            session_mem_dbg = get_session_legal_memory(session_id) if session_id else {}
            follow_up = is_meta_follow_up(query or "")
            context_block = "\n\n".join(
                (c.get("content") or "")[:400] for c in chunks[:6]
            )
            token_est = max(1, len(context_block.split()) // 4) if context_block else 0
            trace.stage(
                "context_assembly",
                ok=bool(context_block.strip()),
                detail={"context_length": len(context_block), "token_estimate": token_est},
            )
            trace.stage(
                "prompt_construction",
                ok=bool(context_block.strip()),
                detail={"context_included": bool(context_block.strip()), "tokens": token_est},
            )
            trace_payload = trace.finalize()
            coord_val = diag.validation.get("retrieval_coordinator") or {}
            debug_report = build_retrieval_debug_report(
                original_query=query,
                expanded_query=search_q,
                retrieval_mode=diag.retrieval_mode or mode,
                chunks=chunks or [],
                session_mem=session_mem_dbg,
                scope=scope if isinstance(scope, dict) else {},
                follow_up_detected=follow_up,
                memory_used=bool(session_mem_dbg.get("last_section") and follow_up),
                context_passed_to_llm=bool(context_block.strip()),
                prompt_preview=context_block[:1200],
                prompt_token_estimate=token_est,
                index_dir=str(index_dir),
                pipe_diag={**diag.to_dict(), "pipeline_trace": trace_payload},
                linked_doc_leak=bool(diag.validation.get("unlinked_filter")),
                retrieval_candidates=coord_val.get("candidates"),
                threshold_used=coord_val.get("threshold_min_accept"),
                top_score=coord_val.get("top_score"),
            )
            debug_report["pipeline_trace"] = trace_payload
            debug_report["rejections"] = trace.rejection_log[:20]
            debug_report["index_stats"] = trace.index_stats
            record_retrieval_debug(debug_report)
            import logging as _logging

            _logging.getLogger(__name__).info(
                "QUERY: %s | EXPANDED: %s | CHUNK_COUNT: %s | CONTEXT_TOKENS: %s",
                (query or "")[:120],
                (search_q or "")[:120],
                len(chunks or []),
                token_est,
            )
        except Exception:
            pass

        if parsed.query_class == QueryClass.CONSTITUTIONAL or _is_constitutional_text(
            query or ""
        ):
            chunks = _prefer_constitutional_chunks(
                query,
                chunks or [],
                index_dir=index_dir,
                parsed=parsed,
                scope=scope if isinstance(scope, dict) else {},
            )

        if chunks and index_dir:
            try:
                from backend.app.core.kb_chunk_stitch import expand_chunks_across_page_breaks

                chunks = expand_chunks_across_page_breaks(
                    search_q or query,
                    chunks or [],
                    index_dir,
                    window=2,
                )
            except ImportError:
                pass

        try:
            from backend.app.core.kb_case_context_lock import (
                is_case_locked_query,
                lock_chunks_to_query,
            )

            if is_case_locked_query(query or "") or parsed.query_class == QueryClass.CASE_LAW:
                chunks = lock_chunks_to_query(
                    query or "",
                    chunks or [],
                    index_dir=index_dir,
                )
        except ImportError:
            pass

        if not chunks:
            try:
                from backend.app.core.kb_cascaded_retrieval import (
                    cascaded_retrieve,
                    detect_potential_retrieval_failure,
                )

                rescued, rescue_diag = cascaded_retrieve(
                    search_q or query,
                    index_dir,
                    scope=scope if isinstance(scope, dict) else {},
                    user_id=str(user_id),
                    k=10,
                )
                if rescued:
                    chunks = rescued
                    diag.validation["empty_rescue"] = rescue_diag.get("stages")
                elif detect_potential_retrieval_failure(
                    query, index_dir, chunks or []
                ):
                    diag.validation["potential_retrieval_failure"] = True
            except Exception:
                pass

        answer = generate_answer(
            parsed,
            plan,
            chunks,
            user_id=user_id,
            index_dir=index_dir,
            history=history,
            search_q=search_q,
        )
        try:
            from backend.app.core.kb_strict_policy import finalize_kb_answer

            answer = finalize_kb_answer(answer or "", query, chunks or [])
        except Exception:
            pass
        synth_meta = get_last_kb_synthesis_meta()
        trace.stage(
            "llm_call",
            ok=bool(answer and answer != KB_NOT_FOUND_MESSAGE),
            detail={
                "answer_len": len(answer or ""),
                "skipped": False,
                "ollama_invoked": bool(synth_meta.get("ollama_invoked")),
            },
        )
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "B",
                "legal_orchestrator_v2.py:post_generate",
                "generate_answer",
                {
                    "query_class": parsed.query_class.value,
                    "answer_len": len(answer or ""),
                    "answer_preview": (answer or "")[:160],
                },
            )
        except Exception:
            pass
        # endregion
        ok, reason = validate_response(parsed, answer)
        diag.validation = {"ok": ok, "reason": reason}
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "D",
                "legal_orchestrator_v2.py:post_validate",
                "validate_response",
                {"ok": ok, "reason": reason},
            )
        except Exception:
            pass
        # endregion

        if not ok and chunks:
            try:
                from kb_legal_query_rewrite import is_law_replacement_query

                skip_generic = (
                    parsed.query_class == QueryClass.LAW_MAPPING
                    and is_law_replacement_query(query)
                )
            except Exception:
                skip_generic = parsed.query_class == QueryClass.LAW_MAPPING
            if not skip_generic and parsed.query_class != QueryClass.CONSTITUTIONAL:
                try:
                    from intent_engine import classify_intent
                    from kb_response_state import build_found_answer

                    profile = classify_intent(query, history)
                    reground = build_found_answer(
                        query, chunks[:10], profile, messages=history, use_llm=True, user_id=user_id
                    )
                    if not reground:
                        reground = build_found_answer(
                            query, chunks[:10], profile, messages=history, use_llm=False, user_id=user_id
                        )
                    if reground:
                        ok_reg, reason_reg = validate_response(parsed, reground)
                        if ok_reg:
                            answer = reground
                            ok = True
                            diag.validation = {"ok": True, "reason": f"reground:{reason_reg}"}
                except Exception:
                    pass

        if not ok:
            chunks2, mode2 = execute_retrieval(plan, parsed, index_dir, scope=scope, retry=True)
            if chunks2:
                chunks = chunks2
                diag.retrieval_mode = mode2
                diag.retried = True
                answer2 = generate_answer(
                    parsed,
                    plan,
                    chunks,
                    user_id=user_id,
                    index_dir=index_dir,
                    history=history,
                    search_q=search_q,
                )
                ok2, reason2 = validate_response(parsed, answer2)
                diag.validation = {"ok": ok2, "reason": reason2}
                if ok2 and answer2:
                    answer = answer2

        if (not answer or answer == KB_NOT_FOUND_MESSAGE) and parsed.query_class == QueryClass.LAW_MAPPING:
            try:
                from kb_legal_query_rewrite import build_baseline_law_answer, extract_law_mapping_answer
                from kb_response_state import enforce_single_state
                from citation_formatter import polish_kb_response

                mapped = extract_law_mapping_answer(parsed.raw, chunks) or build_baseline_law_answer(
                    parsed.raw
                )
                if mapped:
                    answer = enforce_single_state(polish_kb_response(mapped, chunks), found=True)
                    diag.validation["fallback"] = "law_mapping_baseline"
            except Exception:
                pass

        if (not answer or answer == KB_NOT_FOUND_MESSAGE) and chunks:
            try:
                from kb_legal_query_rewrite import is_law_replacement_query

                skip_build_found = (
                    parsed.query_class == QueryClass.LAW_MAPPING
                    and is_law_replacement_query(query)
                ) or parsed.query_class in (
                    QueryClass.CONSTITUTIONAL,
                    QueryClass.CASE_LAW,
                )
            except Exception:
                skip_build_found = parsed.query_class == QueryClass.CONSTITUTIONAL
            if not skip_build_found:
                try:
                    from intent_engine import classify_intent
                    from kb_response_state import build_found_answer

                    profile = classify_intent(query, history)
                    fallback = build_found_answer(
                        query,
                        chunks[:10],
                        profile,
                        messages=history,
                        use_llm=True,
                        user_id=user_id,
                    )
                    if not fallback:
                        fallback = build_found_answer(
                            query,
                            chunks[:10],
                            profile,
                            messages=history,
                            use_llm=False,
                            user_id=user_id,
                        )
                    if fallback:
                        answer = fallback
                        diag.validation["fallback"] = "build_found_answer"
                except Exception:
                    pass

        if (not answer or answer == KB_NOT_FOUND_MESSAGE) and chunks:
            try:
                from kb_legal_query_rewrite import is_law_replacement_query

                skip_guarantee = (
                    parsed.query_class == QueryClass.LAW_MAPPING
                    and is_law_replacement_query(query)
                )
            except Exception:
                skip_guarantee = False
            if not skip_guarantee:
                try:
                    from backend.app.core.kb_force_answer import guarantee_kb_answer
                    from kb_response_state import enforce_single_state

                    forced = guarantee_kb_answer(query, chunks)
                    if forced:
                        answer = enforce_single_state(forced, found=True)
                        diag.validation["fallback"] = "guarantee_kb_answer"
                except Exception:
                    pass

        if not answer or answer == KB_NOT_FOUND_MESSAGE:
            try:
                from backend.app.core.universal_kb import (
                    chunks_overlap_query,
                    universal_document_answer,
                )

                if chunks and chunks_overlap_query(query, chunks):
                    forced = universal_document_answer(
                        query, chunks, user_id=user_id, use_llm=True
                    )
                    if not forced:
                        from backend.app.core.kb_force_answer import guarantee_kb_answer

                        forced = guarantee_kb_answer(query, chunks)
                    if forced:
                        from kb_response_state import enforce_single_state

                        answer = enforce_single_state(forced, found=True)
                        diag.validation["fallback"] = "final_universal_guarantee"
                        return answer, chunks, {
                            **diag.to_dict(),
                            "found": True,
                            "found_reason": "universal_guarantee",
                        }
            except Exception:
                pass
            # region agent log
            try:
                from backend.app.core.debug_session_log import debug_log
                from backend.app.core.universal_kb import chunks_overlap_query

                debug_log(
                    "E",
                    "legal_orchestrator_v2.py:not_found",
                    "returning_NOT_FOUND_IN_KB",
                    {
                        "chunk_count": len(chunks or []),
                        "answer_len": len(answer or ""),
                        "chunks_overlap": bool(
                            chunks_overlap_query(query, chunks) if chunks else False
                        ),
                        "validation": diag.validation,
                        "retrieval_mode": diag.retrieval_mode,
                    },
                )
            except Exception:
                pass
            # endregion
            return "NOT_FOUND_IN_KB", chunks, {**diag.to_dict(), "found": False}

        try:
            from backend.app.services.kb_service import append_source_footer

            answer, _src = append_source_footer(answer, chunks)
        except Exception:
            pass

        try:
            from backend.app.core.citation_verifier import verify_citations

            answer, cite_stats = verify_citations(answer, kb_chunks=chunks)
            diag.validation["citations"] = cite_stats
        except Exception:
            pass

        def _record_success() -> None:
            try:
                from backend.app.core.adaptive_learning import record_interaction

                record_interaction(
                    user_id,
                    "knowledge_base",
                    query,
                    answer=answer,
                    intent=parsed.query_class.value,
                    found_in_kb=True,
                    best_score=0.85,
                    chunks=chunks,
                    thread_id=thread_id or "",
                    implicit_signal="orchestrator_v2",
                    learning_handled=True,
                )
            except Exception:
                pass

        try:
            from backend.app.core.resource_scheduler import Priority, defer_low_priority

            defer_low_priority(_record_success, label="kb_interaction_record")
        except Exception:
            _record_success()

        if session_id and (parsed.sections or chunks):
            try:
                from backend.app.core.conversation_memory import update_session_legal_memory

                src_meta: Dict[str, Any] = {}
                if chunks:
                    m0 = chunks[0].get("metadata") or {}
                    fn = str(m0.get("filename") or m0.get("source_file") or "")
                    if fn:
                        src_meta["filename"] = fn
                    sec_m = (
                        parsed.sections[0]
                        if parsed.sections
                        else m0.get("primary_section") or m0.get("section")
                    )
                    if sec_m:
                        src_meta["section"] = str(sec_m)
                parse_patch: Dict[str, Any] = {}
                if parsed.sections:
                    parse_patch = {
                        "section": parsed.sections[0],
                        "law": (plan.law or "IPC").upper(),
                        "intent": "section_lookup",
                    }
                update_session_legal_memory(
                    session_id,
                    query=query,
                    parse=parse_patch or None,
                    mode="knowledge_base",
                    answer=(answer or "")[:800],
                    source_meta=src_meta or None,
                )
                if chunks:
                    from backend.app.core.session_store import get_session, set_session

                    sess = get_session(session_id) or {}
                    mem = dict(sess.get("legal_memory") or {})
                    mem["last_retrieved_chunks"] = [
                        {
                            "source": str(
                                (c.get("metadata") or {}).get("filename")
                                or (c.get("metadata") or {}).get("source_file")
                                or ""
                            ),
                            "score": float(
                                c.get("final_score") or c.get("score") or 0.0
                            ),
                            "excerpt": (c.get("content") or "")[:200],
                        }
                        for c in chunks[:8]
                    ]
                    mem["last_answer"] = (answer or "")[:800]
                    sess["legal_memory"] = mem
                    set_session(session_id, sess)
            except Exception:
                pass

        return answer, chunks, {
            **diag.to_dict(),
            "found": True,
            "found_reason": "orchestrator_v2",
            "document_scope": scope if isinstance(scope, dict) else {},
        }


def run_legal_orchestrator_v2(
    user_id: str,
    query: str,
    history: Optional[List[Dict]] = None,
    index_dir: Any = None,
    thread_id: Optional[str] = None,
    session_id: Optional[str] = None,
    retrieval_query: Optional[str] = None,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    return LegalOrchestratorV2().run(
        user_id=user_id,
        query=query,
        history=history,
        index_dir=index_dir,
        thread_id=thread_id,
        session_id=session_id,
        retrieval_query=retrieval_query,
    )
