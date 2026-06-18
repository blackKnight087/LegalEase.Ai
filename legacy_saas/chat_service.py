"""
Shared chat intelligence — used by Streamlit and FastAPI (no Streamlit session required).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

KB_NOT_FOUND_MESSAGE = "Information not found in document."


def run_chat_turn(
    user_id: str,
    prompt: str,
    mode: str,
    *,
    lang: str = "English",
    conversation_history: Optional[List[dict]] = None,
    attachment: Optional[Dict[str, Any]] = None,
) -> Tuple[str, List[dict], List[dict]]:
    """
    Execute KB / Web / Hybrid pipeline.
    Returns (response_text, similar_cases, web_sources).
    """
    from deep_translator import GoogleTranslator

    from app import (
        KB_NOT_FOUND_MESSAGE as APP_KB_MSG,
        basic_query,
        deep_case_query,
        query_from_ocr_attachment,
        rag_query,
        sanitize_assistant_response,
        web_search_query,
        _compose_web_answer_from_snippets,
    )

    _ = APP_KB_MSG  # same string; keep import for side-effect init
    similar_cases: List[dict] = []
    web_sources: List[dict] = []
    history = conversation_history or []
    current_prompt = (prompt or "").strip()
    enriched_prompt = current_prompt

    if attachment and attachment.get("text"):
        ocr_context = attachment["text"]
        ocr_name = attachment.get("filename", "uploaded_image")
        if mode == "knowledge_base":
            response = query_from_ocr_attachment(
                current_prompt, ocr_context, ocr_name, conversation_history=history
            )
            similar_cases = [{
                "filename": ocr_name,
                "excerpt": ocr_context[:240] + ("..." if len(ocr_context) > 240 else ""),
                "relevance": "High",
                "score": "ocr",
                "chunk_index": 0,
            }]
        elif mode == "web_search":
            combined = f"{current_prompt}\n\n[OCR from {ocr_name}]:\n{ocr_context[:6000]}"
            response, web_sources = web_search_query(combined, conversation_history=history)
        elif mode == "deep_case":
            combined = f"{current_prompt}\n\n[OCR from {ocr_name}]:\n{ocr_context[:6000]}"
            response, kb_hits, web_sources = deep_case_query(user_id, combined)
            similar_cases = [{
                "filename": ocr_name,
                "excerpt": ocr_context[:200] + "...",
                "relevance": "High",
            }]
        else:
            response = query_from_ocr_attachment(
                current_prompt, ocr_context, ocr_name, conversation_history=history
            )
    elif mode == "knowledge_base":
        response, similar_cases = rag_query(
            user_id,
            current_prompt,
            k=14,
            find_similar_cases=True,
            conversation_history=history,
        )
        if str(response).startswith("NOT_FOUND_IN_KB"):
            from kb_response_state import KB_NOT_FOUND_MESSAGE as _KB_NF

            response = _KB_NF
        elif str(response).startswith("### Knowledge Base Empty"):
            similar_cases = []
    elif mode == "web_search":
        from legal_web_engine import (
            expand_web_answer_detail,
            plain_language_explain,
            wants_detailed_explain,
            wants_plain_language_explain,
        )
        from legal_web_query import resolve_web_conversation_query

        last_asst = ""
        for m in reversed(history):
            if m.get("role") == "assistant" and (m.get("content") or "").strip():
                last_asst = m.get("content", "")
                break
        resolved = resolve_web_conversation_query(current_prompt, history)
        if wants_detailed_explain(current_prompt) and last_asst:
            response = expand_web_answer_detail(last_asst, resolved)
            web_sources = []
        elif wants_plain_language_explain(current_prompt) and last_asst:
            response = plain_language_explain(last_asst, resolved)
            web_sources = []
        else:
            response, web_sources = web_search_query(
                current_prompt,
                conversation_history=history,
                user_id=user_id,
            )
    elif mode == "deep_case":
        response, kb_hits, web_sources = deep_case_query(user_id, enriched_prompt)
        response = sanitize_assistant_response(
            response,
            fallback=_compose_web_answer_from_snippets(web_sources or [], enriched_prompt),
        )
        similar_cases = [
            {
                "filename": r.get("metadata", {}).get("filename", "doc"),
                "excerpt": (r.get("content", "") or "")[:200] + "...",
                "relevance": "High" if r.get("score", 1.0) < 0.3 else "Medium",
            }
            for r in kb_hits[:5]
        ]
    else:
        response = basic_query(current_prompt)

    response = sanitize_assistant_response(response)

    if lang != "English":
        try:
            lang_codes = {
                "Hindi": "hi", "Tamil": "ta", "Marathi": "mr",
                "Bengali": "bn", "Gujarati": "gu",
            }
            response = GoogleTranslator(
                source="auto", target=lang_codes.get(lang, "en")
            ).translate(response)
        except Exception:
            pass

    return response, similar_cases, web_sources
