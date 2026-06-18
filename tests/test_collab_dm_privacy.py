"""DM rooms are only visible to the two participants."""
from __future__ import annotations

import uuid

import pytest

from backend.app.core.collab_schema import ensure_collab_schema
from backend.app.core.collab_service import (
    _create_dm_room,
    _register_connection,
    get_room,
    list_messages,
    list_rooms,
    send_message,
)
from backend.app.core.database import connect_data_db


@pytest.fixture
def dm_pair():
    ensure_collab_schema()
    user_a = f"dm-a-{uuid.uuid4().hex[:8]}"
    user_b = f"dm-b-{uuid.uuid4().hex[:8]}"
    outsider = f"dm-out-{uuid.uuid4().hex[:8]}"
    conn = connect_data_db()
    for uid, uname in ((user_a, "dm_alice"), (user_b, "dm_bob"), (outsider, "dm_carol")):
        conn.execute(
            "INSERT OR IGNORE INTO users (id, username) VALUES (?, ?)",
            (uid, uname),
        )
    conn.commit()
    conn.close()
    room = _create_dm_room(user_a, user_b)
    _register_connection(user_a, user_b, room["room_id"])
    send_message(user_a, room["room_id"], body="hello private", message_type="text")
    yield user_a, user_b, outsider, room["room_id"]
    conn = connect_data_db()
    conn.execute("DELETE FROM collab_messages WHERE room_id = ?", (room["room_id"],))
    conn.execute("DELETE FROM collab_room_members WHERE room_id = ?", (room["room_id"],))
    conn.execute("DELETE FROM collab_rooms WHERE room_id = ?", (room["room_id"],))
    conn.commit()
    conn.close()


def test_dm_hidden_from_non_member(dm_pair):
    user_a, user_b, outsider, room_id = dm_pair
    assert get_room(outsider, room_id) is None
    with pytest.raises(PermissionError):
        list_messages(outsider, room_id)
    outsider_rooms = list_rooms(outsider)
    assert room_id not in {r["room_id"] for r in outsider_rooms}


def test_dm_visible_to_participants(dm_pair):
    user_a, user_b, _outsider, room_id = dm_pair
    assert get_room(user_a, room_id) is not None
    assert get_room(user_b, room_id) is not None
    msgs = list_messages(user_b, room_id)
    assert any(m.get("body") == "hello private" for m in msgs)
