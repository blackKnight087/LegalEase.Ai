#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re

from fpdf import FPDF


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_MD = ROOT / "docs" / "blueprint" / "project-blueprint.md"
APPENDIX_MD = ROOT / "docs" / "blueprint" / "appendix" / "feature-inventory.md"
OUT_PDF = ROOT / "docs" / "blueprint" / "project-blueprint.pdf"


def _ascii_safe(text: str) -> str:
    return text.encode("ascii", errors="replace").decode("ascii")


def _load_markdown() -> str:
    parts = []
    for p in (BLUEPRINT_MD, APPENDIX_MD):
        parts.append(p.read_text(encoding="utf-8"))
    return "\n\n---\n\n".join(parts)


def _extract_headings(markdown: str) -> list[str]:
    lines = markdown.splitlines()
    out: list[str] = []
    for line in lines:
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            if title:
                out.append(title)
    return out


def build_pdf() -> Path:
    md = _load_markdown()
    toc = _extract_headings(md)

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)

    left_margin = pdf.l_margin

    def write_block(text: str, h: int = 5) -> None:
        pdf.set_x(left_margin)
        pdf.multi_cell(0, h, _ascii_safe(text))

    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    write_block("LegalEase Project Blueprint", 10)
    pdf.set_font("Helvetica", "", 11)
    write_block("Source: docs/blueprint/project-blueprint.md + appendix", 6)
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 8, "Table of Contents", ln=True)
    pdf.set_font("Helvetica", "", 10)
    for h in toc:
        write_block(f"- {h}")

    in_code = False
    for raw in md.splitlines():
        line = raw.rstrip("\n")
        if line.strip().startswith("```"):
            in_code = not in_code
            pdf.set_font("Courier" if in_code else "Helvetica", "", 9 if in_code else 10)
            continue

        if line.startswith("### "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 12)
            write_block(line[4:].strip(), 7)
            pdf.set_font("Helvetica", "", 10)
            continue
        if line.startswith("## "):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 14)
            write_block(line[3:].strip(), 8)
            pdf.set_font("Helvetica", "", 10)
            continue
        if line.startswith("# "):
            pdf.add_page()
            pdf.set_font("Helvetica", "B", 16)
            write_block(line[2:].strip(), 9)
            pdf.set_font("Helvetica", "", 10)
            continue

        clean = re.sub(r"`([^`]+)`", r"\1", line)
        if not clean.strip():
            pdf.ln(3)
            continue
        write_block(clean)

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PDF))
    return OUT_PDF


if __name__ == "__main__":
    out = build_pdf()
    print(str(out))

