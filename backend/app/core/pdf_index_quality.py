"""
PDF extraction and indexing quality gates — catch "big PDF, tiny index" failures early.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

MIN_CHARS_PER_PAGE = int(os.getenv("PDF_MIN_CHARS_PER_PAGE", "100"))
MIN_CHUNKS_FOR_LARGE_DOC = int(os.getenv("PDF_MIN_CHUNKS_LARGE", "40"))


def pdf_page_count(path: Path) -> int:
    """Best-effort page count from PDF file on disk."""
    path = Path(path)
    try:
        import fitz

        doc = fitz.open(str(path))
        n = len(doc)
        doc.close()
        return n
    except Exception:
        pass
    try:
        from PyPDF2 import PdfReader

        return len(PdfReader(str(path)).pages)
    except Exception:
        return 0


def count_page_markers(text: str) -> int:
    markers = len(re.findall(r"\[Page\s+\d+\]", text or "", re.I))
    if markers:
        return markers
    markers = len(re.findall(r"\[PAGE:\d+\]", text or "", re.I))
    return markers


def is_weak_extraction(text: str, page_count: int = 0) -> bool:
    """
    True when extracted text is too small for the PDF size (scanned PDF, bad cache, wrong path).
    """
    body = (text or "").strip()
    if len(body) < 80:
        return True
    pages = page_count or count_page_markers(body) or max(1, len(body) // 2500)
    chars_per_page = len(body) / max(pages, 1)
    if chars_per_page < MIN_CHARS_PER_PAGE:
        return True
    # Very large PDF with almost no IPC/section structure still needs volume
    if pages >= 30 and len(body) < pages * 80:
        return True
    return False


def expected_min_chunks(text: str, page_count: int = 0) -> int:
    """Minimum FAISS chunks we expect after indexing this text."""
    body = (text or "").strip()
    if not body:
        return 0
    pages = page_count or count_page_markers(body) or max(1, len(body) // 2500)
    # ~1 chunk per 400–500 chars for prose; statutes may be 1 per section
    by_size = max(5, len(body) // 450)
    by_pages = max(5, pages // 2) if pages >= 10 else 3
    return max(by_size, by_pages)


def is_underchunked(text: str, chunk_count: int, page_count: int = 0) -> bool:
    """True when chunk count is suspiciously low for document size."""
    if chunk_count <= 0:
        return True
    pages = page_count or count_page_markers(text) or max(1, len(text or "") // 2500)
    need = expected_min_chunks(text, pages)
    if pages >= 20 and chunk_count < min(MIN_CHUNKS_FOR_LARGE_DOC, need):
        return True
    if chunk_count < max(3, need // 4):
        return True
    return False


def extraction_report(text: str, page_count: int = 0, *, filename: str = "") -> Dict[str, Any]:
    pages = page_count or count_page_markers(text) or max(1, len(text or "") // 2500)
    chars = len((text or "").strip())
    return {
        "filename": filename,
        "page_count": pages,
        "char_count": chars,
        "chars_per_page": round(chars / max(pages, 1), 1),
        "weak_extraction": is_weak_extraction(text, pages),
        "expected_min_chunks": expected_min_chunks(text, pages),
    }


def invalidate_extraction_cache(path: Path) -> None:
    """Remove stale .extracted.txt caches beside the PDF."""
    path = Path(path)
    stem = path.stem
    parent = path.parent
    for tag in ("auto", "native", "ocr"):
        c = parent / f"{stem}.{tag}.extracted.txt"
        try:
            if c.exists():
                c.unlink()
        except OSError:
            pass
