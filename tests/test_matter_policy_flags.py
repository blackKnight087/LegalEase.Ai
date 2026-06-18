from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException


def test_scope_flag_disables_strict_validation(monkeypatch):
    monkeypatch.setenv("MATTER_STRICT_SCOPE_ENFORCEMENT", "0")
    import backend.app.core.matter_policy as policy

    importlib.reload(policy)
    out = policy.validate_chat_scope("non-owner", "knowledge_base", "fake-matter")
    assert out == "fake-matter"


def test_role_flag_disables_write_restrictions(monkeypatch):
    monkeypatch.setenv("MATTER_STRICT_ROLE_WRITE", "0")
    import backend.app.core.matter_policy as policy

    importlib.reload(policy)
    policy.require_matter_write_access({"role": "viewer", "request_user_id": "u1", "owner_user_id": "u2"})


def test_role_enforcement_blocks_viewer_when_enabled(monkeypatch):
    monkeypatch.setenv("MATTER_STRICT_ROLE_WRITE", "1")
    import backend.app.core.matter_policy as policy

    importlib.reload(policy)
    with pytest.raises(HTTPException) as exc:
        policy.require_matter_write_access({"role": "viewer", "request_user_id": "u1", "owner_user_id": "u2"})
    assert exc.value.status_code == 403
