"""
KB query expansion — session memory + conversation history for follow-ups.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from conversation_context import (
    build_conversation_state,
    enrich_query_with_context,
    extract_law_from_text,
    extract_sections_from_text,
    merge_retrieval_query,
)


def expand_kb_query(
    question: str,
    history: Optional[List[Dict]] = None,
    *,
    session_mem: Optional[Dict[str, Any]] = None,
    intent_expanded: str = "",
) -> str:
    """
    Full KB query expansion for retrieval and synthesis.

    Order: session memory → conversation history → intent expansion.
    """
    q = (question or "").strip()
    if not q:
        return q

    expanded = q
    try:
        from kb_query_types import is_bare_section_query, is_case_query

        if is_bare_section_query(q) or is_case_query(q):
            return q
    except ImportError:
        pass

    try:
        from backend.app.core.constitutional_concept_map import is_constitutional_query

        if is_constitutional_query(q):
            return q
    except ImportError:
        pass

    ctx: Dict[str, Any] = {}
    meta_follow_up = False
    try:
        from conversation_context import is_meta_follow_up

        meta_follow_up = is_meta_follow_up(q)
    except ImportError:
        pass
    try:
        from backend.app.core.kb_context_resolver import classify_retrieval_context
        from backend.app.services.followup_detector import get_effective_session_memory

        ctx = classify_retrieval_context(q, session_mem)
        if (ctx.get("fresh_retrieval") or ctx.get("topic_shift")) and not meta_follow_up:
            return q
        session_mem = get_effective_session_memory(q, session_mem)
    except ImportError:
        ctx = {}

    if session_mem and not ctx.get("topic_shift"):
        try:
            from backend.app.core.conversation_memory import resolve_follow_up_query

            mem_expanded = resolve_follow_up_query(q, session_mem)
            if mem_expanded and mem_expanded != q:
                expanded = mem_expanded
        except Exception:
            pass

    if history:
        ctx_expanded = enrich_query_with_context(expanded, history)
        if ctx_expanded and ctx_expanded.strip() != expanded.strip():
            expanded = ctx_expanded

    merged = merge_retrieval_query(expanded, history, intent_expanded=intent_expanded)
    return merged.strip() or q


def memory_context_block(session_mem: Optional[Dict[str, Any]]) -> str:
    """Prompt block so LLM sees active topic during follow-ups."""
    if not session_mem:
        return ""
    topic = session_mem.get("last_topic") or ""
    sec = session_mem.get("last_section") or ""
    law = session_mem.get("last_law") or ""
    if not topic and not sec:
        return ""
    parts = [f"Active legal topic: {topic or f'{law} Section {sec.upper()}'}"]
    if sec:
        parts.append(f"Active section: {law} Section {sec.upper()}")
    return "\n".join(parts)
