"""
Pre/post-generation claim audit — uploaded documents are the only source of truth.

For each factual sentence: keep only if traceable to retrieved chunks.
Statute "explain" queries without a definition in excerpts → mention-only response.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

_MENTION_ONLY_RE = re.compile(
    r"\b(?:charged\s+under|proceedings\s+under|applies?\s+under|"
    r"invoked|mentioned|reference\s+to|under\s+section)\b",
    re.I,
)
_DEFINITION_NEAR_SECTION_RE = re.compile(
    r"(?:"
    r"meaning\s*[:—–-]|definition\s*[:—–-]|whoever\b|shall\s+be\s+punished|"
    r"punishment\s+for|ingredients?\s+of|is\s+defined\s+as|"
    r"constitutes|offence\s+of|offense\s+of|shall\s+be\s+liable"
    r")",
    re.I,
)
_SECTION_HEADER_DEF_RE = re.compile(
    r"\b(?:IPC|BNS|CrPC|section)\s+(\d{1,4}[a-z]?)\s*[—–\-:]\s*(?:meaning|definition|)",
    re.I,
)
_EXPLAIN_SECTION_RE = re.compile(
    r"\b(?:explain|define|what\s+(?:is|does)|meaning\s+of|tell\s+me\s+about)\b",
    re.I,
)
_SECTION_REF_RE = re.compile(
    r"\b(?:section|ipc|bns|crpc|article)\s+(\d{1,4}[a-z]?)\b",
    re.I,
)
_LEGAL_DEF_LEAK_RE = re.compile(
    r"\b(?:whoever|shall\s+be\s+punished|imprisonment\s+(?:for|up\s+to)|"
    r"offence\s+of\s+theft|offense\s+of\s+theft|dishonest\s+intention|"
    r"moves\s+that\s+property|ingredients?\s+(?:of|for)\s+theft)\b",
    re.I,
)

_STOPWORDS = frozenset(
    {
        "section", "indian", "penal", "punishment", "offence", "offense",
        "document", "uploaded", "states", "mentioned", "according", "based",
        "explain", "theft", "under", "charged", "accused", "case",
    }
)


def extract_query_sections(query: str) -> List[str]:
    secs: List[str] = []
    for m in _SECTION_REF_RE.finditer(query or ""):
        s = m.group(1).lower()
        if s not in secs:
            secs.append(s)
    try:
        from kb_rag_decision import extract_query_sections as _ext

        for s in _ext(query or ""):
            sl = str(s).lower()
            if sl and sl not in secs:
                secs.append(sl)
    except Exception:
        pass
    return secs


def is_statute_explanation_query(query: str) -> bool:
    q = (query or "").strip()
    if not q:
        return False
    if not _EXPLAIN_SECTION_RE.search(q):
        return False
    if extract_query_sections(q):
        return True
    if re.search(r"\b(?:ipc|bns|section|article)\s+\d", q, re.I):
        return True
    if re.search(r"\btheft\b.*\b(?:ipc|379)\b", q, re.I):
        return True
    if re.search(r"\b(?:ipc|379)\b.*\btheft\b", q, re.I):
        return True
    return False


def _section_context_windows(text: str, section: str, *, window: int = 420) -> List[str]:
    """Slices of text around each mention of the section number."""
    body = text or ""
    sec = section.lower()
    windows: List[str] = []
    for m in re.finditer(
        rf"\b(?:section\s*{re.escape(sec)}|ipc\s*{re.escape(sec)}|bns\s*{re.escape(sec)})\b",
        body,
        re.I,
    ):
        start = max(0, m.start() - window // 2)
        end = min(len(body), m.end() + window // 2)
        windows.append(body[start:end])
    if not windows and re.search(rf"\b{re.escape(sec)}\b", body, re.I):
        for m in re.finditer(rf"\b{re.escape(sec)}\b", body, re.I):
            start = max(0, m.start() - window // 2)
            end = min(len(body), m.end() + window // 2)
            windows.append(body[start:end])
    return windows


def chunk_defines_section(chunks: Sequence[Dict[str, Any]], section: str) -> bool:
    """True when excerpts contain a legal definition/explanation of the section, not only a mention."""
    if not chunks or not section:
        return False
    combined = "\n".join((c.get("content") or "") for c in chunks)
    if _SECTION_HEADER_DEF_RE.search(combined):
        for m in _SECTION_HEADER_DEF_RE.finditer(combined):
            if m.group(1).lower() == section.lower():
                return True
    for win in _section_context_windows(combined, section):
        wl = win.lower()
        if _DEFINITION_NEAR_SECTION_RE.search(win):
            if not _is_mention_only_window(wl, section):
                return True
        if re.search(
            rf"\b(?:IPC|BNS)\s+Section\s+{re.escape(section)}\b",
            win,
            re.I,
        ) and re.search(r"[—–\-:]\s*\w{8,}", win):
            return True
    return False


def _is_mention_only_window(window_lower: str, section: str) -> bool:
    """Mention-only: charged under / case title parenthetical without definitional prose."""
    if _DEFINITION_NEAR_SECTION_RE.search(window_lower):
        return False
    if _MENTION_ONLY_RE.search(window_lower):
        return True
    if re.search(rf"\(\s*[^)]*ipc\s*{re.escape(section)}", window_lower):
        return True
    if re.search(rf"charged\s+under[^.{{0,80}}]*{re.escape(section)}", window_lower):
        return True
    return len(window_lower) < 120


def chunks_define_any_section(
    chunks: Sequence[Dict[str, Any]], sections: Sequence[str]
) -> bool:
    return any(chunk_defines_section(chunks, s) for s in sections)


def build_statute_mention_only_answer(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    sections: Optional[Sequence[str]] = None,
) -> str:
    """Safe response when the document names a section but does not define it."""
    secs = list(sections or extract_query_sections(query))
    if not secs and chunks:
        combined = "\n".join((c.get("content") or "") for c in chunks[:6])
        for m in re.finditer(r"\bIPC\s+(\d{3})\b", combined, re.I):
            s = m.group(1).lower()
            if s not in secs:
                secs.append(s)
    if not secs:
        return ""

    combined = "\n".join((c.get("content") or "") for c in chunks[:8])
    mentions: List[str] = []
    for sec in secs[:3]:
        if re.search(
            rf"\b(?:section\s*{re.escape(sec)}|ipc\s*{re.escape(sec)})\b",
            combined,
            re.I,
        ):
            mentions.append(sec.upper())

    if not mentions:
        return ""

    if len(mentions) == 1:
        sec_u = mentions[0]
        body = (
            f"The uploaded document mentions that IPC {sec_u} was applied or referenced "
            f"in the case material. The document does not contain the legal definition, "
            f"ingredients, or punishment text of IPC {sec_u}."
        )
    else:
        joined = ", ".join(f"IPC {s}" for s in mentions[:-1])
        if len(mentions) > 1:
            joined = f"{joined}, and IPC {mentions[-1]}"
        else:
            joined = f"IPC {mentions[0]}"
        body = (
            f"The uploaded document mentions {joined} but does not contain the full "
            f"legal definitions or statutory text for those provisions."
        )

    try:
        from backend.app.core.kb_document_first import format_kb_structured_response

        return format_kb_structured_response(body, list(chunks)[:6], confidence=0.88)
    except ImportError:
        return body


def sentence_supported(sentence: str, context_lower: str) -> bool:
    s = (sentence or "").strip()
    if len(s) < 20:
        return True
    words = {w for w in re.findall(r"[a-z]{5,}", s.lower())} - _STOPWORDS
    if not words:
        return True
    hits = sum(1 for w in list(words)[:18] if w in context_lower)
    return hits >= max(2, len(words) // 3)


def audit_and_prune_answer(answer: str, chunks: Sequence[Dict[str, Any]]) -> str:
    """Remove sentences that cannot be traced to retrieved chunks."""
    text = (answer or "").strip()
    if not text or not chunks:
        return text
    ctx = "\n".join((c.get("content") or "")[:1400] for c in chunks[:10]).lower()
    if not ctx.strip():
        return text

    if "## Answer" in text:
        parts = text.split("## Answer", 1)
        head, rest = parts[0], parts[1]
        if "\n\n##" in rest:
            body, tail = rest.split("\n\n##", 1)
            tail = "\n\n##" + tail
        else:
            body, tail = rest, ""
        pruned = _prune_body(body, ctx)
        return f"{head}## Answer\n\n{pruned}{tail}".strip()

    return _prune_body(text, ctx)


def _prune_body(body: str, ctx: str) -> str:
    kept: List[str] = []
    for sent in re.split(r"(?<=[.!?])\s+", body):
        s = sent.strip()
        if not s:
            continue
        if sentence_supported(s, ctx):
            kept.append(s)
    out = " ".join(kept).strip()
    return out if len(out) >= 30 else body


def answer_has_legal_definition_leak(answer: str, chunks: Sequence[Dict[str, Any]]) -> bool:
    """Detect pretrained statute text when excerpts only mention a section."""
    text = answer or ""
    if not text or not _LEGAL_DEF_LEAK_RE.search(text):
        return False
    secs = extract_query_sections(text) or []
    if not secs:
        for m in re.finditer(r"\bIPC\s+(\d{3})\b", text, re.I):
            secs.append(m.group(1).lower())
    if not secs:
        return bool(_LEGAL_DEF_LEAK_RE.search(text) and chunks)
    return not chunks_define_any_section(chunks, secs)


def should_block_llm_for_statute_query(
    query: str, chunks: Sequence[Dict[str, Any]]
) -> Tuple[bool, str]:
    """
    Returns (block, reason). Block Ollama when user asks to explain a section
    that appears in excerpts only as a charge/reference, not as statutory text.
    """
    if not is_statute_explanation_query(query):
        return False, ""
    secs = extract_query_sections(query)
    if not secs:
        return False, ""
    if chunks_define_any_section(chunks, secs):
        return False, ""
    if not chunks:
        return True, "no_chunks"
    combined = "\n".join((c.get("content") or "") for c in chunks[:8])
    for sec in secs:
        if re.search(
            rf"\b(?:section\s*{re.escape(sec)}|ipc\s*{re.escape(sec)})\b",
            combined,
            re.I,
        ):
            return True, f"mention_only:{sec}"
    return False, ""


def try_statute_safe_answer(
    query: str, chunks: Sequence[Dict[str, Any]]
) -> str:
    """Mention-only answer or empty if not applicable."""
    block, _reason = should_block_llm_for_statute_query(query, chunks)
    if not block:
        return ""
    return build_statute_mention_only_answer(query, chunks)


def grounding_score(answer: str, chunks: Sequence[Dict[str, Any]]) -> float:
    """Fraction of substantive sentences supported by chunk text (0–1)."""
    text = (answer or "").strip()
    if not text or not chunks:
        return 0.0
    ctx = "\n".join((c.get("content") or "") for c in chunks[:10]).lower()
    sentences = [
        s.strip()
        for s in re.split(r"(?<=[.!?])\s+", text)
        if len(s.strip()) > 35
    ]
    if not sentences:
        return 1.0
    supported = sum(1 for s in sentences if sentence_supported(s, ctx))
    return supported / len(sentences)
