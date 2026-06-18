"""
KB request classifier — depth and structure for Knowledge Base synthesis.

Mirrors open-law depth routing but grounded in uploaded documents only.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

DEPTH_QUICK = "quick"
DEPTH_STANDARD = "standard"
DEPTH_DETAILED = "detailed"
DEPTH_COMPARISON = "comparison"

STRUCTURE_SECTIONS = "sections"
STRUCTURE_BULLETS = "bullets"
STRUCTURE_NARRATIVE = "narrative"
STRUCTURE_MIXED = "mixed"

_KB_WORD_HINTS = {
    DEPTH_QUICK: 180,
    DEPTH_STANDARD: 420,
    DEPTH_DETAILED: 720,
    DEPTH_COMPARISON: 560,
}


def classify_kb_request(
    query: str,
    *,
    user_prefs: Optional[Dict[str, Any]] = None,
    follow_up_intent: str = "",
) -> Dict[str, Any]:
    """Classify KB turn depth, structure, and synthesis hints."""
    q = (query or "").strip()
    ql = q.lower()
    words = len(q.split())
    prefs = user_prefs or {}

    if follow_up_intent in ("deepen", "elaborate", "detail"):
        depth = DEPTH_DETAILED
    elif follow_up_intent in ("compare", "contrast"):
        depth = DEPTH_COMPARISON
    elif follow_up_intent in ("clarify", "next_element"):
        depth = DEPTH_STANDARD
    elif re.search(r"\b(compare|comparison|difference|versus|vs\.?|between)\b", ql):
        depth = DEPTH_COMPARISON
    elif re.search(
        r"\b(in detail|detailed|explain fully|comprehensive|elaborate|deep dive|"
        r"thorough|full analysis|expand on|all elements|ingredients)\b",
        ql,
    ):
        depth = DEPTH_DETAILED
    elif (
        words <= 8
        and re.search(r"\b(what is|who is|define|meaning of|section)\b", ql)
        and not re.search(r"\b(explain|analyze|discuss)\b", ql)
    ):
        depth = DEPTH_QUICK
    else:
        depth = str(prefs.get("depth") or DEPTH_STANDARD)

    if depth not in _KB_WORD_HINTS:
        depth = DEPTH_STANDARD

    if re.search(r"\b(bullet|point wise|points|list)\b", ql):
        structure = STRUCTURE_BULLETS
    elif re.search(r"\b(paragraph|narrative|essay|story)\b", ql):
        structure = STRUCTURE_NARRATIVE
    elif float(prefs.get("prefer_bullets", 0.5)) >= 0.7:
        structure = STRUCTURE_BULLETS
    elif float(prefs.get("prefer_headings", 0.5)) >= 0.7:
        structure = STRUCTURE_SECTIONS
    else:
        structure = str(prefs.get("structure") or STRUCTURE_SECTIONS)

    citation = str(prefs.get("citation_style") or "inline")
    needs_citations = bool(
        re.search(r"\b(cite|citation|reference|section|article|provision)\b", ql)
        or depth in (DEPTH_DETAILED, DEPTH_COMPARISON)
    )

    return {
        "depth": depth,
        "structure": structure,
        "citation_style": citation,
        "needs_citations": needs_citations,
        "word_hint": _KB_WORD_HINTS.get(depth, 420),
        "follow_up_intent": follow_up_intent or "none",
    }


def kb_depth_instructions(classification: Dict[str, Any]) -> str:
    """Synthesis instruction block from classification."""
    depth = classification.get("depth", DEPTH_STANDARD)
    structure = classification.get("structure", STRUCTURE_SECTIONS)
    parts = [f"Respond at {depth} depth using uploaded documents only."]
    if structure == STRUCTURE_BULLETS:
        parts.append("Use bullet points for lists and elements.")
    elif structure == STRUCTURE_SECTIONS:
        parts.append("Use clear section headings.")
    elif structure == STRUCTURE_NARRATIVE:
        parts.append("Use flowing paragraphs with minimal headings.")
    if classification.get("needs_citations"):
        parts.append("Cite document sections or chunk references inline.")
    cap = int(classification.get("word_hint") or 420)
    parts.append(f"Target roughly {cap} words unless documents are thin.")
    return " ".join(parts)
