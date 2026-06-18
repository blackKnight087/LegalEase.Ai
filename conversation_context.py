"""
Conversational memory for Knowledge Base follow-ups.

Resolves ambiguous queries ("What punishment?", "Explain simply") using
prior turns so retrieval and synthesis stay on the active legal topic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ConversationState:
    active_topic: str = ""
    active_sections: List[str] = field(default_factory=list)
    active_law: str = ""  # ipc, bns, it act, etc.
    active_case: str = ""  # e.g. "Riya Banerjee vs State Medical Board"
    compared_sections: List[str] = field(default_factory=list)
    answer_mode: str = "normal"  # normal | beginner | summary | comparison


_STATUTE_SECTION_RE = re.compile(
    r"\b(?:ipc|bns|crpc|it\s*act|section|sec\.?)\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
_SECTION_RE = re.compile(
    r"\b(?:ipc|bns|crpc|it\s*act|section|article|s\.)\s*(\d{1,4}[a-z]?)\b",
    re.I,
)
_CASE_VS_INLINE_RE = re.compile(
    r"\b(.+?)\s+vs\.?\s+(.+?)(?:\s*\(|\s*–|\s*-|\n|$)",
    re.I,
)
_BARE_SECTION_RE = re.compile(r"\b(?:section|sec\.?)\s*(\d{1,4}[a-z]?)\b", re.I)
_BARE_NUM_RE = re.compile(r"^(?:section|sec\.?)?\s*(\d{1,4}[a-z]?)$", re.I)
_LAW_RE = re.compile(
    r"\b(ipc|bns|crpc|indian penal code|bharatiya nyaya|it act)\b",
    re.I,
)
_COMPARE_SECTIONS_RE = re.compile(
    r"\b(?:section|ipc|bns)?\s*(\d{1,4}[a-z]?)\b",
    re.I,
)

_FOLLOW_UP_PUNISHMENT = (
    "punishment", "penalty", "sentence", "fine", "imprisonment", "what does it carry",
    "how many years", "maximum punishment",
)
_FOLLOW_UP_SIMPLIFY = (
    "explain simply", "simple language", "beginner", "layman", "eli5",
    "like i'm new", "dumb it down", "plain english", "easy to understand",
)
_FOLLOW_UP_EXAMPLE = ("example", "give an example", "illustrate", "scenario")
_FOLLOW_UP_COMPARE = (
    "different from", "difference from", "compare", "versus", " vs ", "distinguish",
)
_FOLLOW_UP_MORE = (
    "more detail", "elaborate", "tell me more", "go deeper", "expand on",
    "explanation", "details", "detail", "overview", "ingredients", "elements",
    "expand", "comprehensive", "break down", "walk me through",
)
_BARE_FOLLOW_UP_RE = re.compile(
    r"^(?:explanation|details?|overview|summary|punishment|ingredients?|elements?|"
    r"meaning|elaborate|more|continue|examples?)\s*[.!?]?\s*$",
    re.I,
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def extract_case_title_from_text(text: str) -> str:
    """Best-effort case caption from a user or assistant turn."""
    t = (text or "").strip()
    if not t:
        return ""
    try:
        from backend.app.core.case_entity_resolver import extract_case_title, is_case_style_query

        if is_case_style_query(t):
            title = extract_case_title(t)
            if title and title.lower() != "case summary":
                return title
    except Exception:
        pass
    m = _CASE_VS_INLINE_RE.search(t[:500])
    if m:
        a = re.sub(r"\s+", " ", m.group(1).strip()).strip(" .")
        b = re.sub(r"\s+", " ", m.group(2).strip()).strip(" .")
        if len(a) > 2 and len(b) > 2:
            return f"{a} vs {b}"
    return ""


def extract_sections_from_text(text: str, *, include_articles: bool = False) -> List[str]:
    found: List[str] = []
    t = (text or "").strip()
    m_bare = _BARE_NUM_RE.match(t)
    if m_bare:
        found.append(m_bare.group(1).lower())
    m_lead = re.search(
        r"\b(\d{1,4}[a-z]?)\s+(?:punishment|penalty|sentence|fine|imprisonment|meaning|explain)\b",
        t,
        re.I,
    )
    if m_lead:
        found.append(m_lead.group(1).lower())
    m_trail = re.search(
        r"\b(?:punishment|penalty|sentence)\s+(?:for|under|of)?\s*(?:ipc|bns)?\s*(\d{1,4}[a-z]?)\b",
        t,
        re.I,
    )
    if m_trail:
        found.append(m_trail.group(1).lower())
    section_patterns = (
        (_SECTION_RE, _BARE_SECTION_RE)
        if include_articles
        else (_STATUTE_SECTION_RE, _BARE_SECTION_RE)
    )
    for pat in section_patterns:
        for m in pat.finditer(t):
            found.append(m.group(1).lower())
    dedup: List[str] = []
    seen = set()
    for s in found:
        if s not in seen:
            seen.add(s)
            dedup.append(s)
    return dedup


def extract_law_from_text(text: str) -> str:
    m = _LAW_RE.search(text or "")
    if not m:
        return ""
    token = m.group(1).lower()
    if "penal" in token:
        return "ipc"
    if "bharatiya" in token or token == "bns":
        return "bns"
    if "it" in token:
        return "it act"
    return token


def build_conversation_state(messages: Optional[List[Dict]]) -> ConversationState:
    state = ConversationState()
    if not messages:
        return state

    for msg in reversed(messages[-10:]):
        role = msg.get("role")
        content = (msg.get("content") or "")[:3000]
        if not content:
            continue

        case_title = extract_case_title_from_text(content)
        if case_title and not state.active_case:
            state.active_case = case_title
            state.active_topic = case_title
            state.active_sections = []
            break

        secs = extract_sections_from_text(content, include_articles=False)
        law = extract_law_from_text(content)

        if secs and not state.active_sections and not state.active_case:
            state.active_sections = secs[:3]
            law_label = law.upper() if law else "IPC"
            state.active_law = law or "ipc"
            state.active_topic = f"{law_label} Section {secs[0].upper()}"

        if law and not state.active_law:
            state.active_law = law

        ql = content.lower()
        if any(c in ql for c in _FOLLOW_UP_SIMPLIFY):
            state.answer_mode = "beginner"
        elif any(c in ql for c in ("summarize", "summary", "overview", "gist")):
            state.answer_mode = "summary"
        elif any(c in ql for c in _FOLLOW_UP_COMPARE):
            state.answer_mode = "comparison"
            if len(secs) >= 2:
                state.compared_sections = secs[:2]

        if (state.active_sections or state.active_case) and state.active_topic:
            break

    return state


def is_meta_follow_up(question: str) -> bool:
    """True for vague continuations (simplify, elaborate, punishment) without a new legal topic."""
    return _is_ambiguous_follow_up(question)


def _is_ambiguous_follow_up(question: str) -> bool:
    q = _normalize(question)
    ql = q.lower()
    try:
        from document_classifier import document_type_for_query, is_contract_topic_query

        if is_contract_topic_query(q) or document_type_for_query(q):
            return False
    except ImportError:
        pass
    if re.search(
        r"\b(case|judgment|judgement|nirbhaya|kesavananda|constitutional|article\s+\d+|"
        r"replaced|replacement|summarize|summarise|list all|compare|difference|topics?)\b",
        ql,
    ):
        return False
    cues = (
        _FOLLOW_UP_PUNISHMENT + _FOLLOW_UP_SIMPLIFY + _FOLLOW_UP_EXAMPLE
        + _FOLLOW_UP_COMPARE + _FOLLOW_UP_MORE
        + ("it", "that", "this", "the same", "above", "earlier", "mentioned")
    )
    for c in cues:
        if len(c) <= 4:
            if re.search(rf"\b{re.escape(c)}\b", ql):
                return True
        elif c in ql:
            return True
    if _BARE_FOLLOW_UP_RE.match(q.strip()):
        return True
    if re.search(r"\bexplain\b", ql) and len(q.split()) <= 6:
        return True
    words = len(q.split())
    if words <= 8 and re.search(r"\b(it|that|this|same|above|earlier)\b", ql):
        return True
    return False


def enrich_query_with_context(
    question: str,
    messages: Optional[List[Dict]] = None,
    state: Optional[ConversationState] = None,
) -> str:
    """
    Rewrite vague follow-ups into explicit retrieval queries.
    """
    q = _normalize(question)
    if not messages:
        return q

    try:
        from backend.app.services.followup_detector import is_new_legal_query

        if is_new_legal_query(q):
            return q
    except ImportError:
        pass

    state = state or build_conversation_state(messages)
    secs_in_q = extract_sections_from_text(q, include_articles=False)
    if secs_in_q:
        return q

    if not state.active_sections and not state.active_case and not _is_ambiguous_follow_up(q):
        return q

    ql = q.lower()
    sec = state.active_sections[0] if state.active_sections else ""
    law = (state.active_law or "ipc").upper()
    topic = state.active_topic or (f"Section {sec.upper()}" if sec else "the prior topic")
    active_case = (state.active_case or "").strip()

    if active_case and _is_ambiguous_follow_up(q):
        if re.match(r"^explain\s*[.!?]?\s*$", ql) or _BARE_FOLLOW_UP_RE.match(q.strip()):
            return (
                f"Explain the case {active_case} in detail using only the uploaded documents, "
                f"including facts, parties, legal issues, and court observations."
            )
        if any(c in ql for c in _FOLLOW_UP_SIMPLIFY):
            return (
                f"Explain the case {active_case} in simple beginner-friendly language "
                f"using only the uploaded documents."
            )
        if any(c in ql for c in _FOLLOW_UP_MORE):
            return (
                f"Provide a comprehensive explanation of the case {active_case} "
                f"from the uploaded documents."
            )
        if any(c in ql for c in _FOLLOW_UP_EXAMPLE):
            return (
                f"Give practical examples or illustrations related to the case {active_case} "
                f"from the uploaded documents."
            )
        if len(q.split()) <= 10:
            return (
                f"{q}\n\n"
                f"[Continue about the case: {active_case}. Use only uploaded case documents.]"
            )

    try:
        from backend.app.services.followup_detector import requires_fresh_retrieval

        if requires_fresh_retrieval(q):
            return q
    except ImportError:
        pass

    if len(q.split()) >= 4 and not _BARE_FOLLOW_UP_RE.match(q.strip()):
        if not re.search(r"\b(?:section|ipc|bns|article)\s*\d", ql):
            return q

    if any(c in ql for c in _FOLLOW_UP_PUNISHMENT) and sec:
        return (
            f"What is the punishment or penalty prescribed for {law} Section {sec.upper()} "
            f"in the uploaded legal documents?"
        )

    if any(c in ql for c in _FOLLOW_UP_SIMPLIFY):
        return (
            f"Explain {topic} in simple beginner-friendly language using only the uploaded documents."
        )

    if any(c in ql for c in _FOLLOW_UP_EXAMPLE) and sec:
        return (
            f"Give a practical example illustrating {law} Section {sec.upper()} "
            f"based only on the uploaded documents."
        )

    if any(c in ql for c in _FOLLOW_UP_MORE) and sec and (
        _BARE_FOLLOW_UP_RE.match(q.strip())
        or len(q.split()) <= 4
    ):
        return (
            f"Provide a comprehensive explanation of {law} Section {sec.upper()} "
            f"from the uploaded documents, including overview, legal meaning, "
            f"essential ingredients or elements, punishment if stated, and "
            f"practical interpretation. Use only the uploaded documents."
        )

    if re.match(r"^explanation\s*[.!?]?\s*$", ql) and sec:
        return (
            f"Provide a comprehensive explanation of {law} Section {sec.upper()} "
            f"from the uploaded documents, including overview, meaning, legal "
            f"ingredients, punishment, and examples."
        )

    # "How is it different from 299?"
    if any(c in ql for c in _FOLLOW_UP_COMPARE):
        nums = extract_sections_from_text(q)
        if len(nums) >= 2:
            a, b = nums[0], nums[1]
            return (
                f"Compare and explain the difference between {law} Section {a.upper()} "
                f"and Section {b.upper()} using only the uploaded documents."
            )
        if sec and nums:
            other = nums[0]
            return (
                f"Compare {law} Section {sec.upper()} with Section {other.upper()}. "
                f"Explain key differences using only the uploaded documents."
            )
        if state.compared_sections and len(state.compared_sections) >= 2:
            a, b = state.compared_sections[0], state.compared_sections[1]
            return f"Compare {law} Section {a.upper()} and Section {b.upper()} from uploaded documents."

    try:
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(q):
            return q
    except ImportError:
        pass

    # Pronoun-only / short follow-ups: "Explanation", "Details", "what does it mean?"
    if sec and (
        re.search(r"\b(it|that|this|same)\b", ql)
        or len(q.split()) <= 8
        or _BARE_FOLLOW_UP_RE.match(q.strip())
    ):
        if re.search(r"\b(mean|meaning|define|what is)\b", ql):
            if re.search(r"\b(?:nda|non[- ]?disclosure|agreement|contract)\b", ql):
                return q
            return f"What is {law} Section {sec.upper()} according to the uploaded documents?"
        if re.search(r"\b(punishment|penalty|sentence)\b", ql):
            return f"What punishment applies to {law} Section {sec.upper()} in the uploaded documents?"

    # Append context block for retrieval when still short/ambiguous
    if _is_ambiguous_follow_up(q) and state.active_topic:
        return (
            f"{q}\n\n"
            f"[Active topic from conversation: {state.active_topic}. "
            f"Answer in continuity; use document evidence about {state.active_topic}.]"
        )

    return q


def merge_retrieval_query(
    question: str,
    messages: Optional[List[Dict]] = None,
    intent_expanded: str = "",
) -> str:
    """Prefer intent expansion only when it preserves the query's law family (IPC vs BNS)."""
    enriched = enrich_query_with_context(question, messages)
    q = (question or "").strip()
    exp = (intent_expanded or "").strip()
    if not exp or exp == q:
        return enriched
    ql = q.lower()
    el = exp.lower()
    if re.search(r"\bbns\b", ql) and re.search(r"\bipc\b", el) and "bns" not in el:
        return enriched
    if re.search(r"\bipc\b", ql) and re.search(r"\bbns\b", el) and "ipc" not in el:
        return enriched
    return exp
