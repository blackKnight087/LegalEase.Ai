"""
Knowledge Base text preprocessing and semantic legal chunking.
Removes OCR/page noise; keeps IPC/BNS sections intact.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Common OCR fixes in legal PDFs
_OCR_FIXES = (
    (r"\bMurdeggravated\b", "Murder aggravated"),
    (r"\bion\s+(\d{3})\b", r"Section \1"),
    (r"\bSecton\b", "Section"),
    (r"\bSeotion\b", "Section"),
    (r"\bSecion\b", "Section"),
    (r"\bSecti0n\b", "Section"),
    (r"\u00ad", ""),
)


def _repair_utf8_mojibake(text: str) -> str:
    """Fix UTF-8 bytes mis-read as Windows-1252 (common in PDF exports)."""
    try:
        repaired = text.encode("cp1252").decode("utf-8")
        return repaired if repaired.strip() else text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text

_PAGE_MARKER_RE = re.compile(
    r"\[\s*Page\s*(\d+)\s*\]|^\s*Page\s+(\d+)\s*$",
    re.I | re.M,
)
_HEADER_FOOTER_RE = re.compile(
    r"^\s*(?:confidential|draft|internal use only)\s*$",
    re.I | re.M,
)
_SECTION_BOUNDARY_RE = re.compile(
    r"(?=\n\s*(?:Section|SECTION|IPC|BNS)\s+\d{1,4}[A-Za-z]?\s*[-–—:])",
    re.I,
)
_SECTION_TITLE_RE = re.compile(
    r"^\s*(?:Section|IPC|BNS)\s+(\d{1,4}[A-Za-z]?)\s*[-–—:]",
    re.I | re.M,
)
_ARROW_RE = re.compile(r"[→\-\–—>]")
_MAPPING_ROW_RE = re.compile(
    r"(?:IPC|CrPC|BNS|BNSS|BSA|Indian Penal Code|Evidence Act|Criminal Procedure)"
    r".{0,120}?(?:IPC|CrPC|BNS|BNSS|BSA|Indian Penal Code|Evidence Act|Bharatiya)",
    re.I,
)
_PAGE_NUM_RE = re.compile(r"\[\s*(?:Page|PAGE)\s*:?\s*(\d+)\s*\]", re.I)


def clean_legal_text(text: str) -> str:
    """Strip page markers, headers, OCR junk, excess whitespace."""
    if not text:
        return ""
    t = _repair_utf8_mojibake(text)
    for pat, repl in _OCR_FIXES:
        t = re.sub(pat, repl, t, flags=re.I)
    # Keep page provenance as internal markers (stripped from display, used for metadata)
    t = _PAGE_MARKER_RE.sub(
        lambda m: f"\n[PAGE:{m.group(1) or m.group(2)}]\n",
        t,
    )
    t = _HEADER_FOOTER_RE.sub("", t)
    t = re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", t)
    t = re.sub(r"\bTopic\s*/?\s*Usage\b", "", t, flags=re.I)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return t.strip()


def _is_mapping_line(line: str) -> bool:
    s = (line or "").strip()
    if not s:
        return False
    if _ARROW_RE.search(s) and _MAPPING_ROW_RE.search(s):
        return True
    if re.search(r"\bIPC\s*\d{1,4}\b.*\bBNS\s*\d{1,4}\b", s, re.I):
        return True
    if re.search(r"\b(?:IPC|CrPC|Evidence Act)\b.*\b(?:BNS|BNSS|BSA)\b", s, re.I):
        return True
    return False


def _split_mapping_table_chunks(
    text: str,
    *,
    chunk_size: int = 900,
    chunk_overlap: int = 200,
    max_chunk: int = 1200,
) -> List[Tuple[str, int, int]]:
    """
    Keep IPC→BNS / CrPC→BNSS row mappings intact within chunks.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return []

    groups: List[str] = []
    buf: List[str] = []
    buf_mapping = False

    def _flush() -> None:
        nonlocal buf, buf_mapping
        if buf:
            groups.append("\n".join(buf))
            buf = []
            buf_mapping = False

    for line in lines:
        mapping_line = _is_mapping_line(line)
        if mapping_line:
            if buf and not buf_mapping:
                _flush()
            buf.append(line)
            buf_mapping = True
            joined = "\n".join(buf)
            if len(joined) >= chunk_size:
                groups.append(joined)
                overlap_lines = buf[-max(1, chunk_overlap // 40) :]
                buf = overlap_lines[:]
                buf_mapping = True
        else:
            if buf_mapping:
                _flush()
            buf.append(line)
            if len("\n".join(buf)) >= max_chunk:
                _flush()
    _flush()

    out: List[Tuple[str, int, int]] = []
    cursor = 0
    for group in groups:
        group = group.strip()
        if len(group) < 25:
            continue
        idx = text.find(group, cursor)
        if idx < 0:
            idx = cursor
        out.append((group, idx, idx + len(group)))
        cursor = idx + len(group)
    return out


def extract_section_heading(text: str) -> str:
    """First heading or mapping row label in chunk."""
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        if _is_mapping_line(line):
            return line[:120]
        m = _SECTION_TITLE_RE.match(line)
        if m:
            return line[:120]
    return ""


def extract_page_number(text: str) -> int:
    m = _PAGE_NUM_RE.search(text or "")
    return int(m.group(1)) if m else 0


def extract_page_range(text: str) -> str:
    """All [Page N] markers in chunk as '3' or '3-5'."""
    pages = [int(m.group(1)) for m in _PAGE_NUM_RE.finditer(text or "")]
    if not pages:
        return ""
    lo, hi = min(pages), max(pages)
    return str(lo) if lo == hi else f"{lo}-{hi}"


def extract_primary_section(text: str) -> Tuple[str, str]:
    """
    First statute heading in chunk → (legal_code, section_number).
    Used for metadata filtering so retrieval never pins the wrong section.
    """
    t = (text or "").strip()
    if not t:
        return "", ""
    m = re.search(
        r"^\s*(?:#+\s*)?(IPC|BNS|CrPC|BNSS|BSA)\s+Section\s+(\d{1,4}[a-z]?)",
        t,
        re.I | re.M,
    )
    if m:
        return m.group(1).upper(), m.group(2).lower()
    m = re.search(
        r"\b(IPC|BNS|CrPC|BNSS)\s+Section\s+(\d{1,4}[a-z]?)\b",
        t[:400],
        re.I,
    )
    if m:
        return m.group(1).upper(), m.group(2).lower()
    m = re.search(r"^\s*Section\s+(\d{1,4}[a-z]?)\s*[-–—:]", t, re.I | re.M)
    if m:
        law = "IPC" if re.search(r"\b(?:ipc|penal)\b", t[:200], re.I) else ""
        if re.search(r"\bbns\b", t[:200], re.I):
            law = "BNS"
        return law or "IPC", m.group(1).lower()
    return "", ""


def extract_section_numbers(text: str) -> List[str]:
    """Section numbers referenced in chunk text."""
    found: List[str] = []
    for pat in (
        re.compile(r"\b(?:Section|IPC|BNS|CrPC|BNSS)\s+(\d{1,4}[a-z]?)\b", re.I),
        re.compile(r"\bSection\s+(\d{1,4}[a-z]?)\b", re.I),
    ):
        for m in pat.finditer(text or ""):
            sec = m.group(1).lower()
            if sec not in found:
                found.append(sec)
    return found


def extract_law_tags(text: str) -> List[str]:
    """Statute family tags present in chunk."""
    cl = (text or "").lower()
    tags: List[str] = []
    mapping = (
        ("ipc", r"\b(?:ipc|indian penal code)\b"),
        ("bns", r"\b(?:bns|bharatiya nyaya sanhita)\b"),
        ("crpc", r"\b(?:crpc|cr\.?\s*p\.?c|criminal procedure code)\b"),
        ("bnss", r"\b(?:bnss|bharatiya nagarik suraksha)\b"),
        ("bsa", r"\b(?:bsa|bharatiya sakshya)\b"),
        ("it act", r"\b(?:it act|information technology act)\b"),
        ("evidence act", r"\bevidence act\b"),
    )
    for tag, pat in mapping:
        if re.search(pat, cl):
            tags.append(tag)
    return tags


def split_semantic_legal_chunks(
    text: str,
    *,
    chunk_size: int = 500,
    chunk_overlap: int = 100,
    max_chunk: int = 1200,
) -> List[Tuple[str, int, int]]:
    """
    Prefer section-boundary splits; fall back to paragraph chunks.
    Returns (chunk_text, start_char, end_char).
    """
    text = clean_legal_text(text)
    if not text:
        return []

    if _ARROW_RE.search(text) or re.search(
        r"\b(?:IPC|CrPC|Evidence Act)\b.*\b(?:BNS|BNSS|BSA)\b", text, re.I
    ):
        mapping_chunks = _split_mapping_table_chunks(
            text,
            chunk_size=max(chunk_size, 700),
            chunk_overlap=max(chunk_overlap, 150),
            max_chunk=max_chunk,
        )
        if mapping_chunks:
            return mapping_chunks

    parts = re.split(r"(?=\b(?:Section|IPC|BNS)\s+\d{1,4}[A-Za-z]?\b)", text, flags=re.I)
    sections: List[str] = []
    for part in parts:
        part = part.strip()
        if len(part) < 30:
            continue
        if len(part) <= max_chunk:
            sections.append(part)
        else:
            for piece in _paragraph_chunks(part, chunk_size, chunk_overlap, max_chunk):
                sections.append(piece[0] if isinstance(piece, tuple) else str(piece))

    if not sections:
        for piece in _paragraph_chunks(text, chunk_size, chunk_overlap, max_chunk):
            sections.append(piece[0] if isinstance(piece, tuple) else str(piece))

    out: List[Tuple[str, int, int]] = []
    cursor = 0
    for sec in sections:
        sec = sec.strip()
        if len(sec) < 25:
            continue
        idx = text.find(sec, cursor)
        if idx < 0:
            idx = cursor
        start, end = idx, idx + len(sec)
        out.append((sec, start, end))
        cursor = end
    return out


def _paragraph_chunks(
    text: str, chunk_size: int, chunk_overlap: int, max_chunk: int
) -> List[Tuple[str, int, int]]:
    """Paragraph-aware fallback chunking."""
    paras = [p.strip() for p in re.split(r"\n\n+", text) if p.strip()]
    chunks: List[str] = []
    buf = ""
    for p in paras:
        if len(p) > max_chunk:
            if buf:
                chunks.append(buf.strip())
                buf = ""
            step = max(chunk_size - chunk_overlap, 200)
            for i in range(0, len(p), step):
                chunks.append(p[i : i + chunk_size].strip())
            continue
        candidate = f"{buf}\n\n{p}".strip() if buf else p
        if len(candidate) <= chunk_size:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)

    positions: List[Tuple[str, int, int]] = []
    cursor = 0
    for c in chunks:
        if len(c) < 25:
            continue
        idx = text.find(c, cursor)
        if idx < 0:
            idx = cursor
        positions.append((c, idx, idx + len(c)))
        cursor = idx + len(c)
    return positions


def extract_primary_section_number(text: str) -> str:
    """First prominent section number in chunk (section id only)."""
    m = _SECTION_TITLE_RE.search(text or "")
    if m:
        return m.group(1).lower()
    m = re.search(r"\bSection\s+(\d{1,4}[A-Za-z]?)\b", text or "", re.I)
    return m.group(1).lower() if m else ""


def chunk_matches_target(content: str, target_sections: List[str]) -> bool:
    if not target_sections:
        return True
    primary = extract_primary_section_number(content)
    targets = {s.lower() for s in target_sections}
    if primary and primary in targets:
        return True
    cl = (content or "").lower()
    return any(re.search(rf"\bsection\s*{re.escape(t)}\b", cl) for t in targets)


def extract_section_content(text: str, section: str) -> str:
    """Isolate text for one statute section from a multi-section chunk."""
    body = clean_legal_text(text or "")
    sec = (section or "").lower().strip()
    if not body or not sec:
        return body

    header_patterns = [
        re.compile(
            rf"(?:^|\n)\s*(?:IPC|BNS|Indian Penal Code)\s+Section\s+{re.escape(sec)}\b[^\n]*",
            re.I,
        ),
        re.compile(rf"(?:^|\n)\s*Section\s+{re.escape(sec)}\b[^\n]*", re.I),
        re.compile(rf"(?:^|\n)\s*IPC\s+{re.escape(sec)}\b[^\n]*", re.I),
    ]
    next_section = re.compile(
        r"(?:^|\n)\s*(?:IPC|BNS|Indian Penal Code)\s+Section\s+\d{1,4}[a-z]?\b",
        re.I,
    )
    next_section_plain = re.compile(r"(?:^|\n)\s*Section\s+\d{1,4}[a-z]?\b", re.I)
    topic_boundary = re.compile(
        r"(?:^|\n)\s*(?:Five Constitutional Rights|Fundamental Rights|"
        r"Case\s+\d+|Suggested\s+KB|Compare\s+IPC)\b",
        re.I,
    )

    start = -1
    for pat in header_patterns:
        m = pat.search(body)
        if m:
            start = m.start()
            break
    if start < 0:
        m = re.search(rf"\b(?:section|ipc)\s+{re.escape(sec)}\b", body, re.I)
        if m:
            start = max(0, m.start() - 40)
        else:
            return ""

    tail = body[start:]
    end = len(tail)
    for pat in (next_section, next_section_plain):
        m = pat.search(tail, pos=20)
        if m:
            end = min(end, m.start())
    m_topic = topic_boundary.search(tail, pos=15)
    if m_topic:
        end = min(end, m_topic.start())
    block = tail[:end].strip()
    if block and re.search(rf"\b{re.escape(sec)}\b", block, re.I):
        return block
    return ""


def filter_chunks_for_section(
    chunks: List[Dict[str, Any]],
    section: str,
    law: str = "",
) -> List[Dict[str, Any]]:
    """Keep only chunks (or isolated section text) for the requested section."""
    from kb_retrieval import section_in_chunk

    if not section or not chunks:
        return chunks
    law_l = (law or "").strip().lower()
    if law_l == "bns":
        bns_hits: List[Dict[str, Any]] = []
        for ch in chunks:
            body = ch.get("content") or ""
            if re.search(
                rf"\bbns\s*(?:section\s*)?{re.escape(section)}\b",
                body,
                re.I,
            ):
                isolated = extract_section_content(body, section)
                bns_hits.append({**ch, "content": isolated or body})
        if bns_hits:
            return bns_hits
    if law_l == "ipc":
        ipc_hits: List[Dict[str, Any]] = []
        for ch in chunks:
            body = ch.get("content") or ""
            if re.search(
                rf"\b(?:ipc|indian penal code)\s*(?:section\s*)?{re.escape(section)}\b",
                body,
                re.I,
            ) and not re.search(rf"\bbns\s*(?:section\s*)?{re.escape(section)}\b", body, re.I):
                isolated = extract_section_content(body, section)
                ipc_hits.append({**ch, "content": isolated or body})
        if ipc_hits:
            return ipc_hits
    scoped: List[Dict[str, Any]] = []
    for ch in chunks:
        body = ch.get("content") or ""
        if not section_in_chunk(body, section):
            continue
        isolated = extract_section_content(body, section)
        if isolated:
            scoped.append({**ch, "content": isolated})
        elif section_in_chunk(body, section):
            scoped.append(ch)
    return scoped


def is_intro_or_generic_chunk(content: str) -> bool:
    cl = (content or "").lower()
    if len(cl) < 80:
        return False
    try:
        from kb_legal_query_rewrite import is_law_mapping_chunk

        if is_law_mapping_chunk(content):
            return False
    except Exception:
        if _ARROW_RE.search(content or "") and _MAPPING_ROW_RE.search(content or ""):
            return False
    intro_markers = (
        "primary criminal code",
        "general principles",
        "introduction to",
        "overview of",
        "this document provides",
        "legal knowledge base",
        "[page ",
    )
    section_hits = len(re.findall(r"\bsection\s+\d{1,4}", cl))
    if any(m in cl for m in intro_markers) and section_hits <= 1:
        return True
    if (
        cl.count("section") == 0
        and "ipc" in cl
        and len(cl) > 400
        and not _ARROW_RE.search(content or "")
    ):
        return True
    return False
