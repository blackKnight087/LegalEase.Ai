"""
Hard KB response state machine — FOUND or NOT_FOUND, never both.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KB_NOT_FOUND_MESSAGE = (
    "I couldn't find a clear reference to that in the uploaded legal documents."
)

try:
    from backend.app.core.kb_strict_policy import KB_INSUFFICIENT_INFO
except ImportError:
    KB_INSUFFICIENT_INFO = (
        "The uploaded document does not contain sufficient information to "
        "answer this part of the question."
    )

# Legacy phrase variants to strip from FOUND answers
_NOT_FOUND_PATTERNS = [
    r"I could not find this information in the uploaded legal documents\.?\s*",
    r"I couldn't find this information in the uploaded legal documents\.?\s*",
    r"I could not find a clear reference[^\n.]*\.?\s*",
    r"I couldn't find a clear reference[^\n.]*\.?\s*",
    r"I checked the uploaded legal documents, but I couldn't find[^\n.]*\.?\s*",
    r"not found in the uploaded legal documents\.?\s*",
    r"not found in uploaded legal documents\.?\s*",
    r"information not found in document\.?\s*",
    r"not_found_in_kb\s*",
    r"this explanation is drawn only from your uploaded document\.?\s*",
]

_LEGAL_CONTENT_RE = re.compile(
    r"\b(?:section|ipc|bns|bnss|bsa|crpc)\s*\d{1,4}[a-z]?|\b\d{1,4}[a-z]?\s*ipc\b"
    r"|\b(?:ipc|bns|bnss|bsa|crpc)\b|\bindian penal code\b|\bbharatiya nyaya\b|\bbharatiya nagarik\b"
    r"|\b(?:article\s+\d+|right to|fundamental rights?|constitutional rights?|equality|liberty)\b",
    re.I,
)


def contains_not_found_phrase(text: str) -> bool:
    tl = (text or "").lower()
    markers = (
        "could not find this information",
        "couldn't find this information",
        "couldn't find a clear reference",
        "could not find a clear reference",
        "not found in the uploaded",
        "not found in uploaded",
        "information not found in document",
        "not_found_in_kb",
        "drawn only from your uploaded document",
    )
    return any(m in tl for m in markers)


_CONTRACT_CONTENT_RE = re.compile(
    r"\b(party|parties|agreement|contract|confidential|nda|disclosing|receiving|"
    r"termination|indemnity|whereas|obligations?)\b",
    re.I,
)


def has_substantive_document_content(text: str) -> bool:
    """Any grounded excerpt from uploaded PDFs (not only statute/contract keywords)."""
    t = (text or "").strip()
    alnum = len(re.findall(r"[A-Za-z0-9]", t))
    if alnum < 40:
        return False
    if re.search(r"^##\s+", t, re.M) and alnum >= 50:
        return True
    if re.search(r"^###\s+", t, re.M) and alnum >= 60:
        return True
    sentences = [s.strip() for s in re.split(r"[.!?]\s+", t) if len(s.strip()) > 20]
    return len(sentences) >= 1 and alnum >= 80


def has_substantive_legal_content(text: str) -> bool:
    t = (text or "").strip()
    if re.search(r"^##\s+(?:IPC|BNS)\s+Section\s+\d", t, re.I | re.M):
        if len(re.findall(r"[A-Za-z0-9]", t)) >= 15:
            return True
    if re.search(r"^###\s+Knowledge Base Empty", t, re.I | re.M):
        return True
    if has_substantive_document_content(t):
        return True
    if len(re.findall(r"[A-Za-z0-9]", t)) < 12:
        return False
    if re.search(r"^##\s+", t, re.M) and len(re.findall(r"[A-Za-z0-9]", t)) >= 40:
        return True
    return bool(
        _LEGAL_CONTENT_RE.search(t)
        or _CONTRACT_CONTENT_RE.search(t)
        or re.search(r"##\s|\*\*", t)
    )


def strip_all_not_found_phrases(text: str) -> str:
    t = (text or "").strip()
    for pat in _NOT_FOUND_PATTERNS:
        t = re.sub(pat, "", t, flags=re.I)
    from response_cleaner import clean_kb_response

    return clean_kb_response(t)


def enforce_single_state(text: str, *, found: bool) -> str:
    """
    FOUND → legal answer only, zero not-found phrasing.
    NOT_FOUND → only the not-found message, nothing else.
    """
    if not found:
        return KB_NOT_FOUND_MESSAGE

    t = strip_all_not_found_phrases(text)
    if contains_not_found_phrase(t):
        t = strip_all_not_found_phrases(t)
    if not t or not has_substantive_legal_content(t):
        return ""
    if contains_not_found_phrase(t):
        return ""
    return t


def log_kb_pipeline(
    *,
    query: str,
    decision: str,
    best_score: float = 0.0,
    threshold: float = 0.0,
    chunks: Optional[List[Dict]] = None,
    answer: str = "",
) -> None:
    excerpt = ""
    if chunks:
        excerpt = (chunks[0].get("content") or "")[:100].replace("\n", " ")
    logger.info(
        "[KB STATE] QUERY=%r | DECISION=%s | BEST_SCORE=%.3f | THRESHOLD=%.3f | EXCERPT=%r",
        query,
        decision,
        best_score,
        threshold,
        excerpt,
    )
    logger.info("[KB STATE] FINAL_ANSWER=%r", (answer or "")[:300])
    try:
        from backend.app.core.kb_pipeline_log import kb_log

        kb_log(
            "KB_STATE",
            query=query,
            decision=decision,
            best_score=best_score,
            threshold=threshold,
            answer_preview=(answer or "")[:400],
            excerpt=excerpt,
        )
    except Exception:
        pass


def build_found_answer(
    question: str,
    chunks: List[Dict],
    profile: Any,
    messages: Optional[List[Dict]] = None,
    *,
    use_llm: bool = True,
    temperature: float = 0.12,
    max_tokens: int = 2048,
    user_id: str = "",
) -> str:
    """Build answer ONLY from chunks — never includes not-found text."""
    from kb_rag_decision import extract_query_sections
    from answer_orchestrator import intent_aware_fallback

    from intent_engine import QueryIntent

    from kb_retrieval import extract_comparison_sections, is_comparison_query

    try:
        from backend.app.core.universal_kb import is_statute_focused_query, universal_document_answer

        if chunks and not is_statute_focused_query(question):
            uni = universal_document_answer(
                question, chunks, user_id=user_id, use_llm=use_llm
            )
            uni = enforce_single_state(uni, found=True)
            if uni:
                return uni
    except Exception:
        pass

    primary = str((profile.signals or {}).get("primary_section") or "")
    if primary:
        sections = [primary]
    else:
        sections = (
            profile.signals.get("entities")
            or profile.signals.get("sections")
            or extract_query_sections(question)
        )
    try:
        from kb_query_types import primary_sections_from_query

        orig = (profile.signals or {}).get("original_query") or question
        pg = primary_sections_from_query(orig)
        if len(pg) == 1:
            sections = pg
    except Exception:
        pass
    if is_comparison_query(question):
        cmp_secs = extract_comparison_sections(question)
        if len(cmp_secs) >= 2:
            sections = cmp_secs
            profile.signals["sections"] = cmp_secs

    if profile.primary == QueryIntent.LIST_EXTRACTION:
        entities = profile.signals.get("extracted_entities") or []
        if entities:
            from answer_orchestrator import format_ipc_sections_list

            answer = enforce_single_state(
                format_ipc_sections_list(question, entities, chunks, profile),
                found=True,
            )
            if answer:
                return answer

    # Comparison / multi-section: structured table (never single-section card)
    orig_q = (profile.signals or {}).get("original_query") or question
    from kb_retrieval import is_comparison_query

    wants_compare = profile.primary == QueryIntent.COMPARISON or (
        is_comparison_query(orig_q) and sections and len(sections) >= 2
    )
    if wants_compare:
        from answer_orchestrator import format_comparison_answer

        answer = enforce_single_state(
            format_comparison_answer(question, chunks, profile), found=True
        )
        if answer:
            return answer

    if use_llm:
        try:
            from answer_orchestrator import _kb_ollama_max_tokens, synthesize_from_chunks

            tok = _kb_ollama_max_tokens()
            profile.signals = dict(profile.signals or {})
            profile.signals["kb_synthesis"] = True
            profile.complexity = profile.complexity or "deep"
            profile.max_answer_tokens = max(int(profile.max_answer_tokens or 0), tok)
            raw = synthesize_from_chunks(
                question,
                chunks,
                profile,
                user_id=user_id,
                temperature=temperature,
                max_tokens=max(int(max_tokens or tok), tok),
            )
            answer = enforce_single_state(raw, found=True)
            if answer:
                return answer
        except Exception:
            pass

    # Single-section deterministic card when Ollama unavailable
    if sections and len(sections) == 1:
        answer = intent_aware_fallback(question, chunks, profile)
        answer = enforce_single_state(answer, found=True)
        if answer:
            return answer

    # Deterministic path when Ollama is empty or refuses — still grounded in chunks
    answer = intent_aware_fallback(question, chunks, profile)
    answer = enforce_single_state(answer, found=True)
    if not answer:
        return ""
    try:
        from response_cleaner import finalize_display_answer

        sections = profile.signals.get("sections") or extract_query_sections(question)
        sec = sections[0] if sections else ""
        answer, _ = finalize_display_answer(
            answer,
            chunks,
            section_hint=f"Section {sec.upper()}" if sec else "",
            section=sec,
        )
    except Exception:
        pass
    return answer or ""
