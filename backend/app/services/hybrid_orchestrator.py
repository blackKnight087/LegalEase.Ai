"""
Jurisprudence / Hybrid Mode Orchestrator — KB RAG + Gemini Web Intelligence.

Fast path (default): light KB retrieval + one Gemini fusion call with live search.
Legacy path: full kb_pipeline + web_search_query + fusion (3 heavy API/LLM legs).
"""
from __future__ import annotations

import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

from backend.app.services.answer_validator import validate_and_clean_answer
from backend.app.services.response_formatter import format_legal_response
from backend.legal_engine.query_parser import LegalQueryParse

logger = logging.getLogger(__name__)


def _env_on(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


def _hybrid_fast_enabled() -> bool:
    return _env_on("HYBRID_FAST", "1")


def _fetch_kb_hybrid(
    user_id: str,
    effective: str,
    history: Optional[List[Dict]],
    *,
    matter_id: Optional[str] = None,
) -> Tuple[str, List[Dict]]:
    """Hybrid: global legal KB + matter case files (strict separation)."""
    from intent_engine import classify_intent
    from kb_response_state import KB_NOT_FOUND_MESSAGE, build_found_answer
    from backend.app.core.kb_retrieval_router import GlobalKBRetriever, hybrid_retrieve

    k = int(os.getenv("HYBRID_KB_TOP_K", "8"))
    global_chunks, matter_chunks = hybrid_retrieve(
        user_id, effective, matter_id, k_global=k, k_matter=k
    )
    chunks = matter_chunks + global_chunks
    if not chunks:
        return (
            "### Knowledge Base Empty\n\n"
            "No indexed documents in global KB or this matter. Hybrid will still use live web research.",
            [],
        )

    profile = classify_intent(effective, history)
    answer = build_found_answer(
        effective,
        chunks[: max(k, 6)],
        profile,
        messages=history,
        use_llm=False,
        user_id=user_id,
    )
    if not answer or answer.startswith("NOT_FOUND"):
        parts = [(c.get("content") or "")[:500] for c in chunks[:3] if c.get("content")]
        answer = "\n\n".join(parts) if parts else KB_NOT_FOUND_MESSAGE
    return answer, chunks if isinstance(chunks, list) else []


def _fetch_web_hybrid(
    user_id: str,
    query: str,
    history: Optional[List[Dict]],
) -> Tuple[str, List[Dict]]:
    """Skip duplicate Gemini web call when fusion will run Google Search."""
    if _hybrid_fast_enabled() and _env_on("HYBRID_SKIP_PREFETCH_WEB", "1"):
        return "", []
    from app import web_search_query

    ans, sources = web_search_query(query, conversation_history=history, user_id=user_id)
    return ans, sources if isinstance(sources, list) else []


def _extract_section_claims(text: str) -> List[str]:
    return [
        m.group(1).lower()
        for m in re.finditer(r"\b(?:IPC|BNS|Section)\s+(\d{1,4}[a-z]?)\b", text or "", re.I)
    ]


def _conflicts(kb_answer: str, web_answer: str) -> List[str]:
    kb_secs = set(_extract_section_claims(kb_answer))
    web_secs = set(_extract_section_claims(web_answer))
    if not kb_secs or not web_secs:
        return []
    return sorted(kb_secs.symmetric_difference(web_secs))


def merge_hybrid_answers(
    kb_answer: str,
    web_answer: str,
    *,
    parse: Optional[LegalQueryParse] = None,
    kb_chunks: Optional[List[Dict]] = None,
) -> str:
    """Legacy merge when Gemini jurisprudence synthesis is unavailable."""
    kb = (kb_answer or "").strip()
    web = (web_answer or "").strip()
    intent = parse.intent if parse else "general"
    parse_dict = parse.to_dict() if parse else {}

    if not kb or kb.startswith("NOT_FOUND") or "couldn't find" in kb.lower():
        return format_legal_response(web, intent=intent, parse=parse_dict)

    if not web:
        return format_legal_response(kb, intent=intent, parse=parse_dict)

    diffs = _conflicts(kb, web)
    kb_block = format_legal_response(kb, intent=intent, parse=parse_dict)
    web_block = format_legal_response(web, intent=intent, parse=parse_dict)

    if not diffs:
        try:
            from backend.app.core.web_answer_cleaner import polish_research_answer

            return polish_research_answer(
                f"{kb_block}\n\n"
                f"**Public Law Context (Web Intel)**\n{web_block}"
            )
        except ImportError:
            pass
        return (
            f"{kb_block}\n\n"
            f"**Public Law Context (Web Intel)**\n{web_block}"
        )

    note = (
        "Where your uploaded documents and public sources differ, "
        "the answer below prioritizes your uploaded documents."
    )
    return (
        f"{note}\n\n"
        f"**From Your Documents (Knowledge Base)**\n{kb_block}\n\n"
        f"**From Public Legal Sources (Gemini)**\n{web_block}"
    )


def _kb_not_found(kb_answer: str) -> bool:
    kb = (kb_answer or "").strip()
    return (
        not kb
        or kb.startswith("NOT_FOUND")
        or "couldn't find" in kb.lower()
        or "not found in document" in kb.lower()
        or kb.startswith("### Knowledge Base Empty")
    )


def _chunks_to_similar_cases(kb_chunks: List[Dict]) -> List[Dict]:
    out: List[Dict] = []
    for ch in kb_chunks[:8]:
        meta = ch.get("metadata") or {}
        content = (ch.get("content") or "")[:240]
        out.append({
            "filename": meta.get("filename") or ch.get("filename") or "document",
            "excerpt": content + ("..." if len(ch.get("content") or "") > 240 else ""),
            "relevance": "High" if float(ch.get("final_score", ch.get("hybrid_score", 0)) or 0) > 0.5 else "Medium",
            "score": ch.get("final_score") or ch.get("hybrid_score"),
            "chunk_index": meta.get("chunk_index", 0),
        })
    return out


def stream_hybrid_research(
    user_id: str,
    query: str,
    history: Optional[List[Dict]] = None,
    *,
    matter_id: Optional[str] = None,
    parse: Optional[LegalQueryParse] = None,
    membership: str = "Free",
) -> Generator[Union[Dict[str, Any], Dict[str, str]], None, None]:
    """
    Yields status events then a final result event for SSE progress UI.
    """
    from backend.app.core.research_progress import (
        HYBRID_ANALYZE,
        HYBRID_COLLECT_WEB,
        HYBRID_COMPOSE,
        HYBRID_FINALIZE,
        HYBRID_SEARCH_KB,
        result_event,
        status_event,
    )

    effective = (parse.resolved_query if parse else None) or query
    kb_answer = ""
    kb_chunks: List[Dict] = []
    web_answer = ""
    web_sources: List[Dict] = []
    t0 = time.perf_counter()

    skip_kb_fetch = False
    try:
        from backend.app.core.kb_hybrid_gate import should_skip_kb_retrieval

        skip_kb_fetch = should_skip_kb_retrieval(query)
        if skip_kb_fetch:
            yield status_event(
                "Topic not in your uploads — using live legal research only…"
            )
    except Exception:
        pass

    if not skip_kb_fetch:
        yield status_event(HYBRID_SEARCH_KB)

    def _fetch_kb() -> Tuple[str, List[Dict]]:
        if skip_kb_fetch:
            return "", []
        if _hybrid_fast_enabled() and _env_on("HYBRID_KB_LIGHT", "1"):
            return _fetch_kb_hybrid(user_id, effective, history, matter_id=matter_id)
        from app import rag_query

        ans, chunks = rag_query(
            user_id,
            effective,
            k=10,
            find_similar_cases=True,
            conversation_history=history,
            matter_id=matter_id,
        )
        return ans, chunks if isinstance(chunks, list) else []

    def _fetch_web() -> Tuple[str, List[Dict]]:
        return _fetch_web_hybrid(user_id, query, history)

    yield status_event(HYBRID_COLLECT_WEB)

    with ThreadPoolExecutor(max_workers=2) as pool:
        kb_future = pool.submit(_fetch_kb)
        web_future = pool.submit(_fetch_web)
        for fut in as_completed([kb_future, web_future]):
            try:
                if fut is kb_future:
                    kb_answer, kb_chunks = fut.result()
                else:
                    web_answer, web_sources = fut.result()
            except Exception as exc:
                logger.warning("[JURISPRUDENCE] parallel leg failed: %s", exc)

    phase1_ms = int((time.perf_counter() - t0) * 1000)

    try:
        from backend.app.core.kb_hybrid_gate import assess_kb_for_hybrid

        use_kb, gate_reason = assess_kb_for_hybrid(query, kb_answer, kb_chunks)
        if not use_kb:
            logger.info(
                "[HYBRID] kb_gated_out reason=%s query=%s",
                gate_reason,
                (query or "")[:80],
            )
            kb_answer = ""
            kb_chunks = []
            yield status_event(
                "No matching content in your uploads — using live legal research only…"
            )
    except Exception as exc:
        logger.debug("[HYBRID] kb gate failed: %s", exc)

    logger.info(
        "[HYBRID] phase1_ms=%s kb_chunks=%s web_prefetch=%s kb_used=%s",
        phase1_ms,
        len(kb_chunks),
        bool(web_answer),
        bool(kb_chunks),
    )

    yield status_event(HYBRID_ANALYZE)
    merged = ""
    try:
        from backend.app.core.web_intelligence import gemini_configured, synthesize_jurisprudence_report

        yield status_event(HYBRID_COMPOSE)
        if gemini_configured():
            use_search = not (web_answer and len(web_answer.strip()) > 200)
            merged, fused_sources, _ = synthesize_jurisprudence_report(
                query,
                kb_answer,
                kb_chunks,
                web_answer,
                web_sources,
                conversation_history=history,
                user_id=user_id,
                membership=membership,
                use_google_search=use_search,
            )
            if fused_sources:
                web_sources = fused_sources
    except Exception as exc:
        logger.warning("[JURISPRUDENCE] fusion failed, using legacy merge: %s", exc)

    if not merged:
        if _hybrid_fast_enabled() and not web_answer:
            try:
                from backend.app.services.open_law_executor import fetch_open_law_answer

                ol = fetch_open_law_answer(
                    user_id,
                    effective,
                    query,
                    history or [],
                    membership=membership,
                    mode="hybrid",
                )
                if ol.has_content():
                    web_answer = ol.content
                    web_sources = ol.web_sources or []
            except Exception:
                pass
        merged = merge_hybrid_answers(
            kb_answer if not _kb_not_found(kb_answer) else "",
            web_answer,
            parse=parse,
            kb_chunks=kb_chunks,
        )

    logger.info("[HYBRID] total_ms=%s", int((time.perf_counter() - t0) * 1000))

    yield status_event(HYBRID_FINALIZE)
    skip_heavy = _hybrid_fast_enabled()
    vr = validate_and_clean_answer(
        merged,
        query,
        kb_chunks,
        intent=parse.intent if parse else "general",
        parse=parse.to_dict() if parse else {},
        strict_grounded=False,
    )
    final_answer = vr.answer
    try:
        from backend.app.core.web_answer_cleaner import polish_research_answer

        final_answer = polish_research_answer(final_answer)
    except Exception:
        pass
    if not skip_heavy:
        try:
            from backend.app.core.citation_verifier import apply_strict_citations

            final_answer, _ = apply_strict_citations(final_answer, kb_chunks, web_sources)
        except Exception:
            pass

    if kb_chunks and matter_id and not skip_heavy:
        try:
            from backend.app.core.contradiction_checker import (
                find_contradictions,
                format_contradiction_report,
            )

            findings = find_contradictions(kb_chunks)
            block = format_contradiction_report(findings)
            if block and block not in final_answer:
                final_answer = final_answer.rstrip() + "\n\n" + block
        except Exception:
            pass

    try:
        from backend.app.core.source_badges import enrich_web_sources

        web_sources = enrich_web_sources(web_sources)
    except Exception:
        pass

    similar = _chunks_to_similar_cases(kb_chunks)
    yield result_event(final_answer, similar, web_sources)


def run_hybrid_turn(
    user_id: str,
    query: str,
    history: Optional[List[Dict]] = None,
    *,
    matter_id: Optional[str] = None,
    parse: Optional[LegalQueryParse] = None,
    membership: str = "Free",
    on_status: Optional[Callable[[str], None]] = None,
) -> Tuple[str, List[Dict], List[Dict]]:
    """Sync Hybrid turn; optional on_status for non-SSE callers."""
    content = ""
    similar: List[Dict] = []
    web_sources: List[Dict] = []
    for event in stream_hybrid_research(
        user_id,
        query,
        history,
        matter_id=matter_id,
        parse=parse,
        membership=membership,
    ):
        if event.get("type") == "status":
            msg = str(event.get("message") or "")
            if on_status and msg:
                on_status(msg)
        elif event.get("type") == "result":
            content = str(event.get("content") or "")
            similar = list(event.get("similar_cases") or [])
            web_sources = list(event.get("web_sources") or [])
    return content, similar, web_sources


def run_jurisprudence_turn(
    user_id: str,
    query: str,
    history: Optional[List[Dict]] = None,
    *,
    matter_id: Optional[str] = None,
    parse: Optional[LegalQueryParse] = None,
    membership: str = "Free",
) -> Tuple[str, List[Dict], List[Dict]]:
    """Alias for deep_case / Hybrid UI mode."""
    return run_hybrid_turn(
        user_id,
        query,
        history,
        matter_id=matter_id,
        parse=parse,
        membership=membership,
    )
