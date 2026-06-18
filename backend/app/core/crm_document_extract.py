"""Extract text from CRM lead uploads for analysis."""
from __future__ import annotations

import io
import logging
from pathlib import Path

logger = logging.getLogger("legalease.crm_docs")

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def extract_crm_upload_text(content: bytes, filename: str = "") -> str:
    """Best-effort text extraction for intake documents."""
    name = (filename or "upload").lower()
    if name.endswith((".txt", ".md", ".csv")):
        return content.decode("utf-8", errors="ignore").strip()

    if content[:4] == b"%PDF" or name.endswith(".pdf"):
        try:
            from PyPDF2 import PdfReader

            reader = PdfReader(io.BytesIO(content))
            parts = [(p.extract_text() or "").strip() for p in reader.pages]
            text = "\n".join(p for p in parts if p)
            if text:
                return text[:50000]
        except Exception as exc:
            logger.warning("CRM PDF extract failed: %s", exc)

    ext = Path(name).suffix.lower()
    if ext in _IMAGE_EXT or content[:8] == b"\x89PNG\r\n\x1a\n" or content[:3] == b"\xff\xd8\xff":
        try:
            from ocr_engine import extract_text_from_image_bytes

            text, _ = extract_text_from_image_bytes(content, filename or "upload.png")
            return (text or "").strip()[:50000]
        except Exception as exc:
            logger.warning("CRM image OCR failed: %s", exc)

    if name.endswith((".doc", ".docx")):
        try:
            import tempfile

            suffix = ".docx" if name.endswith(".docx") else ".doc"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(content)
                tmp_path = Path(tmp.name)
            try:
                from app import extract_text_from_file

                return (extract_text_from_file(tmp_path) or "").strip()[:50000]
            finally:
                tmp_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("CRM docx extract failed: %s", exc)

    return ""
