"""Unit tests for multi-model LLM task routing."""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


def test_route_classification_to_fast_role():
    from backend.app.core.llm_task_router import ModelRole, TaskType, route_task

    assert route_task(TaskType.CLASSIFICATION) == ModelRole.FAST_CLASSIFIER
    assert route_task("legal_reasoning") == ModelRole.LEGAL_REASONING
    assert route_task("retrieval") == ModelRole.EMBEDDING


def test_architecture_snapshot_contains_models():
    from backend.app.core.llm_task_router import architecture_snapshot

    snap = architecture_snapshot()
    assert "models" in snap
    assert snap["models"]["fast_classifier"]
    assert snap["models"]["legal_reasoning"]
    assert snap["models"]["embedding_primary"]


def test_generate_for_task_never_raises_on_failure():
    from backend.app.core.llm_task_router import TaskType
    from backend.app.core import llm_orchestrator

    mock_client = MagicMock()
    mock_client.generate.side_effect = RuntimeError("offline")
    mock_client.model = "qwen3:8b"

    with patch.object(llm_orchestrator, "get_generator_for_task", return_value=mock_client):
        with patch.object(llm_orchestrator, "router_enabled", return_value=True):
            out = llm_orchestrator.generate_for_task(TaskType.LEGAL_REASONING, "test prompt")
    assert out["ok"] is False
    assert "error" in out


def test_web_chain_local_fallback_when_no_providers(monkeypatch):
    from backend.app.core import web_provider_chain

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    with patch(
        "backend.app.core.web_provider_chain._local_legal_fallback",
        return_value="**Using local legal reasoning only.**\n\nTest answer",
    ):
        answer, sources, follow_ups, meta = web_provider_chain.run_legal_web_research(
            "Is Section 420 IPC still valid?",
            user_id="test-user",
        )
    assert "local" in (meta.get("provider") or "")
    assert "Using local legal reasoning only" in answer
    assert sources == []


def test_defaults_use_primary_ollama_not_qwen(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "legalease-tuned")
    monkeypatch.delenv("OLLAMA_MODEL_LEGAL", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL_FAST", raising=False)
    import importlib

    from backend.app.core import llm_task_router

    importlib.reload(llm_task_router)
    assert llm_task_router.OLLAMA_MODEL_LEGAL == "legalease-tuned"
    assert llm_task_router.OLLAMA_MODEL_FAST == "legalease-tuned"
    assert llm_task_router.skip_fast_classifier_llm() is True


def test_merge_classification_prefers_high_confidence_rules():
    from backend.app.core.llm_orchestrator import merge_classification

    rules = {"intent": "FAMILY_LAW", "confidence": 0.92, "source": "rules", "parameters": {}}
    llm = {"intent": "CRIMINAL_DEFENSE", "category": "Criminal", "urgency": "HIGH", "source": "llm_fast"}
    merged = merge_classification(rules, llm)
    assert merged["intent"] == "FAMILY_LAW"
    assert merged.get("urgency") == "HIGH"
