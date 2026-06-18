"""
Query intent router — maps natural language to structured KB intents.

Feeds legal_orchestrator_v2 / kb_pipeline without replacing existing parsers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from kb_query_types import QueryType, detect_query_type, extract_entities


class QueryIntelIntent(str, Enum):
    SECTION_LOOKUP = "section_lookup"
    CASE_EXPLANATION = "case_explanation"
    CASE_SUMMARY = "case_summary"
    CONTRACT_UNDERSTANDING = "contract_understanding"
    DOCUMENT_QA = "document_qa"
    DOCUMENT_SUMMARY = "document_summary"
    COMPARISON = "comparison"
    LEGAL_REASONING = "legal_reasoning"
    TIMELINE_EXTRACTION = "timeline_extraction"
    PUNISHMENT_LOOKUP = "punishment_lookup"
    RIGHTS_EXPLANATION = "rights_explanation"
    PARTY_IDENTIFICATION = "party_identification"
    KEY_CLAUSES = "key_clauses"
    RISK_ANALYSIS = "risk_analysis"
    FOLLOW_UP_QA = "follow_up_qa"
    MULTI_DOC_REASONING = "multi_doc_reasoning"
    LAW_REPLACEMENT = "law_replacement"
    UNKNOWN = "unknown"


_QT_MAP = {
    QueryType.COMPARISON: QueryIntelIntent.COMPARISON,
    QueryType.SECTION_LOOKUP: QueryIntelIntent.SECTION_LOOKUP,
    QueryType.SECTION_EXPLANATION: QueryIntelIntent.SECTION_LOOKUP,
    QueryType.PUNISHMENT_QUERY: QueryIntelIntent.PUNISHMENT_LOOKUP,
    QueryType.LAW_REPLACEMENT: QueryIntelIntent.LAW_REPLACEMENT,
    QueryType.FOLLOW_UP: QueryIntelIntent.FOLLOW_UP_QA,
    QueryType.SUMMARY: QueryIntelIntent.DOCUMENT_SUMMARY,
    QueryType.LIST_EXTRACTION: QueryIntelIntent.DOCUMENT_SUMMARY,
    QueryType.TOPIC_QUERY: QueryIntelIntent.CASE_EXPLANATION,
    QueryType.ENTITY_LOOKUP: QueryIntelIntent.PARTY_IDENTIFICATION,
    QueryType.UNKNOWN: QueryIntelIntent.DOCUMENT_QA,
}


@dataclass
class QueryRoute:
    intent: QueryIntelIntent
    kb_query_type: QueryType
    entities: List[str] = field(default_factory=list)
    typed_entities: List[Dict[str, str]] = field(default_factory=list)
    conceptual_comparison: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)


def route_query(
    query: str,
    history: Optional[List[Dict[str, Any]]] = None,
) -> QueryRoute:
    """Primary intent router entry."""
    q = (query or "").strip()
    qt = detect_query_type(q, history)
    info = extract_entities(q, history)

    conceptual = False
    try:
        from backend.app.core.legal_offence_resolver import is_conceptual_comparison_query

        conceptual = is_conceptual_comparison_query(q)
        if conceptual:
            qt = QueryType.COMPARISON
    except Exception:
        pass

    intent = _QT_MAP.get(qt, QueryIntelIntent.UNKNOWN)

    if conceptual:
        intent = QueryIntelIntent.LEGAL_REASONING

    try:
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(q) and intent == QueryIntelIntent.UNKNOWN:
            intent = QueryIntelIntent.CONTRACT_UNDERSTANDING
    except Exception:
        pass

    try:
        from kb_query_types import is_case_query

        if is_case_query(q):
            intent = QueryIntelIntent.CASE_EXPLANATION
    except Exception:
        pass

    return QueryRoute(
        intent=intent,
        kb_query_type=qt,
        entities=list(info.get("entities") or []),
        typed_entities=list(info.get("typed_entities") or []),
        conceptual_comparison=conceptual,
        meta={"router": "query_intelligence_v1"},
    )
