"""
Chat intelligence service — no Streamlit dependency.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Generator, List, Optional, Tuple

from ..core.conversation_memory import (
    append_turn,
    get_or_create_session,
    get_session_history,
    get_session_state,
)
from ..core.session_store import get_session, set_session
from ..core.kb_pipeline_log import kb_log
from .chat_turn_types import ChatTurnResult
from .open_law_executor import (
    fetch_open_law_answer,
    looks_like_kb_leak,
    merge_stream_buffer,
    needs_open_law_fallback,
    resolve_gemini_history,
)
from intent_engine import classify_intent
from .follow_ups import suggest_follow_ups
from kb_response_state import (
    KB_NOT_FOUND_MESSAGE,
    contains_not_found_phrase,
    enforce_single_state,
    has_substantive_legal_content,
    log_kb_pipeline,
)

KB_NOT_FOUND = KB_NOT_FOUND_MESSAGE

_GARBAGE = frozenset({"{}", "{ }", "[]", "[ ]", "null", "none", '""', "''"})
_BROKEN_FALLBACK_MARKERS = (
    "couldn't generate a proper answer",
    "could not generate a proper answer",
    "found related document content, but",
)


def _enrich_web_sources(web_sources: List[dict]) -> List[dict]:
    try:
        from backend.app.core.source_badges import enrich_web_sources

        return enrich_web_sources(web_sources or [])
    except Exception:
        return web_sources or []


def _translate_if_needed(content: str, lang: str) -> str:
    if lang == "English" or not (content or "").strip():
        return content or ""
    try:
        from backend.app.core.translate_answer import translate_after_synthesis

        return translate_after_synthesis(content, lang)
    except Exception:
        return content


def _log_research(user_id: str, prompt: str, mode: str, matter_id: Optional[str] = None) -> None:
    if mode not in ("web_search", "deep_case", "hybrid", "open_law"):
        return
    try:
        from backend.app.core.research_service import log_research_query

        mode_map = {
            "web_search": "OPEN_LAW",
            "deep_case": "HYBRID",
            "hybrid": "HYBRID",
            "open_law": "OPEN_LAW",
        }
        log_research_query(
            user_id,
            prompt.strip(),
            selected_mode=mode_map.get(mode, mode.upper()),
            matter_id=matter_id or "",
        )
    except Exception:
        pass


def _maybe_oral_argument(content: str, prompt: str, user_id: str, membership: str) -> str:
    try:
        from backend.app.core.oral_argument import is_oral_argument_request, prepare_oral_argument

        if is_oral_argument_request(prompt) and (content or "").strip():
            try:
                from backend.app.core.gemini_usage import assert_gemini_allowed

                assert_gemini_allowed(user_id, membership)
            except RuntimeError:
                raise
            except Exception:
                pass
            prep = prepare_oral_argument(content, prompt, user_id=user_id)
            if prep:
                return prep
    except RuntimeError:
        raise
    except Exception:
        pass
    return content


def _is_garbage_text(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized or normalized in _GARBAGE:
        return True
    if any(m in normalized for m in _BROKEN_FALLBACK_MARKERS):
        return True
    if re.search(r"^##\s+(?:ipc|bns)\s+section\s+\d", normalized, re.I):
        return False
    if len(re.findall(r"[A-Za-z0-9]", normalized)) < 5:
        return True
    return False


def _synthesize_from_chunks_fallback(
    prompt: str,
    history: List[Dict],
    user_id: str,
    matter_id: Optional[str] = None,
) -> str:
    """Last-resort answer from retrieved chunks when the main pipeline fails."""
    try:
        from app import resolve_rag_index_dir
        from rag import query_kb
        from kb_rag_decision import evaluate_retrieval
        from kb_response_state import build_found_answer

        index_dir = resolve_rag_index_dir(user_id, None, retrieval_scope="global")
        profile = classify_intent(prompt, history)
        results = query_kb(
            profile.expanded_query or prompt,
            k=min(profile.retrieval_k or 12, 14),
            index_dir=index_dir,
        )
        if not results:
            return KB_NOT_FOUND_MESSAGE

        found, best_score, decision, debug = evaluate_retrieval(prompt, results)
        if not found:
            log_kb_pipeline(
                query=prompt,
                decision="NOT_FOUND",
                best_score=best_score,
                threshold=debug.get("threshold", 0.28),
                chunks=[],
                answer=KB_NOT_FOUND_MESSAGE,
            )
            return KB_NOT_FOUND_MESSAGE

        answer = build_found_answer(
            prompt,
            results[:6],
            profile,
            messages=history,
            use_llm=True,
            max_tokens=2048,
        )
        if not answer:
            answer = build_found_answer(
                prompt,
                results[:6],
                profile,
                messages=history,
                use_llm=False,
                max_tokens=2048,
            )
        answer = enforce_single_state(answer, found=True)
        if answer:
            log_kb_pipeline(
                query=prompt,
                decision="FOUND",
                best_score=best_score,
                chunks=results[:3],
                answer=answer,
            )
            return answer
        return KB_NOT_FOUND_MESSAGE
    except Exception as exc:
        kb_log("FALLBACK_ERROR", error=str(exc))
        return KB_NOT_FOUND_MESSAGE


def _finalize_kb_answer(
    text: str,
    prompt: str,
    history: List[Dict],
    user_id: str,
    similar_cases: Optional[List[dict]] = None,
    matter_id: Optional[str] = None,
) -> Tuple[str, Dict[str, str]]:
    """Enforce FOUND vs NOT_FOUND; return body + separate source metadata."""
    from response_cleaner import finalize_display_answer, is_empty_payload

    empty_source: Dict[str, str] = {"filename": "", "section": ""}

    try:
        from llms import is_ollama_error_response

        if is_ollama_error_response(str(text or "")):
            kb_log("OLLAMA_OOM", preview=str(text)[:200])
            text = ""
    except Exception:
        pass

    try:
        from backend.app.core.kb_retrieval_debug import is_retrieval_hard_fail

        if is_retrieval_hard_fail(text):
            body = (text or KB_NOT_FOUND_MESSAGE).strip()
            kb_log("KB_HARD_FAIL", reason="zero_chunks", preview=body[:120])
            return body, empty_source
    except Exception:
        pass

    if str(text).startswith("NOT_FOUND_IN_KB"):
        try:
            from app import resolve_rag_index_dir
            from rag import query_kb
            from backend.app.core.kb_force_answer import guarantee_kb_answer

            index_dir = resolve_rag_index_dir(user_id, None, retrieval_scope="global")
            chunks = query_kb(prompt, k=8, index_dir=index_dir)
            # region agent log
            try:
                from backend.app.core.debug_session_log import debug_log

                debug_log(
                    "C",
                    "chat_service.py:_finalize_kb_answer",
                    "NOT_FOUND_recovery",
                    {
                        "prompt": prompt[:120],
                        "matter_id": matter_id or "",
                        "index_dir": str(index_dir),
                        "recovery_chunks": len(chunks or []),
                        "top_score": float(
                            (chunks[0].get("final_score") or chunks[0].get("score") or 0)
                        )
                        if chunks
                        else 0,
                    },
                )
            except Exception:
                pass
            # endregion
            if chunks:
                forced = guarantee_kb_answer(prompt, chunks)
                if forced:
                    return enforce_single_state(forced, found=True), empty_source
        except Exception:
            pass
        try:
            from app import resolve_rag_index_dir
            from backend.app.core.learning_engine import lookup_answer_memory, rescue_broken_kb

            mem = lookup_answer_memory(user_id, prompt)
            if mem and mem.get("answer"):
                try:
                    from backend.app.services.legal_query_parser import answer_satisfies_section_query

                    if not answer_satisfies_section_query(prompt, mem["answer"]):
                        mem = None
                except ImportError:
                    pass
            if mem and mem.get("answer"):
                return enforce_single_state(mem["answer"], found=True), empty_source
            index_dir = resolve_rag_index_dir(user_id, None, retrieval_scope="global")
            profile = classify_intent(prompt, history)
            rescued = rescue_broken_kb(
                user_id,
                prompt,
                history=history,
                index_dir=index_dir,
                profile=profile,
            )
            if rescued:
                ans, _, _ = rescued
                return enforce_single_state(ans, found=True), empty_source
        except Exception:
            pass
        return KB_NOT_FOUND_MESSAGE, empty_source

    cleaned = (text or "").strip()

    if contains_not_found_phrase(cleaned):
        if has_substantive_legal_content(cleaned):
            cleaned = enforce_single_state(cleaned, found=True)
        else:
            return KB_NOT_FOUND_MESSAGE, empty_source

    if is_empty_payload(cleaned) or _is_garbage_text(cleaned):
        recovered = _synthesize_from_chunks_fallback(prompt, history, user_id, matter_id)
        if recovered == KB_NOT_FOUND_MESSAGE:
            return KB_NOT_FOUND_MESSAGE, empty_source
        cleaned = recovered

    final = enforce_single_state(cleaned, found=True)
    if not final:
        if contains_not_found_phrase(cleaned):
            return KB_NOT_FOUND_MESSAGE, empty_source
        final = cleaned

    filename = ""
    section = ""
    if similar_cases:
        filename = str(similar_cases[0].get("filename") or "")
    if not filename and final:
        src_m = re.search(
            r"(?:\*\*Source:\*\*|SOURCE:?)\s*([^\n—]+?)(?:\s*[—–-]\s*Section\s+(\d{1,4}[a-z]?))?",
            final,
            re.I,
        )
        if src_m:
            filename = src_m.group(1).strip()
            if src_m.group(2) and not section:
                section = src_m.group(2).upper()
    from kb_rag_decision import extract_query_sections

    try:
        from document_classifier import is_contract_topic_query

        contract_query = is_contract_topic_query(prompt)
    except ImportError:
        contract_query = False

    secs = extract_query_sections(prompt) if not contract_query else []
    if secs:
        section = secs[0].upper()

    body, source_meta = finalize_display_answer(
        final,
        section_hint=f"Section {section}" if section else "",
        section=secs[0] if secs else "",
    )
    if filename and not source_meta.get("filename"):
        source_meta["filename"] = filename
    if section:
        source_meta["section"] = section
    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        debug_log(
            "FIX",
            "chat_service.py:_finalize_kb_answer",
            "finalize_ok",
            {"answer_len": len(body or ""), "preview": (body or "")[:120]},
            run_id="post-fix",
        )
    except Exception:
        pass
    # endregion
    if matter_id and body:
        try:
            from backend.app.core.matter_autopilot import load_matter_doc_texts
            from backend.app.core.citation_verifier import annotate_matter_legal_claims

            chunks = load_matter_doc_texts(str(user_id), matter_id)
            corpus = "\n".join(c.get("content", "") for c in chunks)
            if len(corpus) > 40:
                body = annotate_matter_legal_claims(body, corpus)
        except Exception:
            pass
    return body or KB_NOT_FOUND_MESSAGE, source_meta


def _resolve_history(history: List[Dict], session_id: str) -> List[Dict]:
    if history:
        return _sanitize_chat_history(history)
    return _sanitize_chat_history(get_session_history(session_id))


def _sanitize_chat_history(history: List[Dict]) -> List[Dict]:
    """Drop verbal feedback turns so they never pollute the next legal query."""
    cleaned: List[Dict] = []
    try:
        from legal_web_query import is_conversational_feedback
    except ImportError:
        is_conversational_feedback = None  # type: ignore

    for msg in history or []:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        if role == "user" and is_conversational_feedback and is_conversational_feedback(
            content, history
        ):
            continue
        if role == "assistant" and (
            "glad that helped" in content.lower()
            or "you're welcome" in content.lower()
            or "thanks for the honest feedback" in content.lower()
            or "thanks for the feedback" in content.lower()
        ):
            continue
        cleaned.append({"role": role, "content": content})
    return cleaned


def _detect_implicit_correction(history: List[Dict], new_prompt: str) -> Optional[Tuple[str, str]]:
    """If user re-asked after NOT_FOUND, return (previous_query, correction)."""
    if len(history) < 2:
        return None
    prev_user = ""
    prev_asst = ""
    for m in reversed(history[:-1] if history[-1].get("role") == "user" else history):
        role = m.get("role", "")
        if role == "assistant" and not prev_asst:
            prev_asst = m.get("content", "")
        elif role == "user" and not prev_user:
            prev_user = m.get("content", "")
        if prev_user and prev_asst:
            break
    if prev_user and contains_not_found_phrase(prev_asst):
        from backend.app.core.adaptive_learning import normalize_query

        if normalize_query(prev_user) != normalize_query(new_prompt):
            return prev_user, new_prompt
    return None


def _record_mode_interaction(
    user_id: str,
    mode: str,
    prompt: str,
    content: str,
    *,
    chat_id: str = "",
    thread_id: str = "",
    found: bool = True,
    scope_key: str = "global",
) -> str:
    import uuid

    fallback_id = str(uuid.uuid4())
    try:
        from backend.app.core.adaptive_learning import record_interaction

        return record_interaction(
            user_id,
            mode,
            prompt,
            answer=content,
            found_in_kb=found and has_substantive_legal_content(content),
            chat_id=chat_id,
            thread_id=thread_id,
            implicit_signal="mode_turn",
            scope_key=scope_key,
        )
    except Exception as exc:
        kb_log("INTERACTION_RECORD_ERROR", error=str(exc)[:120])
        try:
            from backend.app.core.adaptive_learning import get_last_interaction_id

            last = get_last_interaction_id(str(user_id))
            if last:
                return last
        except Exception:
            pass
        return fallback_id


def _stream_text_chunks(text: str, parts: int = 14) -> Generator[str, None, None]:
    if not text:
        return
    step = max(1, len(text) // parts)
    for i in range(0, len(text), step):
        yield text[i : i + step]


def _persist_chat_turn_fast(
    user_id: str,
    prompt: str,
    content: str,
    *,
    lang: str = "English",
    mode: str = "knowledge_base",
    thread_id: Optional[str] = None,
    matter_id: Optional[str] = None,
) -> Dict[str, str]:
    """Fast SQLite save — runs before SSE meta so threads exist for reload/feedback."""
    saved: Dict[str, str] = {"chat_id": "", "thread_id": (thread_id or "").strip()}
    try:
        from backend.app.core.chat_persistence import save_chat_turn

        saved = save_chat_turn(
            user_id,
            prompt.strip(),
            content or "(no response generated)",
            language=lang,
            mode=mode,
            thread_id=thread_id,
            matter_id=matter_id,
        )
        kb_log("CHAT_SAVED", thread_id=saved.get("thread_id"), user_id=user_id)
    except Exception as exc:
        kb_log("CHAT_SAVE_ERROR", error=str(exc)[:160])
    return saved


def _defer_chat_indexing(
    user_id: str,
    prompt: str,
    content: str,
    *,
    thread_id: str,
    history: Optional[List[dict]] = None,
    chat_id: str = "",
    matter_id: Optional[str] = None,
) -> None:
    """Slow indexing/summary — never block the live stream."""

    def _bg() -> None:
        try:
            from backend.app.core.chat_conversation_rag import index_chat_turn
            from backend.app.core.user_memory import update_thread_summary

            tid = thread_id or ""
            update_thread_summary(user_id, tid, prompt.strip(), content or "", history or [])
            index_chat_turn(
                user_id,
                tid,
                prompt.strip(),
                content or "",
                chat_id=chat_id,
                matter_id=matter_id,
            )
        except Exception:
            pass

    try:
        import threading

        threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        pass


def _apply_learner_mode_prefix(user_id: str, routed_prompt: str) -> str:
    try:
        from backend.app.core.user_preferences import get_learner_mode

        if get_learner_mode(user_id):
            return (
                "LEARNER MODE: Use simple language, IRAC structure when explaining legal tests, "
                "define terms briefly, and avoid unexplained jargon.\n\n" + routed_prompt
            )
    except Exception:
        pass
    return routed_prompt


def _matter_mode_instruction(matter_mode: Optional[str]) -> str:
    mm = (matter_mode or "").strip().lower()
    if not mm:
        return ""
    base = (
        "MATTER AI RULES: Answer in clear structured prose (bullets/numbered lists). "
        "Never paste raw PDF text, FIR headers, page markers, or long document dumps. "
        "Maximum ~400 words unless the user asks for a full brief. "
        "Cite only relevant facts; synthesize witness/evidence/hearing answers."
    )
    if mm == "matter_only":
        return (
            f"{base} Answer ONLY from this matter's uploaded documents. "
            "Do not use general legal knowledge unless the document states it."
        )
    if mm == "chronology":
        return f"{base} Produce a chronological timeline, oldest to newest, with dates."
    if mm == "hearing_prep":
        return (
            f"{base} Identify contradictions, weak points, and cross-examination angles "
            "from witness statements and orders in this matter."
        )
    if mm == "evidence":
        return f"{base} List evidence by type with importance; do not dump full exhibits."
    if mm == "research":
        return "Focus on external legal research while noting when matter documents are silent."
    if mm == "hybrid":
        return f"{base} Combine this matter's facts with applicable Indian law and procedure."
    return base


def _persist_chat_to_db(
    user_id: str,
    prompt: str,
    content: str,
    *,
    lang: str = "English",
    mode: str = "knowledge_base",
    thread_id: Optional[str] = None,
    history: Optional[List[dict]] = None,
    matter_id: Optional[str] = None,
) -> Dict[str, str]:
    """Save full Q&A to SQLite with retries; index for past-chat search."""
    import logging
    import time

    log = logging.getLogger(__name__)
    saved: Dict[str, str] = {"chat_id": "", "thread_id": (thread_id or "").strip()}
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            from backend.app.core.chat_persistence import save_chat_turn

            saved = save_chat_turn(
                user_id,
                prompt.strip(),
                content or "(no response generated)",
                language=lang,
                mode=mode,
                thread_id=thread_id,
                matter_id=matter_id,
            )
            try:
                from backend.app.core.user_memory import update_thread_summary
                from backend.app.core.chat_conversation_rag import index_chat_turn

                tid = saved.get("thread_id") or thread_id or ""
                update_thread_summary(user_id, tid, prompt.strip(), content or "", history or [])
                index_chat_turn(
                    user_id,
                    tid,
                    prompt.strip(),
                    content or "",
                    chat_id=saved.get("chat_id", ""),
                    matter_id=matter_id,
                )
            except Exception:
                pass
            kb_log("CHAT_SAVED", thread_id=saved.get("thread_id"), user_id=user_id)
            return saved
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(0.06 * (attempt + 1))
                continue
            kb_log("CHAT_SAVE_ERROR", error=str(exc))
    if last_exc:
        log.warning("Chat persist failed after retries: %s", last_exc)
    return saved


def _run_kb_turn(
    user_id: str,
    prompt: str,
    history: List[Dict],
    thread_id: str = "",
    matter_id: Optional[str] = None,
    attachment: Optional[Dict[str, Any]] = None,
    original_prompt: str = "",
    session_id: str = "",
    matter_mode: Optional[str] = None,
) -> Tuple[str, List[dict], List[str], Dict[str, str]]:
    try:
        from backend.app.core.kb_gemini_safety import enforce_kb_gemini_policy

        enforce_kb_gemini_policy(mode="knowledge_base")
    except RuntimeError:
        kb_log("KB_SAFETY", reason="gemini_synthesis_blocked")
        raise
    except Exception:
        pass
    kb_log("QUERY", query=prompt, user_id=user_id)
    # region agent log
    try:
        from backend.app.core.kb_runtime_debug import kb_runtime_log

        kb_runtime_log(
            "C",
            "chat_service.py:_run_kb_turn",
            "kb_turn_start",
            {
                "user_id": str(user_id)[:12],
                "matter_id": matter_id or "",
                "prompt": prompt[:120],
            },
        )
    except Exception:
        pass
    # endregion

    from backend.app.core.matter_policy import normalize_matter_ai_scope

    retrieval_scope = "global"
    retrieval_matter_id = None
    scoped_matter = normalize_matter_ai_scope(matter_id, matter_mode)
    if scoped_matter:
        retrieval_scope = "matter"
        retrieval_matter_id = scoped_matter

    # region agent log
    try:
        from backend.app.core.debug_matter_index_log import matter_index_log

        matter_index_log(
            "FIX",
            "chat_service.py:_run_kb_turn",
            "retrieval_route",
            {
                "retrieval_scope": retrieval_scope,
                "matter_ai_mid": "",
                "ui_matter_id": (matter_id or "")[:36],
                "matter_mode": (matter_mode or "")[:24],
            },
            run_id="post-fix",
        )
    except Exception:
        pass
    # endregion

    try:
        from backend.app.core.kb_index_gate import check_kb_ready_for_query

        ready, block_msg = check_kb_ready_for_query(
            user_id,
            matter_id=retrieval_matter_id,
            retrieval_scope=retrieval_scope,
        )
        if not ready and block_msg:
            kb_log("INDEX_GATE", blocked=True)
            return block_msg, [], [], {}
    except Exception:
        pass

    if attachment and (attachment.get("text") or "").strip():
        from app import query_from_ocr_attachment

        fname = attachment.get("filename", "uploaded_file")
        response = query_from_ocr_attachment(
            prompt.strip(),
            attachment["text"],
            fname,
            conversation_history=history,
        )
        follow_ups: List[str] = suggest_follow_ups(prompt, response, "knowledge_base")
        return (
            response,
            [{
                "filename": fname,
                "excerpt": (attachment["text"] or "")[:240] + "...",
                "relevance": "High",
                "score": "attachment",
            }],
            follow_ups,
            {"filename": fname, "section": ""},
        )

    if thread_id:
        try:
            from backend.app.core.thread_attachments import thread_attachment_chunks
            from answer_orchestrator import orchestrate_kb_answer, suggest_follow_ups as orch_suggest

            chunks = thread_attachment_chunks(user_id, thread_id)
            if chunks:
                profile = classify_intent(prompt, history)
                result = orchestrate_kb_answer(prompt, chunks, messages=history, user_id=user_id)
                follow_ups = orch_suggest(prompt, result.text, profile) or suggest_follow_ups(
                    prompt, result.text, "knowledge_base"
                )
                fname = chunks[0].get("metadata", {}).get("filename", "chat attachment")
                return (
                    result.text,
                    [{
                        "filename": fname,
                        "excerpt": (chunks[0].get("content") or "")[:240] + "...",
                        "relevance": "High",
                        "score": "thread_attachment",
                    }],
                    follow_ups,
                    {"filename": fname, "section": ""},
                )
        except Exception as exc:
            kb_log("THREAD_ATTACH_ERROR", error=str(exc))
    kb_question = (original_prompt or prompt).strip()
    try:
        from backend.app.core.kb_query_clean import strip_chat_routing_prefix

        kb_question = strip_chat_routing_prefix(kb_question) or kb_question
    except Exception:
        pass
    profile = classify_intent(kb_question, history)
    kb_log(
        "INTENT",
        primary=str(profile.primary),
        expanded_query=profile.expanded_query or prompt,
        sections=profile.signals.get("sections"),
        complexity=profile.complexity,
    )

    retrieval_k = min(profile.retrieval_k or 10, 12)

    try:
        from backend.app.services.kb_service import execute_kb_query

        response, similar_cases = execute_kb_query(
            user_id,
            kb_question,
            conversation_history=history,
            matter_id=retrieval_matter_id,
            thread_id=thread_id or None,
            session_id=session_id or None,
            k=retrieval_k,
            find_similar_cases=True,
            retrieval_scope=retrieval_scope,
        )
    except Exception as exc:
        kb_log("RAG_ERROR", error=str(exc))
        response = ""
        similar_cases = []

    kb_log(
        "RAG_RESPONSE",
        length=len(response or ""),
        preview=(response or "")[:500],
        similar_cases=len(similar_cases or []),
    )

    response, source_meta = _finalize_kb_answer(
        response or "",
        original_prompt or prompt,
        history,
        user_id,
        similar_cases,
        matter_id=retrieval_matter_id,
    )
    kb_log("FINAL_ANSWER", length=len(response), preview=response[:500], source=source_meta)

    follow_ups: List[str] = suggest_follow_ups(prompt, response, "knowledge_base")
    try:
        from answer_orchestrator import suggest_follow_ups as orch_suggest

        orch = orch_suggest(kb_question, response, profile)
        if orch:
            follow_ups = orch
    except Exception:
        pass

    # region agent log
    try:
        from backend.app.core.kb_runtime_debug import kb_runtime_log

        kb_runtime_log(
            "E",
            "chat_service.py:_run_kb_turn",
            "kb_turn_done",
            {
                "answer_len": len(response or ""),
                "preview": (response or "")[:160],
                "source_file": source_meta.get("filename", "")[:80],
                "looks_web": bool(
                    response
                    and any(
                        x in (response or "").lower()[:400]
                        for x in (
                            "open law",
                            "web intelligence",
                            "gemini",
                            "tavily",
                            "google search",
                        )
                    )
                ),
            },
        )
    except Exception:
        pass
    # endregion

    return response, similar_cases or [], follow_ups, source_meta


def _apply_plan_route_guard(mode: str, membership: str) -> str:
    """Block Hybrid for Free tier even when mode router auto-upgrades."""
    from backend.app.core.plan_enforcement import apply_plan_route_guard

    return apply_plan_route_guard(mode, membership)


def resolve_chat_route(
    user_mode: str,
    *,
    matter_mode: Optional[str] = None,
    membership: str = "Free",
) -> str:
    """
    Unified chat mode routing — maps UI/API aliases to execution routes.

    Routes: knowledge_base, open_law, web_search, hybrid, deep_case,
    matter_only, research, drafting, discovery, crm.
    """
    mm = (matter_mode or "").strip().lower()
    if mm == "research":
        return _apply_plan_route_guard("web_search", membership)
    if mm == "hybrid":
        return _apply_plan_route_guard("hybrid", membership)

    raw = (user_mode or "knowledge_base").strip().lower()
    alias = {
        "kb": "knowledge_base",
        "document": "knowledge_base",
        "documents": "knowledge_base",
        "matter_only": "knowledge_base",
        "openlaw": "open_law",
        "web": "web_search",
        "deep": "deep_case",
        "deepstudy": "deep_case",
        "deep_study": "deep_case",
        "jurisprudence": "hybrid",
        "research": "web_search",
    }
    route = alias.get(raw, raw)
    canonical = {
        "knowledge_base",
        "web_search",
        "open_law",
        "hybrid",
        "deep_case",
        "drafting",
        "discovery",
        "crm",
    }
    if route not in canonical:
        route = "knowledge_base"
    if route in ("hybrid", "deep_case", "web_search", "open_law"):
        route = _apply_plan_route_guard(route, membership)
    return route


def _resolve_chat_routing(
    user_id: str,
    prompt: str,
    user_mode: str,
    history: List[Dict],
    sid: str,
    *,
    matter_id: Optional[str] = None,
    membership: str = "Free",
    thread_id: str = "",
) -> Tuple[str, str, Any, Any, Dict[str, Any]]:
    """Shared mode routing for sync + stream chat (KB / Open Law / Hybrid)."""
    session_mem: Dict[str, Any] = {}
    legal_parse = None
    route = None
    effective_prompt = prompt.strip()
    mode = (user_mode or "knowledge_base").strip().lower()

    try:
        from backend.app.core.conversation_memory import (
            get_session_legal_memory,
            merge_query,
        )
        from backend.app.services.mode_router import route_query
        from backend.legal_engine.query_parser import parse_legal_query

        session_mem = get_session_legal_memory(sid)
        try:
            from backend.app.services.followup_detector import get_effective_session_memory

            effective_session_mem = get_effective_session_memory(prompt.strip(), session_mem)
        except ImportError:
            effective_session_mem = session_mem
        try:
            from backend.app.core.kb_query_clean import strip_chat_routing_prefix

            clean_prompt = strip_chat_routing_prefix(prompt.strip()) or prompt.strip()
        except Exception:
            clean_prompt = prompt.strip()
        legal_parse = parse_legal_query(
            clean_prompt, history, session_state=effective_session_mem
        )
        if mode in ("web_search", "open_law"):
            effective_prompt = clean_prompt
        else:
            effective_prompt = legal_parse.resolved_query or merge_query(
                clean_prompt, sid, history
            )
        try:
            from backend.app.core.conversation_memory import resolve_unified_follow_up

            effective_prompt = resolve_unified_follow_up(
                effective_prompt,
                session_id=sid,
                history=history,
                thread_id=thread_id,
                mode=mode,
            )
        except Exception:
            pass
        try:
            from rag import index_exists
            from app import resolve_rag_index_dir
            from backend.app.core.matter_policy import normalize_chat_scope

            scoped_mid = normalize_chat_scope(mode, matter_id)
            strict_matter = bool(scoped_mid)
            has_kb = index_exists(
                resolve_rag_index_dir(
                    user_id,
                    scoped_mid,
                    require_matter_scope=strict_matter,
                )
            )
        except Exception:
            scoped_mid = None
            strict_matter = False
            has_kb = True
        route = route_query(
            effective_prompt,
            mode,
            history,
            session_state=session_mem,
            has_kb_index=has_kb,
        )
        effective_prompt = route.effective_query or effective_prompt
        mode = _apply_plan_route_guard(route.mode, membership)
        # region agent log
        try:
            from backend.app.core.kb_runtime_debug import kb_runtime_log

            kb_runtime_log(
                "A",
                "chat_service.py:_resolve_chat_routing",
                "route_decision",
                {
                    "user_mode": user_mode,
                    "routed_mode": mode,
                    "route_reason": getattr(route, "reason", ""),
                    "has_kb_index": has_kb,
                    "matter_id": (scoped_mid or "")[:36],
                    "index_dir": str(
                        resolve_rag_index_dir(
                            user_id,
                            scoped_mid,
                            require_matter_scope=strict_matter,
                        )
                    )[:120],
                },
            )
        except Exception:
            pass
        # endregion
    except Exception:
        legal_parse = None
        effective_prompt = prompt.strip()
        mode = _apply_plan_route_guard(mode, membership)
        route = None

    return effective_prompt, mode, legal_parse, route, session_mem


def _open_law_history(history: List[Dict]) -> List[Dict]:
    try:
        from backend.app.core.web_intelligence import _filter_open_law_history

        return _filter_open_law_history(history)
    except Exception:
        return history


def _resolve_open_law_search_query(prompt: str, history: List[Dict]) -> str:
    search_q = prompt.strip()
    filtered_history = _open_law_history(history)
    try:
        from legal_web_query import (
            build_web_search_query,
            is_conversational_feedback,
        )

        if is_conversational_feedback(search_q, filtered_history):
            return search_q
        return build_web_search_query(search_q, filtered_history)
    except ImportError:
        pass
    return search_q


def _feedback_follow_ups(feedback_type: str) -> List[str]:
    if feedback_type == "negative":
        return [
            "Try again with more detail",
            "Explain what was missing",
            "Search Open Law instead",
        ]
    return [
        "Summarize key points",
        "Explain in simple language",
        "What should I do next?",
    ]


def _prior_qa_from_history(history: List[Dict]) -> Tuple[str, str]:
    """Last substantive user question + assistant answer before verbal feedback."""
    last_q = ""
    last_a = ""
    try:
        from legal_web_query import is_conversational_feedback
    except ImportError:
        is_conversational_feedback = None  # type: ignore

    for msg in reversed(history or []):
        role = msg.get("role")
        text = (msg.get("content") or "").strip()
        if not text:
            continue
        if role == "assistant" and not last_a:
            last_a = text
        elif role == "user" and not last_q:
            if is_conversational_feedback and is_conversational_feedback(text, history):
                continue
            last_q = text
        if last_q and last_a:
            break
    return last_q, last_a


def _record_verbal_feedback_learning(
    user_id: str,
    history: List[Dict],
    *,
    mode: str,
    feedback_type: str,
    verbal_message: str,
    membership: str = "Free",
    chat_id: str = "",
    thread_id: str = "",
) -> None:
    """Route verbal compliments/criticism into the full training + coach pipeline."""
    last_q, last_a = _prior_qa_from_history(history)
    if not last_a:
        return

    signal = "verbal_positive" if feedback_type == "positive" else "verbal_negative"

    def _bg() -> None:
        try:
            from backend.app.core.adaptive_learning import get_last_interaction_id
            from backend.app.core.learning_signals import process_learning_signal

            interaction_id = get_last_interaction_id(str(user_id))
            tags: List[str] = []
            if feedback_type == "negative":
                low = verbal_message.lower()
                if re.search(r"\bmissing|incomplete|left out\b", low):
                    tags.append("too_short")
                if re.search(r"\bnot relevant|irrelevant|off topic|unrelated\b", low):
                    tags.append("not_in_documents")
                if re.search(r"\bwrong|incorrect|error|mistake\b", low):
                    tags.append("wrong_section")

            result = process_learning_signal(
                str(user_id),
                signal,
                interaction_id=interaction_id,
                chat_id=chat_id,
                comment=verbal_message if feedback_type == "negative" else "",
                tags=tags or None,
                metadata={
                    "source": "verbal_feedback",
                    "verbal_message": verbal_message[:300],
                    "mode": mode,
                    "prior_query": last_q[:300],
                    "thread_id": thread_id,
                },
                membership=membership,
            )

            if feedback_type == "negative" and last_q:
                try:
                    from backend.app.core.learning_engine import learn_from_kb_failure

                    learn_from_kb_failure(str(user_id), last_q)
                except Exception:
                    pass

            if feedback_type == "positive" and last_q and len(last_a) >= 40:
                try:
                    from backend.app.core.learning_engine import (
                        learn_from_kb_success,
                        learn_from_web_success,
                    )

                    if mode in ("web_search", "open_law", "deep_case", "hybrid"):
                        learn_from_web_success(
                            str(user_id),
                            last_q,
                            last_a,
                            source="verbal_positive",
                            confidence=0.9,
                        )
                    else:
                        learn_from_kb_success(
                            str(user_id),
                            last_q,
                            last_a,
                            source="verbal_positive",
                            confidence=0.9,
                        )
                except Exception:
                    pass

            if not result.get("ok") and last_q:
                try:
                    from backend.app.core.neural_finetuning import add_training_pair

                    if feedback_type == "positive" and len(last_a) >= 40:
                        add_training_pair(
                            last_q,
                            last_a,
                            user_id=str(user_id),
                            source="verbal_positive",
                        )
                except Exception:
                    pass
        except Exception as exc:
            kb_log("VERBAL_FEEDBACK_ERROR", error=str(exc)[:120])

    try:
        import threading

        threading.Thread(target=_bg, daemon=True).start()
    except Exception:
        pass


def _try_conversational_feedback(
    user_id: str,
    prompt: str,
    history: List[Dict],
    *,
    mode: str = "open_law",
    membership: str = "Free",
    chat_id: str = "",
    thread_id: str = "",
) -> Optional[ChatTurnResult]:
    """Return a brief reply when the user gives verbal positive/negative feedback."""
    try:
        from legal_web_query import (
            FEEDBACK_NEGATIVE,
            FEEDBACK_POSITIVE,
            build_acknowledgment_response,
            build_negative_feedback_response,
            classify_conversational_feedback,
        )
    except ImportError:
        return None

    feedback_type = classify_conversational_feedback(prompt.strip(), history)
    if not feedback_type:
        return None

    if feedback_type == FEEDBACK_NEGATIVE:
        content = build_negative_feedback_response(prompt.strip(), history)
    else:
        content = build_acknowledgment_response(prompt.strip(), history)

    follow_ups = _feedback_follow_ups(feedback_type)
    _record_verbal_feedback_learning(
        user_id,
        history,
        mode=mode,
        feedback_type=feedback_type,
        verbal_message=prompt.strip(),
        membership=membership,
        chat_id=chat_id,
        thread_id=thread_id,
    )
    return ChatTurnResult(content=content, follow_ups=follow_ups)


def _try_conversational_acknowledgment(
    user_id: str,
    prompt: str,
    history: List[Dict],
    *,
    mode: str = "open_law",
    membership: str = "Free",
    chat_id: str = "",
    thread_id: str = "",
) -> Optional[ChatTurnResult]:
    """Backward-compatible alias for verbal feedback handling."""
    return _try_conversational_feedback(
        user_id,
        prompt,
        history,
        mode=mode,
        membership=membership,
        chat_id=chat_id,
        thread_id=thread_id,
    )


def _defer_stream_persist(
    user_id: str,
    prompt: str,
    body: str,
    *,
    lang: str,
    mode: str,
    thread_id: Optional[str],
    history: Optional[List[dict]],
    sid: str,
    interaction_id: str = "",
) -> Dict[str, str]:
    """Sync save before stream ends; defer only slow indexing."""
    _ = (sid, interaction_id)
    saved = _persist_chat_turn_fast(
        user_id,
        prompt.strip(),
        body,
        lang=lang,
        mode=mode,
        thread_id=thread_id,
    )
    _defer_chat_indexing(
        user_id,
        prompt.strip(),
        body,
        thread_id=saved.get("thread_id") or thread_id or "",
        history=history,
        chat_id=saved.get("chat_id", ""),
    )
    return saved


def _defer_web_learning(user_id: str, prompt: str, content: str, mode: str) -> None:
    """Open Law turns are NOT auto-stored in answer memory — only explicit feedback."""
    _ = (user_id, prompt, content, mode)


def _looks_like_kb_leak(text: str) -> bool:
    return looks_like_kb_leak(text)


def _run_open_law_turn(
    user_id: str,
    prompt: str,
    history: List[Dict],
    *,
    membership: str = "Free",
    thread_id: str = "",
    legal_parse: Any = None,
) -> ChatTurnResult:
    """
    Open Law — instant Gemini grounded web research only (no KB documents).
    """
    ack = _try_conversational_feedback(
        user_id, prompt, history, mode="open_law", membership=membership, thread_id=thread_id
    )
    if ack:
        return ack

    search_q = _resolve_open_law_search_query(prompt, history)
    return fetch_open_law_answer(
        user_id,
        search_q,
        prompt,
        history,
        membership=membership,
        thread_id=thread_id,
        mode="open_law",
    )


def run_chat_turn(
    user_id: str,
    prompt: str,
    mode: str,
    *,
    lang: str = "English",
    conversation_history: Optional[List[dict]] = None,
    attachment: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    matter_mode: Optional[str] = None,
    persist: bool = True,
    membership: str = "Free",
) -> Tuple[str, List[dict], List[dict], List[str], Dict[str, Any], str, Dict[str, str]]:
    from backend.app.core.ai_trust import sanitize_user_prompt
    from backend.app.core.request_context import set_user_context

    set_user_context(str(user_id))
    prompt = sanitize_user_prompt(prompt or "")
    sid = get_or_create_session(session_id)
    history = _resolve_history(conversation_history or [], sid)
    user_mode = resolve_chat_route(
        mode or "knowledge_base",
        matter_mode=matter_mode,
        membership=membership,
    )
    scope_key = f"matter:{(matter_id or '').strip()}" if (matter_id or "").strip() else "global"
    mm_inst = _matter_mode_instruction(matter_mode)
    routed_prompt = prompt.strip()
    if mm_inst and (matter_id or "").strip():
        routed_prompt = f"{mm_inst}\n\nUser question: {routed_prompt}"
    routed_prompt = _apply_learner_mode_prefix(user_id, routed_prompt)

    effective_prompt, mode, legal_parse, route, session_mem = _resolve_chat_routing(
        user_id,
        routed_prompt,
        user_mode,
        history,
        sid,
        matter_id=matter_id,
        membership=membership,
        thread_id=thread_id or "",
    )
    if matter_mode == "research":
        mode = "web_search"
    elif matter_mode == "hybrid" and mode == "knowledge_base":
        mode = "hybrid"

    correction = _detect_implicit_correction(history, prompt.strip())
    if correction:
        try:
            from backend.app.core.adaptive_learning import record_implicit_correction

            record_implicit_correction(user_id, mode, correction[0], correction[1])
        except Exception:
            pass

    try:
        from backend.app.core.user_memory import extract_facts_from_message

        extract_facts_from_message(user_id, prompt.strip())
    except Exception:
        pass

    _log_research(user_id, prompt.strip(), mode, matter_id)

    ack = _try_conversational_feedback(
        user_id,
        prompt.strip(),
        history,
        mode=mode,
        membership=membership,
        thread_id=thread_id or "",
    )
    if ack:
        content, similar_cases, web_sources, follow_ups = ack.as_tuple()
        source_meta = {"filename": "", "section": ""}
        content = _translate_if_needed(content or "", lang)
        append_turn(sid, "user", prompt.strip())
        append_turn(sid, "assistant", content or "")
        saved: Dict[str, str] = {"chat_id": "", "thread_id": thread_id or "", "interaction_id": ""}
        if persist:
            saved = _persist_chat_to_db(
                user_id,
                prompt.strip(),
                content or "",
                lang=lang,
                mode=mode,
                thread_id=thread_id,
                history=history,
                matter_id=matter_id,
            )
        interaction_id = _record_mode_interaction(
            user_id,
            mode,
            prompt.strip(),
            content or "",
            chat_id=saved.get("chat_id") or "",
            thread_id=saved.get("thread_id") or thread_id or "",
            found=True,
            scope_key=scope_key,
        )
        saved["interaction_id"] = interaction_id
        return (
            content,
            similar_cases or [],
            web_sources,
            follow_ups,
            get_session_state(sid),
            sid,
            saved,
        )

    source_meta: Dict[str, str] = {"filename": "", "section": ""}
    interaction_id = ""
    if mode == "knowledge_base":
        content, similar_cases, follow_ups, source_meta = _run_kb_turn(
            user_id,
            effective_prompt,
            history,
            thread_id=thread_id or "",
            matter_id=matter_id,
            attachment=attachment,
            original_prompt=prompt.strip(),
            session_id=sid,
            matter_mode=matter_mode,
        )
        web_sources: List[dict] = []
    elif mode in ("hybrid", "deep_case"):
        try:
            from backend.app.services.hybrid_orchestrator import run_jurisprudence_turn

            content, similar_cases, web_sources = run_jurisprudence_turn(
                user_id,
                effective_prompt,
                history,
                matter_id=matter_id,
                parse=legal_parse,
                membership=membership,
            )
            follow_ups = [
                "Expand similar case cluster analysis",
                "Latest hearing / gazette updates",
                "Explain in simple language",
                "Draft client memo from this report",
            ]
        except Exception:
            try:
                from chat_service import run_chat_turn as _legacy_turn
            except ImportError:
                from legacy_saas.chat_service import run_chat_turn as _legacy_turn
            content, similar_cases, web_sources = _legacy_turn(
                user_id, effective_prompt, mode, lang=lang,
                conversation_history=history, attachment=attachment,
            )
            follow_ups = suggest_follow_ups(prompt, content, mode)
    elif mode in ("open_law", "web_search"):
        turn = _run_open_law_turn(
            user_id,
            effective_prompt,
            history,
            membership=membership,
            thread_id=thread_id or "",
            legal_parse=legal_parse,
        )
        content, similar_cases, web_sources, follow_ups = turn.as_tuple()
    else:
        try:
            from backend.app.core.adaptive_learning import enhance_intent_profile
            from intent_engine import classify_intent

            prof = classify_intent(prompt, history)
            enhance_intent_profile(user_id, mode, prof, prompt)
        except Exception:
            pass
        try:
            from chat_service import run_chat_turn as _legacy_turn
        except ImportError:
            from legacy_saas.chat_service import run_chat_turn as _legacy_turn

        content, similar_cases, web_sources = _legacy_turn(
            user_id,
            prompt.strip(),
            mode,
            lang=lang,
            conversation_history=history,
            attachment=attachment,
        )
        try:
            from backend.app.services.response_formatter import format_legal_response

            content = format_legal_response(
                content,
                intent=legal_parse.intent if legal_parse else "general",
                parse=legal_parse.to_dict() if legal_parse else {},
            )
        except Exception:
            pass
        source_meta = {"filename": "", "section": ""}
        follow_ups = suggest_follow_ups(prompt, content, mode)
        web_sources = _enrich_web_sources(web_sources if isinstance(web_sources, list) else [])

    if mode in ("open_law", "web_search", "hybrid", "deep_case"):
        content = _maybe_oral_argument(content or "", prompt.strip(), user_id, membership)
    content = _translate_if_needed(content or "", lang)

    append_turn(sid, "user", prompt.strip())
    append_turn(sid, "assistant", content or "")

    try:
        from backend.app.core.conversation_memory import update_session_legal_memory

        parse_dict = legal_parse.to_dict() if legal_parse else {}
        update_session_legal_memory(
            sid,
            query=prompt.strip(),
            parse=parse_dict,
            mode=mode,
            answer=content or "",
            source_meta=source_meta if mode == "knowledge_base" else None,
        )
        if matter_id:
            sess = get_session(sid) or {}
            mem = dict(sess.get("legal_memory") or {})
            mem["last_matter_id"] = matter_id
            sess["legal_memory"] = mem
            set_session(sid, sess)
        # Preserve section from original query when follow-up has no section in parse
        if prompt.strip() and not parse_dict.get("section"):
            from backend.legal_engine.query_parser import parse_legal_query

            orig_parse = parse_legal_query(prompt.strip(), history, session_state=session_mem)
            if orig_parse.section:
                update_session_legal_memory(
                    sid, parse={"section": orig_parse.section, "law": orig_parse.law}
                )
    except Exception:
        pass

    saved: Dict[str, str] = {"chat_id": "", "thread_id": thread_id or "", "interaction_id": interaction_id}
    if persist:
        saved = _persist_chat_to_db(
            user_id,
            prompt.strip(),
            content or "",
            lang=lang,
            mode=mode,
            thread_id=thread_id,
            history=history,
            matter_id=matter_id,
        )

    if not interaction_id:
        try:
            from backend.app.core.adaptive_learning import get_last_interaction_id

            if mode == "knowledge_base":
                interaction_id = get_last_interaction_id(user_id)
        except Exception:
            pass
    if not interaction_id or mode in ("web_search", "deep_case", "open_law", "hybrid"):
        interaction_id = _record_mode_interaction(
            user_id,
            mode,
            prompt.strip(),
            content or "",
            chat_id=saved.get("chat_id", ""),
            thread_id=saved.get("thread_id", ""),
            found=not contains_not_found_phrase(content or ""),
            scope_key=scope_key,
        )
    saved["interaction_id"] = interaction_id

    try:
        from backend.app.core.learning_signals import resolve_regenerate_chain

        resolve_regenerate_chain(
            user_id,
            replacement_interaction_id=interaction_id,
            replacement_answer=content or "",
        )
    except Exception:
        pass

    if mode in ("web_search", "deep_case", "open_law", "hybrid") and (content or "").strip():
        _defer_web_learning(user_id, prompt, content or "", mode)

    return (
        content,
        similar_cases or [],
        web_sources if mode != "knowledge_base" else [],
        follow_ups,
        get_session_state(sid),
        sid,
        saved,
    )


def _stream_status_message(mode: str) -> str:
    if mode in ("hybrid", "deep_case"):
        return (
            "⚖️ *Hybrid — Knowledge Base + Web Intel + deep research report…*\n\n"
        )
    return "🔍 *Web Intel — searching live Indian legal sources…*\n\n"


def _stream_kb_status_message(phase: str = "search") -> str:
    if phase == "compose":
        return "📋 *Composing answer from your uploaded documents…*\n\n"
    if phase == "embeddings":
        return "⏳ *Loading embedding model (one-time, ~30–90s)…*\n\n"
    if phase == "heartbeat":
        return "📚 *Still searching your knowledge base…*\n\n"
    return "📚 *Searching your knowledge base…*\n\n"


def _stream_kb_turn_with_heartbeat(
    user_id: str,
    effective_prompt: str,
    history: List[Dict],
    *,
    thread_id: str = "",
    matter_id: Optional[str] = None,
    attachment: Optional[Dict[str, Any]] = None,
    original_prompt: str = "",
    session_id: str = "",
    matter_mode: Optional[str] = None,
) -> Generator[str, None, Tuple[str, List[dict], List[str], Dict[str, str]]]:
    """Run KB turn in a worker thread; yield SSE heartbeats so the UI never looks frozen."""
    import queue
    import threading

    out: queue.Queue = queue.Queue(maxsize=1)

    def _worker() -> None:
        try:
            out.put(
                (
                    "ok",
                    _run_kb_turn(
                        user_id,
                        effective_prompt,
                        history,
                        thread_id=thread_id,
                        matter_id=matter_id,
                        attachment=attachment,
                        original_prompt=original_prompt,
                        session_id=session_id,
                        matter_mode=matter_mode,
                    ),
                )
            )
        except Exception as exc:
            out.put(("err", exc))

    threading.Thread(target=_worker, daemon=True, name="kb-turn").start()

    try:
        from backend.app.core.embedding_manager import get_manager

        mgr = get_manager()
        st = mgr.get_status()
        if st.get("state") == "LOADING_MODEL":
            yield _sse_status(_stream_kb_status_message("embeddings"))
    except Exception:
        pass

    tick = 0
    while True:
        try:
            kind, payload = out.get(timeout=8.0)
            break
        except queue.Empty:
            tick += 1
            if tick <= 90:
                yield _sse_status(_stream_kb_status_message("heartbeat"))
            continue

    if kind == "err":
        raise payload  # type: ignore[misc]
    return payload  # type: ignore[return-value]


def _stream_compose_message(mode: str) -> str:
    if mode in ("hybrid", "deep_case"):
        return "📋 *Composing Jurisprudence research report…*\n\n"
    return "📋 *Composing answer from live legal sources…*\n\n"


def _stream_open_law_turn(
    user_id: str,
    prompt: str,
    mode: str,
    *,
    lang: str = "English",
    history: Optional[List[dict]] = None,
    attachment: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    membership: str = "Free",
) -> Generator[str, None, None]:
    """Stream Open Law or Hybrid turn — live Gemini tokens, persist after."""
    from app import sanitize_assistant_response

    sid = get_or_create_session(session_id)
    hist = history or []

    ack = _try_conversational_feedback(
        user_id,
        prompt,
        hist,
        mode=mode,
        membership=membership,
        thread_id=thread_id or "",
    )
    if ack:
        content, similar_cases, web_sources, follow_ups = ack.as_tuple()
        for part in _stream_text_chunks(content, parts=8):
            yield _sse_token(part)
        try:
            from app import sanitize_assistant_response

            content = sanitize_assistant_response(content or "", fallback=content or "")
        except Exception:
            pass
        body = (content or "").strip()
        interaction_id = ""
        try:
            interaction_id = _record_mode_interaction(
                user_id,
                mode,
                prompt.strip(),
                body,
                chat_id="",
                thread_id=thread_id or "",
                found=True,
                scope_key=f"matter:{(matter_id or '').strip()}" if (matter_id or "").strip() else "global",
            )
        except Exception:
            pass
        append_turn(sid, "user", prompt.strip())
        append_turn(sid, "assistant", body)
        saved = _persist_chat_turn_fast(
            user_id,
            prompt.strip(),
            body,
            lang=lang,
            mode=mode,
            thread_id=thread_id,
        )
        state = get_session_state(sid)
        saved_thread = saved.get("thread_id") or thread_id or ""
        yield _sse_meta(
            follow_ups,
            similar_cases,
            web_sources,
            sid,
            state,
            body,
            thread_id=saved_thread,
            interaction_id=interaction_id,
            chat_id=saved.get("chat_id", ""),
        )
        yield "data: [DONE]\n\n"
        _defer_chat_indexing(
            user_id,
            prompt.strip(),
            body,
            thread_id=saved_thread,
            history=hist,
            chat_id=saved.get("chat_id", ""),
        )
        return

    if mode not in ("hybrid", "deep_case", "open_law", "web_search"):
        yield _sse_status(_stream_status_message(mode))

    content = ""
    web_sources: List[dict] = []
    follow_ups: List[str] = []
    similar_cases: List[dict] = []
    search_q = _resolve_open_law_search_query(prompt, hist)

    try:
        from backend.app.core.learning_engine import lookup_answer_memory

        mem = lookup_answer_memory(user_id, search_q, strict=True)
        if mem and (mem.get("answer") or "").strip():
            content = mem["answer"].strip()
            follow_ups = suggest_follow_ups(prompt, content, mode)
            yield _sse_status(_stream_compose_message(mode))
            for part in _stream_text_chunks(content, parts=10):
                yield _sse_token(part)
    except Exception as exc:
        kb_log("OPEN_LAW_MEMORY_ERROR", error=str(exc)[:120])

    if not content:
        if mode in ("hybrid", "deep_case"):
            try:
                from backend.app.services.hybrid_orchestrator import stream_hybrid_research

                for event in stream_hybrid_research(
                    user_id,
                    prompt,
                    hist,
                    matter_id=matter_id,
                    membership=membership,
                ):
                    if event.get("type") == "status":
                        msg = str(event.get("message") or "").strip()
                        if msg:
                            yield _sse_status(msg)
                    elif event.get("type") == "result":
                        content = str(event.get("content") or "")
                        similar_cases = list(event.get("similar_cases") or [])
                        web_sources = list(event.get("web_sources") or [])
                follow_ups = [
                    "Expand similar case cluster analysis",
                    "Latest hearing / gazette updates",
                    "Explain in simple language",
                    "Draft client memo from this report",
                ]
                yield _sse_status("Preparing your report for display…")
                for part in _stream_text_chunks(content or "", parts=12):
                    yield _sse_token(part)
            except Exception as exc:
                kb_log("WEB_STREAM_ERROR", error=str(exc))
                content = (
                    "### Web Intelligence Error\n\n"
                    f"Could not complete research: {exc}\n\n"
                    "Try again, or restart the backend: `.\\run_backend.ps1`"
                )
        else:
            streamed = False
            streamed_parts: List[str] = []
            stream_gemini_failed = False
            try:
                from backend.app.core.gemini_errors import gemini_quota_cooldown_active
                from backend.app.core.web_intelligence import (
                    gemini_configured,
                    stream_grounded_legal_research,
                )

                if gemini_configured() and not gemini_quota_cooldown_active():
                    gemini_history = resolve_gemini_history(search_q, hist)

                    for event in stream_grounded_legal_research(
                        search_q,
                        gemini_history,
                        user_id=user_id,
                        thread_id=thread_id or None,
                        membership=membership,
                    ):
                        if event.get("type") == "status":
                            msg = str(event.get("message") or "").strip()
                            if msg:
                                yield _sse_status(msg)
                        elif event.get("type") == "token" and event.get("text"):
                            if not streamed:
                                yield _sse_status(_stream_compose_message(mode))
                                streamed = True
                            piece = str(event["text"])
                            streamed_parts.append(piece)
                            yield _sse_token(piece)
                        elif event.get("type") == "done":
                            content = str(event.get("answer") or "") or "".join(streamed_parts)
                            web_sources = event.get("sources") or []
                            follow_ups = event.get("follow_ups") or []
                            if content and not streamed:
                                yield _sse_status(_stream_compose_message(mode))
                                for part in _stream_text_chunks(content, parts=12):
                                    yield _sse_token(part)
                                streamed = True
                elif gemini_configured() and gemini_quota_cooldown_active():
                    stream_gemini_failed = True
                    kb_log("OPEN_LAW_SKIP_GEMINI", reason="quota_cooldown")
            except RuntimeError as exc:
                stream_gemini_failed = True
                content = f"### Open Law\n\n{exc}"
            except OSError as exc:
                stream_gemini_failed = True
                kb_log("OPEN_LAW_STREAM_OS_ERROR", error=str(exc))
                content = ""
            except Exception as exc:
                stream_gemini_failed = True
                kb_log("OPEN_LAW_STREAM_ERROR", error=str(exc))

            content = merge_stream_buffer(content, streamed_parts)

            if needs_open_law_fallback(content, streamed_parts):
                try:
                    fb = fetch_open_law_answer(
                        user_id,
                        search_q,
                        prompt,
                        hist,
                        membership=membership,
                        thread_id=thread_id or "",
                        mode=mode,
                        skip_gemini=stream_gemini_failed,
                    )
                    if fb.has_content():
                        content = fb.content
                        web_sources = fb.web_sources or web_sources
                        follow_ups = fb.follow_ups or follow_ups
                        if not streamed:
                            yield _sse_status(_stream_compose_message(mode))
                        for part in _stream_text_chunks(content, parts=12):
                            yield _sse_token(part)
                except Exception as exc:
                    kb_log("WEB_STREAM_ERROR", error=str(exc))
                    if not content:
                        content = (
                            "### Web Intelligence Error\n\n"
                            "Open Law search failed. Please retry in a moment.\n\n"
                            f"Detail: {str(exc)[:120]}"
                        )

    try:
        from app import sanitize_assistant_response

        content = sanitize_assistant_response(content or "", fallback=content or "")
    except Exception:
        pass
    if not follow_ups:
        follow_ups = suggest_follow_ups(prompt, content, mode)
    web_sources = _enrich_web_sources(web_sources if isinstance(web_sources, list) else [])

    body = (content or "").strip()
    if not body:
        body = (
            "### Web Intelligence\n\n"
            "No response was generated. Check your web search API key in `.env` and restart the backend."
        )

    saved: Dict[str, str] = {"chat_id": "", "thread_id": thread_id or "", "interaction_id": ""}
    interaction_id = ""
    try:
        interaction_id = _record_mode_interaction(
            user_id,
            mode,
            prompt.strip(),
            body,
            chat_id="",
            thread_id=thread_id or "",
            found=not contains_not_found_phrase(body),
            scope_key=f"matter:{(matter_id or '').strip()}" if (matter_id or "").strip() else "global",
        )
    except Exception as exc:
        kb_log("OPEN_LAW_INTERACTION_ERROR", error=str(exc)[:120])

    append_turn(sid, "user", prompt.strip())
    append_turn(sid, "assistant", body)

    saved = _persist_chat_turn_fast(
        user_id,
        prompt.strip(),
        body,
        lang=lang,
        mode=mode,
        thread_id=thread_id,
    )
    state = get_session_state(sid)
    saved_thread = saved.get("thread_id") or thread_id or ""
    yield _sse_meta(
        follow_ups,
        similar_cases,
        web_sources,
        sid,
        state,
        body,
        thread_id=saved_thread,
        interaction_id=interaction_id,
        chat_id=saved.get("chat_id", ""),
    )
    yield "data: [DONE]\n\n"
    _defer_chat_indexing(
        user_id,
        prompt.strip(),
        body,
        thread_id=saved_thread,
        history=hist,
        chat_id=saved.get("chat_id", ""),
    )


def stream_chat_response(
    user_id: str,
    prompt: str,
    mode: str,
    *,
    lang: str = "English",
    conversation_history: Optional[List[dict]] = None,
    attachment: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    thread_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    matter_mode: Optional[str] = None,
    membership: str = "Free",
) -> Generator[str, None, None]:
    from backend.app.core.request_context import set_user_context

    set_user_context(str(user_id))
    sid = get_or_create_session(session_id)
    history = _resolve_history(conversation_history or [], sid)
    user_mode = (mode or "knowledge_base").strip().lower()

    mm_inst = _matter_mode_instruction(matter_mode)
    routed_prompt = prompt.strip()
    if mm_inst and (matter_id or "").strip():
        routed_prompt = f"{mm_inst}\n\nUser question: {routed_prompt}"
    routed_prompt = _apply_learner_mode_prefix(user_id, routed_prompt)

    effective_prompt, routed_mode, legal_parse, route, _session_mem = _resolve_chat_routing(
        user_id,
        routed_prompt,
        user_mode,
        history,
        sid,
        matter_id=matter_id,
        membership=membership,
        thread_id=thread_id or "",
    )
    mode = routed_mode
    if matter_mode == "research":
        mode = "web_search"
    elif matter_mode == "hybrid" and mode == "knowledge_base":
        mode = "hybrid"

    ack = _try_conversational_feedback(
        user_id,
        prompt.strip(),
        history,
        mode=mode,
        membership=membership,
        thread_id=thread_id or "",
    )
    if ack:
        content, similar_cases, web_sources, follow_ups = ack.as_tuple()
        for part in _stream_text_chunks(content or "", parts=8):
            if not _is_garbage_text(part):
                yield _sse_token(part)
        append_turn(sid, "user", prompt.strip())
        append_turn(sid, "assistant", content or "")
        interaction_id = _record_mode_interaction(
            user_id,
            mode,
            prompt.strip(),
            content or "",
            chat_id="",
            thread_id=thread_id or "",
            found=True,
            scope_key=f"matter:{(matter_id or '').strip()}" if (matter_id or "").strip() else "global",
        )
        saved = _persist_chat_turn_fast(
            user_id,
            prompt.strip(),
            content or "",
            lang=lang,
            mode=mode,
            thread_id=thread_id,
        )
        saved_thread = saved.get("thread_id") or thread_id or ""
        yield _sse_meta(
            follow_ups,
            similar_cases,
            web_sources,
            sid,
            get_session_state(sid),
            content or "",
            thread_id=saved_thread,
            interaction_id=interaction_id,
            chat_id=saved.get("chat_id", ""),
        )
        yield "data: [DONE]\n\n"
        _defer_chat_indexing(
            user_id,
            prompt.strip(),
            content or "",
            thread_id=saved_thread,
            history=history,
            chat_id=saved.get("chat_id", ""),
        )
        return

    if mode in ("open_law", "web_search", "hybrid", "deep_case"):
        yield from _stream_open_law_turn(
            user_id,
            effective_prompt,
            mode,
            lang=lang,
            history=history,
            attachment=attachment,
            session_id=sid,
            thread_id=thread_id,
            matter_id=matter_id,
            membership=membership,
        )
        return

    correction = _detect_implicit_correction(history, prompt.strip())
    if correction:
        try:
            from backend.app.core.adaptive_learning import record_implicit_correction

            record_implicit_correction(user_id, "knowledge_base", correction[0], correction[1])
        except Exception:
            pass

    append_turn(sid, "user", prompt.strip())

    source_meta: Dict[str, str] = {"filename": "", "section": ""}
    content = KB_NOT_FOUND_MESSAGE
    similar_cases: List[dict] = []
    follow_ups: List[str] = []
    try:
        yield _sse_status(_stream_kb_status_message("search"))
        yield _sse_status(_stream_kb_status_message("compose"))
        kb_gen = _stream_kb_turn_with_heartbeat(
            user_id,
            effective_prompt,
            history,
            thread_id=thread_id or "",
            matter_id=matter_id,
            attachment=attachment,
            original_prompt=prompt.strip(),
            session_id=sid,
            matter_mode=matter_mode,
        )
        while True:
            try:
                yield next(kb_gen)
            except StopIteration as stop:
                content, similar_cases, follow_ups, source_meta = stop.value
                break
    except Exception as exc:
        kb_log("ERROR", error=str(exc))
        content = KB_NOT_FOUND_MESSAGE
        similar_cases = []
        follow_ups = []

    for part in _stream_text_chunks(content or ""):
        if _is_garbage_text(part):
            continue
        yield _sse_token(part)

    append_turn(sid, "assistant", content or "")
    saved = _persist_chat_turn_fast(
        user_id,
        prompt.strip(),
        content or "",
        lang=lang,
        mode=mode,
        thread_id=thread_id,
        matter_id=matter_id,
    )
    saved_thread = saved.get("thread_id") or thread_id or ""
    saved_chat = saved.get("chat_id", "")
    interaction_id = ""

    if mode in ("web_search", "deep_case", "open_law", "hybrid"):
        interaction_id = _record_mode_interaction(
            user_id,
            mode,
            prompt.strip(),
            content or "",
            chat_id=saved_chat,
            thread_id=saved_thread,
            found=not contains_not_found_phrase(content or ""),
            scope_key=f"matter:{(matter_id or '').strip()}" if (matter_id or "").strip() else "global",
        )
    else:
        interaction_id = _record_mode_interaction(
            user_id,
            mode,
            prompt.strip(),
            content or "",
            chat_id=saved_chat,
            thread_id=saved_thread,
            found=not contains_not_found_phrase(content or ""),
            scope_key=f"matter:{(matter_id or '').strip()}" if (matter_id or "").strip() else "global",
        )

    yield _sse_meta(
        follow_ups,
        similar_cases,
        [],
        sid,
        get_session_state(sid),
        content or "",
        source_meta=source_meta,
        thread_id=saved_thread,
        interaction_id=interaction_id,
        chat_id=saved_chat,
    )
    kb_log("STREAM_DONE", streamed_length=len(content or ""), thread_id=saved_thread)
    yield "data: [DONE]\n\n"
    _defer_chat_indexing(
        user_id,
        prompt.strip(),
        content or "",
        thread_id=saved_thread,
        history=history,
        chat_id=saved_chat,
        matter_id=matter_id,
    )


def _sse_meta(
    follow_ups,
    similar_cases,
    web_sources,
    session_id,
    state,
    answer: str = "",
    source_meta: Optional[Dict[str, str]] = None,
    thread_id: str = "",
    interaction_id: str = "",
    chat_id: str = "",
) -> str:
    payload = {
        "type": "meta",
        "follow_ups": follow_ups,
        "similar_cases": similar_cases,
        "web_sources": web_sources,
        "session_id": session_id,
        "thread_id": thread_id,
        "chat_id": chat_id,
        "interaction_id": interaction_id,
        "conversation_state": state,
        "answer": answer,
        "content": answer,
        "source_meta": source_meta or {},
        "adaptive_learning": True,
    }
    try:
        from backend.app.core.kb_retrieval_debug import get_last_retrieval_debug

        rd = get_last_retrieval_debug()
        if rd:
            payload["retrieval_debug"] = rd
    except Exception:
        pass
    return f"data: {json.dumps(payload)}\n\n"


def _sse_token(text: str) -> str:
    if _is_garbage_text(text):
        return ""
    return f"data: {json.dumps({'type': 'token', 'content': text})}\n\n"


def _sse_status(text: str) -> str:
    """Non-answer progress line — UI shows as loading, not final content."""
    return f"data: {json.dumps({'type': 'status', 'content': text})}\n\n"
