"""
Strip inline source blocks and Gemini grounding redirect URLs from Web Intel answers.

Sources are shown in the UI footer (web_sources) — not as raw links in the answer body.
"""
from __future__ import annotations

import re
from typing import Dict, List

_GROUNDING_URL = re.compile(
    r"https?://vertexaisearch\.cloud\.google\.com/grounding-api-redirect/[^\s\)\]\"']+",
    re.I,
)
_GROUNDING_MD_LINK = re.compile(
    r"\[([^\]]*)\]\(\s*https?://vertexaisearch\.cloud\.google\.com/[^\)]+\)",
    re.I,
)
_SOURCES_SECTION = re.compile(
    r"\n#{1,3}\s*Sources(?:\s*(?:&|and)\s*Citations)?\s*\n[\s\S]*?(?=\n#{1,3}\s|\n---\s*\n\*Disclaimer|\Z)",
    re.I,
)


def is_grounding_redirect_url(url: str) -> bool:
    return "vertexaisearch.cloud.google.com" in (url or "").lower() and "grounding-api-redirect" in (
        url or ""
    ).lower()


def strip_inline_sources_from_web_answer(text: str) -> str:
    """Remove ## Sources blocks and raw grounding URLs from displayed markdown."""
    if not (text or "").strip():
        return text or ""

    out = text
    out = _SOURCES_SECTION.sub("\n", out)
    out = _GROUNDING_MD_LINK.sub(r"\1", out)
    out = _GROUNDING_URL.sub("", out)
    # Collapse link-only bullet lines left after URL removal
    out = re.sub(r"^-\s*\[[^\]]*\]\(\s*\)\s*$", "", out, flags=re.M)
    out = re.sub(r"^-\s*$", "", out, flags=re.M)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


_CITE_ARTIFACT_RE = re.compile(r"\[cite:\s*[^\]]*\]", re.I)
_DUP_SECTION_RE = re.compile(r"^##\s+(.+)$", re.M)
_BOLD_LABEL_LINE_RE = re.compile(
    r"^\s*\*{1,2}([A-Za-z][^*\n:]{2,40})\*{1,2}\s*:\s*",
    re.M,
)


def _dedupe_markdown_sections(text: str) -> str:
    """Drop repeated ## sections with substantially the same body."""
    from difflib import SequenceMatcher

    if not (text or "").strip():
        return text or ""
    parts = re.split(r"(?=^##\s+)", text, flags=re.M)
    if len(parts) <= 1:
        return text
    out: List[str] = []
    seen: Dict[str, str] = {}
    for part in parts:
        if not part.strip():
            continue
        m = _DUP_SECTION_RE.match(part)
        if not m:
            out.append(part)
            continue
        title = re.sub(r"\s+", " ", m.group(1).strip().lower())
        body = part[m.end() :].strip()
        if title in seen:
            prev = seen[title]
            if SequenceMatcher(None, body, prev).ratio() >= 0.65:
                continue
        seen[title] = body
        out.append(part)
    return "".join(out).strip()


def _dedupe_bold_label_blocks(text: str) -> str:
    """Remove repeated **Label:** paragraphs (common in Gemini web answers)."""
    from difflib import SequenceMatcher

    lines = (text or "").splitlines()
    out: List[str] = []
    seen_labels: Dict[str, str] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        m = _BOLD_LABEL_LINE_RE.match(line)
        if not m:
            out.append(line)
            i += 1
            continue
        label = re.sub(r"\s+", " ", m.group(1).strip().lower())
        block_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not _BOLD_LABEL_LINE_RE.match(lines[i]) and not lines[i].startswith("##"):
            block_lines.append(lines[i])
            i += 1
        block = "\n".join(block_lines).strip()
        if label in seen_labels:
            if SequenceMatcher(None, block, seen_labels[label]).ratio() >= 0.6:
                continue
        seen_labels[label] = block
        out.extend(block_lines)
    return "\n".join(out)


def polish_research_answer(text: str) -> str:
    """Full cleanup for Hybrid / Web Intel display: cites, dup sections, dup bullets."""
    if not (text or "").strip():
        return text or ""
    out = strip_inline_sources_from_web_answer(text)
    out = _CITE_ARTIFACT_RE.sub("", out)
    out = re.sub(r"##\s*Direct Answer\s*(?=\s|$)", "", out, flags=re.I)
    out = _dedupe_markdown_sections(out)
    out = _dedupe_bold_label_blocks(out)
    try:
        from response_cleaner import deduplicate_response

        out = deduplicate_response(out)
    except ImportError:
        pass
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()
