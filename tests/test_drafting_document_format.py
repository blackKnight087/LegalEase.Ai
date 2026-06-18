"""Tests for professional legal document formatting (no markdown in PDF)."""
from backend.app.core.drafting_document_format import (
    EXECUTION_BLOCK_HTML,
    export_html_document,
    markdown_to_html,
    normalize_content_for_storage,
)


def test_markdown_table_converts_to_html():
    md = "| Party | Signature |\n|-------|----------|\n| A | ___ |"
    html, fmt = normalize_content_for_storage(md, "markdown")
    assert fmt == "html"
    assert "<table" in html
    assert "| Party |" not in html


def test_execution_block_has_no_markdown_pipes():
    assert "|" not in EXECUTION_BLOCK_HTML or EXECUTION_BLOCK_HTML.count("|") < 3
    assert "<table" in EXECUTION_BLOCK_HTML
    assert "EXECUTION" in EXECUTION_BLOCK_HTML


def test_pdf_export_strips_markdown_tables():
    md = "# Agreement\n\n| Col |\n|-----|\n| Val |"
    data, name, media = export_html_document(md, title="Test", fmt="pdf")
    assert media == "application/pdf"
    assert name.endswith(".pdf")
    assert len(data) > 500
    assert b"| Col |" not in data
    assert b"|-----|" not in data


def test_markdown_to_html_headings():
    html = markdown_to_html("## Definitions\n\nTerm means X.")
    assert "<h2>" in html
    assert "Definitions" in html
