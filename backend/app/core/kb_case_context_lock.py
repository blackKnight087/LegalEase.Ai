"""Query-centric chunk locking — prevent cross-case / cross-topic contamination in KB."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_CASE_HEADER_RE = re.compile(r"(?m)^Case\s+(\d+)\s*:\s*(.+)$", re.I)
_CONTEXT_SUFFIX_RE = re.compile(r"\s*\(context:.*$", re.I)


def strip_query_context_suffix(query: str) -> str:
    """Remove chat-appended '(context: …)' tails that pollute case needle extraction."""
    q = (query or "").strip()
    q = _CONTEXT_SUFFIX_RE.sub("", q).strip()
    q = re.sub(r"\s*\(regarding the case:.*$", "", q, flags=re.I).strip()
    return q


def normalize_case_query(query: str) -> str:
    """Strip context tails and trailing explain/describe for party extraction."""
    q = strip_query_context_suffix(query)
    q = re.sub(
        r"\s+(?:explain|describe|summarize|details?|briefly|brief)\s*$",
        "",
        q,
        flags=re.I,
    ).strip()
    return q


def is_case_locked_query(query: str) -> bool:
    q = strip_query_context_suffix(query)
    try:
        from backend.app.core.kb_landmark_case import is_landmark_case_query

        if is_landmark_case_query(q):
            return True
    except ImportError:
        pass
    try:
        from backend.app.core.case_entity_resolver import is_case_style_query

        return is_case_style_query(q)
    except ImportError:
        return bool(re.search(r"\bvs\.?\b", query or "", re.I))


def pin_party_matched_chunks(
    query: str,
    raw_chunks: List[Dict[str, Any]],
    scoped_chunks: List[Dict[str, Any]],
    *,
    min_score: float = 0.85,
) -> List[Dict[str, Any]]:
    """Re-merge party-matched hits dropped by scope filtering."""
    try:
        from backend.app.core.case_entity_resolver import (
            chunk_matches_case,
            extract_case_needles,
        )
    except ImportError:
        return scoped_chunks or raw_chunks

    needles = extract_case_needles(normalize_case_query(query))
    if not needles:
        return scoped_chunks or raw_chunks

    out = list(scoped_chunks or [])
    seen = {(c.get("content") or "")[:80] for c in out}
    for ch in raw_chunks or []:
        key = (ch.get("content") or "")[:80]
        if not key or key in seen:
            continue
        if _chunk_score(ch) >= min_score and chunk_matches_case(ch, needles):
            out.insert(0, ch)
            seen.add(key)
    out.sort(
        key=lambda c: -float(
            c.get("final_score") or c.get("hybrid_score") or c.get("score") or 0
        )
    )
    return out[:12]


def _chunk_score(c: Dict[str, Any]) -> float:
    return float(
        c.get("final_score") or c.get("hybrid_score") or c.get("score") or 0.0
    )


def lock_chunks_to_query(
    query: str,
    chunks: List[Dict[str, Any]],
    *,
    index_dir: Any = None,
    max_chunks: int = 6,
) -> List[Dict[str, Any]]:
    """
    Keep only chunks belonging to the dominant case/topic for this query.
    """
    clean_q = normalize_case_query(query)
    if not chunks:
        return []

    # region agent log
    try:
        from backend.app.core.debug_session_log import debug_log

        previews = []
        for c in chunks[:8]:
            previews.append(
                {
                    "file": str((c.get("metadata") or {}).get("filename", ""))[:50],
                    "excerpt": (c.get("content") or "")[:90],
                }
            )
        debug_log(
            "H1",
            "kb_case_context_lock.py:lock_chunks_to_query",
            "chunks_before_lock",
            {"query": clean_q[:100], "count": len(chunks), "previews": previews},
        )
    except Exception:
        pass
    # endregion

    if not is_case_locked_query(clean_q):
        return chunks[:max_chunks]

    try:
        from backend.app.core.case_entity_resolver import (
            chunk_matches_case,
            extract_case_needles,
        )
        from backend.app.core.case_narrative_engine import filter_case_chunks

        needles = extract_case_needles(clean_q)
        if not needles:
            return chunks[:max_chunks]

        filtered = filter_case_chunks(chunks, needles)
        strict = [c for c in filtered if chunk_matches_case(c, needles)]

        if strict:
            locked = strict[:max_chunks]
        elif filtered:
            locked = filtered[:max_chunks]
        else:
            locked = _segment_lock_from_combined(clean_q, chunks, needles, max_chunks=max_chunks)

        if not locked and index_dir is not None:
            try:
                from backend.app.core.case_docstore_lookup import lookup_case_chunks_by_query

                rescued = lookup_case_chunks_by_query(
                    index_dir, clean_q, top_k=max_chunks
                )
                if rescued:
                    locked = rescued
                    try:
                        from backend.app.core.debug_session_log import debug_log

                        debug_log(
                            "LOCK_RESCUE",
                            "kb_case_context_lock.py:lock_chunks_to_query",
                            "docstore_rescue",
                            {"query": clean_q[:80], "count": len(rescued)},
                        )
                    except Exception:
                        pass
            except ImportError:
                pass

        if not locked and chunks:
            top = max(chunks, key=_chunk_score)
            if _chunk_score(top) >= 0.50:
                locked = [top]

        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "H2",
                "kb_case_context_lock.py:lock_chunks_to_query",
                "chunks_after_lock",
                {
                    "query": clean_q[:100],
                    "needles": needles[:6],
                    "in_count": len(chunks),
                    "out_count": len(locked),
                    "previews": [
                        (c.get("content") or "")[:100] for c in locked[:4]
                    ],
                },
            )
        except Exception:
            pass
        # endregion
        return locked
    except ImportError:
        return chunks[:max_chunks]


def _segment_lock_from_combined(
    query: str,
    chunks: List[Dict[str, Any]],
    needles: List[str],
    *,
    max_chunks: int,
) -> List[Dict[str, Any]]:
    """Split mega-chunks by 'Case N:' headers and return one synthetic chunk for target case."""
    from backend.app.core.case_entity_resolver import segment_matches_case_needles

    combined = "\n\n".join((c.get("content") or "") for c in chunks[:4])
    if not combined.strip():
        return []

    segments: List[str] = []
    current: List[str] = []
    for line in combined.splitlines():
        if _CASE_HEADER_RE.match(line.strip()) and current:
            segments.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        segments.append("\n".join(current).strip())

    matched = [s for s in segments if segment_matches_case_needles(s, needles)]
    if not matched:
        return []

    meta = dict((chunks[0].get("metadata") or {}))
    synthetic = {
        "content": matched[0],
        "metadata": meta,
        "final_score": 3.0,
        "retrieval_mode": "case_segment_lock",
    }
    return [synthetic][:max_chunks]
