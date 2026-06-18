"""Universal smoke query builder — not tied to one PDF."""
from __future__ import annotations

from backend.app.core.kb_smoke_query_builder import build_smoke_queries_from_index


def test_build_queries_from_empty_index(tmp_path):
    out = build_smoke_queries_from_index(tmp_path)
    assert len(out) >= 2
    assert all(q.get("query") for q in out)
