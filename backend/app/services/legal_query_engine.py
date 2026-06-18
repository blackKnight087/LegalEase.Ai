"""
Legal Query Understanding Engine — FIRST stage before any KB retrieval.

Parses user intent, law systems, sections, comparison vs mapping, and multi-entity
explanation. Produces a retrieval plan consumed by kb_pipeline (no embedding/vector changes).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from kb_query_types import QueryType


class LegalQueryKind(str, Enum):
    SINGLE_SECTION_EXPLANATION = "single_section_explanation"
    SINGLE_SECTION_PUNISHMENT = "single_section_punishment"
    SAME_LAW_COMPARISON = "same_law_comparison"
    LAW_MAPPING_COMPARISON = "law_mapping_comparison"
    MULTI_SECTION_EXPLANATION = "multi_section_explanation"
    CONSTITUTIONAL_QUERY = "constitutional_query"
    GENERAL_LEGAL_QUERY = "general_legal_query"
    LAW_REPLACEMENT = "law_replacement"
    ENTITY_LOOKUP = "entity_lookup"
    CASE_QUERY = "case_query"


_COMPARE_RE = re.compile(
    r"\b(compare|comparison|difference|differences|differentiate|distinguish|versus|vs\.?|between)\b",
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
_CONSTITUTION_RE = re.compile(
    r"\b(constitutional rights?|fundamental rights?|article\s+\d+|"
    r"name\s+(?:five|5)\s+.*rights|five constitutional)\b",
    re.I,
)
_MAPPING_RE = re.compile(
    r"\b(equivalent|counterpart|correspond|mapped|mapping|replace|replaced|successor|"
    r"old\s+vs\s+new|bns\s+equivalent|what replaced|which law replaced)\b",
    re.I,
)
_ARTICLE_RE = re.compile(r"\b(?:article|art\.?)\s*(\d{1,4}[a-z]?)\b", re.I)
_MULTI_JOIN_RE = re.compile(
    r"\b(?:and|&|,)\b",
    re.I,
)


@dataclass
class LegalQueryPlan:
    """Structured understanding of a user KB query."""

    raw_query: str = ""
    normalized_query: str = ""
    kind: LegalQueryKind = LegalQueryKind.GENERAL_LEGAL_QUERY
    law_systems: List[str] = field(default_factory=list)
    sections: List[str] = field(default_factory=list)
    articles: List[str] = field(default_factory=list)
    intent: str = ""
    comparison: bool = False
    mapping_mode: bool = False
    multi_entity: bool = False
    typed_entities: List[Dict[str, str]] = field(default_factory=list)
    primary_law: str = "IPC"
    kb_query_type: QueryType = QueryType.UNKNOWN

    def to_dict(self) -> Dict[str, Any]:
        return {
            "raw_query": self.raw_query,
            "normalized_query": self.normalized_query,
            "kind": self.kind.value,
            "law_systems": self.law_systems,
            "sections": self.sections,
            "articles": self.articles,
            "intent": self.intent,
            "comparison": self.comparison,
            "mapping_mode": self.mapping_mode,
            "multi_entity": self.multi_entity,
            "typed_entities": self.typed_entities,
            "primary_law": self.primary_law,
            "kb_query_type": self.kb_query_type.value,
        }


def normalize_query(query: str) -> str:
    q = (query or "").strip()
    q = re.sub(r"\s+", " ", q)
    return q


def detect_law_systems(query: str) -> List[str]:
    ql = (query or "").lower()
    found: List[str] = []
    for key, label in (
        ("ipc", "IPC"),
        ("indian penal", "IPC"),
        ("bns", "BNS"),
        ("bharatiya nyaya", "BNS"),
        ("crpc", "CrPC"),
        ("bnss", "BNSS"),
        ("evidence act", "Evidence Act"),
        ("bsa", "BSA"),
    ):
        if re.search(rf"\b{re.escape(key)}\b", ql) and label not in found:
            found.append(label)
    if not found and _extract_sections(query) and not _CONSTITUTION_RE.search(ql):
        found.append("IPC")
    return found


def _sections_from_multi_explain(query: str) -> List[str]:
    """e.g. 'explain 307 and 300' -> ['307', '300'] without treating as comparison."""
    ql = (query or "").lower()
    if not _EXPLAIN_RE.search(ql) or not _MULTI_JOIN_RE.search(ql):
        return []
    nums: List[str] = []
    seen: set[str] = set()
    for m in re.finditer(r"\b(\d{1,4}[a-z]?)\b", query or ""):
        n = m.group(1).lower()
        if n in seen:
            continue
        if n.isdigit() and 1 <= int(n) <= 599:
            seen.add(n)
            nums.append(n)
    return nums[:4] if len(nums) >= 2 else []


def detect_sections(query: str) -> List[str]:
    multi = _sections_from_multi_explain(query)
    if len(multi) >= 2:
        return multi
    try:
        from backend.app.services.legal_query_parser import section_numbers_from_query

        nums = section_numbers_from_query(query)
        if len(nums) >= 2:
            return nums
    except Exception:
        pass
    from kb_retrieval import extract_comparison_sections

    return extract_comparison_sections(query) or []


def detect_articles(query: str) -> List[str]:
    return [m.group(1).lower() for m in _ARTICLE_RE.finditer(query or "")]


def detect_comparison(query: str, sections: List[str]) -> bool:
    if _COMPARE_RE.search(query or ""):
        try:
            from backend.app.core.legal_offence_resolver import is_conceptual_comparison_query

            if is_conceptual_comparison_query(query):
                return True
        except Exception:
            pass
        if len(sections) >= 2:
            return True
        return True
    return len(sections) >= 2 and bool(
        re.search(r"\b(?:vs|versus|compare|difference|between)\b", query, re.I)
    )


def detect_mapping_mode(query: str, law_systems: List[str]) -> bool:
    ql = (query or "").lower()
    if _MAPPING_RE.search(ql):
        return True
    try:
        from kb_legal_query_rewrite import is_law_replacement_query

        if is_law_replacement_query(query):
            return True
    except Exception:
        pass
    if len(law_systems) >= 2:
        old = {"IPC", "CrPC", "Evidence Act"} & set(law_systems)
        new = {"BNS", "BNSS", "BSA"} & set(law_systems)
        if old and new:
            return True
    return False


def detect_multi_entity(query: str, sections: List[str]) -> bool:
    if detect_comparison(query, sections):
        return False
    if len(sections) < 2:
        return False
    ql = (query or "").lower()
    if _EXPLAIN_RE.search(ql) or _MULTI_JOIN_RE.search(ql):
        return True
    if re.search(r"\bexplain\s+\d", ql) and _MULTI_JOIN_RE.search(ql):
        return True
    return False


def _extract_sections(query: str) -> List[str]:
    return detect_sections(query)


def build_typed_entities(
    query: str,
    sections: List[str],
    law_systems: List[str],
    *,
    mapping_mode: bool,
) -> List[Dict[str, str]]:
    """Build comparison entities — same law only unless mapping_mode."""
    primary = law_systems[0] if law_systems else "IPC"
    try:
        from kb_compare_engine import extract_all_comparison_entities, extract_typed_entities

        if mapping_mode:
            typed = extract_typed_entities(query)
            return typed if len(typed) >= 2 else []
        typed = extract_all_comparison_entities(query)
        if len(typed) >= 2:
            laws = {normalize_law_code(e.get("type", "")) for e in typed}
            if len(laws) == 1:
                return typed
            if any(e.get("concept") for e in typed):
                return typed
        if len(sections) >= 2:
            return [
                {"type": primary, "section": sections[0]},
                {"type": primary, "section": sections[1]},
            ]
        if len(sections) > 2:
            return [{"type": primary, "section": s} for s in sections[:4]]
    except Exception:
        pass
    if len(sections) >= 2:
        return [
            {"type": primary, "section": sections[0]},
            {"type": primary, "section": sections[1]},
        ]
    return []


def normalize_law_code(law: str) -> str:
    try:
        from kb_legal_mapping import normalize_law_code as _n

        return _n(law)
    except Exception:
        return (law or "IPC").upper()


def detect_intent_kind(
    query: str,
    *,
    sections: List[str],
    law_systems: List[str],
    comparison: bool,
    mapping_mode: bool,
    multi_entity: bool,
) -> LegalQueryKind:
    ql = (query or "").lower()

    try:
        from kb_query_types import QueryType as QT, detect_query_type

        if detect_query_type(query) == QT.ENTITY_LOOKUP:
            return LegalQueryKind.ENTITY_LOOKUP
    except Exception:
        pass

    if _CONSTITUTION_RE.search(ql) or detect_articles(query):
        return LegalQueryKind.CONSTITUTIONAL_QUERY

    if mapping_mode:
        try:
            from kb_legal_query_rewrite import is_law_replacement_query

            if is_law_replacement_query(query) and not sections:
                return LegalQueryKind.LAW_REPLACEMENT
        except Exception:
            pass
        if comparison:
            return LegalQueryKind.LAW_MAPPING_COMPARISON
        return LegalQueryKind.LAW_REPLACEMENT

    if multi_entity and len(sections) >= 2:
        return LegalQueryKind.MULTI_SECTION_EXPLANATION

    if comparison and len(sections) >= 2:
        return LegalQueryKind.SAME_LAW_COMPARISON

    if comparison:
        try:
            from backend.app.core.legal_offence_resolver import extract_conceptual_comparison_entities

            if len(extract_conceptual_comparison_entities(query)) >= 2:
                return LegalQueryKind.SAME_LAW_COMPARISON
        except Exception:
            pass

    if sections:
        if _PUNISH_RE.search(ql):
            return LegalQueryKind.SINGLE_SECTION_PUNISHMENT
        if _EXPLAIN_RE.search(ql) or len(sections) == 1:
            return LegalQueryKind.SINGLE_SECTION_EXPLANATION
        return LegalQueryKind.SINGLE_SECTION_EXPLANATION

    try:
        from kb_query_types import is_case_query

        if is_case_query(query):
            return LegalQueryKind.CASE_QUERY
    except Exception:
        pass

    return LegalQueryKind.GENERAL_LEGAL_QUERY


def kind_to_query_type(kind: LegalQueryKind) -> QueryType:
    mapping = {
        LegalQueryKind.SINGLE_SECTION_EXPLANATION: QueryType.SECTION_EXPLANATION,
        LegalQueryKind.SINGLE_SECTION_PUNISHMENT: QueryType.PUNISHMENT_QUERY,
        LegalQueryKind.SAME_LAW_COMPARISON: QueryType.COMPARISON,
        LegalQueryKind.LAW_MAPPING_COMPARISON: QueryType.COMPARISON,
        LegalQueryKind.MULTI_SECTION_EXPLANATION: QueryType.SECTION_EXPLANATION,
        LegalQueryKind.CONSTITUTIONAL_QUERY: QueryType.TOPIC_QUERY,
        LegalQueryKind.LAW_REPLACEMENT: QueryType.LAW_REPLACEMENT,
        LegalQueryKind.ENTITY_LOOKUP: QueryType.ENTITY_LOOKUP,
        LegalQueryKind.CASE_QUERY: QueryType.TOPIC_QUERY,
        LegalQueryKind.GENERAL_LEGAL_QUERY: QueryType.UNKNOWN,
    }
    return mapping.get(kind, QueryType.UNKNOWN)


def analyze_legal_query(
    query: str,
    history: Optional[List[List[Dict]]] = None,
) -> LegalQueryPlan:
    """
    Main entry — call before retrieval. No vector/embedding operations.
    """
    _ = history
    raw = (query or "").strip()
    normalized = normalize_query(raw)
    sections = detect_sections(normalized)
    try:
        from backend.app.core.legal_offence_resolver import extract_conceptual_comparison_entities

        conceptual = extract_conceptual_comparison_entities(normalized)
        if len(conceptual) >= 2:
            sections = [e.get("section", "") for e in conceptual if e.get("section")]
    except Exception:
        pass
    articles = detect_articles(normalized)
    law_systems = detect_law_systems(normalized)
    comparison = detect_comparison(normalized, sections)
    mapping_mode = detect_mapping_mode(normalized, law_systems)
    multi_entity = detect_multi_entity(normalized, sections)

    if mapping_mode and comparison and len(law_systems) < 2:
        mapping_mode = True
    if comparison and not mapping_mode:
        mapping_mode = False

    kind = detect_intent_kind(
        normalized,
        sections=sections,
        law_systems=law_systems,
        comparison=comparison,
        mapping_mode=mapping_mode,
        multi_entity=multi_entity,
    )

    primary_law = law_systems[0] if law_systems else "IPC"
    typed: List[Dict[str, str]] = []
    if kind in (
        LegalQueryKind.SAME_LAW_COMPARISON,
        LegalQueryKind.LAW_MAPPING_COMPARISON,
    ):
        typed = build_typed_entities(
            normalized,
            sections,
            law_systems,
            mapping_mode=mapping_mode,
        )

    plan = LegalQueryPlan(
        raw_query=raw,
        normalized_query=normalized,
        kind=kind,
        law_systems=law_systems,
        sections=sections,
        articles=articles,
        intent=kind.value,
        comparison=comparison,
        mapping_mode=mapping_mode,
        multi_entity=multi_entity,
        typed_entities=typed,
        primary_law=primary_law,
        kb_query_type=kind_to_query_type(kind),
    )
    return plan


def apply_plan_to_profile(profile: Any, plan: LegalQueryPlan, original_query: str) -> None:
    """Inject plan into IntentProfile.signals for downstream formatters."""
    sig = profile.signals if hasattr(profile, "signals") else {}
    sig["legal_query_plan"] = plan.to_dict()
    sig["original_query"] = original_query
    sig["mapping_mode"] = plan.mapping_mode
    sig["multi_entity"] = plan.multi_entity
    sig["primary_law"] = plan.primary_law
    if plan.sections:
        sig["entities"] = plan.sections
        if plan.multi_entity:
            sig["sections"] = plan.sections
        elif len(plan.sections) == 1:
            sig["primary_section"] = plan.sections[0]
            sig["sections"] = [plan.sections[0]]
    if plan.typed_entities:
        sig["typed_entities"] = plan.typed_entities
    if plan.kind in (
        LegalQueryKind.SAME_LAW_COMPARISON,
        LegalQueryKind.LAW_MAPPING_COMPARISON,
    ):
        from intent_engine import QueryIntent

        profile.primary = QueryIntent.COMPARISON
        sig["comparison_same_law"] = plan.kind == LegalQueryKind.SAME_LAW_COMPARISON


def validate_response_against_plan(answer: str, plan: LegalQueryPlan) -> tuple[bool, str]:
    """Reject answers that introduce wrong law systems or wrong sections."""
    text = (answer or "").strip()
    if not text:
        return False, "empty_answer"

    al = text.lower()

    if plan.kind == LegalQueryKind.SAME_LAW_COMPARISON and not plan.mapping_mode:
        if re.search(r"\bcorresponds to bns\b|\breplaced by\b|\bmapping in your document\b", al):
            return False, "unwanted_bns_mapping"
        for ent in plan.typed_entities:
            law = ent.get("type", "IPC")
            sec = ent.get("section", "")
            if sec and not re.search(
                rf"\b{re.escape(law.lower())}\s*(?:section\s*)?{re.escape(sec)}\b",
                al,
                re.I,
            ):
                if not re.search(rf"\bsection\s*{re.escape(sec)}\b", al, re.I):
                    return False, f"missing_section_in_answer:{sec}"

    if plan.kind == LegalQueryKind.MULTI_SECTION_EXPLANATION:
        for sec in plan.sections[:4]:
            if not re.search(rf"\b{re.escape(sec)}\b", al):
                return False, f"missing_multi_section:{sec}"

    if plan.kind in (
        LegalQueryKind.SINGLE_SECTION_EXPLANATION,
        LegalQueryKind.SINGLE_SECTION_PUNISHMENT,
    ) and plan.sections:
        sec = plan.sections[0]
        wrong_ipc = re.findall(r"\bipc\s*(?:section\s*)?(\d{1,4})\b", al, re.I)
        for w in wrong_ipc:
            if w.lower() != sec.lower():
                return False, f"answer_wrong_section:{w}"
        if not re.search(rf"\b{re.escape(sec)}\b", al):
            return False, f"missing_section:{sec}"
        if not plan.mapping_mode and re.search(
            r"\bhas been replaced by the bharatiya\b", al
        ):
            return False, "law_replacement_drift"

    if plan.kind == LegalQueryKind.CONSTITUTIONAL_QUERY:
        if plan.mapping_mode:
            return False, "constitutional_with_mapping"
        if re.search(r"\bipc\s*section\s*\d{1,4}\b", al) and not re.search(
            r"\barticle\s*\d", al
        ):
            return False, "criminal_drift_in_constitutional"

    return True, "ok"


def generate_multi_section_answer(
    query: str,
    context_chunks: List[Dict[str, Any]],
    sections: List[str],
    *,
    law: str = "ipc",
    user_id: str = "",
) -> str:
    """Per-section retrieval formatting — never merge IPC 300 with IPC 307 chunks."""
    from kb_preprocess import filter_chunks_for_section
    from answer_orchestrator import format_statute_section_answer
    from citation_formatter import polish_kb_response

    law_l = (law or "ipc").strip().lower()
    blocks: List[str] = []
    for sec in sections[:4]:
        scoped = filter_chunks_for_section(context_chunks, sec, law=law_l)
        block = format_statute_section_answer(query, scoped or context_chunks, sec, law_l)
        if not block:
            excerpt = " ".join((c.get("content") or "")[:350] for c in (scoped or [])[:2]).strip()
            if len(excerpt) >= 40:
                law_u = "BNS" if law_l == "bns" else "IPC"
                block = f"## {law_u} Section {sec.upper()}\n\n{excerpt[:900]}"
        if block:
            if not re.search(rf"\bsection\s*{re.escape(sec)}\b", block, re.I):
                law_u = "BNS" if law_l == "bns" else "IPC"
                block = f"## {law_u} Section {sec.upper()}\n\n{block}"
            blocks.append(block.strip())
    if not blocks:
        return ""
    combined = "\n\n---\n\n".join(blocks)
    return polish_kb_response(combined, context_chunks)
