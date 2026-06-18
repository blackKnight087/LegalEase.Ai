"""End-to-end API checks for Drafting Studio buttons (no LLM required for static paths)."""
from __future__ import annotations

import os
import tempfile

# Use isolated DB for tests
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

from backend.app.core.drafting_document_format import (  # noqa: E402
    EXECUTION_BLOCK_HTML,
    SIGNATURE_BLOCK_HTML,
    export_html_document,
    markdown_to_html,
)
from backend.app.core.drafting_v3 import copilot_command, export_document_v3
from backend.app.core.drafting_workspace import create_document, get_document, update_document


def test_copilot_execution_and_signature_blocks():
    uid = "e2e-user"
    doc = create_document(uid, title="E2E", content="<p>Test</p>", content_format="html")
    did = doc["draft_id"]
    ex = copilot_command(uid, did, "execution_block")
    assert "error" not in ex
    assert "<table" in ex["result"]
    assert "| Party |" not in ex["result"]
    sig = copilot_command(uid, did, "signature_block")
    assert "PARTY A" in sig["result"]
    assert sig["result"] != ex["result"]


def test_save_and_export_pdf():
    uid = "e2e-user-2"
    md = "## Agreement\n\n| Party | Date |\n|-------|------|\n| A | 2026 |"
    doc = create_document(uid, title="Export", content=md, content_format="markdown")
    did = doc["draft_id"]
    html = markdown_to_html(md)
    update_document(uid, did, content=html, content_format="html", change_summary="normalize")
    data, name, media = export_document_v3(uid, did, "pdf")
    assert media == "application/pdf"
    assert name.endswith(".pdf")
    assert len(data) > 400
    assert b"| Party |" not in data
    stored = get_document(uid, did)
    assert stored
    assert stored.get("content_format") == "html"


def test_execution_html_export():
    data, name, media = export_html_document(EXECUTION_BLOCK_HTML, title="Exec", fmt="pdf")
    assert media == "application/pdf"
    assert name.endswith(".pdf")
    assert len(data) > 400
    assert SIGNATURE_BLOCK_HTML.count("<h3>") >= 4
