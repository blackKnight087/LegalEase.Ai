"""
Answer Validator — pre-display checks for grounding, quality, and safety.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from kb_query_types import QueryType
from kb_validate import validate_answer
from kb_response_state import KB_NOT_FOUND_MESSAGE, contains_not_found_phrase
from response_cleaner import deduplicate_response, is_empty_payload

from backend.app.services.response_formatter import format_legal_response, strip_json_artifacts

_JSON_LIKE_RE = re.compile(r"^\s*[\[{]")
_REPEAT_BLOCK_RE = re.compile(r"(?s)(.{40,}?)\n\s*\1")


@dataclass
class ValidationResult:
    ok: bool
    answer: str
    reason: str = ""
    should_retry_retrieval: bool = False


def _has_json_blob(text: str) -> bool:
    s = (text or "").strip()
    if _JSON_LIKE_RE.match(s):
        return True
    return bool(re.search(r'\{\s*"(?:left|right|entity|topic|usage)"\s*:', s, re.I))


def _has_repeated_blocks(text: str) -> bool:
    return bool(_REPEAT_BLOCK_RE.search(text or ""))


def _unsupported_claims(answer: str, chunks: List[Dict]) -> bool:
    """Heuristic: answer cites section numbers absent from chunks."""
    if not chunks or not answer:
        return False
    joined = "\n".join((c.get("content") or "") for c in chunks[:10]).lower()
    for m in re.finditer(r"\b(?:IPC|BNS|Section)\s+(\d{1,4}[a-z]?)\b", answer, re.I):
        sec = m.group(1).lower()
        if not re.search(rf"\b(?:section\s*{re.escape(sec)}|ipc\s*{re.escape(sec)}|bns\s*{re.escape(sec)})\b", joined, re.I):
            if len(joined) > 100:
                return True
    return False


def _query_law_missing_from_chunks(query: str, chunks: List[Dict]) -> bool:
    """True when query names a statute/act absent from retrieved context."""
    if not chunks or not query:
        return False
    joined = "\n".join((c.get("content") or "") for c in chunks[:12]).lower()
    ql = (query or "").lower()
    for m in re.finditer(
        r"\b([a-z][\w\s]{2,40}?(?:act|code|sanhita|ordinance))\b",
        ql,
    ):
        act = re.sub(r"\s+", " ", m.group(1).strip())
        if len(act) < 6:
            continue
        if act in joined:
            continue
        if "penal" in act or act == "ipc":
            if re.search(r"\bipc\b|penal code|section\s+\d", joined):
                continue
        return True
    if "alien marriage" in ql and "alien" not in joined:
        return True
    return False


def validate_and_clean_answer(
    answer: str,
    query: str,
    chunks: Optional[List[Dict]] = None,
    *,
    query_type: Optional[QueryType] = None,
    intent: str = "general",
    parse: Optional[Dict[str, Any]] = None,
    strict_grounded: bool = True,
    profile_sections: Optional[List[str]] = None,
    entity_count: int = 0,
) -> ValidationResult:
    """
    Validate answer before sending to frontend.

    - Missing/empty → retry retrieval signal
    - JSON → convert to prose
    - Repeated lines → dedupe
    - Hallucination → block or NOT_FOUND
    """
    text = (answer or "").strip()
    chunks = chunks or []

    if not text or text == "NOT_FOUND_IN_KB":
        return ValidationResult(False, KB_NOT_FOUND_MESSAGE, "missing", True)

    if contains_not_found_phrase(text) and len(text) < 200:
        return ValidationResult(True, text, "not_found_phrase")

    if is_empty_payload(text):
        return ValidationResult(False, KB_NOT_FOUND_MESSAGE, "empty", True)

    if _has_json_blob(text):
        text = format_legal_response(text, intent=intent, parse=parse)

    if _has_repeated_blocks(text):
        text = deduplicate_response(text)

    text = strip_json_artifacts(text)

    qt = query_type or QueryType.UNKNOWN
    if strict_grounded and chunks:
        if _query_law_missing_from_chunks(query, chunks):
            return ValidationResult(False, KB_NOT_FOUND_MESSAGE, "unsupported_law", True)
        ok, reason = validate_answer(
            text,
            query,
            chunks,
            qt,
            profile_sections=profile_sections,
            entity_count=entity_count,
        )
        if not ok:
            if reason.startswith("comparison_missing") or reason == "wrong_law_it_act_only":
                return ValidationResult(False, KB_NOT_FOUND_MESSAGE, reason, True)
            if _unsupported_claims(text, chunks):
                return ValidationResult(False, KB_NOT_FOUND_MESSAGE, "unsupported_claim", True)

    text = format_legal_response(text, intent=intent, parse=parse)

    if is_empty_payload(text):
        return ValidationResult(False, KB_NOT_FOUND_MESSAGE, "empty_after_clean", True)

    return ValidationResult(True, text, "ok")
