"""API chat endpoint tests with mocked KB backend."""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


@pytest.fixture
def authed_client():
    from backend.app.main import app

    def fake_user():
        return {"id": "chat-test-user", "username": "tester", "membership": "Pro", "role": "user"}

    from backend.app.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = fake_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.mark.integration
def test_chat_kb_mocked(authed_client):
    with patch("backend.app.services.chat_service.stream_chat_response") as mock_stream:
        def _fake_stream(*_a, **_k):
            yield 'data: {"type": "token", "content": "IPC 307 "}\n\n'
            yield (
                'data: {"type": "meta", "thread_id": "t1", "session_id": "s1", '
                '"follow_ups": [], "similar_cases": [], "web_sources": [], '
                '"answer": "IPC 307 attempt", "content": "IPC 307 attempt"}\n\n'
            )
            yield "data: [DONE]\n\n"

        mock_stream.side_effect = lambda *a, **k: _fake_stream()
        r = authed_client.post(
            "/api/v1/chat/stream",
            json={
                "message": "What is IPC 307?",
                "mode": "knowledge_base",
                "lang": "English",
                "history": [],
            },
        )
    assert r.status_code == 200
    assert "data:" in r.text


@pytest.mark.integration
def test_sessions_thread_load(authed_client, monkeypatch, tmp_path):
    import backend.app.core.chat_persistence as cp

    monkeypatch.setattr(cp, "DB_PATH", tmp_path / "thread_load.db")
    cp.ensure_chat_schema()
    saved = cp.save_chat_turn("chat-test-user", "Q1", "A1 about IPC 307", thread_id="tid-99")

    r = authed_client.get(f"/api/v1/sessions/threads/{saved['thread_id']}")
    assert r.status_code == 200
    data = r.json()
    assert len(data.get("messages", [])) >= 2
