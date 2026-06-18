"""Session store — memory fallback (no Redis required in CI)."""
from backend.app.core import session_store


def test_session_roundtrip_memory():
    session_store._MEMORY.clear()
    session_store._redis_checked = True
    session_store._redis_client = None

    sid = "test-session-1"
    session_store.set_session(sid, {"history": [{"role": "user", "content": "hi"}], "state": {}})
    data = session_store.get_session(sid)
    assert len(data["history"]) == 1
    assert data["history"][0]["content"] == "hi"
    assert session_store.backend_name() == "memory"


def test_conversation_memory_uses_store():
    from backend.app.core.conversation_memory import append_turn, get_session_history

    session_store._MEMORY.clear()
    session_store._redis_checked = True
    session_store._redis_client = None

    sid = "conv-test-1"
    append_turn(sid, "user", "What is IPC 302?")
    hist = get_session_history(sid)
    assert len(hist) >= 1
    assert "IPC" in hist[-1]["content"]
