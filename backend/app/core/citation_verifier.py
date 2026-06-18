"""
Citation verification for Jurisprudence / Open Law answers.

Annotates [KB-N] and [WEB-N] references against retrieved evidence.
When STRICT_CITATIONS=1, unverified markers are stripped from the answer body.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

STRICT_CITATIONS = os.getenv("STRICT_CITATIONS", "0").lower() in ("1", "true", "yes")
from urllib.parse import urlparse


def _kb_label(chunk: Dict[str, Any], index: int) -> str:
    meta = chunk.get("metadata") or {}
    fn = meta.get("filename") or chunk.get("filename") or f"document {index}"
    sec = meta.get("section") or meta.get("section_label") or ""
    return f"{fn}" + (f" §{sec}" if sec else "")


def verify_citations(
    answer: str,
    kb_chunks: Optional[List[Dict[str, Any]]] = None,
    web_sources: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Append ## Citation Verification when [KB-N] / [WEB-N] markers are present.
    Returns (annotated_answer, stats).
    """
    text = (answer or "").strip()
    if not text:
        return text, {"verified_kb": 0, "failed_kb": 0, "verified_web": 0, "failed_web": 0}

    kb_chunks = kb_chunks or []
    web_sources = web_sources or []
    lines: List[str] = []
    stats = {"verified_kb": 0, "failed_kb": 0, "verified_web": 0, "failed_web": 0}

    for ref in sorted(set(re.findall(r"\[KB-(\d+)\]", text, re.I)), key=int):
        idx = int(ref) - 1
        if 0 <= idx < len(kb_chunks):
            lines.append(f"- **[KB-{ref}]** ✓ Verified — {_kb_label(kb_chunks[idx], idx + 1)}")
            stats["verified_kb"] += 1
        else:
            lines.append(f"- **[KB-{ref}]** ⚠ Not found in retrieved document chunks")
            stats["failed_kb"] += 1

    for ref in sorted(set(re.findall(r"\[WEB-(\d+)\]", text, re.I)), key=int):
        idx = int(ref) - 1
        if 0 <= idx < len(web_sources) and (web_sources[idx].get("href") or "").strip():
            title = web_sources[idx].get("title") or web_sources[idx].get("href")
            lines.append(f"- **[WEB-{ref}]** ✓ Verified — {title}")
            stats["verified_web"] += 1
        else:
            lines.append(f"- **[WEB-{ref}]** ⚠ Source link not in grounding results")
            stats["failed_web"] += 1

    # Markdown links vs web source domains
    link_hrefs = re.findall(r"\]\((https?://[^)]+)\)", text)
    known_hosts = {
        urlparse(str(s.get("href", ""))).netloc.lower()
        for s in web_sources
        if s.get("href")
    }
    for href in link_hrefs[:12]:
        host = urlparse(href).netloc.lower()
        if known_hosts and host and host not in known_hosts and "google" not in host:
            lines.append(f"- **Link** ⚠ External source not in grounding set — `{host}`")

    if not lines:
        return text, stats

    if "## Citation Verification" in text:
        return text, stats

    block = "## Citation Verification\n\n" + "\n".join(lines)
    return text.rstrip() + "\n\n" + block, stats


def apply_strict_citations(
    answer: str,
    kb_chunks: Optional[List[Dict[str, Any]]] = None,
    web_sources: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """Verify citations; in strict mode remove unverified [KB-N]/[WEB-N] markers."""
    annotated, stats = verify_citations(answer, kb_chunks, web_sources)
    if not STRICT_CITATIONS:
        return annotated, stats

    body = (answer or "").strip()
    failed_kb = {
        int(m.group(1))
        for m in re.finditer(r"\[KB-(\d+)\]", body, re.I)
        if int(m.group(1)) - 1 >= len(kb_chunks or [])
    }
    failed_web = {
        int(m.group(1))
        for m in re.finditer(r"\[WEB-(\d+)\]", body, re.I)
        if int(m.group(1)) - 1 >= len(web_sources or [])
        or not ((web_sources or [{}])[int(m.group(1)) - 1].get("href") if int(m.group(1)) - 1 < len(web_sources or []) else "")
    }

    for idx in failed_kb:
        body = re.sub(rf"\[KB-{idx}\]", "", body, flags=re.I)
    for idx in failed_web:
        body = re.sub(rf"\[WEB-{idx}\]", "", body, flags=re.I)

    body = re.sub(r"\s{2,}", " ", body)
    body = re.sub(r" +([,.;])", r"\1", body)
    if stats.get("failed_kb") or stats.get("failed_web"):
        note = (
            "\n\n> _Strict citation mode: unverified source markers were removed._"
        )
        if note.strip() not in body:
            body = body.rstrip() + note

    annotated, stats = verify_citations(body, kb_chunks, web_sources)
    return annotated, stats


_SECTION_CLAIM = re.compile(
    r"\b(?:IPC|BNS|Section|Sec\.?)\s*(\d+[A-Z]?)\b",
    re.I,
)
_CASE_CLAIM = re.compile(
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+v\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b",
)


def annotate_matter_legal_claims(answer: str, matter_text: str) -> str:
    """Flag IPC/BNS sections and case citations not supported by matter document text."""
    text = (answer or "").strip()
    corpus = (matter_text or "").lower()
    if not text or len(corpus) < 40:
        return text

    flags: List[str] = []
    seen_secs: set = set()
    for m in _SECTION_CLAIM.finditer(text):
        sec = m.group(1)
        key = sec.lower()
        if key in seen_secs:
            continue
        seen_secs.add(key)
        if (
            sec not in matter_text
            and f"section {sec}" not in corpus
            and f"sec {sec}" not in corpus
            and f"ipc {sec}" not in corpus
            and f"bns {sec}" not in corpus
        ):
            flags.append(
                f"- **Section {sec}** — not found in matter documents; verify before relying on it."
            )

    for m in _CASE_CLAIM.finditer(text):
        case_label = f"{m.group(1)} v. {m.group(2)}"
        if case_label.lower() not in corpus:
            flags.append(
                f"- **{case_label}** — case name not found in matter documents; confirm citation."
            )

    if not flags:
        return text
    if "## Claim verification" in text:
        return text
    block = "## Claim verification (matter documents)\n\n" + "\n".join(flags[:12])
    return text.rstrip() + "\n\n" + block
