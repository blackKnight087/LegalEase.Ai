"""Enterprise drafting features — track changes, TOC, DOCX, precedents."""
from __future__ import annotations

import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp())

from backend.app.core.drafting_docx_export import html_to_docx_bytes
from backend.app.core.drafting_enterprise import (
    add_track_change,
    generate_annexure_index_html,
    generate_toc_html,
    list_track_changes,
    resolve_track_change,
)
from backend.app.core.drafting_workspace import create_document, get_document


def test_toc_and_annexure_index():
    html = "<h1>Title</h1><h2>Section A</h2><p>Body</p>"
    toc = generate_toc_html(html)
    assert "Table of Contents" in toc
    assert "Section A" in toc
    idx = generate_annexure_index_html([{"label": "Annexure A", "content": "Affidavit copy"}])
    assert "Annexure A" in idx


def test_track_change_accept_updates_document():
    uid = "ent-user"
    doc = create_document(uid, title="TC", content="<p>Old clause text here.</p>", content_format="html")
    did = doc["draft_id"]
    add_track_change(
        uid,
        did,
        original_text="Old clause text",
        suggested_text="New clause text",
    )
    changes = list_track_changes(uid, did)
    assert len(changes) == 1
    out = resolve_track_change(uid, did, changes[0]["change_id"], True)
    assert out.get("ok")
    stored = get_document(uid, did)
    assert stored
    assert "New clause text" in (stored.get("content") or "")


def test_docx_export_from_html():
    html = "<h1>Agreement</h1><table><tr><th>Party</th></tr><tr><td>A</td></tr></table>"
    data = html_to_docx_bytes(html, title="Agreement", firm_name="Test Firm")
    assert len(data) > 1000
    assert data[:2] == b"PK"
