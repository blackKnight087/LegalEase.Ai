"""Platform integrations — matter overview, litigation, billing."""
from __future__ import annotations

import pytest


@pytest.fixture
def uid():
    return "test-platform-int-user"


def test_matter_overview_and_filing_sync(uid):
    from backend.app.core import practice_schema
    from backend.app.core.drafting_lifecycle import create_matter_draft, ensure_v4_schema
    from backend.app.core.matter_repo import create_matter
    from backend.app.core.platform_integrations import (
        ensure_integration_schema,
        matter_drafting_overview,
        sync_draft_filed_to_litigation,
    )

    practice_schema.ensure_practice_schema()
    ensure_v4_schema()
    ensure_integration_schema()
    m = create_matter(uid, matter_name="Platform Test", client_name="Client A", case_number="WP/1/2024")
    mid = m["matter_id"]
    out = create_matter_draft(uid, mid, title="Test Petition", document_type="petition")
    did = out["document"]["draft_id"]
    ov = matter_drafting_overview(uid, mid)
    assert ov["total"] >= 1
    assert "control_center_url" in ov
    doc = sync_draft_filed_to_litigation(uid, did)
    assert doc.get("ok") or doc.get("order_id")


def test_billing_cooldown(uid):
    from backend.app.core import practice_schema
    from backend.app.core.drafting_workspace import create_document
    from backend.app.core.matter_repo import create_matter
    from backend.app.core.platform_integrations import (
        ensure_integration_schema,
        log_drafting_billing_session,
    )

    practice_schema.ensure_practice_schema()
    ensure_integration_schema()
    m = create_matter(uid, matter_name="Bill Test", client_name="C")
    doc = create_document(uid, title="Bill doc", matter_id=m["matter_id"], content="# Test")
    did = doc["draft_id"]
    first = log_drafting_billing_session(uid, did, change_summary="Manual save")
    second = log_drafting_billing_session(uid, did, change_summary="Manual save")
    assert first.get("billed") or first.get("skipped")
    assert second.get("skipped") is True
