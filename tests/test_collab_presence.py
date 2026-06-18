"""Collaboration presence tests."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.ci_gate

from backend.app.core.collab_presence import heartbeat, list_online


def test_presence_heartbeat_memory():
    out = heartbeat("user-p1", "org-p1", room_id="room-1", display_name="Alice")
    assert out.get("ok") is True
    online = list_online("org-p1", room_id="room-1")
    ids = {o["user_id"] for o in online}
    assert "user-p1" in ids


def test_presence_filters_by_room():
    heartbeat("user-p2", "org-p2", room_id="room-a")
    heartbeat("user-p3", "org-p2", room_id="room-b")
    a_only = list_online("org-p2", room_id="room-a")
    assert all(o.get("room_id") == "room-a" for o in a_only)
