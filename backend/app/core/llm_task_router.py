"""
Task → model routing for LegalEase multi-model architecture.

Defaults to OLLAMA_MODEL (legalease-tuned). Optional Qwen models apply only when
explicitly set via OLLAMA_MODEL_FAST / OLLAMA_MODEL_LEGAL — never by default.
"""
from __future__ import annotations

import os
from enum import Enum
from typing import Any, Dict


class TaskType(str, Enum):
    CLASSIFICATION = "classification"
    LEGAL_REASONING = "legal_reasoning"
    RETRIEVAL = "retrieval"
    WEB_RESEARCH = "web_research"
    DRAFT_POLISH = "draft_polish"
    SPEECH_CLEANUP = "speech_cleanup"
    ENTITY_PREFILTER = "entity_prefilter"


class ModelRole(str, Enum):
    FAST_CLASSIFIER = "fast_classifier"
    LEGAL_REASONING = "legal_reasoning"
    EMBEDDING = "embedding"
    WEB_INTELLIGENCE = "web_intelligence"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def primary_ollama_model() -> str:
    """Canonical tuned model — same as legacy KB chat (OLLAMA_MODEL)."""
    return (
        _env("OLLAMA_MODEL")
        or _env("OLLAMA_TUNED_MODEL_NAME")
        or "legalease-tuned"
    )


_PRIMARY = primary_ollama_model()

# All Ollama roles default to legalease-tuned; set OLLAMA_MODEL_FAST=qwen2.5:3b only if you want a separate fast model.
OLLAMA_MODEL_LEGAL = (
    _env("OLLAMA_MODEL_LEGAL") or _env("OLLAMA_MODEL_REASONING") or _PRIMARY
)
OLLAMA_MODEL_FAST = _env("OLLAMA_MODEL_FAST") or _PRIMARY
OLLAMA_MODEL_LEGAL_FALLBACK = _env("OLLAMA_MODEL_LEGAL_FALLBACK") or _PRIMARY

HF_EMBEDDING_PRIMARY = _env("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
HF_EMBEDDING_FALLBACK = _env("HF_EMBEDDING_FALLBACK", "BAAI/bge-base-en-v1.5")

CLASSIFY_MAX_TOKENS = int(_env("LLM_CLASSIFY_MAX_TOKENS", "320"))
CLASSIFY_TIMEOUT_SEC = float(_env("LLM_CLASSIFY_TIMEOUT_SEC", "8"))
LEGAL_MAX_TOKENS_DEFAULT = int(_env("LLM_LEGAL_MAX_TOKENS", "2048"))
LEGAL_TIMEOUT_SEC = float(_env("LLM_LEGAL_TIMEOUT_SEC", "180"))
INTAKE_LEGAL_TIMEOUT_SEC = float(_env("LLM_INTAKE_TIMEOUT_SEC", "45"))

_TASK_TO_ROLE: Dict[TaskType, ModelRole] = {
    TaskType.CLASSIFICATION: ModelRole.FAST_CLASSIFIER,
    TaskType.ENTITY_PREFILTER: ModelRole.FAST_CLASSIFIER,
    TaskType.SPEECH_CLEANUP: ModelRole.FAST_CLASSIFIER,
    TaskType.LEGAL_REASONING: ModelRole.LEGAL_REASONING,
    TaskType.DRAFT_POLISH: ModelRole.LEGAL_REASONING,
    TaskType.RETRIEVAL: ModelRole.EMBEDDING,
    TaskType.WEB_RESEARCH: ModelRole.WEB_INTELLIGENCE,
}


def router_enabled() -> bool:
    return _env("LLM_ROUTER_ENABLED", "1").lower() in {"1", "true", "yes"}


def uses_separate_fast_model() -> bool:
    """True only when a different Ollama model is explicitly configured for fast tasks."""
    fast = (OLLAMA_MODEL_FAST or "").lower()
    legal = (OLLAMA_MODEL_LEGAL or "").lower()
    return bool(fast and legal and fast != legal)


def skip_fast_classifier_llm() -> bool:
    """Avoid a second LLM call on the same legalease-tuned model (rules + legal pass suffice)."""
    return not uses_separate_fast_model()


def route_task(task: TaskType | str) -> ModelRole:
    if isinstance(task, str):
        try:
            task = TaskType(task.strip().lower())
        except ValueError:
            task = TaskType.LEGAL_REASONING
    return _TASK_TO_ROLE.get(task, ModelRole.LEGAL_REASONING)


def model_name_for_role(role: ModelRole | str) -> str:
    if isinstance(role, str):
        try:
            role = ModelRole(role.strip().lower())
        except ValueError:
            role = ModelRole.LEGAL_REASONING

    if role == ModelRole.FAST_CLASSIFIER:
        return OLLAMA_MODEL_FAST
    if role == ModelRole.LEGAL_REASONING:
        return OLLAMA_MODEL_LEGAL
    if role == ModelRole.EMBEDDING:
        return HF_EMBEDDING_PRIMARY
    return ""


def generation_limits_for_task(task: TaskType | str) -> Dict[str, Any]:
    if isinstance(task, str):
        try:
            task = TaskType(task.strip().lower())
        except ValueError:
            task = TaskType.LEGAL_REASONING

    if task in (TaskType.CLASSIFICATION, TaskType.ENTITY_PREFILTER, TaskType.SPEECH_CLEANUP):
        return {
            "temperature": 0.05,
            "max_tokens": CLASSIFY_MAX_TOKENS,
            "timeout_sec": CLASSIFY_TIMEOUT_SEC,
        }
    if task == TaskType.DRAFT_POLISH:
        return {
            "temperature": 0.15,
            "max_tokens": min(LEGAL_MAX_TOKENS_DEFAULT, 2400),
            "timeout_sec": LEGAL_TIMEOUT_SEC,
        }
    return {
        "temperature": 0.12,
        "max_tokens": LEGAL_MAX_TOKENS_DEFAULT,
        "timeout_sec": LEGAL_TIMEOUT_SEC,
    }


def architecture_snapshot() -> Dict[str, Any]:
    return {
        "router_enabled": router_enabled(),
        "primary_ollama": _PRIMARY,
        "uses_separate_fast_model": uses_separate_fast_model(),
        "tasks": {t.value: route_task(t).value for t in TaskType},
        "models": {
            "fast_classifier": OLLAMA_MODEL_FAST,
            "legal_reasoning": OLLAMA_MODEL_LEGAL,
            "legal_reasoning_fallback": OLLAMA_MODEL_LEGAL_FALLBACK,
            "embedding_primary": HF_EMBEDDING_PRIMARY,
            "embedding_fallback": HF_EMBEDDING_FALLBACK,
            "legacy_ollama_model": _PRIMARY,
        },
        "note": (
            "All Ollama tasks use OLLAMA_MODEL (legalease-tuned) unless "
            "OLLAMA_MODEL_FAST / OLLAMA_MODEL_LEGAL override. Qwen is opt-in only."
        ),
        "targets_sec": {
            "classification": 2,
            "legal_reasoning": "3-8",
            "matter_retrieval": 3,
        },
    }
