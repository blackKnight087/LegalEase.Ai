"""V4 court package PDF — cover page, matter metadata, annexures."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.drafting_v3 import html_to_plain
from backend.app.core.drafting_export_v3 import export_legal_document


def export_court_pdf(
    content: str,
    *,
    title: str = "Document",
    matter_meta: Optional[Dict[str, str]] = None,
    annexures: Optional[List[Dict[str, Any]]] = None,
    watermark: str = "CONFIDENTIAL",
) -> Tuple[bytes, str, str]:
    meta = matter_meta or {}
    header_block = _court_cover_block(title, meta)
    body = html_to_plain(content) if "<" in (content or "") else (content or "")
    full = f"{header_block}\n\n{body}"
    if annexures:
        full += "\n\n## ANNEXURES INDEX\n"
        for ax in annexures:
            full += f"- {ax.get('label', 'Annexure')}\n"
    firm = meta.get("ClientName") or "LegalEase"
    return export_legal_document(
        full,
        title=title,
        fmt="pdf",
        watermark=watermark,
        firm_name=firm[:40],
        content_format="markdown",
    )


def merge_pdf_bundle(parts: List[bytes]) -> bytes:
    try:
        import fitz

        out = fitz.open()
        for blob in parts:
            src = fitz.open(stream=blob, filetype="pdf")
            out.insert_pdf(src)
            src.close()
        buf = out.write()
        out.close()
        return buf
    except Exception:
        return parts[0] if parts else b""


def _court_cover_block(title: str, meta: Dict[str, str]) -> str:
    lines = [
        "# " + title,
        "",
        f"**Client:** {meta.get('ClientName', '—')}",
        f"**Matter:** {meta.get('MatterName', '—')}",
        f"**Case Number:** {meta.get('CaseNumber', '—')}",
        f"**Court:** {meta.get('CourtName', '—')}",
        f"**Opposing Party:** {meta.get('OpposingParty', '—')}",
        "",
        f"Generated: {datetime.now(timezone.utc).strftime('%d %B %Y')}",
    ]
    return "\n".join(lines)
