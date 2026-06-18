"""
Global Knowledge Base strict policy.

Gemini MUST NOT participate in user-facing KB answers or retrieval.
KB answers: retrieved chunks → document-first extract → optional Ollama paraphrase → validation.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional

KB_INSUFFICIENT_INFO = (
    "The uploaded documents do not contain sufficient information to answer this question."
)

_OUTSIDE_KNOWLEDGE_RE = re.compile(
    r"\b(?:"
    r"in many legal systems|many legal systems|generally speaking|"
    r"typically in most jurisdictions|under most constitutions|"
    r"worldwide|internationally recognized|universally|"
    r"as a general rule|it is widely understood that"
    r")\b",
    re.I,
)

_DISCLAIMER_THEN_GENERAL_RE = re.compile(
    r"(?:not\s+(?:explicitly\s+)?(?:mentioned|defined|stated|found)|"
    r"does not contain|not in the (?:provided\s+)?document|"
    r"excerpts focus on)[\s\S]{0,220}"
    r"(?:in many legal systems|fundamental rights refer to|typically include|"
    r"such as freedom of speech)",
    re.I,
)


def answer_has_outside_knowledge_bleed(answer: str) -> bool:
    text = (answer or "").strip()
    if not text:
        return False
    if _OUTSIDE_KNOWLEDGE_RE.search(text):
        return True
    if _DISCLAIMER_THEN_GENERAL_RE.search(text):
        return True
    return False


def chunks_support_query_topic(query: str, chunks: List[Dict]) -> bool:
    """True when retrieved excerpts plausibly cover the user's topic (domain-agnostic)."""
    if not chunks:
        return False
    ql = (query or "").lower()
    combined = " ".join((c.get("content") or "")[:800].lower() for c in chunks[:6])
    if re.search(r"\b(?:fundamental|constitutional)\s+rights?\b", ql):
        return bool(
            re.search(
                r"\b(?:fundamental\s+rights|constitutional\s+rights|right\s+to\s+)"
                r"|article\s+(?:1[2-9]|[2-3]\d)\b",
                combined,
                re.I,
            )
        )
    try:
        from backend.app.core.universal_kb import chunks_overlap_query

        return chunks_overlap_query(query, chunks, min_ratio=0.2)
    except Exception:
        pass
    terms = [
        w
        for w in re.findall(r"[a-z]{4,}", ql)
        if w not in {"explain", "what", "does", "mean", "summarize", "summary"}
    ]
    if not terms:
        return len(combined) > 80
    hits = sum(1 for t in terms if t in combined)
    return hits >= max(1, len(terms) // 2)


STRICT_KB_GROUNDING_PROMPT = """
STRICT KB MODE (mandatory):
- Uploaded documents are the ONLY source of truth. No legal training data, IPC memory, or internet knowledge.
- You may ONLY reorganize, paraphrase, or summarize text that appears in the excerpts.
- Do NOT invent facts, clauses, definitions, punishments, or parties absent from excerpts.
- If the user asks to explain a section/statute and excerpts only mention it (e.g. "charged under IPC 379"),
  state that the document mentions it but does NOT contain the definition — do NOT supply the statute text.
- If the excerpts do not contain the answer, output exactly one line:
  "The uploaded documents do not contain sufficient information to answer this question."
- Never combine that line with other paragraphs. Do not include a Source line in the body.
"""


def gemini_allowed_in_kb() -> bool:
    return False


def kb_learning_inject_allowed() -> bool:
    return os.getenv("KB_BLOCK_LEARNING_INJECT", "1").lower() not in {"1", "true", "yes"}


def prepare_kb_synthesis_signals(signals: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out = dict(signals or {})
    out["kb_synthesis"] = True
    out["kb_no_learning_inject"] = True
    out["strict_grounding"] = True
    out["grounded_mode"] = True
    out["external_knowledge"] = False
    out["mode"] = "knowledge_base"
    return out


def kb_llm_temperature() -> float:
    try:
        from backend.app.core.kb_document_first import kb_llm_temperature as _t

        return _t()
    except ImportError:
        return 0.23


def finalize_kb_answer(
    answer: str,
    query: str,
    chunks: List[Dict],
    *,
    query_type: Any = None,
) -> str:
    from kb_response_state import KB_NOT_FOUND_MESSAGE, contains_not_found_phrase

    try:
        from backend.app.core.kb_landmark_case import (
            answer_mentions_wrong_landmark,
            build_landmark_case_answer,
            is_landmark_case_query,
        )

        if is_landmark_case_query(query):
            rebuilt = build_landmark_case_answer(query, chunks or [])
            if rebuilt:
                return rebuilt
            return KB_INSUFFICIENT_INFO
        if answer and answer_mentions_wrong_landmark(answer, query):
            rebuilt = build_landmark_case_answer(query, chunks or [])
            if rebuilt:
                return rebuilt
    except ImportError:
        pass

    try:
        from backend.app.core.kb_question_aware import generate_question_aware_answer

        qa = generate_question_aware_answer(query, chunks or [])
        if qa:
            return qa
    except ImportError:
        pass

    try:
        from backend.app.core.kb_document_first import finalize_document_first

        return finalize_document_first(answer or "", query, chunks or [])
    except ImportError:
        pass

    text = (answer or "").strip()
    if not text or text == KB_NOT_FOUND_MESSAGE or contains_not_found_phrase(text):
        return text if text else KB_INSUFFICIENT_INFO
    if not chunks:
        return KB_NOT_FOUND_MESSAGE
    if answer_has_outside_knowledge_bleed(text):
        return KB_INSUFFICIENT_INFO
    return text
