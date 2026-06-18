"""
Shared legal-query detection and enrichment for Open Law / Tavily web search.

CRITICAL: Each user turn must search and synthesize for the CURRENT question only.
Prior turns must not be appended to search queries unless the message is a vague follow-up.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

LEGAL_TERMS = (
    "law", "legal", "act", "section", "ipc", "bns", "crpc", "court", "judgment",
    "statute", "contract", "tort", "petition", "fir", "bail", "appeal", "precedent",
    "india", "supreme", "high court", "tribunal", "arbitration", "compliance",
    "cji", "chief justice", "justice", "judiciary", "judge", "bench",
    "punishment", "penalty", "offence", "offense", "murder", "homicide", "negligence",
    "constitution", "article", "summarize", "summary", "explain", "difference",
    "compare", "precedent", "statutes", "criminal", "civil", "plaintiff", "defendant",
)

# Only these cues justify pulling prior-turn context (pronoun / continuation).
_VAGUE_FOLLOWUP_RE = re.compile(
    r"\b("
    r"explain it|this section|that section|the same|above|earlier|"
    r"what about it|tell me more\b(?! about)|go deeper|elaborate on that|more detail|"
    r"what punishment|punishment applies|does it carry|simply explain|"
    r"what does it|how about it|and what about|continue|expand on that"
    r")\b",
    re.I,
)

_DETAIL_FOLLOWUP_RE = re.compile(
    r"\b("
    r"explain in detail|explain in details|in detail|in details|"
    r"more details|detailed explanation|explain further|expand on|"
    r"elaborate|go deeper|break it down|can you explain|please explain"
    r")\b",
    re.I,
)

_TOPIC_STOPWORDS = frozenset({
    "tell", "me", "more", "about", "explain", "in", "detail", "details",
    "please", "what", "the", "a", "an", "is", "are", "was", "were", "it",
    "this", "that", "how", "why", "when", "where", "who", "which",
})

_KNOWN_CASE_RE = re.compile(
    r"\b(?:rg\s*karr?|rg\s*kar|nirbhaya|kesavananda|vishaka|navtej|"
    r"puttaswamy|shayara|maneka\s+gandhi|indira\s+gandhi|sarad?ha|sarada)\b",
    re.I,
)

_QUERY_FILLER_PREFIX = re.compile(
    r"^(?:please\s+)?(?:can you\s+)?(?:"
    r"explain|describe|summarize|summarise|outline|tell me about|tell me|"
    r"what is|what are|what was|who is|who are|give me|overview of|brief on|"
    r"details about|detail about|write about|discuss"
    r")\s+",
    re.I,
)

# High-value expansions — used instead of raw user text for search/grounding
_TOPIC_SEARCH_EXPANSIONS: Tuple[Tuple[re.Pattern, str], ...] = (
    (
        re.compile(r"\bsarad?ha\b|\bsarada\s+case\b", re.I),
        "Saradha chit fund scam India Supreme Court Calcutta High Court verdict judgment",
    ),
    (
        re.compile(r"\bfarmers?\s+law|\bfarm\s+law|\bthree\s+farm\s+acts\b", re.I),
        "India farm laws 2020 2021 farmers protest repeal Supreme Court constitutional validity",
    ),
    (
        re.compile(r"\bnirbhaya\b", re.I),
        "Nirbhaya case India Supreme Court judgment criminal law reform",
    ),
)

_ACK_LEGAL_EXCLUDE_RE = re.compile(
    r"\b(good\s+faith|good\s+governance|good\s+law|good\s+title|"
    r"goods\s+and\s+services|section|ipc|bns|crpc|article|"
    r"governing\s+law|legal\s+agreement|contract)\b",
    re.I,
)

_ACK_STANDALONE_RE = re.compile(
    r"^(?:"
    r"thanks?(?:\s+you)?|thank\s+you|thx|ty|"
    r"good|great|nice|perfect|excellent|wonderful|awesome|amazing|brilliant|"
    r"helpful|very\s+helpful|that\s+helps|that\s+helped|"
    r"ok(?:ay)?|got\s+it|understood|clear|makes\s+sense|"
    r"well\s+done|nicely\s+done|appreciate(?:\s+it)?|"
    r"exactly(?:\s+what\s+i\s+needed)?|"
    r"👍|🙏|✅"
    r")(?:[\s!.,']*)*$",
    re.I,
)

_ACK_SHORT_WORDS = frozenset({
    "good", "great", "nice", "perfect", "excellent", "thanks", "thank", "you",
    "ok", "okay", "helpful", "clear", "understood", "awesome", "amazing",
    "very", "so", "much", "a", "lot", "that", "helps", "helped", "well",
    "done", "appreciate", "it", "makes", "sense", "spot", "on", "exactly",
    "right", "correct", "explained", "answer",
})

_POSITIVE_FEEDBACK_RE = re.compile(
    r"\b("
    r"well\s+explained|nicely\s+explained|perfect\s+answer|spot\s+on|"
    r"exactly\s+right|exactly\s+what\s+i\s+(?:needed|wanted)|"
    r"good\s+answer|great\s+answer|nice\s+answer|"
    r"very\s+helpful|super\s+helpful|really\s+helpful"
    r")\b",
    re.I,
)

_NEGATIVE_FEEDBACK_RE = re.compile(
    r"\b("
    r"not\s+(?:relevant|helpful|correct|right|good|accurate|useful|complete|related)|"
    r"no[t']?\s+(?:relevant|helpful|correct|right)|"
    r"wrong|incorrect|inaccurate|error|mistake|mistaken|"
    r"missing|incomplete|lacks|left\s+out|didn['']t\s+(?:cover|include|mention|answer)|"
    r"irrelevant|off[\s-]?topic|unrelated|different\s+(?:answer|topic|question)|"
    r"can\s+do\s+better|could\s+be\s+better|do\s+better|needs?\s+improvement|"
    r"not\s+what\s+i\s+(?:asked|wanted|meant)|"
    r"bad\s+answer|useless|unhelpful|terrible|horrible|awful|"
    r"doesn['']t\s+(?:match|answer|help)|"
    r"completely\s+wrong|totally\s+wrong|way\s+off|"
    r"not\s+in\s+(?:documents|document|kb|knowledge\s+base)|"
    r"hallucinat|made\s+up|fabricat"
    r")\b",
    re.I,
)

_NEGATIVE_SHORT_WORDS = frozenset({
    "wrong", "incorrect", "error", "missing", "incomplete", "irrelevant",
    "unrelated", "unhelpful", "useless", "bad", "terrible", "awful",
    "inaccurate", "mistake",
})

FEEDBACK_POSITIVE = "positive"
FEEDBACK_NEGATIVE = "negative"


def looks_legal_query_for_web(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Open Law accepts legal queries only — never infer legality from chat history."""
    _ = conversation_history
    q = (query or "").lower().strip()
    if not q:
        return False
    if any(term in q for term in LEGAL_TERMS):
        return True
    if _KNOWN_CASE_RE.search(q):
        return True
    if re.search(r"\b(?:case|judgment|judgement|verdict|ruling|petition|court)\b", q):
        return True
    if re.search(r"\b(?:section|ipc|bns|crpc|article)\s*\d", q, re.I):
        return True
    return False


