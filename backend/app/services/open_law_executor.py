"""
Central Open Law answer pipeline — one code path for sync turns and stream fallback.

All external APIs with inconsistent return shapes (2-tuple, 3-tuple) are normalized
to ChatTurnResult here so callers never unpack the wrong arity.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend.app.core.kb_pipeline_log import kb_log
from backend.app.services.chat_turn_types import ChatTurnResult
from .follow_ups import suggest_follow_ups

_KB_LEAK_MARKERS = (
    "from your documents (knowledge base)",
    "ipc sections mentioned in your document",
    "where your uploaded documents and public sources differ",
    "this list is extracted only from your uploaded document",
    "not found in the uploaded legal documents",
)


def looks_like_kb_leak(text: str) -> bool:
    low = (text or "").lower()
    return any(m in low for m in _KB_LEAK_MARKERS)


def merge_stream_buffer(content: str, streamed_parts: List[str]) -> str:
    return (content or "").strip() or "".join(streamed_parts)


def needs_open_law_fallback(content: str, streamed_parts: Optional[List[str]] = None) -> bool:
    merged = merge_stream_buffer(content, streamed_parts or [])
    return not merged or looks_like_kb_leak(merged)


def resolve_gemini_history(search_q: str, history: List[Dict]) -> Optional[List[Dict]]:
    filtered: List[Dict] = history
    try:
        from backend.app.core.web_intelligence import _filter_open_law_history

        filtered = _filter_open_law_history(history)
    except Exception:
        pass
    try:
        from legal_web_query import is_self_contained_web_query

        if is_self_contained_web_query(search_q):
            return None
    except ImportError:
        pass
    return filtered


def _enrich_web_sources(web_sources: List[dict]) -> List[dict]:
    try:
        from backend.app.core.source_badges import enrich_web_sources

        return enrich_web_sources(web_sources or [])
    except Exception:
        return web_sources or []


def _from_grounded_research(
    search_q: str,
    gemini_history: Optional[List[Dict]],
    *,
    user_id: str,
    thread_id: str,
    membership: str,
) -> ChatTurnResult:
    from backend.app.core.web_provider_chain import run_legal_web_research

    answer, sources, follow_ups, meta = run_legal_web_research(
        search_q,
        gemini_history,
        user_id=user_id,
        thread_id=thread_id or "",
        membership=membership,
    )
    return ChatTurnResult(
        content=answer or "",
        web_sources=list(sources or []),
        follow_ups=list(follow_ups or []),
        metadata={"web_provider": meta.get("provider"), "web_chain": meta.get("chain")},
    )


def _from_web_search(
    search_q: str,
    gemini_history: Optional[List[Dict]],
    *,
    user_id: str,
    skip_gemini: bool = False,
) -> ChatTurnResult:
    if skip_gemini:
        return _from_legacy_web_search(search_q, gemini_history, user_id=user_id)

    from app import web_search_query

    answer, sources = web_search_query(
        search_q,
        conversation_history=gemini_history,
        user_id=user_id,
    )
    return ChatTurnResult(content=answer or "", web_sources=list(sources or []))


def _memory_answer_usable(query: str, answer: str) -> bool:
    """Reject polluted memory replays (IPC chart dumps for unrelated contract queries)."""
    import re

    q = (query or "").lower()
    a = (answer or "").lower()
    if not a.strip():
        return False
    chart_hits = len(re.findall(r"\bipc\s+\d+", a))
    if chart_hits >= 3 and "bns" in a:
        if not re.search(r"\b(ipc|bns|crpc|bnss|section|mapping|compare|versus|vs\.?)\b", q):
            return False
    stop = {
        "what", "when", "where", "which", "why", "how", "explain", "define", "about",
        "under", "indian", "india", "legal", "law", "the", "and", "for", "with",
    }
    terms = [
        w.strip("?.!,;:'\"()[]")
        for w in q.split()
        if len(w) > 3 and w.lower() not in stop
    ]
    if len(terms) >= 2:
        hits = sum(1 for t in terms if t in a)
        if hits < max(1, len(terms) // 3):
            return False
    return True


def _fast_compose_from_snippets(search_q: str, snippets: List[dict], history: Optional[List[Dict]]) -> ChatTurnResult:
    """Fast Open Law fallback — snippet compose only, no local LLM call."""
    from intent_engine import classify_intent
    from legal_web_engine import intent_compose_from_snippets, rank_legal_snippets, resolve_web_response_kind
    from legal_web_query import is_self_contained_web_query

    hist = None if is_self_contained_web_query(search_q) else history
    ranked = rank_legal_snippets(snippets, search_q)
    profile = classify_intent(search_q, hist)
    kind = resolve_web_response_kind(search_q, profile)
    text, follow_ups = intent_compose_from_snippets(search_q, ranked, kind)
    return ChatTurnResult(content=text or "", web_sources=list(snippets or []), follow_ups=list(follow_ups or []))


def _from_legacy_web_search(
    search_q: str,
    gemini_history: Optional[List[Dict]],
    *,
    user_id: str,
    fast_compose: bool = False,
) -> ChatTurnResult:
    """Backup path: DuckDuckGo/Tavily snippets + compose — never calls Gemini."""
    import os

    from app import _web_intel_unavailable_message
    from legal_web_query import is_self_contained_web_query
    from llms import search_web

    max_web = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6"))
    snippets = search_web(
        search_q,
        max_results=max_web,
        conversation_history=gemini_history,
        skip_gemini=True,
    )
    if snippets and snippets[0].get("provider") == "LegalEase":
        return ChatTurnResult(content=snippets[0].get("body", ""), web_sources=snippets)

    if not snippets or (len(snippets) == 1 and snippets[0].get("provider") == "Unavailable"):
        return ChatTurnResult(
            content=_web_intel_unavailable_message(),
            web_sources=snippets or [],
        )

    synth_history = None if is_self_contained_web_query(search_q) else gemini_history
    if fast_compose:
        return _fast_compose_from_snippets(search_q, snippets, synth_history)

    from answer_orchestrator import orchestrate_web_answer
    from app import sanitize_assistant_response, _compose_web_answer_from_snippets

    result = orchestrate_web_answer(search_q, snippets, messages=synth_history, user_id=user_id)
    answer = sanitize_assistant_response(
        result.text,
        fallback=_compose_web_answer_from_snippets(snippets, search_q),
    )
    return ChatTurnResult(
        content=answer or "",
        web_sources=list(snippets or []),
        follow_ups=list(result.follow_ups or []),
    )


def fetch_open_law_answer(
    user_id: str,
    search_q: str,
    prompt: str,
    history: List[Dict],
    *,
    membership: str = "Free",
    thread_id: str = "",
    mode: str = "open_law",
    skip_gemini: bool = False,
) -> ChatTurnResult:
    """
    Single sync Open Law fetch: strict memory → Gemini → legacy web fallback.
    Used by non-stream turns and stream recovery (never call _run_open_law_turn twice).
    """
    from app import sanitize_assistant_response
    from backend.app.core.gemini_errors import (
        gemini_error_user_hint,
        gemini_quota_cooldown_active,
        is_gemini_quota_error,
        mark_gemini_quota_exhausted,
    )

    kb_log("OPEN_LAW", query=search_q, user_id=user_id, skip_gemini=skip_gemini)

    if skip_gemini or gemini_quota_cooldown_active():
        skip_gemini = True

    try:
        from backend.app.core.learning_engine import lookup_answer_memory

        mem = lookup_answer_memory(user_id, search_q, strict=True)
        if mem and (mem.get("answer") or "").strip():
            ans = mem["answer"].strip()
            if _memory_answer_usable(search_q, ans):
                return ChatTurnResult(
                    content=ans,
                    web_sources=_enrich_web_sources([]),
                    follow_ups=suggest_follow_ups(prompt, ans, mode),
                )
            kb_log("OPEN_LAW_MEMORY_SKIP", query=search_q, reason="irrelevant_cached_answer")
    except Exception:
        pass

    gemini_history = resolve_gemini_history(search_q, history)
    result = ChatTurnResult(content="")
    gemini_failed = skip_gemini
    last_gemini_error: Optional[Exception] = None

    if not skip_gemini:
        try:
            from backend.app.core.web_intelligence import gemini_configured

            if gemini_configured():
                result = _from_grounded_research(
                    search_q,
                    gemini_history,
                    user_id=user_id,
                    thread_id=thread_id,
                    membership=membership,
                )
                try:
                    from legal_web_query import (
                        build_web_search_query,
                        looks_like_dictionary_web_answer,
                    )

                    if looks_like_dictionary_web_answer(
                        result.content, result.web_sources
                    ):
                        retry_q = build_web_search_query(prompt, history)
                        if retry_q and retry_q.lower() != search_q.lower():
                            kb_log("OPEN_LAW_RETRY", query=retry_q[:120])
                            result = _from_grounded_research(
                                retry_q,
                                None,
                                user_id=user_id,
                                thread_id=thread_id,
                                membership=membership,
                            )
                except ImportError:
                    pass
        except RuntimeError as exc:
            gemini_failed = True
            last_gemini_error = exc
            result = ChatTurnResult(content=f"### Open Law\n\n{exc}")
        except Exception as exc:
            gemini_failed = True
            last_gemini_error = exc
            if is_gemini_quota_error(exc):
                mark_gemini_quota_exhausted()
            kb_log("OPEN_LAW_GEMINI_ERROR", error=str(exc)[:160])

        if (
            not gemini_failed
            and looks_like_kb_leak(result.content)
            and not is_gemini_quota_error(last_gemini_error or "")
        ):
            kb_log("OPEN_LAW_KB_LEAK_RETRY", query=search_q)
            try:
                from backend.app.core.web_intelligence import gemini_configured

                if gemini_configured():
                    result = _from_grounded_research(
                        search_q,
                        None,
                        user_id=user_id,
                        thread_id=thread_id,
                        membership=membership,
                    )
            except Exception as exc:
                gemini_failed = True
                last_gemini_error = exc

    if skip_gemini or gemini_failed or needs_open_law_fallback(result.content):
        try:
            result = _from_legacy_web_search(
                search_q,
                gemini_history,
                user_id=user_id,
                fast_compose=True,
            )
            if gemini_failed and last_gemini_error and is_gemini_quota_error(last_gemini_error):
                hint = gemini_error_user_hint(last_gemini_error)
                if result.has_content() and "Web Intelligence Unavailable" not in result.content:
                    result = ChatTurnResult(
                        content=f"> *{hint}*\n\n{result.content}",
                        web_sources=result.web_sources,
                        follow_ups=result.follow_ups,
                    )
        except Exception as exc:
            kb_log("OPEN_LAW_FALLBACK_ERROR", error=str(exc)[:160])
            hint = gemini_error_user_hint(last_gemini_error or exc) if gemini_failed else str(exc)
            result = ChatTurnResult(
                content=(
                    "### Open Law Intelligence\n\n"
                    f"Could not complete web research.\n\n{hint}"
                )
            )

    content = sanitize_assistant_response(result.content or "", fallback=result.content or "")
    follow_ups = result.follow_ups or suggest_follow_ups(prompt, content, mode)
    web_sources = _enrich_web_sources(result.web_sources if isinstance(result.web_sources, list) else [])
    return ChatTurnResult(content=content, web_sources=web_sources, follow_ups=follow_ups)
