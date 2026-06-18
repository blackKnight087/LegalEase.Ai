"""Matter AI retrieval scope — ensures matter index is used for matter_only mode."""
from __future__ import annotations

from unittest.mock import patch


def test_kb_turn_routes_matter_ai_to_matter_index():
    captured: dict = {}

    def fake_check(user_id, matter_id=None, retrieval_scope="global"):
        captured["retrieval_scope"] = retrieval_scope
        captured["matter_id"] = matter_id
        return False, "blocked-for-test"

    with patch("backend.app.core.kb_index_gate.check_kb_ready_for_query", fake_check):
        with patch("backend.app.services.chat_service.kb_log", lambda *a, **k: None):
            with patch(
                "backend.app.core.kb_gemini_safety.enforce_kb_gemini_policy",
                lambda **k: None,
            ):
                from backend.app.services.chat_service import _run_kb_turn

                msg, *_ = _run_kb_turn(
                    "user-1",
                    "What evidence supports the alibi?",
                    [],
                    matter_id="matter-abc",
                    matter_mode="matter_only",
                )

    assert msg == "blocked-for-test"
    assert captured.get("retrieval_scope") == "matter"
    assert captured.get("matter_id") == "matter-abc"


def test_kb_turn_stays_global_without_matter_mode():
    captured: dict = {}

    def fake_check(user_id, matter_id=None, retrieval_scope="global"):
        captured["retrieval_scope"] = retrieval_scope
        captured["matter_id"] = matter_id
        return False, "blocked-for-test"

    with patch("backend.app.core.kb_index_gate.check_kb_ready_for_query", fake_check):
        with patch("backend.app.services.chat_service.kb_log", lambda *a, **k: None):
            with patch(
                "backend.app.core.kb_gemini_safety.enforce_kb_gemini_policy",
                lambda **k: None,
            ):
                from backend.app.services.chat_service import _run_kb_turn

                _run_kb_turn("user-1", "What is Section 302 IPC?", [])

    assert captured.get("retrieval_scope") == "global"
    assert captured.get("matter_id") is None
