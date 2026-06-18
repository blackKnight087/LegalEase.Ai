"""CRM 2.0 API — dashboard, kanban, extended create, analyze."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.auth import get_current_user
from backend.app.core.org_service import create_org_for_user
from backend.app.core.saas_schema import ensure_saas_schema


@pytest.fixture
def client():
    ensure_saas_schema()
    create_org_for_user("crm-v2-user", "crm_v2_tester")
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "crm-v2-user",
        "username": "crm_v2_tester",
        "membership": "Pro",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_crm_dashboard_and_kanban(client):
    dash = client.get("/api/v1/crm/dashboard")
    assert dash.status_code == 200
    assert "kpis" in dash.json()
    assert "funnel" in dash.json()

    kanban = client.get("/api/v1/crm/kanban")
    assert kanban.status_code == 200
    body = kanban.json()
    assert "columns" in body
    assert "NEW_INQUIRY" in body.get("stages", [])


def test_crm_extended_create_and_analyze(client):
    r = client.post(
        "/api/v1/crm",
        json={
            "prospect_name": "Test Lead",
            "contact_email": "test@example.com",
            "raw_intake_query": "Property dispute in Mumbai regarding ancestral land partition.",
            "city": "Mumbai",
            "referral_source": "unit_test",
        },
    )
    assert r.status_code == 200
    lead = r.json()
    lid = lead.get("lead_id")
    assert lid
    assert lead.get("lead_score") is not None

    detail = client.get(f"/api/v1/crm/{lid}")
    assert detail.status_code == 200
    assert detail.json().get("analysis") or detail.json().get("analysis_json")

    analyzed = client.post(f"/api/v1/crm/{lid}/analyze")
    assert analyzed.status_code == 200


def test_crm_follow_up_templates_and_assistant(client):
    r = client.post(
        "/api/v1/crm",
        json={
            "prospect_name": "Template Test",
            "contact_email": "tpl@example.com",
            "raw_intake_query": "Land dispute in Delhi needing mutation documents urgently.",
        },
    )
    lid = r.json()["lead_id"]
    tpls = client.get(f"/api/v1/crm/{lid}/follow-up/templates")
    assert tpls.status_code == 200
    assert len(tpls.json().get("templates", [])) >= 1
    tid = tpls.json()["templates"][0]["template_id"]
    applied = client.post(
        f"/api/v1/crm/{lid}/follow-up/apply",
        json={"template_id": tid},
    )
    assert applied.status_code == 200
    assert applied.json().get("draft")

    asst = client.post(
        "/api/v1/crm/assistant",
        json={"lead_id": lid, "action": "missing_documents"},
    )
    assert asst.status_code == 200
    assert "missing_documents" in asst.json()


def test_crm_convert_preview(client):
    r = client.post(
        "/api/v1/crm",
        json={
            "prospect_name": "Convert Me",
            "contact_email": "convert@example.com",
            "raw_intake_query": "Cheating case vendor took payment in Kolkata under IPC.",
        },
    )
    lid = r.json()["lead_id"]
    prev = client.post(f"/api/v1/crm/{lid}/convert/preview")
    assert prev.status_code == 200
    assert prev.json().get("matter_preview")
