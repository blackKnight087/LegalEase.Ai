"""CRM Intake Command Center API."""
from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


@pytest.fixture
def api_client():
    from backend.app.main import app

    return TestClient(app)


@pytest.fixture
def crm_user(api_client, monkeypatch, tmp_path):
    from backend.app.core.auth import get_current_user
    from backend.app.main import app
    from backend.app.core.crm_schema import ensure_crm_v2_schema
    from backend.app.core.saas_schema import ensure_saas_schema
    from backend.app.core.crm_v2_service import create_lead_extended

    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "crm_cc.db"))
    ensure_crm_schema = ensure_crm_v2_schema
    ensure_crm_schema()
    ensure_saas_schema()

    uid = f"crm-cc-{uuid.uuid4().hex[:8]}"

    create_lead_extended(
        uid,
        prospect_name="Rahul Sharma",
        contact_email="rahul@example.com",
        raw_intake_query="Property dispute with builder — need urgent consultation",
        referral_source="Website",
    )

    def fake_user():
        return {"id": uid, "username": "crm", "membership": "Pro", "role": "user"}

    app.dependency_overrides[get_current_user] = fake_user
    yield uid
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_command_center(api_client, crm_user):
    r = api_client.get("/api/v1/crm/command-center")
    assert r.status_code == 200
    body = r.json()
    assert body.get("has_leads") is True
    assert body.get("kpis", {}).get("total", 0) >= 1
    assert "public_portal" in body
    assert "urgent_leads" in body
    assert "pipeline_value" in body
