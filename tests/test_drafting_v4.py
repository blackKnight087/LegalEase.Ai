"""Drafting Studio V4 lifecycle tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def uid():
    return "test-drafting-v4-user"


def test_control_center_and_precedent(uid):
    from backend.app.core.drafting_lifecycle import (
        control_center,
        create_precedent,
        ensure_v4_schema,
        filing_readiness,
        search_precedents_ai,
    )
    from backend.app.core.drafting_workspace import create_document
    from backend.app.core import practice_schema

    practice_schema.ensure_practice_schema()
    ensure_v4_schema()
    cc = control_center(uid)
    assert "columns" in cc
    assert "reviewer_queue" in cc
    p = create_precedent(
        uid,
        title="Sample Bail",
        content="# Bail\n\nApplicant seeks bail.",
        document_type="bail_application",
        tags=["bail", "criminal"],
        court="Sessions Court",
    )
    hits = search_precedents_ai(uid, "bail petition applicant")
    assert hits["results"]
    doc = create_document(uid, title="Filing test", content="# Petition\n\nParty A vs Party B.\n\nSigned.", matter_id="")
    fr = filing_readiness(uid, doc["draft_id"])
    assert "filing_readiness_score" in fr
    assert p.get("precedent_id")
