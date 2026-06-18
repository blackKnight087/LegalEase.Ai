"""Court-ready PDF/DOCX export for Drafting Studio V3 — HTML tables, no raw markdown."""
from __future__ import annotations

from typing import Tuple

from backend.app.core.drafting_document_format import export_html_document


def export_legal_document(
    content: str,
    *,
    title: str = "Legal Document",
    fmt: str = "pdf",
    watermark: str = "",
    firm_name: str = "LegalEase",
    content_format: str = "markdown",
) -> Tuple[bytes, str, str]:
    return export_html_document(
        content,
        title=title,
        fmt=fmt,
        content_format=content_format,
        watermark=watermark,
        firm_name=firm_name,
    )
