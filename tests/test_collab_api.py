"""Collaboration Hub API smoke tests."""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.auth import get_current_user
from backend.app.core.collab_schema import ensure_collab_schema


@pytest.fixture
def client():
    ensure_collab_schema()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "collab-test-user",
        "username": "collab_tester",
        "membership": "Pro",
        "role": "user",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_collab_rate_limit_exempt():
    from backend.app.middleware.rate_limit import (
        _is_ai_chat_api_path,
        _skip_rate_limit,
        rate_limit_audit_report,
    )

    assert _skip_rate_limit("/api/v1/collaboration/rooms") is True
    assert _skip_rate_limit("/api/v1/collaboration/rooms/abc/messages") is True
    assert _skip_rate_limit("/api/v1/collaboration/rooms/abc/messages", "POST") is True
    assert _skip_rate_limit("/api/v1/speech/transcribe") is True
    assert _skip_rate_limit("/api/v1/collaboration/rooms/abc/typing") is True
    assert _skip_rate_limit("/api/v1/collaboration/ws") is True
    assert _skip_rate_limit("/api/v1/collaboration/notifications") is True
    assert _is_ai_chat_api_path("/api/v1/collaboration/rooms") is False
    assert _skip_rate_limit("/api/v1/chat/query") is True
    assert _skip_rate_limit("/api/v1/auth/login", "POST") is False
    from backend.app.middleware.rate_limit import _is_read_heavy, _limit_for_path

    assert _is_read_heavy("/api/v1/sessions/history", "GET") is True
    assert _is_read_heavy("/api/v1/sessions/threads/abc-123", "GET") is True
    assert _limit_for_path("/api/v1/sessions/history", "GET")[1] == "read"
    assert _limit_for_path("/api/v1/health/stability", "GET")[1] == "read"
    audit = rate_limit_audit_report()
    assert audit["collab_exempt"] is True
    assert "/api/v1/collaboration" in audit["messaging_exempt_paths"][0]


def test_collab_permissions(client):
    r = client.get("/api/v1/collaboration/permissions")
    assert r.status_code == 200
    perms = r.json()["permissions"]
    assert perms["view"] is True
    assert perms["post"] is True
    assert perms.get("included_free") is True
    assert perms.get("dm") is True


def test_collab_list_rooms(client):
    r = client.get("/api/v1/collaboration/rooms")
    assert r.status_code == 200
    assert "rooms" in r.json()


def test_collab_search(client):
    r = client.get("/api/v1/collaboration/search", params={"q": "general"})
    assert r.status_code == 200
    assert "rooms" in r.json()


def test_collab_user_search_short_query(client):
    r = client.get("/api/v1/collaboration/users/search", params={"q": "a"})
    assert r.status_code == 200
    data = r.json()
    assert data["users"] == []
    assert "hint" in data


def test_collab_chat_requests_list(client):
    r = client.get("/api/v1/collaboration/requests")
    assert r.status_code == 200
    data = r.json()
    assert "incoming" in data
    assert "outgoing" in data


@pytest.mark.ci_gate
def test_collab_room_stream_emits_events(client, monkeypatch):
    from backend.app.api.v1.endpoints.collab import collab_room_event_stream

    sample = {
        "message_id": "msg-stream-1",
        "room_id": "room-stream-1",
        "body": "hello stream",
        "created_at": "2025-06-01T12:00:00Z",
    }
    monkeypatch.setattr(
        "backend.app.api.v1.endpoints.collab.list_messages",
        lambda *a, **k: [sample],
    )

    async def collect() -> str:
        body = ""
        agen = collab_room_event_stream(
            "collab-test-user", "room-stream-1", poll_interval=0
        )
        async for chunk in agen:
            body += chunk
            if "hello stream" in body:
                await agen.aclose()
                break
        return body

    body = asyncio.run(collect())
    assert "event: connected" in body
    assert "event: message" in body
    payload = json.loads(
        body.split("event: message", 1)[1].split("data: ", 1)[1].split("\n", 1)[0]
    )
    assert payload["message_id"] == sample["message_id"]


@pytest.mark.ci_gate
def test_collab_room_stream_requires_auth():
    r = TestClient(app).get("/api/v1/collaboration/rooms/room-stream-1/stream")
    assert r.status_code == 401


def test_collab_room_member_uses_postgres_on_conflict(monkeypatch):
    """Channel creation adds members via ON CONFLICT on Postgres, not INSERT OR IGNORE."""
    from backend.app.core import collab_service
    from backend.app.core import sql_compat

    executed: list[tuple[str, tuple]] = []

    class FakeConn:
        def execute(self, sql, params=()):
            executed.append((str(sql).strip(), tuple(params)))

        def commit(self):
            pass

        def close(self):
            pass

    monkeypatch.setattr(collab_service, "ensure_collab_schema", lambda: None)
    monkeypatch.setattr(collab_service, "connect_data_db", lambda: FakeConn())
    monkeypatch.setattr(sql_compat, "use_postgres_legacy", lambda: True)

    collab_service._add_room_member("room-pg-1", "user-pg-1", role="member")

    assert executed
    sql = executed[0][0]
    assert "ON CONFLICT (room_id, user_id) DO NOTHING" in sql
    assert "INSERT OR IGNORE" not in sql
    assert executed[0][1][0] == "room-pg-1"
    assert executed[0][1][1] == "user-pg-1"
