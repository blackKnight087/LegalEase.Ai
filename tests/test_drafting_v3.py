"""Drafting Studio V3 — matter vars, templates, workflow."""
from __future__ import annotations

import pytest


@pytest.fixture
def uid():
    return "test-drafting-v3-user"


def test_apply_variables():
    from backend.app.core.drafting_v3 import apply_variables

    out = apply_variables("Client: {{ClientName}}, Case {{CaseNumber}}", {"ClientName": "Acme", "CaseNumber": "123"})
    assert "Acme" in out
    assert "123" in out


def test_render_builtin_template(uid):
    from backend.app.core.drafting_v3 import render_v3_template

    out = render_v3_template(uid, "petition", extra_vars={"ClientName": "Raj", "CaseNumber": "WP/1/2024"})
    assert "Raj" in out["rendered"]
    assert "WP/1/2024" in out["rendered"]


def test_workflow_transition(uid, monkeypatch):
    from backend.app.core import practice_schema
    from backend.app.core.drafting_v3 import ensure_workspace_v3_schema, transition_status
    from backend.app.core.drafting_workspace import create_document

    practice_schema.ensure_practice_schema()
    ensure_workspace_v3_schema()
    doc = create_document(uid, title="Workflow test", content="# Test\n")
    did = doc["draft_id"]
    r1 = transition_status(uid, did, "in_review")
    assert r1["document"]["status"] == "in_review"
    r2 = transition_status(uid, did, "filed")
    assert r2.get("error")


def test_clause_recommendations_v3(uid):
    from backend.app.core.drafting_clause_intel import clause_recommendations_v3

    out = clause_recommendations_v3(uid, "# Agreement\n\nPayment terms only.\n")
    assert "recommendations" in out
    assert "clause_risk_score" in out
