"""Tests for inference-time rewards and LLM fine-tuning pipeline."""
from __future__ import annotations

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "full_learning.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


class TestRewardInference:
    def test_build_reward_prompt_block_empty_without_labels(self):
        from backend.app.core.reward_inference import build_reward_prompt_block

        assert build_reward_prompt_block("user-x", query="IPC 302") == ""

    def test_build_reward_prompt_block_with_positive_labels(self):
        from backend.app.core.human_training import record_human_label
        from backend.app.core.reward_inference import build_reward_prompt_block, get_reward_summary

        uid = f"u-{uuid.uuid4().hex[:8]}"
        record_human_label(
            uid,
            signal="thumbs_up",
            query="Explain IPC 307",
            answer_preview="IPC Section 307 covers attempt to murder with imprisonment up to ten years.",
            rlaif={"overall": 0.9, "clarity": 0.85, "structure": 0.8},
        )
        record_human_label(
            uid,
            signal="thumbs_up",
            query="What is IPC 302?",
            answer_preview="IPC Section 302 prescribes punishment for murder including death or life imprisonment.",
            rlaif={"overall": 0.88, "clarity": 0.9},
        )
        summary = get_reward_summary(uid)
        assert summary["samples"] >= 2
        block = build_reward_prompt_block(uid, query="Explain IPC 307")
        assert "LEARNED REWARD GUIDANCE" in block
        assert "307" in block or "preferred style" in block.lower()

    def test_select_best_candidate_picks_higher_reward(self):
        from backend.app.core.human_training import record_human_label
        from backend.app.core.reward_inference import select_best_candidate

        uid = f"u-{uuid.uuid4().hex[:8]}"
        record_human_label(
            uid,
            signal="thumbs_up",
            query="Explain IPC 307",
            answer_preview="Structured answer with clear section heading and punishment details for attempt to murder.",
            rlaif={"overall": 0.95},
        )
        record_human_label(
            uid,
            signal="thumbs_up",
            query="Explain IPC 307",
            answer_preview="Another structured answer with section reference and imprisonment term for attempt to murder.",
            rlaif={"overall": 0.9},
        )
        good = (
            "IPC Section 307 — Attempt to Murder. Punishment: imprisonment up to ten years. "
            "Structured answer with clear section heading."
        )
        bad = "Maybe something about murder."
        best, meta = select_best_candidate(uid, "Explain IPC 307", [bad, good])
        assert "307" in best
        assert meta.get("reranked") is True

    def test_rlaif_applies_to_preferences(self):
        from backend.app.core.chat_coach_runtime import apply_rlaif_to_preferences
        from backend.app.core.user_preferences import get_preference_profile

        uid = f"u-{uuid.uuid4().hex[:8]}"
        applied = apply_rlaif_to_preferences(
            uid,
            {"clarity": 0.9, "structure": 0.85, "tone": 0.9, "conciseness": 0.5, "overall": 0.88},
        )
        assert applied is True
        profile = get_preference_profile(uid)["profile"]
        assert float(profile.get("prefer_bullets", 0)) >= 0.5


class TestLLMFinetuning:
    def test_tuning_status_reports_readiness(self):
        from backend.app.core.llm_finetuning import tuning_status

        status = tuning_status(f"u-{uuid.uuid4().hex[:8]}")
        assert "enabled" in status
        assert "sft_ready" in status
        assert "dpo_ready" in status
        assert "training_deps_ok" in status

    @patch("backend.app.core.llm_finetuning._run_lora_sft")
    def test_train_lora_sft_mock(self, mock_train):
        from backend.app.core.adaptive_learning import ensure_learning_schema, record_feedback, record_interaction
        from backend.app.core.llm_finetuning import train_lora_sft

        uid = f"u-{uuid.uuid4().hex[:8]}"
        ensure_learning_schema()
        long_answer = (
            "IPC Section 302 prescribes punishment for murder including death or life imprisonment "
            "and fine according to the uploaded legal documents."
        )
        for i in range(6):
            iid = record_interaction(
                uid,
                "knowledge_base",
                f"What is IPC 30{i}?",
                answer=long_answer,
                found_in_kb=True,
            )
            record_feedback(uid, interaction_id=iid, signal="thumbs_up")

        adapter_dir = f"/tmp/adapter-{uuid.uuid4().hex[:6]}"
        mock_train.return_value = {"train_loss": 0.5, "steps": 10, "adapter_path": adapter_dir}

        with patch("backend.app.core.llm_finetuning._training_deps_ok", return_value=(True, "")):
            with patch("backend.app.core.llm_finetuning._local_gpu_available", return_value=True):
                with patch("backend.app.core.llm_finetuning._activate_adapter"):
                    result = train_lora_sft(uid, min_examples=5)

        assert result.get("ok") is True
        assert result.get("train_type") == "sft"
        mock_train.assert_called_once()


class TestChatCoachRuntime:
    def test_schedule_runtime_coach_respects_threshold(self):
        from backend.app.core.chat_coach_runtime import schedule_runtime_coach

        uid = f"u-{uuid.uuid4().hex[:8]}"
        out = schedule_runtime_coach(uid, trigger="thumbs_up", membership="Free")
        assert out.get("skipped") or out.get("scheduled")

    @patch("backend.app.core.chat_coach_runtime._run_coach_analyze_apply")
    def test_force_runtime_coach(self, mock_run):
        from backend.app.core.chat_coach_runtime import schedule_runtime_coach

        mock_run.return_value = {"ok": True, "trigger": "thumbs_down"}
        uid = f"u-{uuid.uuid4().hex[:8]}"
        out = schedule_runtime_coach(uid, trigger="thumbs_down", force=True)
        assert out.get("scheduled") is True
