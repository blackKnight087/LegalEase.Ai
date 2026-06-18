"""Tests for Ollama Modelfile export and coach scheduler."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_build_modelfile_content():
    from backend.app.core.ollama_modelfile_export import build_modelfile_content

    with patch(
        "backend.app.core.ollama_modelfile_export.build_system_prompt",
        return_value="You are LegalEase.",
    ), patch(
        "backend.app.core.ollama_modelfile_export._collect_training_examples",
        return_value=[{"query": "What is IPC 302?", "answer": "A" * 50, "source": "feedback"}],
    ):
        content, count = build_modelfile_content("user-1", base_model="llama3.1:8b")
    assert "FROM llama3.1:8b" in content
    assert "SYSTEM" in content
    assert "MESSAGE user" in content
    assert count == 1


def test_export_ollama_bundle_empty_user(tmp_path, monkeypatch):
    import backend.app.core.ollama_modelfile_export as exp

    monkeypatch.setattr(exp, "EXPORT_DIR", tmp_path / "exports")
    with patch.object(exp, "build_modelfile_content", return_value=("FROM test\n", 0)), patch.object(
        exp, "build_jsonl_content", return_value=("", 0)
    ):
        result = exp.export_ollama_bundle("user-x")
    assert result["ok"] is True
    assert (tmp_path / "exports" / "user-x").exists()


def test_count_feedback_since():
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.coach_scheduler import count_feedback_since

    ensure_learning_schema()
    n = count_feedback_since("nonexistent-user-xyz")
    assert n >= 0


def test_set_auto_schedule():
    from backend.app.core.coach_scheduler import get_schedule_prefs, set_auto_schedule
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema

    ensure_coach_schema()
    set_auto_schedule("sched-user", True)
    prefs = get_schedule_prefs("sched-user")
    assert prefs.get("auto_schedule_enabled") is True


def test_is_due_requires_min_feedback(monkeypatch):
    import backend.app.core.coach_scheduler as sched

    monkeypatch.setattr(sched, "MIN_NEW_FEEDBACK", 1)
    with patch("backend.app.core.gemini_ollama_coach.coach_available", return_value=True):
        assert sched._is_due(None, 0, True) is False
        assert sched._is_due(None, 1, True) is True
