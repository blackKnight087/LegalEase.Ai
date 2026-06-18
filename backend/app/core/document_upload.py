"""Document save + image OCR (lives under backend/ for hot-reload on upload fixes)."""
from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def infer_ext_from_bytes(data: bytes, filename: str = "") -> str:
    lower = (filename or "").lower()
    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return ".webp"
    for ext in IMAGE_EXT:
        if lower.endswith(ext):
            return ext
    if lower.endswith(".pdf"):
        return ".pdf"
    return ".png"


def extract_image_text(path: Path, data: Optional[bytes] = None) -> str:
    """OCR an image file; raises ValueError with actionable message on failure."""
    path = Path(path)
    raw = data if data is not None else path.read_bytes()

    from ocr_engine import extract_text_from_image_bytes, get_easyocr_reader, ocr_status

    # Warm reader before OCR (first call can take 30–90s on CPU)
    reader = get_easyocr_reader()
    st = ocr_status()
    if not st.get("enabled"):
        raise ValueError("OCR is disabled. Set OCR_ENABLED=1 in .env and restart the backend.")
    if reader is None or st.get("reader_failed"):
        raise ValueError(
            "EasyOCR could not start. Run: pip install easyocr pillow — then restart the backend."
        )

    text, method = extract_text_from_image_bytes(raw, path.name)
    cleaned = (text or "").strip()
    if cleaned:
        logger.info("Image OCR %s | method=%s | chars=%s", path.name, method, len(cleaned))
        return cleaned
    raise ValueError(
        "No text detected in this image. Use a clearer photo with readable text, or try a higher-resolution scan."
    )


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
