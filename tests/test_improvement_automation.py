"""Tests for fully automated improvement pipeline."""
from __future__ import annotations

from unittest.mock import patch

import pytest


def test_automation_status_defaults():
    from backend.app.core.improvement_automation import automation_status

    st = automation_status("user-test-1")
    assert "enabled" in st
    assert "min_thumbs_for_export" in st
    assert st["thumbs_up"] >= 0
    assert isinstance(st["export_ready"], bool)


def test_auto_export_skips_below_threshold(monkeypatch):
    import backend.app.core.improvement_automation as auto

    monkeypatch.setattr(auto, "MIN_THUMBS_FOR_EXPORT", 20)
    with patch.object(auto, "count_thumbs_up", return_value=5):
        result = auto.auto_export_and_create_ollama("user-low")
    assert result.get("skipped") is True
    assert result.get("reason") == "below_threshold"
    assert result.get("thumbs_up") == 5


def test_schedule_noop_when_disabled(monkeypatch):
    import backend.app.core.improvement_automation as auto

    monkeypatch.setattr(auto, "ENABLED", False)
    with patch.object(auto, "run_full_improvement_pipeline") as mock_run:
        auto.schedule_improvement_pipeline("user-x", trigger="thumbs_up")
        mock_run.assert_not_called()


def test_run_ollama_create_success(monkeypatch, tmp_path):
    import backend.app.core.improvement_automation as auto

    export_dir = tmp_path / "export"
    export_dir.mkdir()
    (export_dir / "Modelfile").write_text("FROM llama3.1:8b\n", encoding="utf-8")
    monkeypatch.setattr(auto, "AUTO_OLLAMA_CREATE", True)
    monkeypatch.setattr(auto, "AUTO_USE_TUNED", True)

    class FakeProc:
        returncode = 0
        stdout = "success"
        stderr = ""

    with patch.object(auto, "_activate_tuned_model") as mock_activate:
        result = auto.run_ollama_create(str(export_dir), "legalease-tuned", "user-z")
    assert result["ok"] is True
    mock_activate.assert_called_once_with("user-z", "legalease-tuned")


def test_on_neural_train_complete_reindex(monkeypatch):
    import backend.app.core.improvement_automation as auto

    with patch.object(auto, "auto_reindex_kb", return_value={"ok": True, "chunks_after": 10}) as mock_reindex:
        out = auto.on_neural_train_complete("user-1", {"ok": True})
    assert out["reindex"]["ok"] is True
    mock_reindex.assert_called_once_with("user-1")
