"""
Semantic follow-up intent classification for in-chat learning.

Intents: clarify | deepen | compare | next_element | new_topic | example | simplify
"""
from __future__ import annotations

import re
from typing import Any, Dict, Tuple

INTENT_CLARIFY = "clarify"
INTENT_DEEPEN = "deepen"
INTENT_COMPARE = "compare"
INTENT_NEXT_ELEMENT = "next_element"
INTENT_NEW_TOPIC = "new_topic"
INTENT_EXAMPLE = "example"
INTENT_SIMPLIFY = "simplify"
INTENT_PUNISHMENT = "punishment"
INTENT_CONTINUE = "continue"
INTENT_ACKNOWLEDGMENT = "acknowledgment"
INTENT_NEGATIVE_FEEDBACK = "negative_feedback"


def classify_follow_up_intent(
    question: str,
    session_memory: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Classify follow-up intent and confidence using rules + session state.
    Ollama-local path; no Gemini in chat.
    """
    q = (question or "").strip()
    ql = q.lower()
    words = len(q.split())
    has_context = bool(
        session_memory.get("last_section")
        or session_memory.get("last_case")
        or session_memory.get("last_topic")
        or session_memory.get("last_user_query")
    )

    if not has_context:
        return {"intent": INTENT_NEW_TOPIC, "confidence": 0.9, "is_follow_up": False}

    try:
        from legal_web_query import classify_conversational_feedback

        fb = classify_conversational_feedback(q)
        if fb == "positive":
            return {
                "intent": INTENT_ACKNOWLEDGMENT,
                "confidence": 0.92,
                "is_follow_up": True,
            }
        if fb == "negative":
            return {
                "intent": INTENT_NEGATIVE_FEEDBACK,
                "confidence": 0.9,
                "is_follow_up": True,
            }
    except ImportError:
        pass

    # Explicit new topic signals
    if re.search(r"\b(now tell me about|switch to|different topic|new question)\b", ql):
        return {"intent": INTENT_NEW_TOPIC, "confidence": 0.85, "is_follow_up": False}

    if re.search(r"\b(compare|comparison|difference|versus|vs\.?|between)\b", ql):
        return {"intent": INTENT_COMPARE, "confidence": 0.88, "is_follow_up": True}

    if re.search(r"\b(example|illustrate|scenario|hypothetical)\b", ql):
        return {"intent": INTENT_EXAMPLE, "confidence": 0.85, "is_follow_up": True}

    if re.search(r"\b(simple|plain|eli5|layman|beginner|easier)\b", ql):
        return {"intent": INTENT_SIMPLIFY, "confidence": 0.85, "is_follow_up": True}

    if re.search(
        r"\b(punishment|penalty|sentence|fine|imprisonment|bail|remedy|relief)\b",
        ql,
    ):
        return {"intent": INTENT_PUNISHMENT, "confidence": 0.82, "is_follow_up": True}

    if re.search(
        r"\b(more|elaborate|detail|deeper|expand|in depth|comprehensive|full)\b",
        ql,
    ):
        return {"intent": INTENT_DEEPEN, "confidence": 0.84, "is_follow_up": True}

    if re.search(
        r"\b(next|also|what about|and what|other element|remaining|third element|"
        r"fourth element|further)\b",
        ql,
    ):
        return {"intent": INTENT_NEXT_ELEMENT, "confidence": 0.8, "is_follow_up": True}

    if re.search(r"\b(what do you mean|clarify|explain that|which part|unclear)\b", ql):
        return {"intent": INTENT_CLARIFY, "confidence": 0.86, "is_follow_up": True}

    if re.search(r"\b(continue|go on|and then|proceed)\b", ql):
        return {"intent": INTENT_CONTINUE, "confidence": 0.78, "is_follow_up": True}

    # Short vague queries likely follow-ups
    if words <= 12 and any(
        c in ql
        for c in (
            "it", "that", "this", "same", "above", "those", "they", "there",
            "explain", "why", "how",
        )
    ):
        return {"intent": INTENT_CLARIFY, "confidence": 0.72, "is_follow_up": True}

    if words <= 6 and has_context:
        try:
            from legal_web_query import is_conversational_acknowledgment

            if is_conversational_acknowledgment(q):
                return {
                    "intent": INTENT_ACKNOWLEDGMENT,
                    "confidence": 0.88,
                    "is_follow_up": True,
                }
        except ImportError:
            pass
        return {"intent": INTENT_CLARIFY, "confidence": 0.65, "is_follow_up": True}

    return {"intent": INTENT_NEW_TOPIC, "confidence": 0.55, "is_follow_up": False}


def expand_query_with_intent(
    question: str,
    session_memory: Dict[str, Any],
    intent_info: Dict[str, Any],
) -> Tuple[str, Dict[str, Any]]:
    """Expand query using semantic intent + session memory."""
    from backend.app.core.conversation_memory import _resolve_follow_up_rules

    intent = intent_info.get("intent") or INTENT_NEW_TOPIC
    if intent in (INTENT_ACKNOWLEDGMENT, INTENT_NEGATIVE_FEEDBACK):
        return question, intent_info
    sec = str(session_memory.get("last_section") or "").lower()
    law = str(session_memory.get("last_law") or "IPC").upper()
    topic = str(session_memory.get("last_topic") or "").strip()
    if topic.startswith("#") or re.search(r"\barticle\s+\d+\b", topic, re.I):
        topic = ""
    if not topic and sec:
        topic = f"{law} Section {sec.upper()}"
    last_case = str(session_memory.get("last_case") or "").strip()
    if not last_case:
        try:
            from conversation_context import extract_case_title_from_text

            last_case = extract_case_title_from_text(
                str(session_memory.get("last_user_query") or "")
            )
        except ImportError:
            pass

    if last_case and intent in (
        INTENT_DEEPEN,
        INTENT_EXAMPLE,
        INTENT_SIMPLIFY,
        INTENT_NEXT_ELEMENT,
        INTENT_CONTINUE,
        INTENT_CLARIFY,
    ):
        if intent == INTENT_SIMPLIFY:
            return f"Explain the case {last_case} in simple language.", intent_info
        if intent == INTENT_EXAMPLE:
            return f"Give examples related to the case {last_case}.", intent_info
        return f"Explain the case {last_case} in detail from the uploaded documents.", intent_info

    if intent == INTENT_DEEPEN and topic:
        return f"Provide a detailed explanation of {topic} from the documents.", intent_info
    if intent == INTENT_EXAMPLE and topic:
        return f"Give a practical example related to {topic}.", intent_info
    if intent == INTENT_SIMPLIFY and topic:
        return f"Explain {topic} in simple language.", intent_info
    if intent == INTENT_NEXT_ELEMENT and topic:
        return f"What are the remaining elements or aspects of {topic}?", intent_info
    if intent == INTENT_CONTINUE and topic:
        return f"Continue the explanation of {topic}.", intent_info
    if intent == INTENT_PUNISHMENT:
        try:
            from conversation_context import extract_sections_from_text

            nums = extract_sections_from_text(question)
            if nums:
                law_u = str(session_memory.get("last_law") or "IPC").upper()
                return (
                    f"What is the punishment prescribed for {law_u} Section {nums[0].upper()}?",
                    intent_info,
                )
        except Exception:
            pass

    return _resolve_follow_up_rules(question, session_memory), intent_info
