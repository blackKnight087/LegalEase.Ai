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
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "0")
    from backend.app.middleware import rate_limit as rate_limit_mod

    monkeypatch.setattr(rate_limit_mod, "_ENABLED", False)
    from backend.app.main import app
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    client = TestClient(app)
    yield client, app, path
    app.dependency_overrides.clear()
    try:
        os.unlink(path)
    except OSError:
        pass


def _override_user(app, user_obj):
    from backend.app.core.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user_obj


def test_member_viewer_read_but_cannot_write(api_client_with_db):
    client, app, _ = api_client_with_db
    from backend.app.core.database import connect_sqlite
    from backend.app.core.matter_repo import create_matter

    owner_id = f"owner-{uuid.uuid4().hex[:6]}"
    viewer_id = f"viewer-{uuid.uuid4().hex[:6]}"
    matter = create_matter(owner_id, matter_name="Viewer Matrix", practice_area="Civil")

    conn = connect_sqlite()
    conn.execute(
        "INSERT INTO matter_members (member_id, matter_id, user_id, role, created_at) VALUES (?, ?, ?, ?, datetime('now'))",
        (str(uuid.uuid4()), matter["matter_id"], viewer_id, "viewer"),
    )
    conn.commit()
    conn.close()

    _override_user(app, {"id": viewer_id, "username": "v", "membership": "Pro", "role": "user"})
    r_get = client.get(f"/api/v1/matters/{matter['matter_id']}")
    assert r_get.status_code == 200

    r_patch = client.patch(
        f"/api/v1/matters/{matter['matter_id']}",
        json={"description": "viewer attempt"},
    )
    assert r_patch.status_code == 403


def test_archive_restore_and_hard_delete_contract(api_client_with_db):
    client, app, _ = api_client_with_db
    from backend.app.core.matter_repo import create_matter

    owner_id = f"owner-{uuid.uuid4().hex[:6]}"
    _override_user(app, {"id": owner_id, "username": "o", "membership": "Pro", "role": "user"})
    matter = create_matter(owner_id, matter_name="Archive Contract", practice_area="Criminal")
    mid = matter["matter_id"]

    r_archive = client.delete(f"/api/v1/matters/{mid}")
    assert r_archive.status_code == 200
    body = r_archive.json()
    assert body["archived"] is True
    assert body["deleted"] is False

    r_list_active = client.get("/api/v1/matters")
    assert r_list_active.status_code == 200
    ids_active = [m.get("matter_id") for m in r_list_active.json().get("matters", [])]
    assert mid not in ids_active

    r_restore = client.post(f"/api/v1/matters/{mid}/restore")
    assert r_restore.status_code == 200
    assert r_restore.json().get("restored") is True

    r_hard = client.delete(f"/api/v1/matters/{mid}?hard=true")
    assert r_hard.status_code == 200
    hard_body = r_hard.json()
    assert hard_body["deleted"] is True
    assert hard_body["archived"] is False


def test_learning_scope_promotion_admin_only(api_client_with_db, monkeypatch):
    monkeypatch.setenv("LEARNING_SCOPE_PROMOTION_ENABLED", "1")
    from backend.app.api.v1.endpoints import learning as learning_mod

    monkeypatch.setattr(learning_mod, "SCOPE_PROMOTION_ENABLED", True)

    client, app, _ = api_client_with_db
    from backend.app.core.adaptive_learning import ensure_learning_schema, record_interaction

    uid = f"user-{uuid.uuid4().hex[:6]}"
    ensure_learning_schema()
    record_interaction(
        uid,
        "knowledge_base",
        "test query",
        answer="test answer",
        found_in_kb=True,
        scope_key="matter:m1",
    )

    _override_user(app, {"id": "not-admin", "username": "u", "membership": "Pro", "role": "user"})
    forbidden = client.post(
        "/api/v1/learning/tuning/scope/promote",
        json={"user_id": uid, "matter_id": "m1", "limit": 10},
    )
    assert forbidden.status_code == 403

    _override_user(app, {"id": "admin-1", "username": "a", "membership": "Pro", "role": "admin"})
    ok = client.post(
        "/api/v1/learning/tuning/scope/promote",
        json={"user_id": uid, "matter_id": "m1", "limit": 10},
    )
    assert ok.status_code == 200
    payload = ok.json()
    assert payload.get("ok") is True
    assert payload.get("target_scope") == "global"
