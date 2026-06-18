from __future__ import annotations

import os
import tempfile
import uuid

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


@pytest.fixture
def api_client_with_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("LEGALEASE_DB_PATH", path)
    from backend.app.main import app
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    client = TestClient(app)
    yield client, app
    app.dependency_overrides.clear()
    try:
        os.unlink(path)
    except OSError:
        pass


def _override_user(app, user_obj):
    from backend.app.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user_obj


def test_e2e_matter_upload_chat_lifecycle_mocked(api_client_with_db, monkeypatch):
    client, app = api_client_with_db
    owner_id = f"owner-{uuid.uuid4().hex[:6]}"
    _override_user(app, {"id": owner_id, "username": "owner", "membership": "Pro", "role": "owner"})

    create_res = client.post(
        "/api/v1/matters",
        json={"matter_name": "E2E Matter", "practice_area": "Civil"},
    )
    assert create_res.status_code == 200
    mid = create_res.json()["matter_id"]

    async def _fake_upload_document(*args, **kwargs):
        return {
            "ok": True,
            "message": "mock upload accepted",
            "file_id": "doc-e2e-1",
            "pages": 1,
            "kb_total_chunks": 1,
            "indexing_ok": True,
            "index_job_id": "",
            "filename": "x.pdf",
            "index_status": "ready",
        }

    import backend.app.api.v1.endpoints.documents as docs_ep

    monkeypatch.setattr(docs_ep, "upload_document", _fake_upload_document)

    upload_res = client.post(
        f"/api/v1/matters/{mid}/documents/upload?ocr=0",
        files={"file": ("x.pdf", b"%PDF-1.4\nfake", "application/pdf")},
    )
    assert upload_res.status_code == 200
    assert upload_res.json().get("ok") is True

    captured = {}

    def _fake_run_chat_turn(user_id, prompt, mode, **kwargs):
        captured["matter_id"] = kwargs.get("matter_id")
        return (
            "Mock scoped answer",
            [],
            [],
            [],
            {},
            "sid-1",
            {"chat_id": "c1", "thread_id": "t1", "interaction_id": "i1"},
        )

    import backend.app.api.v1.endpoints.chat as chat_ep

    monkeypatch.setattr(chat_ep, "run_chat_turn", _fake_run_chat_turn)

    chat_res = client.post(
        "/api/v1/chat",
        json={
            "message": "What does this matter say?",
            "mode": "knowledge_base",
            "matter_id": mid,
            "history": [],
        },
    )
    assert chat_res.status_code == 200
    assert chat_res.json()["content"] == "Mock scoped answer"
    assert captured.get("matter_id") == mid

    archive_res = client.delete(f"/api/v1/matters/{mid}")
    assert archive_res.status_code == 200
    assert archive_res.json()["archived"] is True

    restore_res = client.post(f"/api/v1/matters/{mid}/restore")
    assert restore_res.status_code == 200
    assert restore_res.json()["restored"] is True

    delete_res = client.delete(f"/api/v1/matters/{mid}?hard=true")
    assert delete_res.status_code == 200
    assert delete_res.json()["deleted"] is True
