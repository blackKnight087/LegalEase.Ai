"""
Multi-section and comparison-aware retrieval helpers for LegalEase KB.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple, Union

from conversation_context import extract_sections_from_text

_COMPARE_RE = re.compile(
    r"\b(difference|compare|comparison|distinction|between|differ)\b",
    re.I,
)
_SECTION_NUM_RE = re.compile(r"\b(\d{1,4}[a-z]?)\b", re.I)


def is_comparison_query(query: str) -> bool:
    q = query or ""
    if not _COMPARE_RE.search(q):
        return False
    try:
        from backend.app.core.case_entity_resolver import is_case_style_query

        if is_case_style_query(q) and not re.search(
            r"\b(?:compare|comparison|difference|differences|distinguish|between)\b",
            q,
            re.I,
        ):
            return False
    except ImportError:
        if re.search(r"\b\w+\s+vs\.?\s+\w+", q, re.I) and not re.search(
            r"\b(?:compare|comparison|difference|distinguish|between)\b", q, re.I
        ):
            return False
    return True


def extract_comparison_sections(query: str) -> List[str]:
    """
    Extract all section numbers for comparison queries.
    e.g. 'Difference between IPC 299 and 300' -> ['299', '300']
    """
    q = (query or "").strip()
    found: List[str] = []
    seen = set()

    for s in extract_sections_from_text(q):
        sl = s.lower()
        if sl not in seen:
            seen.add(sl)
            found.append(sl)

    if not is_comparison_query(q):
        return found

    pair = re.search(
        r"\b(\d{1,4}[a-z]?)\s*(?:vs\.?|versus)\s*(\d{1,4}[a-z]?)\b",
        q,
        re.I,
    )
    if pair:
        for g in (pair.group(1), pair.group(2)):
            sl = g.lower()
            if sl not in seen:
                seen.add(sl)
                found.append(sl)

    # Bare numbers after and / vs / between (e.g. '299 and 300')
    for m in re.finditer(
        r"\b(?:and|or|vs\.?|versus|,|between)\s*(\d{1,4}[a-z]?)\b",
        q,
        re.I,
    ):
        sl = m.group(1).lower()
        if sl not in seen:
            seen.add(sl)
            found.append(sl)

    if is_comparison_query(q):
        for m in _SECTION_NUM_RE.finditer(q):
            sl = m.group(1).lower()
            if sl in seen:
                continue
            if sl.isdigit() and 1 <= int(sl) <= 599:
                seen.add(sl)
                found.append(sl)

    return found[:6]


def section_in_chunk(content: str, section: str) -> bool:
    cl = (content or "").lower()
    sec = section.lower()
    if re.search(rf"\bsection\s*{re.escape(sec)}\b", cl):
        return True
    if re.search(rf"\b(?:ipc|bns)\s*{re.escape(sec)}\b", cl):
        return True
    if re.search(rf"\bsection\s*{re.escape(sec)}\b", cl, re.I):
        return True
    return bool(re.search(rf"(?<![0-9]){re.escape(sec)}(?![0-9])", cl))


def ensure_per_section_chunks(
    ranked: List[Dict[str, Any]],
    sections: List[str],
    max_total: int = 6,
) -> List[Dict[str, Any]]:
    """Guarantee at least one chunk per requested section."""
    if not sections or len(sections) < 2:
        return ranked[:max_total]

    chosen: List[Dict[str, Any]] = []
    seen_ids = set()

    for sec in sections:
        best = None
        best_score = -1.0
        for item in ranked:
            cid = id(item)
            content = str(item.get("content", ""))
            if not section_in_chunk(content, sec):
                continue
            score = float(item.get("final_score", item.get("hybrid_score", 0)))
            if score > best_score:
                best_score = score
                best = item
        if best is not None and id(best) not in seen_ids:
            chosen.append(best)
            seen_ids.add(id(best))

    for item in ranked:
        if len(chosen) >= max_total:
            break
        if id(item) not in seen_ids:
            chosen.append(item)
            seen_ids.add(id(item))

    return chosen[:max_total]


def retrieve_chunks_per_entity(
    index_dir: Any,
    entities: List[str],
    base_query: str = "",
    *,
    k_per_entity: int = 5,
    max_total: int = 12,
) -> List[Dict[str, Any]]:
    """
    Multi-entity retrieval: one search per section, merge guaranteed per-entity hits.
    """
    from pathlib import Path
    from typing import Union

    from rag import query_kb

    if not entities:
        return []

    law = "IPC"
    if re.search(r"\bbns\b", base_query, re.I):
        law = "BNS"

    pool: List[Dict[str, Any]] = []
    for sec in entities[:6]:
        sub_q = f"{law} Section {sec} {base_query}".strip()
        try:
            hits = query_kb(sub_q, k=k_per_entity, index_dir=index_dir)
        except Exception:
            hits = []
        for h in hits:
            if section_in_chunk(h.get("content", ""), sec):
                h = dict(h)
                h["entity"] = sec
                h["final_score"] = float(h.get("final_score", 0.5)) + 0.2
                pool.append(h)

    if len(entities) >= 2:
        pool = ensure_per_section_chunks(pool, entities, max_total=max_total)
    else:
        pool = pool[:max_total]
    return pool


def build_section_retrieval_queries(sections: List[str], base_query: str) -> List[str]:
    """Per-section sub-queries for comparison retrieval."""
    law = "IPC"
    if re.search(r"\bbns\b", base_query, re.I):
        law = "BNS"
    queries = [base_query]
    for sec in sections:
        queries.extend([
            f"{law} Section {sec}",
            f"Section {sec} {law}",
            f"Section {sec.upper()}",
        ])
    return list(dict.fromkeys(queries))
