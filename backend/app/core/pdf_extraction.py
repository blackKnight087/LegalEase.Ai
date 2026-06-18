"""
Large-PDF extraction — fast native text for all pages, OCR only where needed (parallel).
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PDF_MAX_PAGES = int(os.getenv("PDF_MAX_PAGES", "0"))  # 0 = no limit
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "0"))  # 0 = no limit on full-doc OCR
OCR_SPARSE_ONLY = os.getenv("OCR_SPARSE_ONLY", "1").lower() in ("1", "true", "yes")
OCR_WORKERS = max(1, min(8, int(os.getenv("OCR_WORKERS", "4"))))
OCR_MIN_CHARS_PER_PAGE = int(os.getenv("OCR_MIN_CHARS_PER_PAGE", "120"))
OCR_RENDER_SCALE = float(os.getenv("OCR_RENDER_SCALE", "1.75"))


def _page_limit(total: int, cap: int) -> int:
    if cap and cap > 0:
        return min(total, cap)
    return total


def _extract_pymupdf_pages(path: Path) -> Tuple[List[Tuple[int, str]], int]:
    import fitz

    pages: List[Tuple[int, str]] = []
    doc = fitz.open(str(path))
    total = len(doc)
    limit = _page_limit(total, PDF_MAX_PAGES)
    for idx in range(limit):
        page = doc.load_page(idx)
        text = (page.get_text("text") or "").strip()
        if len(text) < 40:
            blocks = page.get_text("blocks") or []
            block_text = "\n".join(
                str(b[4]).strip() for b in blocks if len(b) > 4 and str(b[4]).strip()
            )
            if len(block_text) > len(text):
                text = block_text.strip()
        pages.append((idx + 1, text))
    doc.close()
    return pages, total


def _extract_pdfplumber_pages(path: Path) -> Tuple[List[Tuple[int, str]], int]:
    import pdfplumber

    pages: List[Tuple[int, str]] = []
    with pdfplumber.open(str(path)) as pdf:
        total = len(pdf.pages)
        limit = _page_limit(total, PDF_MAX_PAGES)
        for idx in range(limit):
            t = (pdf.pages[idx].extract_text() or "").strip()
            pages.append((idx + 1, t))
    return pages, total


def _extract_pypdf2_pages(path: Path) -> Tuple[List[Tuple[int, str]], int]:
    from PyPDF2 import PdfReader

    pages: List[Tuple[int, str]] = []
    reader = PdfReader(str(path))
    total = len(reader.pages)
    limit = _page_limit(total, PDF_MAX_PAGES)
    for idx in range(limit):
        try:
            t = (reader.pages[idx].extract_text() or "").strip()
        except Exception:
            t = ""
        pages.append((idx + 1, t))
    return pages, total


def extract_native_pages(path: Path) -> Tuple[List[Tuple[int, str]], int]:
    """
    Per-page native extraction — tries PyMuPDF, pdfplumber, PyPDF2 and keeps the richest result.
    """
    path = Path(path)
    candidates: List[Tuple[str, List[Tuple[int, str]], int]] = []

    try:
        pages, total = _extract_pymupdf_pages(path)
        if any(t for _, t in pages):
            candidates.append(("pymupdf", pages, total))
            logger.info("PyMuPDF native: %s | pages=%s/%s", path.name, len(pages), total)
    except Exception as exc:
        logger.warning("PyMuPDF native failed for %s: %s", path.name, exc)

    try:
        pages, total = _extract_pdfplumber_pages(path)
        if any(t for _, t in pages):
            candidates.append(("pdfplumber", pages, total))
    except Exception as exc:
        logger.warning("pdfplumber per-page failed for %s: %s", path.name, exc)

    try:
        pages, total = _extract_pypdf2_pages(path)
        if any(t for _, t in pages):
            candidates.append(("pypdf2", pages, total))
    except Exception as exc:
        logger.warning("PyPDF2 per-page failed for %s: %s", path.name, exc)

    if not candidates:
        return [], 0

    def _score(pgs: List[Tuple[int, str]]) -> int:
        return sum(len(t) for _, t in pgs)

    best_tag, best_pages, best_total = max(candidates, key=lambda x: _score(x[1]))
    if len(candidates) > 1:
        logger.info(
            "PDF extract winner=%s for %s (%s chars)",
            best_tag,
            path.name,
            _score(best_pages),
        )
    return best_pages, best_total


def _ocr_single_page(path: Path, page_idx: int, reader) -> str:
    """OCR one page (0-based index) with EasyOCR."""
    import fitz
    import numpy as np

    doc = fitz.open(str(path))
    try:
        page = doc.load_page(page_idx)
        matrix = fitz.Matrix(OCR_RENDER_SCALE, OCR_RENDER_SCALE)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        channels = pix.n
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, channels)
        if channels == 4:
            arr = arr[:, :, :3]
    finally:
        doc.close()

    lines = reader.readtext(arr, detail=0, paragraph=True)
    cleaned = []
    for line in lines:
        t = re.sub(r"\s+", " ", str(line or "")).strip()
        if t:
            cleaned.append(t)
    return "\n".join(cleaned)


def ocr_pages_parallel(
    path: Path,
    page_numbers: List[int],
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[int, str]:
    """page_numbers are 1-based. Returns {page_num: text}."""
    if not page_numbers:
        return {}

    from ocr_engine import get_easyocr_reader

    reader = get_easyocr_reader()
    if reader is None:
        return {}

    path = Path(path)
    cap = OCR_MAX_PAGES if OCR_MAX_PAGES > 0 else len(page_numbers)
    todo = page_numbers[:cap]
    results: Dict[int, str] = {}
    total = len(todo)

    def _work(pnum: int) -> Tuple[int, str]:
        return pnum, _ocr_single_page(path, pnum - 1, reader)

    with ThreadPoolExecutor(max_workers=OCR_WORKERS) as pool:
        futures = {pool.submit(_work, p): p for p in todo}
        done = 0
        for fut in as_completed(futures):
            done += 1
            pnum = futures[fut]
            try:
                pn, text = fut.result()
                if text.strip():
                    results[pn] = text.strip()
            except Exception as exc:
                logger.warning("OCR page %s failed: %s", pnum, exc)
            if progress_callback:
                progress_callback(f"OCR page {done}/{total} ({path.name})")

    return results


def _merge_pages(pages: List[Tuple[int, str]]) -> str:
    parts = []
    for pnum, text in sorted(pages, key=lambda x: x[0]):
        if text.strip():
            parts.append(f"[Page {pnum}]\n{text.strip()}")
    return "\n\n".join(parts)


def extract_pdf_production(
    path: Path,
    *,
    force_ocr: bool = False,
    allow_ocr: bool = True,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str]:
    """
    Extract full PDF text optimized for large multi-page files.
    Returns (text, method_tag).
    """
    path = Path(path)
    if progress_callback:
        progress_callback(f"Reading {path.name} (native text)…")

    page_rows, total_pages = extract_native_pages(path)
    if not page_rows:
        page_rows = []

    if force_ocr:
        if progress_callback:
            progress_callback(f"OCR all pages ({len(page_rows)} pages)…")
        from ocr_engine import extract_text_with_ocr

        text, method = extract_text_with_ocr(path, progress_callback=progress_callback)
        if text.strip():
            return text, method or "ocr_full"
        return "", "none"

    if not allow_ocr:
        text = _merge_pages(page_rows)
        return text, "native_pymupdf" if text.strip() else ("", "none")

    sparse_nums = [p for p, t in page_rows if len(t.strip()) < OCR_MIN_CHARS_PER_PAGE]
    dense_ok = len(page_rows) - len(sparse_nums)

    if OCR_SPARSE_ONLY and sparse_nums and dense_ok > 0:
        if progress_callback:
            progress_callback(
                f"OCR on {len(sparse_nums)} sparse pages (native OK on {dense_ok})…"
            )
        ocr_map = ocr_pages_parallel(path, sparse_nums, progress_callback)
        merged: List[Tuple[int, str]] = []
        for pnum, native_t in page_rows:
            ocr_t = ocr_map.get(pnum, "")
            best = ocr_t if len(ocr_t) > len(native_t) else native_t
            merged.append((pnum, best))
        text = _merge_pages(merged)
        if text.strip():
            return text, "hybrid_native+ocr"

    if page_rows and sum(len(t) for _, t in page_rows) > OCR_MIN_CHARS_PER_PAGE:
        text = _merge_pages(page_rows)
        return text, "native_pymupdf"

    need_full, reason = False, "sparse"
    try:
        from backend.app.core.ocr_router import needs_ocr_fallback

        combined = _merge_pages(page_rows)
        need_full, reason = needs_ocr_fallback(combined, page_count=max(total_pages, 1))
    except Exception:
        need_full = True

    if need_full or not page_rows:
        if progress_callback:
            progress_callback(f"Full OCR ({reason}) for {path.name}…")
        from ocr_engine import extract_text_with_ocr, read_ocr_cache, write_ocr_cache

        cached = read_ocr_cache(path)
        if cached and len(cached.strip()) > 50:
            return cached, "ocr_cache"
        text, method = extract_text_with_ocr(path, progress_callback=progress_callback)
        if text.strip():
            write_ocr_cache(path, text)
            return text, method or "ocr_full"

    text = _merge_pages(page_rows)
    return text, "native_pymupdf" if text.strip() else ("", "none")
