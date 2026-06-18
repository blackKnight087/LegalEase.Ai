"""Legal document HTML normalization — no raw markdown in editor or PDF."""
from __future__ import annotations

import html as html_lib
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from io import BytesIO
from typing import Any, Dict, List, Optional, Tuple

SIGNATURE_BLOCK_HTML = """
<h2>EXECUTION</h2>
<p>IN WITNESS WHEREOF the parties have executed this Agreement.</p>
<h3>PARTY A</h3>
<p>Name:</p>
<p>Signature:</p>
<p>Date:</p>
<h3>PARTY B</h3>
<p>Name:</p>
<p>Signature:</p>
<p>Date:</p>
<h3>WITNESS 1</h3>
<p>Name:</p>
<p>Signature:</p>
<p>Date:</p>
<h3>WITNESS 2</h3>
<p>Name:</p>
<p>Signature:</p>
<p>Date:</p>
"""

EXECUTION_BLOCK_HTML = """
<h2>EXECUTION</h2>
<p>IN WITNESS WHEREOF the parties have executed this Agreement on the date written below.</p>
<table class="legal-signature-table">
<thead><tr><th>Party</th><th>Name</th><th>Signature</th><th>Date</th></tr></thead>
<tbody>
<tr><td><strong>Party A</strong></td><td></td><td></td><td></td></tr>
<tr><td><strong>Party B</strong></td><td></td><td></td><td></td></tr>
</tbody>
</table>
<h3>Witnesses</h3>
<table class="legal-signature-table">
<thead><tr><th>Witness</th><th>Name</th><th>Signature</th><th>Date</th></tr></thead>
<tbody>
<tr><td>Witness 1</td><td></td><td></td><td></td></tr>
<tr><td>Witness 2</td><td></td><td></td><td></td></tr>
</tbody>
</table>
"""

EXECUTION_BLOCK_PLAIN = """
EXECUTION

IN WITNESS WHEREOF the parties have executed this Agreement on the date written below.

PARTY A
Name:
Signature:
Date:

PARTY B
Name:
Signature:
Date:

WITNESS 1
Name:
Signature:
Date:

WITNESS 2
Name:
Signature:
Date:
"""


def normalize_content_for_storage(content: str, content_format: str = "markdown") -> Tuple[str, str]:
    """Return (html, format) — always prefer HTML for professional output."""
    raw = content or ""
    if content_format == "html" or raw.strip().startswith("<"):
        html = _fix_pipe_tables_in_html(sanitize_html(raw))
        return html, "html"
    html = markdown_to_html(raw)
    return html, "html"


def sanitize_html(html: str) -> str:
    t = html or ""
    t = re.sub(r"\|[-:\s|]+\|", "", t)
    t = re.sub(r"^\s*\|(.+)\|\s*$", "", t, flags=re.M)
    return t.strip() or "<p></p>"


def _fix_pipe_tables_in_html(html: str) -> str:
    """Convert leftover markdown pipe lines inside HTML to tables."""
    lines = html.split("\n")
    out: List[str] = []
    buf: List[str] = []
    for line in lines:
        if _is_md_table_row(line):
            buf.append(line)
        else:
            if buf:
                out.append(_md_table_lines_to_html(buf))
                buf = []
            out.append(line)
    if buf:
        out.append(_md_table_lines_to_html(buf))
    return "\n".join(out)


def _is_md_table_row(line: str) -> bool:
    s = line.strip()
    return bool(s) and s.startswith("|") and s.endswith("|") and s.count("|") >= 2


