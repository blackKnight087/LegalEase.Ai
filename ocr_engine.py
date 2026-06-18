"""
Production-grade OCR for LegalEase.AI using EasyOCR.

Design goals:
- Lazy-loaded singleton reader (avoid reloading models on every page)
- Configurable via environment variables
- Disk cache for OCR output (re-index without re-running OCR)
- Graceful degradation when OCR is disabled or unavailable
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv()

OCR_ENABLED = os.getenv("OCR_ENABLED", "1").lower() in {"1", "true", "yes"}
OCR_LANGUAGES = [x.strip() for x in os.getenv("OCR_LANGUAGES", "en").split(",") if x.strip()]
OCR_GPU = os.getenv("OCR_GPU", "0").lower() in {"1", "true", "yes"}
OCR_RENDER_SCALE = float(os.getenv("OCR_RENDER_SCALE", "2.0"))
OCR_MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "0"))  # 0 = no page cap
OCR_MIN_NATIVE_CHARS = int(os.getenv("OCR_MIN_NATIVE_CHARS", "80"))
OCR_MIN_CHARS_PER_PAGE = int(os.getenv("OCR_MIN_CHARS_PER_PAGE", "40"))
OCR_CACHE_DIR = BASE_DIR / "Data" / "ocr_cache"
OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

_reader_singleton = None
_reader_init_failed = False


def ocr_status() -> dict:
    """Health info for Settings / diagnostics UI."""
    return {
        "enabled": OCR_ENABLED,
        "languages": OCR_LANGUAGES,
        "gpu": OCR_GPU,
        "render_scale": OCR_RENDER_SCALE,
        "max_pages": OCR_MAX_PAGES,
        "cache_dir": str(OCR_CACHE_DIR),
        "reader_ready": _reader_singleton is not None,
        "reader_failed": _reader_init_failed,
    }


def _cache_key(path: Path) -> str:
    stat = path.stat()
    raw = f"{path.resolve()}|{stat.st_size}|{int(stat.st_mtime)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _cache_path(path: Path) -> Path:
    return OCR_CACHE_DIR / f"{_cache_key(path)}.txt"


def read_ocr_cache(path: Path) -> Optional[str]:
    cache_file = _cache_path(path)
    if not cache_file.exists():
        return None
    try:
        text = cache_file.read_text(encoding="utf-8", errors="ignore").strip()
        return text or None
    except OSError as exc:
        logger.warning("OCR cache read failed for %s: %s", path.name, exc)
        return None


def write_ocr_cache(path: Path, text: str) -> None:
    cache_file = _cache_path(path)
    try:
        cache_file.write_text(text, encoding="utf-8")
    except OSError as exc:
        logger.warning("OCR cache write failed for %s: %s", path.name, exc)


def get_easyocr_reader():
    """
    Lazy singleton EasyOCR reader.
    Returns None if OCR is disabled or initialization fails.
    """
    global _reader_singleton, _reader_init_failed

    if not OCR_ENABLED:
        return None
    if _reader_init_failed:
        return None
    if _reader_singleton is not None:
        return _reader_singleton

    try:
        import easyocr

        logger.info(
            "Initializing EasyOCR reader (languages=%s, gpu=%s)...",
            OCR_LANGUAGES,
            OCR_GPU,
        )
        _reader_singleton = easyocr.Reader(OCR_LANGUAGES, gpu=OCR_GPU, verbose=False)
        logger.info("EasyOCR reader ready.")
        return _reader_singleton
    except Exception as exc:
        _reader_init_failed = True
        logger.exception("EasyOCR initialization failed: %s", exc)
        return None


def _render_pdf_pages(path: Path, scale: float = OCR_RENDER_SCALE) -> List[Tuple[int, object]]:
    """
    Render PDF pages to RGB numpy arrays using PyMuPDF.
    Returns list of (page_number, ndarray).
    """
    import fitz
    import numpy as np

    doc = fitz.open(str(path))
    pages: List[Tuple[int, object]] = []
    matrix = fitz.Matrix(scale, scale)
    page_limit = len(doc) if OCR_MAX_PAGES <= 0 else min(len(doc), OCR_MAX_PAGES)

    for page_idx in range(page_limit):
        page = doc.load_page(page_idx)
        pix = page.get_pixmap(matrix=matrix, alpha=False)
        channels = pix.n
        arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, channels)
        if channels == 4:
            arr = arr[:, :, :3]
        pages.append((page_idx + 1, arr))
    doc.close()
    return pages


def _ocr_image(reader, image) -> str:
    """Run EasyOCR on one page image and join detected lines."""
    lines = reader.readtext(image, detail=0, paragraph=True)
    cleaned = []
    for line in lines:
        text = re.sub(r"\s+", " ", str(line or "")).strip()
        if text:
            cleaned.append(text)
    return "\n".join(cleaned)


def extract_text_from_image_bytes(
    data: bytes,
    filename: str = "upload.png",
) -> Tuple[str, str]:
    """
    OCR a chat attachment (PNG/JPG/WebP bytes).
    Tier 1: RapidOCR (if installed) on preprocessed image
    Tier 2: EasyOCR on preprocessed image
    Tier 3: Tesseract fallback when confidence is low
    Returns (text, method).
    """
    if not data:
        return "", ""

    try:
        import io

        import numpy as np
        from PIL import Image

        from backend.app.core.ocr_preprocessor import ocr_confidence_score, preprocess_for_ocr

        image = Image.open(io.BytesIO(data))
        if image.mode != "RGB":
            image = image.convert("RGB")
        arr = np.array(image)
        processed = preprocess_for_ocr(arr)

        # Tier 1 — RapidOCR
        try:
            from rapidocr_onnxruntime import RapidOCR

            engine = RapidOCR()
            result, _ = engine(processed if processed is not None else arr)
            if result:
                lines = [str(row[1]).strip() for row in result if row and len(row) > 1]
                text = "\n".join(lines).strip()
                if ocr_confidence_score(text) >= 0.45:
                    return text, "ocr_rapidocr"
        except ImportError:
            pass
        except Exception as exc:
            logger.debug("RapidOCR failed (%s): %s", filename, exc)

        # Tier 2 — EasyOCR
        reader = get_easyocr_reader()
        if reader is not None:
            try:
                ocr_input = processed if processed is not None else arr
                text = _ocr_image(reader, ocr_input).strip()
                if text and ocr_confidence_score(text) >= 0.35:
                    return text, "ocr_easyocr"
            except Exception as exc:
                logger.debug("EasyOCR failed (%s): %s", filename, exc)

        # Tier 3 — Tesseract
        try:
            from backend.app.core.ocr_router import extract_with_tesseract
            from PIL import Image as PILImage

            pil = PILImage.fromarray(processed if processed is not None else arr)
            import tempfile

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pil.save(tmp.name)
                tess_text, _ = extract_with_tesseract(Path(tmp.name))
            tess_text = (tess_text or "").strip()
            if tess_text:
                return tess_text, "ocr_tesseract"
        except Exception as exc:
            logger.debug("Tesseract fallback failed (%s): %s", filename, exc)

        return "", ""
    except Exception as exc:
        logger.exception("Image OCR failed (%s): %s", filename, exc)
        return "", ""


def extract_text_with_ocr(
    path: Path,
    progress_callback: Optional[Callable[[str], None]] = None,
    use_cache: bool = True,
) -> Tuple[str, str]:
    """
    OCR a PDF file page-by-page.

    Returns:
        (text, method) where method is 'ocr_easyocr' or 'ocr_cache' or '' if failed.
    """
    if use_cache:
        cached = read_ocr_cache(path)
        if cached:
            return cached, "ocr_cache"

    reader = get_easyocr_reader()
    if reader is None:
        return "", ""

    try:
        rendered_pages = _render_pdf_pages(path)
    except Exception as exc:
        logger.exception("PDF render for OCR failed (%s): %s", path.name, exc)
        return "", ""

    if not rendered_pages:
        return "", ""

    chunks: List[str] = []
    total = len(rendered_pages)
    for idx, (page_number, image) in enumerate(rendered_pages, start=1):
        if progress_callback:
            progress_callback(f"OCR {path.name} - page {page_number}/{total}")
        try:
            page_text = _ocr_image(reader, image)
        except Exception as exc:
            logger.warning("OCR failed on %s page %s: %s", path.name, page_number, exc)
            page_text = ""
        if page_text.strip():
            chunks.append(f"[Page {page_number}]\n{page_text.strip()}")

    text = "\n\n".join(chunks).strip()
    if text and use_cache:
        write_ocr_cache(path, text)
    return text, "ocr_easyocr" if text else ""


def should_run_ocr(native_text: str, page_count: int = 1) -> bool:
    """
    Decide whether OCR fallback is needed for a PDF.
    Triggers on very low native text or low average density per page.
    """
    if not OCR_ENABLED:
        return False
    stripped = (native_text or "").strip()
    if len(stripped) < OCR_MIN_NATIVE_CHARS:
        return True
    pages = max(page_count, 1)
    if len(stripped) / pages < OCR_MIN_CHARS_PER_PAGE:
        return True
    return False
