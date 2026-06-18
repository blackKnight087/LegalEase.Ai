"""Practice API — Litigation Desk (court-day + evidence-desk)."""
from __future__ import annotations

import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

def test_litigation_dashboard(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/litigation/dashboard")
    assert r.status_code == 200
    data = r.json()
    assert "today_hearings" in data
    assert "limitation_deadlines" in data
    assert "evidence_records" in data
    assert "evidence_pending_review" in data
    assert "tomorrow_hearings" in data
    assert "orders_awaiting_review" in data
    assert "upcoming_timeline" in data
    assert "urgent_alerts" in data
    assert "matter_health" in data


def test_litigation_analytics_computed(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/litigation/analytics")
    assert r.status_code == 200
    data = r.json()
    assert data.get("metrics_source") == "computed"
    assert "risk_factors" in data
    assert "court_workload" in data
    assert "lawyer_workload" in data


def test_litigation_hearing_create_and_patch(api_client, litigation_user):
    from backend.app.core.matter_repo import list_matters

    matter_id = list_matters(litigation_user)[0]["matter_id"]
    r = api_client.post(
        "/api/v1/practice/litigation/hearings",
        json={
            "matter_id": matter_id,
            "hearing_date": "2025-04-01",
            "court_name": "Delhi HC",
            "purpose": "Admission",
            "status": "scheduled",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    hearing = body.get("hearing") or {}
    hid = hearing.get("hearing_id")
    assert hid
    r2 = api_client.patch(
        f"/api/v1/practice/litigation/hearings/{hid}",
        json={"status": "prepared"},
    )
    assert r2.status_code == 200


def test_litigation_tasks_crud(api_client, litigation_user):
    from backend.app.core.matter_repo import list_matters

    matter_id = list_matters(litigation_user)[0]["matter_id"]
    r = api_client.post(
        "/api/v1/practice/litigation/tasks",
        json={"matter_id": matter_id, "title": "Collect Evidence", "due_date": "2025-04-15", "assignee": "Counsel"},
    )
    assert r.status_code == 200
    task_id = r.json().get("task_id")
    assert task_id
    r2 = api_client.patch(
        f"/api/v1/practice/litigation/tasks/{task_id}",
        json={"status": "done"},
    )
    assert r2.status_code == 200
    r3 = api_client.delete(f"/api/v1/practice/litigation/tasks/{task_id}")
    assert r3.status_code == 200


def test_litigation_orders_crud(api_client, litigation_user):
    from backend.app.core.matter_repo import list_matters

    matter_id = list_matters(litigation_user)[0]["matter_id"]
    r = api_client.post(
        "/api/v1/practice/litigation/orders",
        json={"matter_id": matter_id, "title": "Interim order", "order_type": "interim_order", "summary": ""},
    )
    assert r.status_code == 200
    order_id = r.json().get("order_id")
    assert order_id
    r2 = api_client.patch(
        f"/api/v1/practice/litigation/orders/{order_id}",
        json={"summary": "Stay granted", "judge": "Justice Singh"},
    )
    assert r2.status_code == 200
    r3 = api_client.delete(f"/api/v1/practice/litigation/orders/{order_id}")
    assert r3.status_code == 200


def test_litigation_limitation_deadlines(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/litigation/limitation/deadlines")
    assert r.status_code == 200
    assert "deadlines" in r.json()


def test_litigation_notifications(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/litigation/notifications")
    assert r.status_code == 200
    data = r.json()
    assert "notifications" in data
    assert "unread_count" in data


def test_court_sync_history(api_client, litigation_user):
    api_client.post(
        "/api/v1/practice/court-sync",
        json={"source": "paste", "text": SAMPLE_CAUSE_LIST, "auto_schedule": True},
    )
    r = api_client.get("/api/v1/practice/court-sync/history")
    assert r.status_code == 200
    assert len(r.json().get("history") or []) >= 1


def test_prep_pack_pdf(api_client, litigation_user):
    from backend.app.core.matter_repo import list_matters

    matter_id = list_matters(litigation_user)[0]["matter_id"]
    r = api_client.get(f"/api/v1/practice/court-day/prep/{matter_id}/pdf?use_ai=0")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/pdf")
    assert len(r.content) > 100


def test_litigation_diagnostics(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/litigation/diagnostics")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "modules" in data
    assert "table_counts" in data
    assert data.get("overall_status") in ("ok", "partial", "empty", "error")
    assert "routes" in data
    assert "checks" in data
    assert "llm_health" in data


SAMPLE_CAUSE_LIST = (
    "15-03-2025\nBefore Honble Justice Singh\n"
    "WP 99/2024 Sharma v State listed for admission\n"
)


@pytest.fixture
def api_client():
    from backend.app.main import app

    return TestClient(app)


@pytest.fixture
def litigation_user(api_client, monkeypatch, tmp_path):
    from backend.app.core.auth import get_current_user
    from backend.app.main import app
    from backend.app.core.practice_schema import ensure_practice_schema
    from backend.app.core.saas_schema import ensure_saas_schema
    from backend.app.core.matter_repo import create_matter

    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "litigation_api.db"))
    ensure_practice_schema()
    ensure_saas_schema()

    uid = f"lit-api-{uuid.uuid4().hex[:8]}"

    create_matter(
        uid,
        matter_name="Sharma v State",
        practice_area="Civil",
        case_number="WP 99/2024",
        client_name="Sharma",
        opposing_party="State",
        venue="Delhi HC",
    )

    def fake_user():
        return {"id": uid, "username": "lit", "membership": "Pro", "role": "user"}

    app.dependency_overrides[get_current_user] = fake_user
    yield uid
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_study_routes_removed(api_client):
    r = api_client.post("/api/v1/study/irac", json={"question": "test"})
    assert r.status_code == 404


@pytest.mark.integration
def test_court_day_parse(api_client, litigation_user):
    r = api_client.post(
        "/api/v1/practice/court-day/parse",
        json={"text": SAMPLE_CAUSE_LIST},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("parsed_count", 0) >= 1


@pytest.mark.integration
def test_court_sync_paste(api_client, litigation_user):
    r = api_client.post(
        "/api/v1/practice/court-sync",
        json={"source": "paste", "text": SAMPLE_CAUSE_LIST, "auto_schedule": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert (body.get("parsed") or {}).get("parsed_count", 0) >= 1
    scheduled = body.get("scheduled_hearings") or []
    assert scheduled
    assert scheduled[0].get("inserted", 0) >= 1


@pytest.mark.integration
def test_court_sync_status(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/court-sync/status")
    assert r.status_code == 200
    body = r.json()
    assert "modes" in body
    assert any(m.get("id") == "paste" for m in body.get("modes") or [])


@pytest.mark.integration
def test_court_sync_ecourtsindia_mock(api_client, litigation_user, monkeypatch):
    from backend.app.core import ecourtsindia_client

    monkeypatch.setenv("ECOURTSINDIA_API_KEY", "eci_live_test_key_xxxxxxxxxxxxxxx")

    def _fake_search(api_key, **kwargs):
        return {
            "results": [
                {
                    "date": "2025-03-15",
                    "caseNumber": ["WP 99/2024"],
                    "party": "Sharma v State",
                    "judge": ["Justice Singh"],
                    "courtName": "Delhi HC",
                    "status": "ADMISSION",
                }
            ],
            "returned_count": 1,
            "limit": 50,
            "offset": 0,
            "query_params": kwargs,
            "request_id": "test-req",
        }

    monkeypatch.setattr(ecourtsindia_client, "search_cause_list", _fake_search)
    r = api_client.post(
        "/api/v1/practice/court-sync",
        json={
            "source": "ecourtsindia",
            "api_date": "2025-03-15",
            "api_state": "DL",
            "auto_schedule": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("source") == "ecourtsindia"
    assert (body.get("scheduled_hearings") or [{}])[0].get("inserted", 0) >= 1


@pytest.mark.integration
def test_ecourts_case_preview_mock(api_client, litigation_user, monkeypatch):
    from backend.app.core import ecourtsindia_client

    monkeypatch.setenv("ECOURTSINDIA_API_KEY", "eci_live_test_key_xxxxxxxxxxxxxxx")

    def _fake_case(api_key, cnr):
        return {
            "cnr": cnr,
            "data": {
                "courtCaseData": {
                    "cnr": cnr,
                    "caseStatus": "PENDING",
                    "courtName": "Delhi HC",
                    "petitioners": ["Sharma"],
                    "respondents": ["State"],
                    "nextHearingDate": "2025-04-01",
                    "orderCount": 2,
                    "historyOfCaseHearings": [
                        {
                            "businessOnDate": "2025-03-01",
                            "hearingDate": "2025-03-15",
                            "purposeOfListing": "Admission",
                            "judge": "Justice Singh",
                        }
                    ],
                    "interimOrders": [
                        {"orderDate": "2025-03-01", "description": "Interim order", "orderUrl": "o1.pdf"}
                    ],
                }
            },
            "request_id": "test-case",
        }

    monkeypatch.setattr(ecourtsindia_client, "get_case_by_cnr", _fake_case)
    r = api_client.get("/api/v1/practice/ecourts/case/DLHC010001232024")
    assert r.status_code == 200
    body = r.json()
    assert body.get("cnr") == "DLHC010001232024"
    assert body.get("parties") == "Sharma v State"
    assert body.get("order_count") == 2


@pytest.mark.integration
def test_ecourts_case_sync_mock(api_client, litigation_user, monkeypatch):
    from backend.app.core import ecourtsindia_client
    from backend.app.core.matter_repo import list_matters

    monkeypatch.setenv("ECOURTSINDIA_API_KEY", "eci_live_test_key_xxxxxxxxxxxxxxx")
    matters = list_matters(litigation_user)
    matter_id = matters[0]["matter_id"]

    def _fake_case(api_key, cnr):
        return {
            "cnr": cnr,
            "data": {
                "courtCaseData": {
                    "cnr": cnr,
                    "caseStatus": "PENDING",
                    "registrationNumber": "WP 99/2024",
                    "courtName": "Delhi HC",
                    "petitioners": ["Sharma"],
                    "respondents": ["State"],
                    "nextHearingDate": "2025-04-01",
                    "historyOfCaseHearings": [
                        {
                            "businessOnDate": "2025-03-15",
                            "hearingDate": "2025-03-15",
                            "purposeOfListing": "Admission",
                        }
                    ],
                    "interimOrders": [
                        {"orderDate": "2025-03-01", "description": "Interim order", "orderUrl": "o1.pdf"}
                    ],
                }
            },
            "request_id": "test-sync",
        }

    monkeypatch.setattr(ecourtsindia_client, "get_case_by_cnr", _fake_case)
    r = api_client.post(
        "/api/v1/practice/ecourts/case/DLHC010001232024/sync",
        json={"matter_id": matter_id, "import_hearings": True, "import_orders": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("hearings_imported", 0) >= 1
    assert body.get("orders_imported", 0) >= 1


@pytest.mark.integration
def test_ecourts_search_mock(api_client, litigation_user, monkeypatch):
    from backend.app.core import ecourtsindia_client

    monkeypatch.setenv("ECOURTSINDIA_API_KEY", "eci_live_test_key_xxxxxxxxxxxxxxx")

    def _fake_search(api_key, **kwargs):
        return {
            "results": [
                {
                    "cnr": "DLHC010001232024",
                    "caseStatus": "PENDING",
                    "petitioners": ["Sharma"],
                    "respondents": ["State"],
                    "nextHearingDate": "2025-04-01",
                }
            ],
            "raw": {"totalHits": 1},
            "page": 1,
            "request_id": "test-search",
        }

    monkeypatch.setattr(ecourtsindia_client, "search_cases", _fake_search)
    r = api_client.get("/api/v1/practice/ecourts/search?advocates=Sharma")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert len(body.get("results") or []) == 1


@pytest.mark.integration
def test_evidence_desk_export(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/evidence-desk/export")
    assert r.status_code == 200
    assert "Litigation Evidence Desk" in r.text


@pytest.mark.integration
def test_court_day_today(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/court-day/today")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "digest" in body


@pytest.mark.integration
def test_evidence_desk_get(api_client, litigation_user):
    r = api_client.get("/api/v1/practice/evidence-desk")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "summary" in body
    assert "contradictions" in body


@pytest.mark.integration
def test_evidence_desk_scan(api_client, litigation_user):
    r = api_client.post("/api/v1/practice/evidence-desk/scan?max_matters=1")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "scanned" in body
