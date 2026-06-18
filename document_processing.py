"""
Production-grade document text extraction for LegalEase.AI.

Pipeline:
1) Native PDF text (PyPDF2)
2) Layout-aware fallback (pdfplumber)
3) EasyOCR for scanned / low-text PDFs
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from PyPDF2 import PdfReader

from ocr_engine import extract_text_with_ocr, ocr_status, should_run_ocr

logger = logging.getLogger(__name__)


def _extract_native_pdf(path: Path) -> Tuple[str, int]:
    """Extract text with PyPDF2, then pdfplumber if output is weak."""
    text = ""
    page_count = 0
    try:
        reader = PdfReader(str(path))
        page_count = len(reader.pages)
        for page_number, page in enumerate(reader.pages, start=1):
            try:
                t = page.extract_text() or ""
            except Exception:
                t = ""
            if t.strip():
                text += f"\n\n[Page {page_number}]\n{t.strip()}"
        if text.strip():
            logger.info(
                "Native PDF extract OK: %s | pages=%s | chars=%s",
                path.name,
                page_count,
                len(text),
            )
    except Exception as exc:
        logger.warning("PyPDF2 extraction failed for %s: %s", path.name, exc)

    if len(text.strip()) < 80:
        try:
            import pdfplumber

            plumber_text = ""
            with pdfplumber.open(str(path)) as pdf:
                page_count = max(page_count, len(pdf.pages))
                for page_number, page in enumerate(pdf.pages, start=1):
                    t = page.extract_text() or ""
                    if t.strip():
                        plumber_text += f"\n\n[Page {page_number}]\n{t.strip()}"
            if len(plumber_text.strip()) > len(text.strip()):
                text = plumber_text
                logger.info("pdfplumber improved extraction for %s (%s chars)", path.name, len(text))
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("pdfplumber extraction failed for %s: %s", path.name, exc)

    return text, page_count


def extract_text_from_pdf(
    path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[str, str]:
    """
    Production extraction — routes through ocr_router (150 chars/page gate + OCR).
    """
    path = Path(path)
    if not path.exists():
        return "", "none"
    try:
        from backend.app.core.ocr_router import extract_text_routed

        return extract_text_routed(path, progress_callback=progress_callback)
    except Exception as exc:
        logger.warning("ocr_router fallback to legacy path: %s", exc)

    native_text, page_count = _extract_native_pdf(path)
    method = "native_pdf" if native_text.strip() else "none"
    if should_run_ocr(native_text, page_count=max(page_count, 1)):
        if progress_callback:
            progress_callback(f"Scanned/low-text PDF detected - running OCR on {path.name}")
        ocr_text, ocr_method = extract_text_with_ocr(path, progress_callback=progress_callback)
        if len(ocr_text.strip()) > len(native_text.strip()):
            return ocr_text, ocr_method or "ocr_easyocr"
    if native_text.strip():
        return native_text, method
    ocr_text, ocr_method = extract_text_with_ocr(path, progress_callback=progress_callback)
    if ocr_text.strip():
        return ocr_text, ocr_method or "ocr_easyocr"
    return "", "none"


def get_extraction_capabilities() -> dict:
    """Summary for UI / health panels."""
    status = ocr_status()
    return {
        "ocr": status,
        "native": ["PyPDF2", "pdfplumber"],
    }


def pdf_extraction_diagnostics(text: str, page_count: int, method: str) -> Dict[str, Any]:
    """
    Quality signals after PDF/OCR extraction (for indexing warnings).
    """
    body = (text or "").strip()
    pages = max(1, page_count or 1)
    chars = len(body)
    markers = len(re.findall(r"\[Page\s+\d+\]", body, re.I))
    return {
        "extraction_method": method or "none",
        "page_count": pages,
        "char_count": chars,
        "chars_per_page": round(chars / pages, 1),
        "page_markers": markers,
        "ocr_used": bool(method and "ocr" in method.lower()),
        "weak_extraction": chars < 80 * pages,
        "empty_extraction": chars < 40,
    }
