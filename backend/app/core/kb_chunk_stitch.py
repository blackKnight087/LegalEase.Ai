"""
Stitch retrieved KB chunks across page breaks.

When lists or sections span multiple PDF pages, vector search often returns only
the first chunk. This module loads adjacent chunks from the same document (by
chunk_index and page) and merges them before answer extraction.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_PAGE_RE = re.compile(r"\[\s*Page\s+(\d+)\s*\]", re.I)
_RIGHT_ITEM_RE = re.compile(
    r"(?:^|\n)\s*(\d+)\.\s*(Right\s+(?:to|against)\s+[^,\n(]+?\(\s*Article\s+\d{1,3}\s*\))",
    re.I | re.M,
)
_RIGHT_INLINE_RE = re.compile(
    r"Right\s+(?:to|against)\s+[^,(\n]+?\(\s*Article\s+\d{1,3}\s*\)",
    re.I,
)
_LIST_HEADING_RE = re.compile(
    r"\b(?:Five Constitutional Rights|Fundamental Rights)\b",
    re.I,
)
_CONTINUATION_MARKERS = (
    "five constitutional rights",
    "fundamental rights",
    "right to ",
    "right against ",
    "article 25",
    "article 32",
    "sample nda",
    "parties involved",
)


def _meta_filename(meta: Dict[str, Any]) -> str:
    return str(meta.get("filename") or meta.get("source_file") or "").strip()


def _meta_chunk_index(meta: Dict[str, Any]) -> int:
    raw = meta.get("chunk_index")
    if raw is None or raw == "":
        return -1
    try:
        return int(raw)
    except (TypeError, ValueError):
        return -1


def _meta_page(meta: Dict[str, Any], content: str = "") -> int:
    for key in ("page_number", "page"):
        raw = meta.get(key)
        if raw not in (None, ""):
            try:
                return int(str(raw).split("-")[0])
            except ValueError:
                pass
    m = _PAGE_RE.search(content or "")
    return int(m.group(1)) if m else 0


def _chunk_key(ch: Dict[str, Any]) -> Tuple[str, str]:
    meta = ch.get("metadata") or {}
    content = (ch.get("content") or "")[:96]
    return (_meta_filename(meta), content)


def count_numbered_rights(text: str) -> int:
    """Highest numbered 'N. Right … (Article X)' entry in text."""
    nums = [int(m.group(1)) for m in _RIGHT_ITEM_RE.finditer(text or "")]
    if nums:
        return max(nums)
    return len(_RIGHT_INLINE_RE.findall(text or ""))


def rights_list_truncated(text: str, query: str = "") -> bool:
    """True when a five-rights list clearly stops before item 5."""
    body = text or ""
    ql = (query or "").lower()
    if not _LIST_HEADING_RE.search(body):
        return False
    want = 5 if re.search(r"\b(?:five|5)\b", ql) and "right" in ql else 0
    if not want:
        want = 5 if re.search(r"\bfive\s+constitutional\s+rights\b", ql) else 0
    if not want:
        return False
    found = count_numbered_rights(body)
    if found >= want:
        return False
    if found >= 1 and found < want:
        return True
  # List heading present but no numbered items — likely split mid-heading
    if _LIST_HEADING_RE.search(body) and found == 0 and len(body) > 40:
        return True
    return False


def content_suggests_continuation(text: str) -> bool:
    """Chunk may continue a list/section started on a previous page."""
    t = (text or "").lower()
    if re.match(r"^\s*\d+\.\s*right\b", t):
        return True
    if re.match(r"^\s*\d+\.\s", t) and "article" in t[:120]:
        return True
    return any(m in t for m in _CONTINUATION_MARKERS)


def _load_docstore_chunks(index_dir: Any) -> List[Dict[str, Any]]:
    """All chunks from FAISS docstore pickle."""
    if not index_dir:
        return []
    try:
        from rag import _load_docstore_only

        view = _load_docstore_only(Path(index_dir))
        if not view:
            return []
        store = getattr(view, "docstore", None)
        doc_dict = getattr(store, "_dict", None) or {}
    except Exception:
        return []

    out: List[Dict[str, Any]] = []
    for doc in doc_dict.values():
        content = (getattr(doc, "page_content", None) or "").strip()
        if not content:
            continue
        meta = dict(getattr(doc, "metadata", None) or {})
        out.append(
            {
                "content": content,
                "metadata": meta,
                "final_score": 0.5,
                "hybrid_score": 0.5,
                "retrieval_mode": "docstore_stitch",
            }
        )
    return out


def fetch_chunks_for_file(
    index_dir: Any,
    filename: str,
    *,
    chunk_indices: Optional[Set[int]] = None,
    page_numbers: Optional[Set[int]] = None,
) -> List[Dict[str, Any]]:
    """Load chunks from one file, optionally filtered by index or page."""
    if not filename:
        return []
    fn_lower = filename.lower()
    hits: List[Dict[str, Any]] = []
    for ch in _load_docstore_chunks(index_dir):
        meta = ch.get("metadata") or {}
        ch_fn = _meta_filename(meta).lower()
        if ch_fn != fn_lower and fn_lower not in ch_fn and ch_fn not in fn_lower:
            continue
        idx = _meta_chunk_index(meta)
        page = _meta_page(meta, ch.get("content") or "")
        by_index = chunk_indices is None or (idx >= 0 and idx in chunk_indices)
        by_page = page_numbers is None or (page > 0 and page in page_numbers)
        if chunk_indices is not None or page_numbers is not None:
            if not (by_index or by_page):
                continue
        hits.append(ch)
    hits.sort(
        key=lambda c: (
            _meta_chunk_index(c.get("metadata") or {}),
            _meta_page(c.get("metadata") or {}, c.get("content") or ""),
        )
    )
    return hits


def fetch_neighbor_chunks(
    index_dir: Any,
    seed: Dict[str, Any],
    *,
    window: int = 2,
) -> List[Dict[str, Any]]:
    """±window chunks by chunk_index and adjacent pages from the same file."""
    meta = seed.get("metadata") or {}
    filename = _meta_filename(meta)
    if not filename or not index_dir:
        return [seed]

    center_idx = _meta_chunk_index(meta)
    center_page = _meta_page(meta, seed.get("content") or "")

    indices: Set[int] = set()
    pages: Set[int] = set()
    if center_idx >= 0:
        for d in range(-window, window + 1):
            indices.add(center_idx + d)
    if center_page > 0:
        for d in range(-1, 2):
            if center_page + d > 0:
                pages.add(center_page + d)

    neighbors = fetch_chunks_for_file(
        index_dir,
        filename,
        chunk_indices=indices if indices else None,
        page_numbers=pages if pages else None,
    )
    if not neighbors:
        return [seed]

    out: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()
    for ch in neighbors:
        key = _chunk_key(ch)
        if key in seen:
            continue
        seen.add(key)
        out.append(ch)
    if not any(_chunk_key(c) == _chunk_key(seed) for c in out):
        out.insert(0, seed)
    return out


def fetch_continuation_chunks(
    index_dir: Any,
    seed_chunks: Sequence[Dict[str, Any]],
    query: str = "",
) -> List[Dict[str, Any]]:
    """
    Docstore scan: same file, chunks that continue a truncated list/section.
    """
    if not index_dir or not seed_chunks:
        return []

    files: Set[str] = set()
    for ch in seed_chunks:
        fn = _meta_filename(ch.get("metadata") or {})
        if fn:
            files.add(fn)

    combined = "\n".join((c.get("content") or "") for c in seed_chunks)
    if not rights_list_truncated(combined, query) and not _LIST_HEADING_RE.search(combined):
        if not any(content_suggests_continuation((c.get("content") or "")[:200]) for c in seed_chunks):
            return []

    extra: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = {_chunk_key(c) for c in seed_chunks}

    for filename in files:
        for ch in fetch_chunks_for_file(index_dir, filename):
            key = _chunk_key(ch)
            if key in seen:
                continue
            body = ch.get("content") or ""
            bl = body.lower()
            if _LIST_HEADING_RE.search(body) or _RIGHT_INLINE_RE.search(body):
                extra.append(ch)
                seen.add(key)
                continue
            if content_suggests_continuation(body[:300]):
                extra.append(ch)
                seen.add(key)

    return extra


def merge_chunk_texts(chunks: Sequence[Dict[str, Any]], *, max_chars: int = 12000) -> str:
    """Ordered merge of chunk bodies (dedupe overlapping prefixes)."""
    ordered = sorted(
        chunks,
        key=lambda c: (
            _meta_chunk_index(c.get("metadata") or {}),
            _meta_page(c.get("metadata") or {}, c.get("content") or ""),
        ),
    )
    parts: List[str] = []
    seen_prefix: Set[str] = set()
    total = 0
    for ch in ordered:
        t = (ch.get("content") or "").strip()
        if not t:
            continue
        prefix = t[:80]
        if prefix in seen_prefix:
            continue
        seen_prefix.add(prefix)
        if total + len(t) > max_chars:
            t = t[: max(0, max_chars - total)]
        parts.append(t)
        total += len(t)
        if total >= max_chars:
            break
    return "\n\n".join(parts)


def build_stitched_mega_chunk(
    chunks: Sequence[Dict[str, Any]],
    query: str = "",
) -> Optional[Dict[str, Any]]:
    """Single synthetic chunk with merged text for downstream extractors."""
    if not chunks:
        return None
    merged = merge_chunk_texts(chunks)
    if not merged or len(merged) < 60:
        return None
    meta = dict((chunks[0].get("metadata") or {}))
    meta["stitched"] = "true"
    meta["stitched_chunk_count"] = str(len(chunks))
    pages = sorted(
        {
            p
            for c in chunks
            for p in [_meta_page(c.get("metadata") or {}, c.get("content") or "")]
            if p > 0
        }
    )
    if pages:
        meta["page_range"] = (
            str(pages[0]) if len(pages) == 1 else f"{pages[0]}-{pages[-1]}"
        )
    return {
        "content": merged,
        "metadata": meta,
        "final_score": max(
            float(c.get("final_score") or c.get("hybrid_score") or 0) for c in chunks
        )
        + 0.1,
        "hybrid_score": max(float(c.get("hybrid_score") or 0) for c in chunks) + 0.1,
        "retrieval_mode": "page_stitch",
    }


def expand_chunks_across_page_breaks(
    query: str,
    chunks: Sequence[Dict[str, Any]],
    index_dir: Any = None,
    *,
    window: int = 2,
) -> List[Dict[str, Any]]:
    """
    Expand retrieval results with neighbor / continuation chunks from the index.
    Prefer a stitched mega-chunk when a list spans pages.
    """
    if not chunks:
        return []

    base = list(chunks)
    if not index_dir:
        return base

    expanded: List[Dict[str, Any]] = []
    seen: Set[Tuple[str, str]] = set()

    for ch in base:
        for neighbor in fetch_neighbor_chunks(index_dir, ch, window=window):
            key = _chunk_key(neighbor)
            if key not in seen:
                seen.add(key)
                expanded.append(neighbor)

    for extra in fetch_continuation_chunks(index_dir, expanded or base, query):
        key = _chunk_key(extra)
        if key not in seen:
            seen.add(key)
            expanded.append(extra)

    if not expanded:
        expanded = base

    combined = merge_chunk_texts(expanded)
    ql = (query or "").lower()
    needs_stitch = rights_list_truncated(combined, query) or (
        re.search(r"\b(?:five|5)\b", ql)
        and "constitutional" in ql
        and "right" in ql
        and count_numbered_rights(combined) < 5
        and count_numbered_rights(combined) >= 1
    )

    if needs_stitch and len(expanded) > 1:
        mega = build_stitched_mega_chunk(expanded, query)
        if mega:
            out = [mega]
            for ch in expanded:
                key = _chunk_key(ch)
                if key not in seen or mega.get("content") != ch.get("content"):
                    out.append(ch)
            return out[: max(12, len(expanded) + 1)]

    return expanded[:12]
