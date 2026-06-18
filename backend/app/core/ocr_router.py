"""Dual-path PDF ingestion — native extract vs OCR fallback (150 chars/page gate)."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

logger = logging.getLogger(__name__)

MIN_CHARS_PER_PAGE = int(__import__("os").getenv("OCR_MIN_CHARS_PER_PAGE", "150"))
NON_PRINTABLE_RATIO_MAX = 0.35


def page_char_counts(native_text: str) -> List[int]:
    """Split native PDF text by [Page N] markers into per-page counts."""
    if not native_text:
        return []
    parts = re.split(r"\[Page\s+(\d+)\]", native_text)
    counts: List[int] = []
    if len(parts) <= 1:
        return [len(native_text.strip())]
    for i in range(2, len(parts), 2):
        if i < len(parts):
            counts.append(len(parts[i].strip()))
    return counts or [len(native_text.strip())]


def non_printable_ratio(text: str) -> float:
    if not text:
        return 1.0
    bad = sum(1 for c in text if ord(c) < 32 and c not in "\n\r\t")
    return bad / max(len(text), 1)


def needs_ocr_fallback(native_text: str, page_count: int = 1) -> Tuple[bool, str]:
    """
    Returns (should_ocr, reason).
    Triggers when avg chars/page < 150 or high non-printable density.
    """
    stripped = (native_text or "").strip()
    pages = max(page_count, 1)
    counts = page_char_counts(stripped)
    if counts:
        avg = sum(counts) / len(counts)
        low_pages = sum(1 for c in counts if c < MIN_CHARS_PER_PAGE)
        if low_pages >= max(1, len(counts) // 2):
            return True, f"low_text_pages={low_pages}/{len(counts)}"
        if avg < MIN_CHARS_PER_PAGE:
            return True, f"avg_chars_per_page={avg:.0f}<{MIN_CHARS_PER_PAGE}"
    elif len(stripped) < MIN_CHARS_PER_PAGE * pages:
        return True, "empty_or_sparse_document"

    if non_printable_ratio(stripped) > NON_PRINTABLE_RATIO_MAX:
        return True, "high_non_printable_ratio"

    from ocr_engine import should_run_ocr

    if should_run_ocr(stripped, page_count=pages):
        return True, "legacy_density_check"
    return False, "native_ok"


def extract_with_tesseract(
    path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str]:
    """OCR via pdf2image + pytesseract when available."""
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError:
        logger.info("Tesseract/pdf2image not installed — skipping tesseract path")
        return "", ""

    try:
        images = convert_from_path(str(path), dpi=200, first_page=1, last_page=30)
    except Exception as exc:
        logger.warning("pdf2image failed: %s", exc)
        return "", ""

    chunks: List[str] = []
    for i, img in enumerate(images, start=1):
        if progress_callback:
            progress_callback(f"Tesseract OCR page {i}/{len(images)}")
        try:
            t = pytesseract.image_to_string(img) or ""
        except Exception:
            t = ""
        if t.strip():
            chunks.append(f"[Page {i}]\n{t.strip()}")
    text = "\n\n".join(chunks).strip()
    return text, "ocr_tesseract" if text else ""


def extract_text_routed(
    path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
    *,
    force_ocr: bool = False,
) -> Tuple[str, str]:
    """Delegates to large-PDF hybrid extractor (native all pages + parallel sparse OCR)."""
    from backend.app.core.pdf_extraction import extract_pdf_production

    return extract_pdf_production(path, force_ocr=force_ocr, progress_callback=progress_callback)
