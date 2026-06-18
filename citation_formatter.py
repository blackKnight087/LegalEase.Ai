"""
Professional citation formatting for Knowledge Base answers.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


def _chunk_lookup(chunks: List[Dict]) -> Dict[Tuple[str, int], Dict]:
    table: Dict[Tuple[str, int], Dict] = {}
    for ch in chunks or []:
        meta = ch.get("metadata", {}) or {}
        fname = str(meta.get("filename", "document"))
        try:
            idx = int(meta.get("chunk_index", 0))
        except (TypeError, ValueError):
            idx = 0
        table[(fname, idx)] = ch
    return table


def format_source_label(meta: Dict) -> str:
    fname = meta.get("filename", "document")
    page = meta.get("page", meta.get("page_number", ""))
    parts = [str(fname)]
    if page not in ("", None):
        parts.append(f"Page {page}")
    return ", ".join(parts)


def strip_inline_citation_markers(text: str) -> str:
    """Remove [[file:chunk]] markers from visible answer body."""
    cleaned = re.sub(r"\s*\[\[[^\]]+:\d+\]\]\s*", " ", text or "")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def build_source_footer(chunks: List[Dict], section_hint: str = "") -> str:
    if not chunks:
        return ""
    meta = chunks[0].get("metadata", {}) or {}
    label = format_source_label(meta)
    if section_hint:
        return f"**Source:** {label} · {section_hint}"
    return f"**Source:** {label}"


def polish_kb_response(
    text: str,
    chunks: List[Dict],
    *,
    section_hint: str = "",
    attach_source: bool = False,
    law: str = "",
) -> str:
    """Polish body text. Source is NOT appended unless attach_source=True (UI renders footer)."""
    from response_cleaner import finalize_display_answer, strip_embedded_source

    body = strip_inline_citation_markers(text)
    if not section_hint:
        m = re.search(r"Section\s+(\d{1,4}[a-z]?)", body or "", re.I)
        if m:
            section_hint = f"Section {m.group(1).upper()}"
    sec = ""
    m2 = re.search(r"(\d{1,4}[a-z]?)", section_hint or "", re.I)
    if m2:
        sec = m2.group(1).lower()
    law_use = (law or "").strip().upper()
    if not law_use:
        bl = (body or "").lower()
        law_use = "BNS" if re.search(r"\bbns\b", bl) else "IPC"
    body, _ = finalize_display_answer(
        body,
        chunks if attach_source else None,
        section_hint=section_hint,
        section=sec,
        law=law_use,
    )
    if attach_source:
        footer = build_source_footer(chunks, section_hint=section_hint)
        if footer and "source:" not in body.lower()[-120:]:
            return f"{body.rstrip()}\n\n{footer}"
    return body

