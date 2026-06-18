from __future__ import annotations

import os
import tempfile
import uuid

import pytest
from fastapi import HTTPException


@pytest.fixture
def practice_db(monkeypatch):
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setenv("LEGALEASE_DB_PATH", path)
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


def test_archive_and_include_archived_filter(practice_db):
    from backend.app.core.matter_repo import archive_matter, create_matter, list_matters

    uid = f"u-{uuid.uuid4().hex[:8]}"
    created = create_matter(uid, matter_name="Archive Regression", practice_area="Civil")
    mid = created["matter_id"]

    assert len(list_matters(uid, include_archived=False)) == 1
    assert archive_matter(uid, mid) is True

    active = list_matters(uid, include_archived=False)
    all_rows = list_matters(uid, include_archived=True)
    assert len(active) == 0
    assert len(all_rows) == 1
    assert int(all_rows[0].get("is_archived") or 0) == 1


def test_member_access_context_resolves_owner(practice_db):
    from backend.app.core.database import connect_sqlite
    from backend.app.core.matter_repo import create_matter, get_matter_access_context

    owner_id = f"owner-{uuid.uuid4().hex[:6]}"
    member_id = f"member-{uuid.uuid4().hex[:6]}"
    mid = create_matter(owner_id, matter_name="Member Context", practice_area="Criminal")["matter_id"]

    conn = connect_sqlite()
    conn.execute(
        """
        INSERT INTO matter_members (member_id, matter_id, user_id, role, created_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        """,
        (str(uuid.uuid4()), mid, member_id, "viewer"),
    )
    conn.commit()
    conn.close()

    ctx = get_matter_access_context(member_id, mid)
    assert ctx is not None
    assert ctx["owner_user_id"] == owner_id
    assert ctx["role"] == "viewer"


def test_chat_scope_rejects_unauthorized_matter(practice_db):
    from backend.app.api.v1.endpoints.chat import _validated_scope
    from backend.app.core.matter_repo import create_matter

    owner_id = f"owner-{uuid.uuid4().hex[:6]}"
    intruder_id = f"intruder-{uuid.uuid4().hex[:6]}"
    mid = create_matter(owner_id, matter_name="Scope Guard", practice_area="General")["matter_id"]

    with pytest.raises(HTTPException) as exc:
        _validated_scope(intruder_id, "knowledge_base", mid)
    assert exc.value.status_code == 404


def test_chat_scope_strips_matter_for_open_law(practice_db):
    from backend.app.api.v1.endpoints.chat import _validated_scope
    from backend.app.core.matter_repo import create_matter

    uid = f"u-{uuid.uuid4().hex[:8]}"
    mid = create_matter(uid, matter_name="Mode Separation", practice_area="General")["matter_id"]
    assert _validated_scope(uid, "open_law", mid) is None
