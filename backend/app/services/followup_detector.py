"""
Detect fresh legal section queries vs vague follow-ups.

When the user names a new IPC/BNS/Article/Section reference, prior session
context must not bleed into retrieval or synthesis.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

_NEW_LEGAL_PATTERNS = (
    re.compile(r"ipc\s*\d+", re.I),
    re.compile(r"bns\s*\d+", re.I),
    re.compile(r"crpc\s*\d+", re.I),
    re.compile(r"article\s*\d+", re.I),
    re.compile(r"section\s*\d+", re.I),
    # "307 punishment" / "302 penalty" — fresh section, not a follow-up to prior section
    re.compile(
        r"\b\d{1,4}[a-z]?\s+(?:punishment|penalty|sentence|fine|imprisonment|meaning|explain)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:punishment|penalty|sentence)\s+(?:for|under|of)?\s*(?:ipc|bns)?\s*\d{1,4}[a-z]?\b",
        re.I,
    ),
)


def is_new_legal_query(query: str) -> bool:
    """True when the user names a fresh legal topic — section, contract, or case."""
    query_lower = (query or "").lower()
    if not query_lower.strip():
        return False
    for pattern in _NEW_LEGAL_PATTERNS:
        if pattern.search(query_lower):
            return True
    try:
        from document_classifier import is_contract_topic_query

        if is_contract_topic_query(query):
            return True
    except ImportError:
        pass
    if re.search(
        r"\b(?:important\s+)?case\s+law\b",
        query_lower,
    ):
        return True
    if re.search(
        r"\b(?:comprehensive|testing material|criminal law testing|important case|"
        r"constitutional rights?|dense kb|legal testing)\b",
        query_lower,
    ):
        return True
    if re.search(
        r"\b(?:sample\s+)?(?:nda|non[- ]?disclosure|agreement|contract)\b",
        query_lower,
    ):
        return True
    if re.search(
        r"\b(?:case|judgment|judgement|petition|verdict|ruling)\b",
        query_lower,
    ):
        return True
    if re.search(r"\b\w+(?:\s+\w+){0,2}\s+vs\.?\s+\w+", query_lower):
        return True
    if re.search(
        r"\b(?:nirbhaya|kesavananda|constitutional|parties involved|confidential information)\b",
        query_lower,
    ):
        return True
    if re.search(
        r"\b(?:right\s+to\s+(?:equality|freedom|life|religion)|fundamental\s+rights?|"
        r"constitutional\s+rights?|article\s+\d+)\b",
        query_lower,
    ):
        return True
    if re.search(r"\bexplain\s+right\b", query_lower):
        return True
    if re.search(
        r"\b(?:replaced|replacement|list all|compare|difference|topics?)\b",
        query_lower,
    ):
        return True
    if re.search(r"\b(?:summarize|summarise)\b", query_lower) and len(query_lower.split()) > 6:
        return True
    if re.search(
        r"\b(?:custody|witness|hearing|fir|property dispute|nda|agreement|contract|"
        r"testimony|deponent|affidavit)\b",
        query_lower,
    ):
        return True
    if re.search(
        r"\b(?:who|which)\s+(?:sought|filed|said|testified|witnessed|alleged)\b",
        query_lower,
    ):
        return True
    return False


def requires_fresh_retrieval(query: str, session_mem: Optional[Dict[str, Any]] = None) -> bool:
    """True when prior session topic must not influence retrieval expansion."""
    if is_new_legal_query(query):
        return True
    try:
        from backend.app.core.kb_context_resolver import classify_retrieval_context

        ctx = classify_retrieval_context(query, session_mem)
        return bool(ctx.get("fresh_retrieval") or ctx.get("topic_shift"))
    except ImportError:
        return False


def should_reset_session_context(query: str) -> bool:
    """Alias used by routing/pipeline code when deciding to discard session memory."""
    return requires_fresh_retrieval(query)


def get_effective_session_memory(
    query: str,
    session_mem: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Return session memory for follow-up expansion, or {} when the query is a
    fresh legal lookup that must not inherit prior topic/section context.
    """
    reset_context = requires_fresh_retrieval(query, session_mem)
    log_followup_detection(query, reset_context)
    if reset_context:
        return {}
    return dict(session_mem or {})


def log_followup_detection(query: str, reset_context: bool) -> None:
    """Debug logging for memory reset decisions."""
    print("Detected new legal query:", is_new_legal_query(query))
    print("Session reset:", reset_context)
