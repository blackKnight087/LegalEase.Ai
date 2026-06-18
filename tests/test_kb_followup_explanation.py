"""Bare 'Explanation' must stay on prior IPC section, not random matter files."""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.legacy_kb


def test_explanation_is_meta_follow_up():
    from conversation_context import is_meta_follow_up

    assert is_meta_follow_up("Explanation")
    assert is_meta_follow_up("explain")
    assert is_meta_follow_up("more detail")


def test_enrich_explanation_after_ipc_304():
    from conversation_context import enrich_query_with_context
    from backend.app.core.kb_strict_retrieval import enrich_query_sections_from_history

    history = [
        {"role": "user", "content": "IPC Section 304"},
        {"role": "assistant", "content": "IPC Section 304. IPC Meaning: Punishment for culpable homicide."},
    ]
    out = enrich_query_with_context("Explanation", history)
    assert "304" in out
    assert "imran" not in out.lower()

    out2 = enrich_query_sections_from_history("Explanation", history)
    assert "304" in out2


def test_mode_router_never_kb_to_open_law():
    from backend.app.services.mode_router import route_query

    r = route_query("IPC 304", "knowledge_base", [], has_kb_index=False)
    assert r.mode == "knowledge_base"
    assert r.reason == "user_kb"
