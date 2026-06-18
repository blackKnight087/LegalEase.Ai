#!/usr/bin/env python3
"""
Generate LegalEase Product Design & Technical Architecture PDF from markdown source.

Usage:
  py scripts/generate_architecture_pdf.py
  py scripts/generate_architecture_pdf.py --input docs/LEGALEASE_PRODUCT_ARCHITECTURE_SUITE.md --output docs/LegalEase_Product_Architecture_Suite.pdf
"""
from __future__ import annotations

import argparse
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "docs" / "LEGALEASE_COMPLETE_DOCUMENTATION.md"
DEFAULT_OUTPUT = ROOT / "docs" / "LegalEase_Product_Architecture_Suite.pdf"
FALLBACK_INPUT = ROOT / "docs" / "LEGALEASE_PRODUCT_ARCHITECTURE_SUITE.md"


def _sanitize(text: str) -> str:
    """Replace Unicode chars that core Helvetica cannot render."""
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2022": "*",
        "\u2192": "->",
        "\u2193": "v",
        "\u2713": "[Y]",
        "\u2717": "[N]",
        "\u2714": "[Y]",
        "\u2716": "[N]",
        "\u00a0": " ",
        "\u2026": "...",
        "\u20b9": "INR ",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class ArchitecturePDF:
    def __init__(self, output: Path) -> None:
        from fpdf import FPDF

        self.pdf = FPDF(orientation="P", unit="mm", format="A4")
        self.pdf.set_auto_page_break(auto=True, margin=20)
        self.output = output
        self._in_code = False
        self._code_lines: list[str] = []
        self._page_header = "LegalEase.AI Complete Product & Deployment Documentation"
        self.pdf.set_margins(15, 18, 15)

        def _footer() -> None:
            self.pdf.set_y(-12)
            self.pdf.set_font("Helvetica", "I", 8)
            self.pdf.cell(
                0,
                8,
                _sanitize(f"{self._page_header} | Page {self.pdf.page_no()}"),
                align="C",
                new_x="LMARGIN",
                new_y="NEXT",
            )

        self.pdf.footer = _footer  # type: ignore[method-assign]

    def add_cover(self) -> None:
        self.pdf.add_page()
        self.pdf.set_font("Helvetica", "B", 28)
        self.pdf.ln(40)
        self.pdf.multi_cell(0, 14, _sanitize("LegalEase.AI"), align="C")
        self.pdf.ln(4)
        self.pdf.set_font("Helvetica", "", 16)
        self.pdf.multi_cell(
            0,
            10,
            _sanitize("Product Design & Technical Architecture Documentation Suite"),
            align="C",
        )
        self.pdf.ln(8)
        self.pdf.set_font("Helvetica", "I", 11)
        self.pdf.multi_cell(
            0,
            7,
            _sanitize(
                "PRD | System Architecture | Database Design | API Reference\n"
                "AI Architecture | Security | Deployment | Workflows\n"
                "Competitive Analysis | Technical Deep Dive | Roadmap"
            ),
            align="C",
        )
        self.pdf.ln(20)
        self.pdf.set_font("Helvetica", "", 10)
        ts = datetime.now(timezone.utc).strftime("%d %B %Y (UTC)")
        self.pdf.cell(0, 8, _sanitize(f"Document Version 1.0 | Generated {ts}"), align="C")
        self.pdf.ln(6)
        self.pdf.cell(0, 8, _sanitize("Classification: Confidential - Internal & Investor Use"), align="C")

    def add_toc(self) -> None:
        self.pdf.add_page()
        self.pdf.set_font("Helvetica", "B", 16)
        self.pdf.cell(0, 10, _sanitize("Table of Contents"), new_x="LMARGIN", new_y="NEXT")
        self.pdf.ln(4)
        sections = [
            "Executive Summary",
            "Document 1 - Product Requirements Document (PRD)",
            "Document 2 - System Architecture",
            "Document 3 - Database Design",
            "Document 4 - API Documentation",
            "Document 5 - AI Architecture",
            "Document 6 - Security Architecture",
            "Document 7 - Complete Deployment Guide (Laptop + EC2 + Docker)",
            "Document 8 - Product Workflow Guide",
            "Document 9 - Competitive Analysis",
            "Document 10 - Technical Deep Dive",
            "Appendix A-L - Glossary, Roadmap, Related Docs",
            "Appendix D - Expanded Module Specifications",
            "Appendix E-U - API Index, DB, UI, Runbooks, FAQ",
            "Appendix V - Complete API Route Index (493 routes, auto-generated)",
            "Appendix W - Complete Environment Variables Catalog",
        ]
        self.pdf.set_font("Helvetica", "", 10)
        for i, s in enumerate(sections, 1):
            self.pdf.cell(0, 6, _sanitize(f"{i}. {s}"), new_x="LMARGIN", new_y="NEXT")

    def _write_wrapped(self, text: str, *, size: int = 10, style: str = "", indent: int = 0) -> None:
        self.pdf.set_font("Helvetica", style, size)
        width = self.pdf.w - self.pdf.l_margin - self.pdf.r_margin - indent
        lh = size * 0.52
        self.pdf.set_x(self.pdf.l_margin + indent)
        for para in text.split("\n"):
            para = para.strip()
            if not para:
                self.pdf.ln(lh * 0.6)
                continue
            wrapped = textwrap.wrap(_sanitize(para), width=int(width / (size * 0.42)) or 40)
            for line in wrapped:
                self.pdf.set_x(self.pdf.l_margin + indent)
                self.pdf.multi_cell(width, lh, line)
            self.pdf.ln(lh * 0.3)

    def _flush_code(self) -> None:
        if not self._code_lines:
            return
        self.pdf.set_font("Courier", "", 8)
        self.pdf.set_fill_color(245, 245, 245)
        block = "\n".join(self._code_lines)
        width = self.pdf.w - self.pdf.l_margin - self.pdf.r_margin
        for line in block.split("\n"):
            self.pdf.set_x(self.pdf.l_margin)
            self.pdf.multi_cell(width, 4, _sanitize(line[:120]), fill=True)
        self._code_lines = []
        self.pdf.ln(2)

    def render_markdown(self, md_text: str) -> None:
        lines = md_text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("```"):
                if self._in_code:
                    self._in_code = False
                    self._flush_code()
                else:
                    self._in_code = True
                i += 1
                continue

            if self._in_code:
                self._code_lines.append(line.rstrip())
                i += 1
                continue

            if stripped == "---":
                self.pdf.ln(2)
                self.pdf.set_draw_color(200, 200, 200)
                y = self.pdf.get_y()
                self.pdf.line(self.pdf.l_margin, y, self.pdf.w - self.pdf.r_margin, y)
                self.pdf.ln(4)
                i += 1
                continue

            if stripped.startswith("# "):
                self.pdf.add_page()
                self.pdf.set_font("Helvetica", "B", 18)
                self.pdf.ln(4)
                self.pdf.multi_cell(0, 10, _sanitize(stripped[2:].strip()))
                self.pdf.ln(6)
                i += 1
                continue

            if stripped.startswith("## "):
                if self.pdf.get_y() > 240:
                    self.pdf.add_page()
                self.pdf.ln(4)
                self.pdf.set_font("Helvetica", "B", 14)
                self.pdf.multi_cell(0, 8, _sanitize(stripped[3:].strip()))
                self.pdf.ln(4)
                i += 1
                continue

            if stripped.startswith("### "):
                self.pdf.ln(3)
                self.pdf.set_font("Helvetica", "B", 11)
                self.pdf.multi_cell(0, 6, _sanitize(stripped[4:].strip()))
                self.pdf.ln(2)
                i += 1
                continue

            if stripped.startswith("#### "):
                self.pdf.set_font("Helvetica", "B", 10)
                self.pdf.ln(1)
                self.pdf.multi_cell(0, 5, _sanitize(stripped[5:].strip()))
                i += 1
                continue

            if stripped.startswith("|") and "|" in stripped[1:]:
                table_rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    row = lines[i].strip()
                    if re.match(r"^\|[-:\s|]+\|$", row):
                        i += 1
                        continue
                    cells = [c.strip() for c in row.strip("|").split("|")]
                    table_rows.append(cells)
                    i += 1
                if table_rows:
                    for ri, cells in enumerate(table_rows):
                        row_text = " | ".join(cells)
                        style = "B" if ri == 0 else ""
                        self._write_wrapped(row_text, size=8, style=style)
                    self.pdf.ln(2)
                continue

            if stripped.startswith("- ") or stripped.startswith("* "):
                self._write_wrapped(stripped[2:], size=10, indent=4)
                i += 1
                continue

            if re.match(r"^\d+\.\s", stripped):
                self._write_wrapped(stripped, size=10, indent=4)
                i += 1
                continue

            if stripped.startswith(">"):
                self._write_wrapped(stripped.lstrip("> ").strip(), size=10, style="I", indent=6)
                i += 1
                continue

            if not stripped:
                self.pdf.ln(2)
                i += 1
                continue

            self._write_wrapped(stripped, size=10)
            i += 1

        self._flush_code()

    def save(self) -> Path:
        self.output.parent.mkdir(parents=True, exist_ok=True)
        self.pdf.output(str(self.output))
        return self.output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LegalEase architecture PDF")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    input_path = args.input
    if not input_path.exists() and input_path == DEFAULT_INPUT and FALLBACK_INPUT.exists():
        input_path = FALLBACK_INPUT
    if not input_path.exists():
        raise SystemExit(f"Input not found: {input_path}")

    md = input_path.read_text(encoding="utf-8")
    gen = ArchitecturePDF(args.output)
    gen.add_cover()
    gen.add_toc()
    gen.pdf.add_page()
    gen.render_markdown(md)
    out = gen.save()
    pages = gen.pdf.page_no()
    print(f"Generated: {out}")
    print(f"Pages: {pages}")


if __name__ == "__main__":
    main()
