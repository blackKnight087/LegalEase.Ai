"""Drafting Studio V2 workspace persistence."""
from __future__ import annotations

import pytest


@pytest.fixture
def drafting_user_id():
    return "test-drafting-ws-user"


def test_create_list_document(drafting_user_id, monkeypatch):
    from backend.app.core import practice_schema
    from backend.app.core.drafting_workspace import create_document, get_document, list_documents

    practice_schema.ensure_practice_schema()
    doc = create_document(
        drafting_user_id,
        title="Test NDA",
        document_type="nda",
        content="# NDA\n\nParty A and Party B agree.\n",
    )
    assert doc.get("draft_id")
    assert doc.get("version_count") == 1
    loaded = get_document(drafting_user_id, doc["draft_id"])
    assert loaded and "NDA" in loaded["content"]
    rows = list_documents(drafting_user_id, q="NDA")
    assert any(r["draft_id"] == doc["draft_id"] for r in rows)


def test_clause_intel_score():
    from backend.app.core.drafting_clause_intel import analyze_document

    out = analyze_document("# Agreement\n\nPayment within 30 days.\n", document_type="contract")
    assert "clause_risk_score" in out
    assert isinstance(out["missing_clauses"], list)
