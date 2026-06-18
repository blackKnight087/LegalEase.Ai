"""KB observability unit tests."""
from __future__ import annotations

import pytest


@pytest.fixture
def obs_db(tmp_path, monkeypatch):
    db = tmp_path / "obs.db"
    faiss = tmp_path / "faiss"
    faiss.mkdir()
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(faiss))

    from backend.app.core.core_db import ensure_app_schemas

    ensure_app_schemas()
    return db


def test_format_upload_zero_chunks(obs_db):
    from backend.app.core.kb_observability import format_upload_index_result
    from pathlib import Path

    out = format_upload_index_result(
        ok=False,
        index_msg="No searchable chunks",
        index_dir=Path("/tmp/index"),
        was_dup=False,
        user_id="u1",
    )
    assert out["error_code"] == "ZERO_CHUNKS"
    assert out["indexing_ok"] is False
    assert "Re-index" in out["user_action"]


def test_resolve_index_scope_unlinked(obs_db):
    from backend.app.core.kb_observability import resolve_active_index_scope

    active = resolve_active_index_scope("test-user")
    assert active["index_scope"] in ("unlinked", "legacy", "global_kb")
    assert "index_path" in active
