#!/usr/bin/env python3
"""Generate LegalEase SaaS Thesis PDF from Markdown source with embedded diagrams."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MD = ROOT / "docs" / "LegalEase_SAAS_Thesis.md"
DEFAULT_PDF = ROOT / "docs" / "LegalEase_SAAS_Thesis.pdf"
DOCS_DIR = ROOT / "docs"

# Typography
FONT_BODY = 9
FONT_H2 = 15
FONT_H3 = 12
FONT_H4 = 11
FONT_CODE = 7.5
FONT_CAPTION = 8.5
LINE_H = 5.5


class ThesisPDF(FPDF):
    def header(self) -> None:
        if self.page_no() <= 2:
            return
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "LegalEase.AI - SaaS Product Thesis v3.0", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")


def _clean_inline(text: str) -> str:
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2192", "->").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.encode("latin-1", errors="replace").decode("latin-1")


def _write_para(pdf: FPDF, text: str, h: float = LINE_H) -> None:
    pdf.set_x(pdf.l_margin)
    try:
        pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin, h, text)
    except Exception:
        for chunk in re.split(r"(?<=\.)\s+", text):
            if chunk.strip():
                pdf.set_x(pdf.l_margin)
                pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin, h, chunk.strip())


def _resolve_image(path_str: str, md_dir: Path) -> Path | None:
    candidates = [
        md_dir / path_str,
        DOCS_DIR / path_str,
        ROOT / path_str,
    ]
    for c in candidates:
        if c.exists() and c.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            return c
    return None


def _embed_image(pdf: FPDF, img_path: Path, caption: str) -> None:
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin
    max_h = pdf.h - pdf.t_margin - pdf.b_margin - 30
    pdf.ln(3)
    try:
        pdf.image(str(img_path), x=pdf.l_margin, w=usable_w)
    except Exception as exc:
        pdf.set_font("Helvetica", "I", 9)
        _write_para(pdf, f"[Image unavailable: {img_path.name} - {exc}]", 5)
        return
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", FONT_CAPTION)
    pdf.set_text_color(80, 80, 80)
    cap = _clean_inline(caption or img_path.stem.replace("_", " ").title())
    _write_para(pdf, f"Figure: {cap}", 4.5)
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)


def _add_title_page(pdf: FPDF) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(20, 40, 80)
    pdf.ln(40)
    pdf.multi_cell(0, 14, "LegalEase.AI", align="C")
    pdf.ln(8)
    pdf.set_font("Helvetica", "", 14)
    pdf.set_text_color(60, 60, 60)
    pdf.multi_cell(0, 9, "SaaS Blueprint - Investor and CTO Edition", align="C")
    pdf.ln(20)
    pdf.set_font("Helvetica", "", 11)
    for line in (
        "Indian Legal AI Practice Platform",
        "Version 3.0 | June 2026",
        "Next.js 15 + FastAPI + Multi-LLM Architecture",
        "Multi-Tenant RAG + Practice Management SaaS",
    ):
        pdf.cell(0, 8, line, align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(30)
    pdf.set_font("Helvetica", "I", 9)
    pdf.multi_cell(
        0, 6,
        "Confidential - For investors, stakeholders, and technical review.\n"
        "Derived from production codebase Legal_AI_Final 3.",
        align="C",
    )


def _add_toc(pdf: FPDF, titles: list[str]) -> None:
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(20, 40, 80)
    pdf.cell(0, 12, "Table of Contents", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(6)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(0, 0, 0)
    for i, t in enumerate(titles, 1):
        pdf.cell(0, 6.5, _clean_inline(f"{i}. {t}"), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)


def build_pdf(md_path: Path, pdf_path: Path) -> None:
    md_dir = md_path.parent
    lines = md_path.read_text(encoding="utf-8").splitlines()
    pdf = ThesisPDF()
    pdf.set_auto_page_break(auto=True, margin=22)
    pdf.set_margins(18, 18, 18)

    toc_titles: list[str] = []
    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if m:
            toc_titles.append(m.group(1).strip())

    _add_title_page(pdf)
    _add_toc(pdf, toc_titles)
    pdf.add_page()

    i = 0
    while i < len(lines):
        line = lines[i]

        # Embedded images: ![caption](path)
        img_m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", line.strip())
        if img_m:
            caption, path_str = img_m.group(1), img_m.group(2)
            img_path = _resolve_image(path_str, md_dir)
            if img_path:
                _embed_image(pdf, img_path, caption)
            else:
                pdf.set_font("Helvetica", "I", 9)
                _write_para(pdf, f"[Diagram not found: {path_str}]", 5)
            i += 1
            continue

        if line.strip().startswith("```mermaid"):
            i += 1
            mermaid_buf: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                mermaid_buf.append(lines[i])
                i += 1
            i += 1
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_fill_color(248, 250, 252)
            _write_para(pdf, "[Mermaid diagram - see embedded PNG figures in this document]", 4.5)
            pdf.ln(2)
            continue

        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i][:110])
                i += 1
            pdf.ln(2)
            if lang:
                pdf.set_font("Helvetica", "I", 7)
                pdf.set_text_color(100, 100, 100)
                pdf.cell(0, 4, f"Code ({lang}):", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(0, 0, 0)
            pdf.set_font("Courier", "", FONT_CODE)
            pdf.set_fill_color(245, 247, 250)
            for b in buf:
                pdf.set_x(pdf.l_margin)
                pdf.cell(0, 4.2, _clean_inline(b), fill=True, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(3)
            i += 1
            continue

        if line.startswith("# ") and not line.startswith("## "):
            i += 1
            continue

        m = re.match(r"^(#{2,4})\s+(.+)$", line)
        if m:
            lvl = len(m.group(1)) - 1
            sizes = {1: FONT_H2, 2: FONT_H3, 3: FONT_H4, 4: 10}
            if lvl == 1 and pdf.page_no() > 3:
                pdf.add_page()
            pdf.ln(6 if lvl == 1 else 4)
            pdf.set_font("Helvetica", "B", sizes.get(lvl, 10))
            pdf.set_text_color(20, 40, 80) if lvl <= 2 else pdf.set_text_color(50, 50, 50)
            _write_para(pdf, _clean_inline(m.group(2)), 7)
            pdf.set_text_color(0, 0, 0)
            i += 1
            continue

        if line.strip().startswith("|") and "|" in line:
            pdf.set_fill_color(240, 244, 248)
            row_idx = 0
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                if not re.match(r"^\|[-:\s|]+\|$", row):
                    cells = [c.strip() for c in row.split("|")[1:-1]]
                    pdf.set_font("Helvetica", "B" if row_idx == 0 else "", 9)
                    _write_para(pdf, _clean_inline("  |  ".join(cells)), 5)
                    row_idx += 1
                i += 1
            pdf.ln(2)
            continue

        if re.match(r"^[-*]\s+", line.strip()):
            pdf.set_font("Helvetica", "", FONT_BODY)
            _write_para(pdf, "  - " + _clean_inline(re.sub(r"^[-*]\s+", "", line.strip())))
            i += 1
            continue

        if re.match(r"^\d+\.\s+", line.strip()):
            pdf.set_font("Helvetica", "", FONT_BODY)
            _write_para(pdf, _clean_inline(line.strip()))
            i += 1
            continue

        if line.strip() == "---":
            pdf.ln(5)
            pdf.set_draw_color(200, 200, 200)
            pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
            pdf.ln(5)
            i += 1
            continue

        if line.strip():
            pdf.set_font("Helvetica", "", FONT_BODY)
            _write_para(pdf, _clean_inline(line.strip()))
            pdf.ln(1)
        i += 1

    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(pdf_path))
    page_count = pdf.page_no()
    kb = pdf_path.stat().st_size // 1024
    print(f"Wrote {pdf_path} ({page_count} pages, {kb} KB)")


if __name__ == "__main__":
    md = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_MD
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PDF
    if not md.exists():
        print(f"Missing: {md}", file=sys.stderr)
        sys.exit(1)
    build_pdf(md, out)