def _has_prior_assistant_turn(
    conversation_history: Optional[List[Dict[str, Any]]],
) -> bool:
    if not conversation_history:
        return False
    return any(
        (m.get("role") == "assistant" and (m.get("content") or "").strip())
        for m in conversation_history
    )


def is_conversational_acknowledgment(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Short compliments / thanks after an answer — not a new legal question."""
    return classify_conversational_feedback(query, conversation_history) == FEEDBACK_POSITIVE


def is_conversational_feedback(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """True when the user is reacting to the prior answer (positive or negative)."""
    return classify_conversational_feedback(query, conversation_history) is not None


def classify_conversational_feedback(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> Optional[str]:
    """
    Classify short user reactions to the prior assistant answer.
    Returns 'positive', 'negative', or None (treat as a normal query).
    """
    q = (query or "").strip()
    if not q or len(q) > 120:
        return None
    if conversation_history is not None and not _has_prior_assistant_turn(conversation_history):
        return None

    ql = q.lower()

    if _NEGATIVE_FEEDBACK_RE.search(ql):
        return FEEDBACK_NEGATIVE

    neg_words = re.findall(r"[a-z']+", ql)
    if len(neg_words) <= 4 and neg_words and all(w in _NEGATIVE_SHORT_WORDS for w in neg_words):
        return FEEDBACK_NEGATIVE

    if re.search(r"\b(not|no)\s+\w+", ql) and re.search(
        r"\b(good|helpful|relevant|correct|right|accurate|useful|answer)\b", ql
    ):
        return FEEDBACK_NEGATIVE

    if _ACK_LEGAL_EXCLUDE_RE.search(q):
        return None

    if _POSITIVE_FEEDBACK_RE.search(ql):
        return FEEDBACK_POSITIVE

    if _ACK_STANDALONE_RE.match(q):
        return FEEDBACK_POSITIVE

    words = re.findall(r"[a-z']+", ql)
    if words and len(words) <= 6 and all(w in _ACK_SHORT_WORDS for w in words):
        return FEEDBACK_POSITIVE

    return None


def _prior_substantive_user_query(
    conversation_history: Optional[List[Dict[str, Any]]],
) -> str:
    """Last user message that is not itself verbal feedback."""
    if not conversation_history:
        return ""
    for msg in reversed(conversation_history):
        if msg.get("role") != "user":
            continue
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        if is_conversational_feedback(text, conversation_history):
            continue
        return text[:400]
    return _prior_user_topic(conversation_history)


def build_acknowledgment_response(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Brief reply when the user is reacting positively to the prior answer."""
    prior_topic = _prior_substantive_user_query(conversation_history)

    ql = (query or "").lower()
    if re.search(r"\b(thanks|thank|appreciate)\b", ql):
        opener = "You're welcome!"
    else:
        opener = "Glad that helped!"

    if prior_topic:
        topic_short = prior_topic[:100] + ("…" if len(prior_topic) > 100 else "")
        return (
            f"{opener} Your feedback helps improve my answers on topics like **{topic_short}**.\n\n"
            "If you'd like to go deeper, try:\n\n"
            "- Summarize the key points\n"
            "- Explain in simpler language\n"
            "- What should I do next?"
        )

    return (
        f"{opener} Your feedback is recorded and used to improve future answers. "
        "Ask a follow-up anytime, or start a new legal question when you're ready."
    )


def build_negative_feedback_response(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Acknowledge criticism and invite a clearer retry — no new legal search."""
    prior_topic = _prior_substantive_user_query(conversation_history)

    if prior_topic:
        topic_short = prior_topic[:100] + ("…" if len(prior_topic) > 100 else "")
        return (
            "Thanks for the honest feedback — I've recorded this as **negative feedback** "
            "so the system can learn and tune future answers.\n\n"
            f"I understand my previous response on **{topic_short}** missed the mark"
            f"{' (' + (query or '').strip()[:80] + ')' if (query or '').strip() else ''}.\n\n"
            "Gemini will analyze what went wrong to help improve Ollama retrieval and neural learning.\n\n"
            "To get a better answer, try:\n\n"
            "- Rephrase your question with more detail\n"
            "- Name the specific section, case, or issue that's missing\n"
            "- Ask me to try again with a narrower focus"
        )

    return (
        "Thanks for the feedback — I've recorded this as **negative feedback** for learning and tuning.\n\n"
        "Please rephrase your question with more detail, or tell me exactly what was wrong "
        "with the previous answer so I can improve."
    )


def non_legal_web_refusal(query: str) -> str:
    return (
        "## Open Law — legal questions only\n\n"
        "Open Law Intelligence answers **Indian legal research** questions "
        "(statutes, sections, cases, courts, contracts, compliance).\n\n"
        f"Your question *\"{(query or '').strip()[:120]}\"* is outside that scope. "
        "Try rephrasing with legal context, or switch to **Knowledge Base** for document Q&A."
    )


def is_self_contained_web_query(query: str) -> bool:
    """
    Query carries its own subject — never merge prior Q&A into search or synthesis.
    """
    q = (query or "").strip()
    if not q:
        return False
    try:
        from kb_query_types import is_bare_section_query, is_case_query

        if is_bare_section_query(q) or is_case_query(q):
            return True
    except ImportError:
        pass

    ql = q.lower()
    if _KNOWN_CASE_RE.search(q):
        return True
    if re.search(r"\b(?:case|judgment|judgement|verdict|ruling|petition)\b", ql):
        return True
    if re.search(r"\b(?:section|sec\.?|ipc|bns|crpc|article)\s*\d", ql, re.I):
        return True
    if re.search(r"\b\d{1,4}[a-z]?\b", q) and re.search(
        r"\b(difference|compare|versus|vs\.?|between|punishment|murder|offence)\b", ql
    ):
        return True
    if re.search(r"\b(compare|difference|versus|vs\.?)\b", ql) and re.search(
        r"\b\d{1,4}\b", q
    ):
        return True
    if re.search(r"\btell me more about\b", ql) and _has_topic_in_query(q):
        return True
    if re.search(r"\b(what is|who is|what are|about|explain)\b", ql) and len(q.split()) >= 4:
        return True
    return len(q.split()) > 14


def _has_topic_in_query(query: str) -> bool:
    """True when the message names a subject beyond filler words."""
    words = [
        w for w in re.findall(r"[a-z0-9]{2,}", (query or "").lower())
        if w not in _TOPIC_STOPWORDS
    ]
    return len(words) >= 1


def is_detail_follow_up(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    if _DETAIL_FOLLOWUP_RE.search(q):
        return True
    if len(q.split()) <= 5 and re.search(r"\b(detail|details|elaborate|deeper)\b", q, re.I):
        return True
    return False


def is_vague_web_follow_up(query: str) -> bool:
    return _is_vague_web_follow_up(query)


def _is_vague_web_follow_up(query: str) -> bool:
    q = (query or "").strip()
    if is_self_contained_web_query(q):
        return False
    if is_detail_follow_up(q):
        return True
    if _VAGUE_FOLLOWUP_RE.search(q):
        return True
    if len(q.split()) <= 8 and re.search(r"\b(it|this|that|same)\b", q, re.I):
        return True
    return False


def _assistant_context_usable(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 80:
        return False
    low = t.lower()
    if "web intelligence unavailable" in low or "no web sources could be retrieved" in low:
        return False
    if "knowledge base empty" in low or "not found in document" in low:
        return False
    return True


def _prior_user_topic(conversation_history: Optional[List[Dict[str, Any]]]) -> str:
    """Last user turn that carries a real topic — skip bare follow-ups."""
    if not conversation_history:
        return ""
    for msg in reversed(conversation_history):
        if msg.get("role") != "user":
            continue
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        if _is_vague_web_follow_up(text) and not _has_topic_in_query(text):
            continue
        return text[:400]
    return ""


def resolve_web_conversation_query(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
    session_mem: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Resolve vague follow-ups (e.g. "explain in details") to the prior substantive topic.
    Used for both web search and LLM synthesis so the model understands context.
    """
    q = (query or "").strip()
    if not q:
        return q

    if is_conversational_feedback(q, conversation_history):
        return q

    topic = _prior_user_topic(conversation_history)
    if not topic and session_mem:
        topic = (
            (session_mem.get("last_topic") or session_mem.get("last_query") or "")
            .strip()[:400]
        )
        if not topic:
            topic = (session_mem.get("last_user_query") or "").strip()[:400]

    if not topic:
        return q

    if is_detail_follow_up(q):
        return f"Provide a comprehensive detailed explanation about {topic}"

    if _is_vague_web_follow_up(q):
        if re.search(r"\btell me more\b", q, re.I) and not _has_topic_in_query(q):
            return f"Tell me more about {topic} with full context and legal analysis"
        if re.search(r"\b(explain|elaborate|continue)\b", q, re.I):
            return f"Explain {topic} in depth with legal context and analysis"
        return f"{q} — continuing discussion about: {topic}"

    if len(q.split()) <= 6 and re.search(
        r"\b(explain|detail|details|more|elaborate|continue)\b", q, re.I
    ):
        if is_self_contained_web_query(q):
            return q
        return f"Explain {topic} in depth with legal context and analysis"

    return q


def strip_web_query_fillers(query: str) -> str:
    """Remove leading 'explain / what is / tell me' so search targets the legal topic."""
    q = (query or "").strip()
    if not q:
        return q
    prev = None
    while prev != q:
        prev = q
        q = _QUERY_FILLER_PREFIX.sub("", q).strip()
        q = re.sub(r"^(?:about|on|regarding)\s+", "", q, flags=re.I).strip()
    return q


def _topic_search_expansion(query: str) -> str:
    for pat, expansion in _TOPIC_SEARCH_EXPANSIONS:
        if pat.search(query):
            return expansion
    return ""


def looks_like_dictionary_web_answer(answer: str, sources: Optional[List[Dict[str, Any]]] = None) -> bool:
    """Detect when web search answered a filler word (e.g. 'explain') not the legal topic."""
    low = (answer or "").lower()
    if "to explain is to make plain" in low or "to explain is to make" in low:
        return True
    if re.search(r"\bdefinition of explain\b", low):
        return True
    blob = low + " " + " ".join(
        str(s.get("title", "")) + " " + str(s.get("href", ""))
        for s in (sources or [])
    ).lower()
    dict_hits = sum(
        1
        for d in (
            "dictionary.cambridge",
            "merriam-webster",
            "dictionary.com",
            "collinsdictionary",
            "thefreedictionary",
        )
        if d in blob
    )
    legal_hits = sum(
        1
        for d in ("supreme court", "high court", "indiankanoon", "live law", "barandbench")
        if d in blob
    )
    return dict_hits >= 2 and legal_hits == 0


def build_web_search_query(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Focused query for Tavily / Serp / Gemini grounding — one topic per turn, no answer mixing.
    """
    q = (query or "").strip()
    if not q:
        return q

    resolved = resolve_web_conversation_query(q, conversation_history)
    q = strip_web_query_fillers(resolved)
    if not q:
        q = strip_web_query_fillers((query or "").strip()) or (query or "").strip()

    expanded = _topic_search_expansion(q)
    if expanded:
        return expanded[:480]

    ql = q.lower()

    if resolved != (query or "").strip() and resolved != q:
        return resolved[:480]

    if _is_vague_web_follow_up(q) and conversation_history:
        topic = _prior_user_topic(conversation_history)
        if topic:
            return f"{q} regarding {topic} India law"[:480]

    if re.search(r"\brg\s*karr?\b|\brg\s*kar\b", ql):
        return (
            "RG Kar Medical College Kolkata rape murder case India "
            "Supreme Court Calcutta High Court judgment 2024"
        )[:480]

    if re.search(r"\bdifference\b|\bcompare\b|\bvs\.?\b|\bversus\b", ql):
        secs = re.findall(r"\b(\d{1,4}[a-z]?)\b", q)
        if len(secs) >= 2:
            return (
                f"IPC Section {secs[0]} vs Section {secs[1]} difference "
                f"Indian Penal Code India murder culpable homicide punishment"
            )[:480]
        if len(secs) == 1:
            return (
                f"IPC Section {secs[0]} Indian Penal Code definition punishment India"
            )[:480]

    m_sec = re.search(r"\b(?:section|sec\.?)\s*(\d{1,4}[a-z]?)\b", q, re.I)
    if m_sec:
        return f"IPC Section {m_sec.group(1)} Indian Penal Code India"[:480]

    m_ipc = re.search(r"\bipc\s*(\d{1,4}[a-z]?)\b", q, re.I)
    if m_ipc:
        return f"IPC Section {m_ipc.group(1)} Indian Penal Code India"[:480]

    if _KNOWN_CASE_RE.search(q) or re.search(r"\bcase\b", ql):
        core = strip_web_query_fillers(q) or q
        return f"{core} India Supreme Court case judgment legal"[:480]

    if re.search(r"\bsupreme court\b", ql) or re.search(r"\bverdict\b", ql):
        core = strip_web_query_fillers(q) or q
        return f"{core} India law Supreme Court judgment"[:480]

    if looks_legal_query_for_web(q, conversation_history):
        core = strip_web_query_fillers(q) or q
        return f"{core} India law legal"[:480]

    return q[:480]


def search_api_query(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Query string sent to Tavily / Serp — never append prior full answers."""
    return build_web_search_query(query, conversation_history)


def enrich_web_query(
    query: str,
    conversation_history: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Optional expansion for LLM synthesis — self-contained queries stay isolated.
    """
    q = (query or "").strip()
    if not q:
        return q
    if is_self_contained_web_query(q):
        return q
    resolved = resolve_web_conversation_query(q, conversation_history)
    if resolved != q:
        return resolved[:600]

    if not _is_vague_web_follow_up(q) or not conversation_history:
        return q

    topic = _prior_user_topic(conversation_history)
    if not topic:
        return q

    return f"{q} (continuing discussion about: {topic[:200]})"[:600]
