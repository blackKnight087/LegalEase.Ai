"""Day 1 — per-user ML isolation and chat mode guards."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def test_per_user_active_ollama_model(tmp_path, monkeypatch):
    import backend.app.core.improvement_automation as auto

    monkeypatch.setattr(auto, "EXPORT_DIR", tmp_path / "exports")
    auto._activate_tuned_model("user-a", "legalease-a")
    auto._activate_tuned_model("user-b", "legalease-b")
    assert auto.get_active_tuned_model_name("user-a") == "legalease-a"
    assert auto.get_active_tuned_model_name("user-b") == "legalease-b"
    assert auto.get_active_tuned_model_name("user-c") == ""


def test_get_generator_uses_per_user_tuned_model(monkeypatch):
    import llms
    from backend.app.core.request_context import set_user_context

    class _FakeOllama:
        instances = []

        def __init__(self, base_url=None, model=None):
            self.raw_base_url = base_url
            self.model = model
            _FakeOllama.instances.append(self)

    monkeypatch.setenv("LLM_BACKEND", "ollama")
    monkeypatch.setenv("OLLAMA_KB_LOCK_MODEL", "0")
    llms.reset_generator()
    with patch(
        "backend.app.core.improvement_automation.AUTO_USE_TUNED", True
    ), patch(
        "backend.app.core.improvement_automation.get_active_tuned_model_name",
        side_effect=lambda uid: f"tuned-{uid[:6]}" if uid else "",
    ), patch.object(llms, "OllamaClient", _FakeOllama):
        set_user_context("user-alpha")
        llms.get_generator()
        set_user_context("user-beta")
        llms.get_generator()
        models = [c.model for c in _FakeOllama.instances]
        assert len(models) >= 2
        assert any("tuned-user" in (m or "") for m in models)


def test_maybe_auto_train_uses_user_scope():
    import backend.app.core.neural_finetuning as nf

    def _run_now(fn, label=""):
        return fn()

    with patch.object(nf, "count_unused_pairs", return_value=10), patch.object(
        nf, "train_embedding_model", return_value={"ok": True}
    ) as mock_train, patch(
        "backend.app.core.resource_scheduler.defer_low_priority", side_effect=_run_now
    ), patch("backend.app.core.resource_scheduler.can_run", return_value=True):
        nf.maybe_auto_train("uid-123")
        mock_train.assert_called_once_with("uid-123", scope="user")


def test_resolve_embedding_model_name_per_user(tmp_path, monkeypatch):
    import backend.app.core.neural_finetuning as nf

    monkeypatch.setattr(nf, "MODELS_DIR", tmp_path / "models")
    user_dir = tmp_path / "models" / "u1"
    user_dir.mkdir(parents=True)
    (user_dir / "latest.txt").write_text(str(user_dir.resolve()), encoding="utf-8")
    (user_dir / "config.json").write_text("{}", encoding="utf-8")
    path = nf.get_finetuned_model_path("u1")
    assert path is not None
    assert "u1" in path.replace("\\", "/")


def test_plan_route_guard_blocks_hybrid_for_free():
    from backend.app.services.chat_service import _apply_plan_route_guard

    assert _apply_plan_route_guard("hybrid", "Free") == "knowledge_base"
    assert _apply_plan_route_guard("deep_case", "Free") == "knowledge_base"
    assert _apply_plan_route_guard("hybrid", "Pro") == "hybrid"
    assert _apply_plan_route_guard("open_law", "Free") == "open_law"
