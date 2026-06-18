"""Integration tests — dashboard, public intake, matter-linked upload."""
from __future__ import annotations

import os
import uuid

import pytest


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "int.db"))
    from backend.app.core.practice_schema import ensure_practice_schema
    from backend.app.core.saas_schema import ensure_saas_schema

    ensure_practice_schema()
    ensure_saas_schema()


def test_practice_overview_counts():
    from backend.app.core.matter_repo import create_matter
    from backend.app.core.billing_service import log_time_entry
    from backend.app.core.crm_service import create_lead
    from backend.app.services.practice_dashboard import practice_overview

    uid = f"u-{uuid.uuid4().hex[:6]}"
    mid = create_matter(uid, matter_name="Test", practice_area="Criminal")["matter_id"]
    log_time_entry(uid, matter_id=mid, raw_activity="Bail research", units_logged=1, rate_per_unit=1000)
    create_lead(uid, prospect_name="A", contact_email="a@b.com", raw_intake_query="FIR bail help needed")
    ov = practice_overview(uid)
    assert ov["matters_total"] >= 1
    assert ov["billing"]["unbilled_entries"] >= 1
    assert ov["crm"]["leads_total"] >= 1


def test_matter_dashboard_workflow():
    from backend.app.core.matter_repo import create_matter
    from backend.app.core.matter_workflow import (
        add_deadline,
        add_task,
        get_matter_dashboard,
    )
    from backend.app.core.crm_service import analyze_intake_query, convert_lead_to_matter, create_lead

    uid = f"u-{uuid.uuid4().hex[:6]}"
    mid = create_matter(
        uid,
        matter_name="Ramesh v State",
        practice_area="Criminal",
        client_name="Ramesh Gupta",
        venue="Calcutta High Court",
    )["matter_id"]
    add_task(uid, mid, title="File bail application", due_date="2026-06-01")
    add_deadline(uid, mid, title="Limitation check", due_date="2026-05-30")
    dash = get_matter_dashboard(uid, mid)
    assert dash["matter"]["matter_name"] == "Ramesh v State"
    assert dash["stats"]["open_tasks"] >= 1
    assert dash["rag_scope"] == "matter_only"

    analysis = analyze_intake_query("IPC 420 cheating in Kolkata", uid)
    assert analysis["case_type"] == "Criminal"
    assert "risk_score" in analysis

    lead = create_lead(
        uid,
        prospect_name="Test Lead",
        contact_email="t@t.com",
        raw_intake_query="Vendor fraud 5 lakh Kolkata IPC 420",
    )
    out = convert_lead_to_matter(uid, lead["lead_id"])
    assert out.get("converted")
    assert out["matter"]["matter_id"]


def test_saas_tuning_export(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "tune.db"))
    from backend.app.core.practice_schema import ensure_practice_schema
    from backend.app.core.saas_schema import ensure_saas_schema
    from backend.app.core.billing_service import record_lexicon_correction
    from backend.app.core.tuning_export import export_saas_training_pairs

    ensure_practice_schema()
    ensure_saas_schema()
    record_lexicon_correction("u1", "looked at section 437", "Devoted 2 hours to BNSS bail analysis.")
    out = export_saas_training_pairs("u1")
    assert out["status"] in ("ok", "empty")
