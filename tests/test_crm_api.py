"""CRM intake API smoke tests."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.auth import get_current_user


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "crm-test-user",
        "username": "crm_tester",
        "membership": "Pro",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_crm_classify_returns_fast(client):
    with patch(
        "backend.app.core.llm_orchestrator.generate_for_task",
        return_value={"ok": False, "text": "", "error": "timeout"},
    ):
        r = client.post(
            "/api/v1/crm/classify",
            json={
                "query": (
                    "Vendor took 5 lakhs down payment in Kolkata and vanished. Cheating under IPC."
                )
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("intent")
    assert data.get("risk_score") is not None
    assert data.get("legal_analysis")


def test_crm_pipeline_and_list(client):
    stages = client.get("/api/v1/crm/pipeline-stages")
    assert stages.status_code == 200
    assert "NEW_INQUIRY" in stages.json().get("stages", [])

    leads = client.get("/api/v1/crm")
    assert leads.status_code == 200
    assert "leads" in leads.json()
