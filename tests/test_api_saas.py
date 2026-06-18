"""SaaS API smoke and contract tests (FastAPI TestClient)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


@pytest.fixture
def api_client():
    from backend.app.main import app

    return TestClient(app)


@pytest.mark.integration
def test_health_live(api_client):
    r = api_client.get("/api/v1/health/live")
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert data.get("live") is True


@pytest.mark.integration
def test_chat_requires_auth(api_client):
    r = api_client.post(
        "/api/v1/chat",
        json={"message": "What is IPC 307?", "mode": "knowledge_base", "lang": "English", "history": []},
    )
    assert r.status_code == 401


@pytest.mark.integration
def test_sessions_history_requires_auth(api_client):
    r = api_client.get("/api/v1/sessions/history")
    assert r.status_code == 401


@pytest.mark.integration
def test_openapi_docs_available(api_client):
    r = api_client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert "/api/v1/chat" in spec.get("paths", {}) or any("chat" in p for p in spec.get("paths", {}))


@pytest.mark.integration
def test_authenticated_sessions_history(api_client, monkeypatch, tmp_path):
    from backend.app.core.auth import get_current_user
    from backend.app.main import app
    import backend.app.core.chat_persistence as cp

    def fake_user():
        return {"id": "saas-test-user", "username": "saas", "membership": "Pro", "role": "user"}

    monkeypatch.setattr(cp, "DB_PATH", tmp_path / "api_test.db")
    cp.ensure_chat_schema()
    cp.save_chat_turn("saas-test-user", "Test Q", "Test A")

    app.dependency_overrides[get_current_user] = fake_user
    try:
        r = api_client.get("/api/v1/sessions/history?limit=10")
        assert r.status_code == 200
        body = r.json()
        assert body.get("count", 0) >= 1
        assert len(body.get("sessions", [])) >= 1
    finally:
        app.dependency_overrides.clear()


@pytest.mark.integration
def test_delete_chat_thread(api_client, monkeypatch, tmp_path):
    from backend.app.core.auth import get_current_user
    from backend.app.main import app
    import backend.app.core.chat_persistence as cp

    uid = "saas-delete-user"

    def fake_user():
        return {"id": uid, "username": "saas", "membership": "Pro", "role": "user"}

    monkeypatch.setattr(cp, "DB_PATH", tmp_path / "api_del.db")
    cp.ensure_chat_schema()
    saved = cp.save_chat_turn(uid, "Delete me?", "Answer", thread_id="thread-del-1")

    app.dependency_overrides[get_current_user] = fake_user
    try:
        r = api_client.delete(
            f"/api/v1/sessions/threads/{saved['thread_id']}"
        )
        assert r.status_code == 200
        assert r.json().get("status") == "deleted"
        assert cp.load_chat_thread(uid, saved["thread_id"]) == []
        r2 = api_client.get("/api/v1/sessions/history?limit=10")
        ids = [s.get("thread_id") for s in r2.json().get("sessions", [])]
        assert saved["thread_id"] not in ids
    finally:
        app.dependency_overrides.clear()