def _md_table_lines_to_html(lines: List[str]) -> str:
    rows = []
    for line in lines:
        s = line.strip()
        if re.match(r"^\|[-:\s|]+\|$", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        rows.append(cells)
    if not rows:
        return ""
    head = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    parts = ["<table class='legal-signature-table'><thead><tr>"]
    for c in head:
        parts.append(f"<th>{html_lib.escape(c)}</th>")
    parts.append("</tr></thead><tbody>")
    for row in body:
        parts.append("<tr>")
        for c in row:
            parts.append(f"<td>{html_lib.escape(c)}</td>")
        parts.append("</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def markdown_to_html(md: str) -> str:
    text = md or ""
    if text.strip().startswith("<"):
        return sanitize_html(text)
    lines = text.split("\n")
    parts: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            parts.append("<p><br></p>")
            i += 1
            continue
        if _is_md_table_row(stripped):
            tbl_lines = []
            while i < len(lines) and _is_md_table_row(lines[i].strip()):
                tbl_lines.append(lines[i])
                i += 1
            parts.append(_md_table_lines_to_html(tbl_lines))
            continue
        if stripped.startswith("### "):
            parts.append(f"<h3>{_esc(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            parts.append(f"<h2>{_esc(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            parts.append(f"<h1>{_esc(stripped[2:])}</h1>")
        elif stripped.startswith("- "):
            parts.append(f"<ul><li>{_esc(stripped[2:])}</li></ul>")
        elif stripped.startswith("**") and stripped.endswith("**"):
            parts.append(f"<p><strong>{_esc(stripped[2:-2])}</strong></p>")
        else:
            parts.append(f"<p>{_esc(stripped)}</p>")
        i += 1
    return "".join(parts) or "<p></p>"


def _esc(s: str) -> str:
    return html_lib.escape(s)


def html_to_plain_text(html: str) -> str:
    t = html or ""
    if "<" not in t:
        return t
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n", t, flags=re.I)
    t = re.sub(r"</h[1-6]>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = re.sub(r"&nbsp;", " ", t)
    t = re.sub(r"&amp;", "&", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = t.strip()
    t = re.sub(r"\|[-:\s|]+\|", "", t)
    t = re.sub(r"^\s*\|.+\|\s*$", "", t, flags=re.M)
    return t.strip()


class _HtmlBlockParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.blocks: List[Dict[str, Any]] = []
        self._table: List[List[str]] = []
        self._row: List[str] = []
        self._cell = ""
        self._in_table = False
        self._in_cell = False
        self._tag_stack: List[str] = []

    def handle_starttag(self, tag: str, attrs: List) -> None:
        t = tag.lower()
        self._tag_stack.append(t)
        if t == "table":
            self._in_table = True
            self._table = []
        elif t == "tr" and self._in_table:
            self._row = []
        elif t in ("td", "th") and self._in_table:
            self._in_cell = True
            self._cell = ""
        elif t in ("h1", "h2", "h3"):
            self.blocks.append({"type": "heading", "level": int(t[1]), "text": ""})
        elif t == "p" and not self._in_table:
            self.blocks.append({"type": "paragraph", "text": ""})
        elif t == "hr":
            self.blocks.append({"type": "page_break"})
        elif t == "li":
            self.blocks.append({"type": "bullet", "text": ""})
        elif t == "strong" or t == "b":
            pass

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._in_cell:
            self._row.append(self._cell.strip())
            self._in_cell = False
        elif t == "tr" and self._in_table:
            if self._row:
                self._table.append(self._row)
            self._row = []
        elif t == "table" and self._in_table:
            self.blocks.append({"type": "table", "rows": self._table})
            self._in_table = False
        elif t in ("h1", "h2", "h3", "p", "li") and self.blocks:
            if self.blocks[-1].get("text") is not None:
                self.blocks[-1]["text"] = self.blocks[-1].get("text", "").strip()

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell += data
        elif self.blocks and not self._in_table:
            last = self.blocks[-1]
            if "text" in last:
                last["text"] = (last.get("text") or "") + data


def html_to_pdf_bytes(
    html: str,
    *,
    title: str = "Legal Document",
    firm_name: str = "LegalEase",
    watermark: str = "",
) -> bytes:
    """Render HTML to professional A4 PDF with real tables."""
    import fitz

    parser = _HtmlBlockParser()
    try:
        parser.feed(sanitize_html(html))
        parser.close()
    except Exception:
        parser.blocks = [{"type": "paragraph", "text": html_to_plain_text(html)}]

    page_w, page_h = 595.0, 842.0
    margin_x, margin_top, margin_bottom = 56.0, 72.0, 64.0
    doc = fitz.open()
    pages: List[fitz.Page] = []
    y = margin_top
    page = doc.new_page(width=page_w, height=page_h)
    pages.append(page)

    def new_page() -> fitz.Page:
        nonlocal y, page
        page = doc.new_page(width=page_w, height=page_h)
        pages.append(page)
        y = margin_top
        return page

    def ensure_space(need: float) -> None:
        nonlocal y, page
        if y + need > page_h - margin_bottom:
            page = new_page()

    # Cover line (firm letterhead style)
    page.insert_text((margin_x, 48), firm_name[:60], fontsize=11, fontname="helv")
    page.insert_text((margin_x, 68), title[:80], fontsize=16, fontname="helv")
    page.insert_text(
        (margin_x, 90),
        datetime.now(timezone.utc).strftime("%d %B %Y"),
        fontsize=9,
        fontname="helv",
    )
    y = margin_top + 8

    for block in parser.blocks:
        btype = block.get("type")
        if btype == "page_break":
            page = new_page()
            continue
        if btype == "heading":
            lvl = int(block.get("level") or 2)
            size = {1: 16, 2: 13, 3: 12}.get(lvl, 12)
            text = (block.get("text") or "").strip()
            if not text:
                continue
            ensure_space(size + 12)
            page.insert_text((margin_x, y), text[:200], fontsize=size, fontname="helv")
            y += size + 10
        elif btype == "bullet":
            text = (block.get("text") or "").strip()
            if not text:
                continue
            ensure_space(14)
            page.insert_text((margin_x + 8, y), f"• {text[:300]}", fontsize=11, fontname="helv")
            y += 14
        elif btype == "table":
            rows = block.get("rows") or []
            if not rows:
                continue
            cols = max(len(r) for r in rows)
            if cols == 0:
                continue
            table_w = page_w - 2 * margin_x
            col_w = table_w / cols
            row_h = 22.0
            need_h = row_h * len(rows) + 8
            ensure_space(need_h)
            x0 = margin_x
            for ri, row in enumerate(rows):
                for ci in range(cols):
                    cell = row[ci] if ci < len(row) else ""
                    rx = x0 + ci * col_w
                    ry = y + ri * row_h
                    rect = fitz.Rect(rx, ry, rx + col_w - 2, ry + row_h - 2)
                    page.draw_rect(rect, color=(0.75, 0.75, 0.75), width=0.5)
                    if ri == 0:
                        page.draw_rect(rect, fill=(0.94, 0.94, 0.96))
                    page.insert_text(
                        (rx + 4, ry + 6),
                        str(cell)[:40],
                        fontsize=9 if ri == 0 else 10,
                        fontname="helv",
                    )
            y += need_h + 8
        elif btype == "paragraph":
            text = (block.get("text") or "").strip()
            if not text:
                y += 6
                continue
            for chunk in _wrap(text, 88):
                ensure_space(13)
                page.insert_text((margin_x, y), chunk, fontsize=11, fontname="helv")
                y += 13

    total = len(pages)
    for i, p in enumerate(pages, 1):
        p.insert_text((margin_x, page_h - 36), f"{firm_name} — Confidential", fontsize=8, fontname="helv")
        p.insert_text((page_w - margin_x - 72, page_h - 36), f"Page {i} of {total}", fontsize=8, fontname="helv")
        if watermark:
            try:
                p.insert_text((page_w / 2 - 100, page_h / 2), watermark[:40], fontsize=22, rotate=45)
            except Exception:
                pass

    buf = BytesIO()
    doc.save(buf)
    doc.close()
    buf.seek(0)
    return buf.read()


def _wrap(text: str, width: int) -> List[str]:
    words = text.split()
    lines: List[str] = []
    line = ""
    for w in words:
        trial = f"{line} {w}".strip()
        if len(trial) > width:
            if line:
                lines.append(line)
            line = w
        else:
            line = trial
    if line:
        lines.append(line)
    return lines or [""]


def export_html_document(
    content: str,
    *,
    title: str = "Legal Document",
    fmt: str = "pdf",
    content_format: str = "markdown",
    watermark: str = "",
    firm_name: str = "LegalEase",
) -> Tuple[bytes, str, str]:
    html, _ = normalize_content_for_storage(content, content_format)
    safe = re.sub(r"[^\w\s-]", "", title or "document")[:60].strip() or "document"
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    if fmt == "pdf":
        data = html_to_pdf_bytes(html, title=safe, firm_name=firm_name, watermark=watermark)
        return data, f"{safe}_{ts}.pdf", "application/pdf"
    if fmt == "docx":
        from backend.app.core.drafting_docx_export import export_docx_document

        return export_docx_document(
            content,
            title=title,
            content_format="html",
            firm_name=firm_name,
        )
    from backend.app.core.report_export import export_report_bytes

    return export_report_bytes(html_to_plain_text(html), title=title, fmt=fmt)
