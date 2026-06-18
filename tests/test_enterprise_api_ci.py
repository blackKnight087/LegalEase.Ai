"""Enterprise API CI smoke — branding, agents, court, pilot, SSO."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.auth import get_current_user
from backend.app.core.admin_auth import require_superadmin


@pytest.fixture
def client():
    user = {
        "id": "enterprise-ci-user",
        "username": "admin",
        "membership": "Pro",
        "role": "admin",
        "org_id": "",
    }
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[require_superadmin] = lambda: user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.ci_gate
def test_enterprise_branding(client):
    r = client.get("/api/v1/enterprise/branding")
    assert r.status_code == 200
    data = r.json()
    assert "branding" in data


@pytest.mark.ci_gate
def test_enterprise_agents_list(client):
    r = client.get("/api/v1/enterprise/agents")
    assert r.status_code == 200
    agents = r.json().get("agents", [])
    assert len(agents) >= 4
    assert "matter_agent" in {a["id"] for a in agents}


@pytest.mark.ci_gate
def test_enterprise_court_status(client):
    r = client.get("/api/v1/enterprise/court/status")
    assert r.status_code == 200
    body = r.json()
    assert "live_api_enabled" in body
    assert "supported_sources" in body


@pytest.mark.ci_gate
def test_enterprise_pilot_summary(client):
    r = client.get("/api/v1/enterprise/pilot/summary")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


@pytest.mark.ci_gate
def test_sso_status_public():
    with TestClient(app) as anon:
        r = anon.get("/api/v1/sso/status")
    assert r.status_code == 200
    st = r.json()
    assert "enabled" in st
    assert "oidc_configured" in st
