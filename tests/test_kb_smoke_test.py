"""KB smoke test module — unit checks without live index."""
from __future__ import annotations

import pytest

from backend.app.core.kb_smoke_test import DEFAULT_SMOKE_QUERIES


@pytest.mark.unit
def test_default_smoke_queries_defined():
    assert len(DEFAULT_SMOKE_QUERIES) >= 2
    assert all(q.get("query") for q in DEFAULT_SMOKE_QUERIES)


@pytest.mark.unit
def test_smoke_fails_without_vectors(tmp_path, monkeypatch):
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss"))
    from backend.app.core.kb_smoke_test import run_kb_smoke_test

    uid = "smoke-user-no-index"
    out = run_kb_smoke_test(uid)
    assert out["ok"] is False
    assert out.get("faiss_vectors", 0) == 0
