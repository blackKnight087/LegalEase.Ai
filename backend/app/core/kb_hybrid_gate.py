"""
Hybrid mode — only use KB when retrieved chunks substantively match the query.

Prevents wrong-document bleed (e.g. RG Kar public case question → Imran Khan upload).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

_GENERIC_LEGAL = frozenset({
    "explain", "describe", "what", "when", "where", "which", "who", "why", "how",
    "case", "court", "judgment", "judgement", "hearing", "fir", "police", "cbi",
    "evidence", "failed", "provide", "more", "about", "under", "the", "and", "for",
    "from", "with", "your", "this", "that", "india", "indian", "law", "legal",
    "section", "ipc", "bns", "state", "versus", "accused", "witness", "complainant",
})

_PUBLIC_CASE_MARKERS = (
    re.compile(r"\brg\s*kar\b", re.I),
    re.compile(r"\br\.g\.\s*kar\b", re.I),
    re.compile(r"\bnirbhaya\b", re.I),
    re.compile(r"\bkesavananda\b", re.I),
    re.compile(r"\bputtaswamy\b", re.I),
    re.compile(r"\bnavtej\b", re.I),
    re.compile(r"\bshayara\b", re.I),
    re.compile(r"\bmaneka\s+gandhi\b", re.I),
)


def _kb_text(kb_answer: str, chunks: List[Dict[str, Any]]) -> str:
    parts = [(kb_answer or "")]
    for c in chunks[:6]:
        parts.append((c.get("content") or "")[:900])
    return " ".join(parts).lower()


def _query_signature_terms(query: str) -> List[str]:
    """Distinctive terms/phrases the KB must reflect."""
    q = (query or "").strip()
    ql = q.lower()
    sigs: List[str] = []

    if re.search(r"\brg\s*kar\b|\br\.g\.\s*kar\b", ql):
        sigs.extend(["rg kar", "rgkar"])

    try:
        from backend.app.core.case_entity_resolver import extract_case_needles, extract_entity_needles

        for n in extract_case_needles(q) + extract_entity_needles(q):
            if n and len(n) >= 4 and n not in sigs:
                sigs.append(n.lower())
    except Exception:
        pass

    # Multi-word proper names (e.g. "rg kar", "priya verma")
    for m in re.finditer(r"\b([a-z]{2,15})\s+([a-z]{2,15})\b", ql):
        a, b = m.group(1), m.group(2)
        if a in _GENERIC_LEGAL or b in _GENERIC_LEGAL:
            continue
        phrase = f"{a} {b}"
        if phrase not in sigs:
            sigs.append(phrase)

    for w in re.findall(r"\b[a-z0-9]{4,}\b", ql):
        if w not in _GENERIC_LEGAL and w not in sigs:
            sigs.append(w)

    return list(dict.fromkeys(sigs))[:12]


def _signature_satisfied(query: str, kb_text: str) -> bool:
    ql = (query or "").lower()
    if re.search(r"\brg\s*kar\b|\br\.g\.\s*kar\b", ql):
        if re.search(r"\brg\s*kar\b|\br\.g\.\s*kar\b|rgkar|rg\s+kar\s+medical", kb_text, re.I):
            return True
        return False
    return True


def _is_public_case_query(query: str) -> bool:
    return any(p.search(query or "") for p in _PUBLIC_CASE_MARKERS)


def should_skip_kb_retrieval(query: str) -> bool:
    """Skip KB search for public-case questions unless the user cites their upload."""
    if not __import__("os").getenv("HYBRID_SKIP_KB_PREFETCH_PUBLIC", "1").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return False
    ql = (query or "").lower()
    if re.search(
        r"\b(?:my document|uploaded|from my (?:file|pdf|document)|in the (?:pdf|document)|"
        r"according to (?:the )?upload)\b",
        ql,
    ):
        return False
    return _is_public_case_query(query)


def assess_kb_for_hybrid(
    query: str,
    kb_answer: str,
    chunks: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """
    Return (use_kb, reason). When False, Hybrid must not cite uploaded documents.
    """
    if not chunks:
        return False, "no_chunks"

    body = (kb_answer or "").strip()
    if not body or body.startswith("NOT_FOUND") or "couldn't find" in body.lower():
        return False, "kb_not_found"

    if "knowledge base empty" in body.lower():
        return False, "kb_empty"

    kb_text = _kb_text(body, chunks)

    try:
        from kb_rag_decision import evaluate_retrieval

        found, score, decision, _ = evaluate_retrieval(query, chunks)
        if not found:
            return False, f"retrieval_{decision}"
        min_score = float(__import__("os").getenv("HYBRID_KB_MIN_SCORE", "0.32"))
        if score < min_score:
            return False, f"low_score_{score:.2f}"
    except Exception as exc:
        logger.debug("hybrid evaluate_retrieval: %s", exc)

    try:
        from backend.app.core.universal_kb import chunks_overlap_query

        ratio = float(__import__("os").getenv("HYBRID_KB_TERM_RATIO", "0.4"))
        if not chunks_overlap_query(query, chunks, min_ratio=ratio):
            return False, "term_overlap"
    except Exception:
        pass

    if not _signature_satisfied(query, kb_text):
        return False, "signature_mismatch"

    sigs = _query_signature_terms(query)
    distinctive = [s for s in sigs if s not in _GENERIC_LEGAL and len(s) >= 3]
    if distinctive:
        hits = 0
        for s in distinctive:
            if s in kb_text:
                hits += 1
            elif " " in s:
                a, b = s.split(" ", 1)
                if a in kb_text and b in kb_text:
                    hits += 1
        need = 1 if len(distinctive) <= 2 else max(1, (len(distinctive) + 1) // 2)
        if hits < need:
            return False, "entity_miss"

    if _is_public_case_query(query):
        if not any(p.search(kb_text) for p in _PUBLIC_CASE_MARKERS):
            return False, "public_case_not_in_kb"

    try:
        from backend.app.core.case_entity_resolver import extract_case_needles

        needles = extract_case_needles(query)
        if needles:
            from backend.app.core.case_entity_resolver import chunk_matches_case

            if not any(chunk_matches_case(c, needles) for c in chunks[:8]):
                return False, "case_needle_miss"
    except Exception:
        pass

    return True, "ok"
