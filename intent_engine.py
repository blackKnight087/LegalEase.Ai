"""
Query intent classification for LegalEase answer orchestration.

Classifies user questions BEFORE retrieval so synthesis can adapt
(ChatGPT/Gemini-style) instead of dumping raw chunks.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from conversation_context import (
    build_conversation_state,
    enrich_query_with_context,
    extract_sections_from_text,
)


class QueryIntent(str, Enum):
    FACTUAL_LOOKUP = "factual_lookup"
    SUMMARIZATION = "summarization"
    BEGINNER_EXPLANATION = "beginner_explanation"
    COMPARISON = "comparison"
    LIST_EXTRACTION = "list_extraction"
    MULTI_INTENT = "multi_intent"
    FOLLOW_UP_CONTEXT = "follow_up_context"
    GENERAL_ANALYSIS = "general_analysis"


@dataclass
class IntentProfile:
    primary: QueryIntent
    secondary: List[QueryIntent] = field(default_factory=list)
    response_mode: str = "minimal"  # minimal | bullets | table | structured | multi_section
    complexity: str = "medium"  # short | medium | deep
    retrieval_k: int = 8
    max_context_chunks: int = 5
    max_answer_tokens: int = 600
    is_follow_up: bool = False
    expanded_query: str = ""
    subtasks: List[Tuple[QueryIntent, str]] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    conversation_state: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_simple(self) -> bool:
        return self.response_mode in {"minimal", "bullets", "table"}


_FOLLOW_UP_CUES = (
    "punishment", "penalty", "sentence", "what about", "and that", "also",
    "more detail", "elaborate", "it carry", "does it", "that section",
    "this section", "the same", "above", "mentioned", "earlier",
)
_SUMMARY_CUES = (
    "summarize", "summarise", "summary", "overview", "gist", "in brief",
    "key points from", "main points", "high level",
)
_BEGINNER_CUES = (
    "beginner", "simple language", "explain simply", "layman", "non-lawyer",
    "easy to understand", "plain english", "like i'm", "eli5", "dumb it down",
)
_COMPARE_CUES = (
    "compare", "comparison", "difference", "differences", "differentiate",
    "distinguish", "versus", "between",
)
_LIST_CUES = (
    "list all", "list the", "enumerate", "all sections", "all offences",
    "all crimes", "what sections", "which sections", "bullet",
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _word_count(text: str) -> int:
    return len(_normalize(text).split())


def _is_litigation_caption(q: str) -> bool:
    try:
        from backend.app.core.case_entity_resolver import is_case_style_query

        return is_case_style_query(q)
    except ImportError:
        return bool(re.search(r"\b\w+(?:\s+\w+){0,4}\s+vs\.?\s+\w+", q or "", re.I))


def _detect_intent_flags(q: str) -> Dict[str, bool]:
    ql = (q or "").lower()
    litigation = _is_litigation_caption(q)
    explicit_compare = bool(
        re.search(
            r"\b(?:compare|comparison|difference|differences|distinguish|between)\b",
            ql,
        )
    )
    return {
        "summary": any(c in ql for c in _SUMMARY_CUES),
        "beginner": any(c in ql for c in _BEGINNER_CUES),
        "compare": (
            explicit_compare
            or (any(c in ql for c in _COMPARE_CUES) and not litigation)
        ),
        "list": bool(
            re.search(
                r"\b(list|enumerate|all)\b.*\b(section|offence|crime|provision|ipc|bns)\b",
                ql,
            )
            or re.search(r"\blist all\b", ql)
            or re.search(
                r"\b(summarize|summarise|summary)\b.*\b(all\s+)?(ipc|bns)?\s*sections?\b",
                ql,
            )
            or re.search(r"\ball\s+(ipc|bns)?\s*sections?\s+mentioned\b", ql)
        ),
        "factual": bool(
            re.search(r"\b(what is|what's|define|meaning of)\b", ql)
            and (
                extract_sections_from_text(q)
                or re.search(r"\b(section|ipc|bns|article)\s+\d", ql)
            )
        ),
        "explain_depth": bool(re.search(r"\b(explain|describe|walk me through|break down)\b", ql)),
        "deep": bool(
            re.search(
                r"\b(difference|compare|versus|between|analysis|implications)\b", ql
            )
            or (re.search(r"\bvs\.?\b", ql) and explicit_compare)
            or len(q.split()) > 18
        ),
    }


def _is_follow_up(question: str, messages: Optional[List[Dict]]) -> bool:
    if not messages:
        return False
    try:
        from backend.app.services.followup_detector import is_new_legal_query

        if is_new_legal_query(question):
            return False
    except ImportError:
        pass
    q = question.lower().strip()
    if _word_count(question) > 14 and not any(c in q for c in _FOLLOW_UP_CUES):
        return False
    has_prior = any(m.get("role") == "assistant" for m in messages[-6:])
    if not has_prior:
        return False
    if _word_count(question) <= 10:
        return True
    if re.search(r"^(explain|what|how|why|when|punishment|penalty|simplify|compare)\b", q):
        return True
    return any(c in q for c in _FOLLOW_UP_CUES)


def _expand_follow_up(question: str, messages: List[Dict]) -> str:
    state = build_conversation_state(messages)
    enriched = enrich_query_with_context(question, messages, state)
    if enriched != question:
        return enriched
    last_user = ""
    last_assistant = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and not last_assistant:
            last_assistant = (msg.get("content") or "")[:1500]
        elif msg.get("role") == "user" and not last_user:
            last_user = (msg.get("content") or "")[:500]
        if last_user and last_assistant:
            break
    if not last_user:
        return question
    return (
        f"{enriched}\n\n"
        f"[Conversation context — prior question: {last_user}]\n"
        f"[Prior answer excerpt: {last_assistant[:800]}]\n"
        "Answer the follow-up in continuity with the same topic and document evidence."
    )


def detect_question_complexity(question: str, flags: Dict[str, bool]) -> str:
    """
    short → 2–5 lines; medium → 5–12 lines; deep → detailed structured answer.
    """
    ql = (question or "").lower()
    if flags.get("summary") or flags.get("list"):
        return "medium"
    if flags.get("beginner"):
        return "medium"
    if flags.get("compare") or flags.get("deep"):
        return "deep"
    if flags.get("explain_depth") and not re.search(r"\b(what is|what's|define)\b", ql):
        return "medium"
    if re.search(r"\b(what is|what's|define|meaning of)\b", ql) and not flags.get("explain_depth"):
        return "short"
    if _word_count(question) <= 8:
        return "short"
    if _word_count(question) > 16:
        return "deep"
    return "medium"


def decompose_multi_intent(question: str, flags: Dict[str, bool]) -> List[Tuple[QueryIntent, str]]:
    """Split compound questions into ordered subtasks."""
    tasks: List[Tuple[QueryIntent, str]] = []
    ql = question.lower()

    if flags.get("compare"):
        m = re.search(
            r"(difference|compare|distinguish).{0,120}",
            ql,
            re.I,
        )
        tasks.append((QueryIntent.COMPARISON, question if m else question))

    if flags.get("list") or re.search(r"\blist\b", ql):
        tasks.append((QueryIntent.LIST_EXTRACTION, question))

    if flags.get("summary") and QueryIntent.SUMMARIZATION not in [t[0] for t in tasks]:
        tasks.append((QueryIntent.SUMMARIZATION, question))

    if flags.get("beginner") and QueryIntent.BEGINNER_EXPLANATION not in [t[0] for t in tasks]:
        tasks.append((QueryIntent.BEGINNER_EXPLANATION, question))

    if flags.get("factual") and not tasks:
        tasks.append((QueryIntent.FACTUAL_LOOKUP, question))

    if not tasks:
        parts = re.split(r"\s+and\s+", question, flags=re.I)
        if len(parts) > 1:
            for part in parts:
                part = part.strip(" ,.?")
                if len(part) >= 8:
                    sub_flags = _detect_intent_flags(part.lower())
                    if sub_flags["compare"]:
                        tasks.append((QueryIntent.COMPARISON, part))
                    elif sub_flags["list"]:
                        tasks.append((QueryIntent.LIST_EXTRACTION, part))
                    else:
                        tasks.append((QueryIntent.GENERAL_ANALYSIS, part))
        else:
            tasks.append((QueryIntent.GENERAL_ANALYSIS, question))

    return tasks


def classify_intent(
    question: str,
    messages: Optional[List[Dict]] = None,
) -> IntentProfile:
    """
    Classify query intent before retrieval/synthesis.
    """
    q = _normalize(question)
    ql = q.lower()
    flags = _detect_intent_flags(q)
    signals: Dict[str, Any] = {"flags": flags, "word_count": _word_count(q)}

    from kb_retrieval import extract_comparison_sections, is_comparison_query

    try:
        from kb_query_types import is_case_query

        case_q = is_case_query(q)
    except ImportError:
        case_q = False
    try:
        from backend.app.core.case_entity_resolver import is_case_style_query

        case_q = case_q or is_case_style_query(q)
    except ImportError:
        pass

    if case_q:
        sections = []
    elif is_comparison_query(q) or flags.get("compare"):
        sections = extract_comparison_sections(q)
    else:
        sections = extract_sections_from_text(q)
    if flags.get("compare") and len(sections) < 2:
        sections = extract_comparison_sections(q) or sections
    signals["sections"] = sections
    conv_state = build_conversation_state(messages)
    signals["conversation_state"] = {
        "active_topic": conv_state.active_topic,
        "active_sections": conv_state.active_sections,
        "active_law": conv_state.active_law,
        "compared_sections": conv_state.compared_sections,
        "answer_mode": conv_state.answer_mode,
    }

    follow_up = _is_follow_up(q, messages)
    expanded = _expand_follow_up(q, messages or []) if follow_up else enrich_query_with_context(q, messages)
    complexity = detect_question_complexity(q, flags)
    if flags.get("explain_depth") and complexity == "short":
        complexity = "medium"
    if re.search(r"\bexplain\b", ql) and sections and complexity == "short":
        complexity = "medium"
    token_map = {"short": 450, "medium": 900, "deep": 1800}
    max_tokens = token_map.get(complexity, 900)

    active_flags = sum(
        1 for k in ("summary", "beginner", "compare", "list", "factual") if flags.get(k)
    )

    try:
        from kb_query_types import is_case_query, is_document_fact_query
        from backend.app.core.case_entity_resolver import is_case_style_query, is_entity_focus_query

        if is_case_query(q) or is_case_style_query(q):
            return IntentProfile(
                primary=QueryIntent.GENERAL_ANALYSIS,
                response_mode="structured",
                complexity="deep",
                retrieval_k=12,
                max_context_chunks=8,
                max_answer_tokens=1800,
                expanded_query=expanded,
                signals=signals,
                conversation_state=signals["conversation_state"],
            )
        if is_entity_focus_query(q) or is_document_fact_query(q):
            return IntentProfile(
                primary=QueryIntent.GENERAL_ANALYSIS,
                response_mode="structured",
                complexity="medium",
                retrieval_k=12,
                max_context_chunks=8,
                max_answer_tokens=1200,
                expanded_query=expanded,
                signals=signals,
                conversation_state=signals["conversation_state"],
            )
    except Exception:
        pass

    if follow_up and active_flags <= 1:
        return IntentProfile(
            primary=QueryIntent.FOLLOW_UP_CONTEXT,
            response_mode="minimal",
            complexity=complexity,
            retrieval_k=10,
            max_context_chunks=6,
            max_answer_tokens=max_tokens,
            is_follow_up=True,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if active_flags >= 2 or (flags["compare"] and flags["list"]):
        subtasks = decompose_multi_intent(q, flags)
        return IntentProfile(
            primary=QueryIntent.MULTI_INTENT,
            secondary=[t[0] for t in subtasks],
            response_mode="multi_section",
            complexity="deep",
            retrieval_k=14,
            max_context_chunks=8,
            max_answer_tokens=1800,
            expanded_query=expanded,
            subtasks=subtasks,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if flags["compare"]:
        return IntentProfile(
            primary=QueryIntent.COMPARISON,
            response_mode="table",
            complexity="deep",
            retrieval_k=18,
            max_context_chunks=6,
            max_answer_tokens=1200,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if flags["list"]:
        return IntentProfile(
            primary=QueryIntent.LIST_EXTRACTION,
            response_mode="bullets",
            complexity="medium",
            retrieval_k=12,
            max_context_chunks=8,
            max_answer_tokens=1200,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if flags["summary"]:
        return IntentProfile(
            primary=QueryIntent.SUMMARIZATION,
            response_mode="bullets",
            complexity="medium",
            retrieval_k=12,
            max_context_chunks=8,
            max_answer_tokens=1000,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if flags["beginner"]:
        return IntentProfile(
            primary=QueryIntent.BEGINNER_EXPLANATION,
            response_mode="minimal",
            complexity="medium",
            retrieval_k=10,
            max_context_chunks=6,
            max_answer_tokens=900,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if flags["factual"] or re.search(
        r"\b(what is|what's|define|meaning of)\b", ql
    ):
        return IntentProfile(
            primary=QueryIntent.FACTUAL_LOOKUP,
            response_mode="minimal",
            complexity="short" if not flags.get("explain_depth") else "medium",
            retrieval_k=8,
            max_context_chunks=4,
            max_answer_tokens=450 if complexity == "short" else 750,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if sections and re.search(r"\bexplain\b", ql):
        sec = sections[0].upper()
        if re.search(r"\bbns\b", ql):
            expanded = f"BNS Section {sec} explain definition meaning"
        elif re.search(r"\bipc\b", ql):
            expanded = f"IPC Section {sec} explain definition meaning"
        else:
            expanded = q
        return IntentProfile(
            primary=QueryIntent.FACTUAL_LOOKUP,
            response_mode="minimal",
            complexity="medium",
            retrieval_k=12,
            max_context_chunks=6,
            max_answer_tokens=900,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    if re.search(r"\b(analyze|analyse|review|assess|implications|strategy)\b", ql):
        return IntentProfile(
            primary=QueryIntent.GENERAL_ANALYSIS,
            response_mode="structured",
            complexity="deep",
            retrieval_k=10,
            max_context_chunks=6,
            max_answer_tokens=1600,
            expanded_query=expanded,
            signals=signals,
            conversation_state=signals["conversation_state"],
        )

    # Bare section lookup: "section 300", "ipc 307", "300"
    if sections and not flags.get("compare") and not flags.get("list"):
        bare_section = bool(
            re.match(r"^(?:section|sec\.?)\s*[0-9]{1,4}[a-z]?$", ql)
            or re.match(r"^[0-9]{1,4}[a-z]?$", ql)
            or (sections and len(q.split()) <= 4 and not flags.get("summary"))
        )
        if bare_section:
            sec = sections[0]
            law = (conv_state.active_law or "ipc").upper()
            if law == "IPC":
                expanded = f"IPC Section {sec.upper()} definition meaning"
            elif law == "BNS":
                expanded = f"BNS Section {sec.upper()} definition meaning"
            else:
                expanded = f"Section {sec.upper()} IPC definition meaning"
            return IntentProfile(
                primary=QueryIntent.FACTUAL_LOOKUP,
                response_mode="minimal",
                complexity="short",
                retrieval_k=12,
                max_context_chunks=5,
                max_answer_tokens=700,
                expanded_query=expanded,
                signals=signals,
                conversation_state=signals["conversation_state"],
            )

    return IntentProfile(
        primary=QueryIntent.GENERAL_ANALYSIS,
        response_mode="minimal",
        complexity=complexity,
        retrieval_k=8,
        max_context_chunks=5,
        max_answer_tokens=max_tokens,
        expanded_query=expanded,
        signals=signals,
        conversation_state=signals["conversation_state"],
    )
