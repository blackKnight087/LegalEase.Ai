"""Tests for Settings-only Gemini Ollama tuning coach."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _coach_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_OLLAMA_TUNING", "1")
    import backend.app.core.gemini_ollama_coach as coach

    monkeypatch.setattr(coach, "ENABLED", True)
    return coach


def test_coach_available_when_configured(_coach_env):
    with patch.object(_coach_env, "_gemini_ready", return_value=True):
        assert _coach_env.coach_available() is True


def test_coach_unavailable_without_flag(monkeypatch):
    monkeypatch.setenv("GEMINI_OLLAMA_TUNING", "0")
    import importlib

    import backend.app.core.gemini_ollama_coach as coach

    importlib.reload(coach)
    assert coach.coach_available() is False


def test_set_coach_enabled(_coach_env):
    _coach_env.ensure_coach_schema()
    prefs = _coach_env.set_coach_enabled("user-1", True)
    assert prefs["enabled"] is True


def test_apply_coaching_insights(_coach_env):
    insights = {
        "persona_suggestion": "concise",
        "communication_notes_addition": "Prefer short bullet points.",
        "suggested_facts": [{"key": "answer_style", "value": "bullet points"}],
        "training_pairs": [{"query": "IPC 302", "passage": "ignored by guard"}],
        "query_healings": [
            {"mode": "knowledge_base", "query_norm": "ipc 302", "expansion": "shorter phrasing for retrieval"}
        ],
    }
    with patch("backend.app.core.user_memory.update_profile") as upd, patch(
        "backend.app.core.user_memory.add_fact"
    ) as add_f, patch(
        "backend.app.core.neural_finetuning.collect_pairs_from_feedback", return_value=1
    ) as collect_p, patch(
        "backend.app.core.adaptive_learning.teach_query_expansion"
    ) as teach, patch(
        "backend.app.core.user_memory.get_or_create_profile",
        return_value={"communication_notes": ""},
    ):
        applied = _coach_env.apply_coaching_insights("user-1", insights)
    assert applied["persona_updated"] is True
    assert applied["facts_added"] == 1
    assert applied["training_pairs_added"] == 1
    upd.assert_called()
    add_f.assert_called_once()
    collect_p.assert_called_once()
    assert applied["query_healings_added"] == 1


def test_analyze_feedback_requires_enabled(_coach_env):
    _coach_env.ensure_coach_schema()
    with patch.object(_coach_env, "_gemini_ready", return_value=True):
        result = _coach_env.analyze_feedback("user-2")
    assert result["ok"] is False
    assert "Enable" in result["error"]


def test_analyze_feedback_mock(_coach_env):
    _coach_env.ensure_coach_schema()
    _coach_env.set_coach_enabled("user-3", True)
    feedback = [
        {"mode": "knowledge_base", "query": "IPC 302", "answer_preview": "A" * 50, "signal": "thumbs_up"},
        {"mode": "knowledge_base", "query": "IPC 307", "answer_preview": "B" * 50, "signal": "thumbs_down"},
    ]
    fake_insights = {
        "summary": "Use shorter answers.",
        "persona_suggestion": "keep",
        "suggested_facts": [],
        "training_pairs": [],
        "query_healings": [],
        "healing_actions": ["Be more concise"],
    }
    with patch.object(_coach_env, "_gemini_ready", return_value=True), patch.object(
        _coach_env, "_fetch_feedback_rows", return_value=feedback
    ), patch.object(_coach_env, "_fetch_correction_rows", return_value=[]), patch.object(
        _coach_env, "_call_gemini_coach", return_value=fake_insights
    ):
        result = _coach_env.analyze_feedback("user-3", apply=False)
    assert result["ok"] is True
    assert result["insights"]["summary"] == "Use shorter answers."


def test_save_directives(_coach_env):
    _coach_env.ensure_coach_schema()
    r = _coach_env.save_directives("user-d", "Always cite sections.")
    assert r["ok"] is True
    assert _coach_env.get_directives("user-d") == "Always cite sections."
    assert _coach_env._coach_memory_count("user-d") >= 1


def test_get_coach_memory_block(_coach_env):
    _coach_env.ensure_coach_schema()
    _coach_env.store_coach_memory("user-m", "user_directive", "Prefer bullet points.")
    block = _coach_env.get_coach_memory_block("user-m")
    assert "bullet points" in block


def test_process_negative_feedback_saves_without_coach(_coach_env):
    _coach_env.ensure_coach_schema()
    with patch.object(_coach_env, "_fetch_interaction_detail", return_value={
        "interaction_id": "i1",
        "mode": "knowledge_base",
        "query": "IPC 302",
        "answer_preview": "wrong answer",
        "found_in_kb": True,
    }), patch.object(_coach_env, "coach_available", return_value=False):
        r = _coach_env.process_negative_feedback(
            "user-n", interaction_id="i1", user_comment="Too vague"
        )
    assert r["ok"] is True
    assert r["saved"] is True
    assert r["coach_applied"] is False
