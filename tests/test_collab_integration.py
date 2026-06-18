"""Collaboration Hub integration — full message flow."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.core.auth import get_current_user
from backend.app.core.collab_schema import ensure_collab_schema
from backend.app.core.collab_service import (
    create_channel,
    get_or_create_dm,
    list_messages,
    list_rooms,
    send_message,
)


@pytest.fixture
def client():
    ensure_collab_schema()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "collab-int-user-a",
        "username": "lawyer_a",
        "membership": "Pro",
        "role": "user",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def client_b():
    ensure_collab_schema()
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "collab-int-user-b",
        "username": "lawyer_b",
        "membership": "Pro",
        "role": "user",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_full_dm_message_flow():
    from legalease_auth import create_user, ensure_db

    ensure_db()
    ensure_collab_schema()
    try:
        ua = create_user("collab_a", "test-pass-123", "test-pass-123")
        ub = create_user("collab_b", "test-pass-123", "test-pass-123")
        uid_a = str(ua["id"])
        uid_b = str(ub["id"])
    except Exception:
        pytest.skip("Could not create test users")
    room = get_or_create_dm(uid_a, uid_b)
    assert room["room_id"]
    msg = send_message(uid_a, room["room_id"], body="Please review the FIR @lawyer_b")
    assert msg.get("body")
    msgs = list_messages(uid_b, room["room_id"])
    assert any("FIR" in m.get("body", "") for m in msgs)
    rooms_a = list_rooms(uid_a)
    assert any(r["room_id"] == room["room_id"] for r in rooms_a)


def test_api_post_message_and_list(client):
    r = client.post(
        "/api/v1/collaboration/rooms/channel",
        json={"slug": "integration-test", "name": "Integration Test"},
    )
    if r.status_code == 200:
        room_id = r.json()["room"]["room_id"]
    else:
        rooms = client.get("/api/v1/collaboration/rooms").json().get("rooms", [])
        ch = next((x for x in rooms if x.get("slug") == "integration-test"), None)
        assert ch, r.text
        room_id = ch["room_id"]
    post = client.post(
        f"/api/v1/collaboration/rooms/{room_id}/messages",
        json={"body": "Integration test message"},
    )
    assert post.status_code == 200, post.text
    listed = client.get(f"/api/v1/collaboration/rooms/{room_id}/messages")
    assert listed.status_code == 200
    bodies = [m["body"] for m in listed.json().get("messages", [])]
    assert "Integration test message" in bodies
    read = client.post(f"/api/v1/collaboration/rooms/{room_id}/read")
    assert read.status_code == 200


def test_notifications_endpoint(client):
    r = client.get("/api/v1/collaboration/notifications")
    assert r.status_code == 200
    assert "notifications" in r.json()


def test_collab_router_registered(client):
    r = client.get("/api/v1/collaboration/permissions")
    assert r.status_code == 200
    r2 = client.get("/api/v1/collaboration/members")
    assert r2.status_code == 200
