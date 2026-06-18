"""Phase 3 CRM intake — rigorous parametrize tests."""
from __future__ import annotations

import uuid

import pytest

from backend.app.core.saas_schema import ensure_saas_schema
from backend.app.core.practice_schema import ensure_practice_schema
from backend.app.core.crm_service import (
    classify_intake_query,
    create_lead,
    draft_follow_up_email,
    record_intent_correction,
    update_lead,
)

INTAKE_QUERIES = [
    (
        "My vendor took 5 lakhs and stopped answering. Contract signed in Kolkata.",
        "COMMERCIAL_LITIGATION",
    ),
    (
        "Police registered FIR against me under IPC 420 need bail urgently",
        "CRIMINAL_DEFENSE",
    ),
    (
        "Wife filed divorce and demanding maintenance in Mumbai",
        "FAMILY_LAW",
    ),
    (
        "Tenant not paying rent for 6 months want eviction",
        "PROPERTY_REAL_ESTATE",
    ),
    (
        "Company terminated me without notice want wrongful termination remedy",
        "EMPLOYMENT_LABOUR",
    ),
    (
        "Need general legal advice about a business dispute",
        "GENERAL_CONSULTATION",
    ),
]


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "crm.db"))
    ensure_practice_schema()
    ensure_saas_schema()


@pytest.mark.parametrize("query,expected_intent", INTAKE_QUERIES)
def test_classify_intake_intent(query, expected_intent):
    uid = f"u-{uuid.uuid4().hex[:6]}"
    out = classify_intake_query(query, uid)
    assert out["intent"] == expected_intent
    assert out["confidence"] >= 0.4


@pytest.mark.parametrize("query,_", INTAKE_QUERIES[:4])
def test_extract_params_amount_or_venue(query, _):
    out = classify_intake_query(query)
    params = out.get("parameters") or {}
    assert params  # at least one extracted field for real-world queries


@pytest.mark.parametrize("query,expected_intent", INTAKE_QUERIES[:3])
def test_create_lead_pipeline(query, expected_intent):
    uid = f"u-{uuid.uuid4().hex[:6]}"
    lead = create_lead(
        uid,
        prospect_name="Test Prospect",
        contact_email="test@example.com",
        raw_intake_query=query,
    )
    assert lead["lead_id"]
    assert lead["calculated_intent"] == expected_intent
    assert lead["pipeline_stage"] == "NEW_INTAKE"
    assert len(lead["follow_up_draft"]) > 80


@pytest.mark.parametrize("intent", [q[1] for q in INTAKE_QUERIES[:5]])
def test_follow_up_email_contains_substance(intent):
    draft = draft_follow_up_email("Rahul Sharma", intent, {"venue": "Kolkata"})
    assert "Dear" in draft
    assert len(draft) > 100


def test_intent_correction_overrides_rules():
    uid = f"u-{uuid.uuid4().hex[:6]}"
    q = "vendor payment issue in delhi"
    record_intent_correction(uid, q, "FAMILY_LAW", original_intent="COMMERCIAL_LITIGATION")
    out = classify_intake_query(q, uid)
    assert out["intent"] == "FAMILY_LAW"
    assert out.get("source") == "learned_correction"


def test_update_lead_stage():
    uid = f"u-{uuid.uuid4().hex[:6]}"
    lead = create_lead(
        uid,
        prospect_name="A",
        contact_email="a@b.com",
        raw_intake_query=INTAKE_QUERIES[0][0],
    )
    updated = update_lead(uid, lead["lead_id"], pipeline_stage="VETTED")
    assert updated["pipeline_stage"] == "VETTED"
