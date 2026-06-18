"""
Response Quality Engine — structured, human-readable legal answers.

No JSON blobs, no retrieval dumps, no repeated lines.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from response_cleaner import deduplicate_response, is_empty_payload

_SECTION_HEADINGS = (
    "Meaning",
    "Key Elements",
    "Punishment",
    "Example",
    "Important Note",
)
_COMPARE_HEADINGS = ("Key Difference", "Short Conclusion")
_CASE_HEADINGS = ("Background", "Facts", "Judgement", "Legal Impact", "Why Important")
_GENERAL_HEADINGS = ("Simple Explanation", "Key Points", "Example")

_JSON_LIKE_RE = re.compile(r"^\s*[\[{]")
_REPEAT_LINE_RE = re.compile(r"(?m)^(.{20,})\s*\n\s*\1\s*$")


def strip_json_artifacts(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    if _JSON_LIKE_RE.match(t):
        return t
    return re.sub(r"\n*\{[\s\S]{10,}?\}\n*", "\n", t).strip()


def _strip_repeated_lines(text: str) -> str:
    lines = (text or "").splitlines()
    seen: set[str] = set()
    out: List[str] = []
    for line in lines:
        key = re.sub(r"\s+", " ", line.strip().lower())
        if not key:
            out.append(line)
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(line)
    return "\n".join(out)


def _json_to_prose(raw: str) -> str:
    s = (raw or "").strip()
    if not _JSON_LIKE_RE.match(s):
        return raw
    try:
        data = json.loads(s)
    except Exception:
        return strip_json_artifacts(raw) if "{" in raw or "[" in raw else raw

    if isinstance(data, dict):
        parts: List[str] = []
        for k, v in data.items():
            label = str(k).replace("_", " ").title()
            if isinstance(v, (list, tuple)):
                parts.append(f"**{label}**\n" + "\n".join(f"- {x}" for x in v))
            else:
                parts.append(f"**{label}**\n{v}")
        return "\n\n".join(parts)
    if isinstance(data, list):
        return "\n".join(f"- {x}" for x in data)
    return str(data)


def _ensure_headings(text: str, headings: tuple[str, ...]) -> str:
    """Add missing section headings only when answer is a flat blob."""
    t = (text or "").strip()
    if not t or any(h.lower() in t.lower() for h in headings):
        return t
    if len(t) < 120:
        return t
    blocks = [b.strip() for b in re.split(r"\n{2,}", t) if b.strip()]
    if len(blocks) <= 1:
        return t
    out: List[str] = []
    for i, block in enumerate(blocks[: len(headings)]):
        out.append(f"**{headings[i]}**\n{block}")
    if len(blocks) > len(headings):
        out.extend(blocks[len(headings) :])
    return "\n\n".join(out)


def format_legal_response(
    answer: str,
    *,
    intent: str = "general",
    parse: Optional[Dict[str, Any]] = None,
) -> str:
    """Format answer by legal intent type."""
    if is_empty_payload(answer):
        return answer

    text = _json_to_prose(answer)
    text = strip_json_artifacts(text)
    text = _strip_repeated_lines(text)
    text = deduplicate_response(text)

    intent = intent or (parse or {}).get("intent", "general")

    if intent == "section_lookup":
        text = _ensure_headings(text, _SECTION_HEADINGS)
    elif intent == "comparison":
        if "|" not in text and " vs " not in text.lower():
            text = _ensure_headings(text, _COMPARE_HEADINGS)
    elif intent == "case_explanation":
        text = _ensure_headings(text, _CASE_HEADINGS)
    elif intent in ("concept_explanation", "general", "follow_up"):
        text = _ensure_headings(text, _GENERAL_HEADINGS)

    return text.strip()
