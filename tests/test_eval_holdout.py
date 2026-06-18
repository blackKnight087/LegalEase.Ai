"""Tests for holdout eval before Modelfile export."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_load_holdout_queries(tmp_path, monkeypatch):
    import backend.app.core.eval_holdout as ev

    holdout = tmp_path / "eval_holdout.json"
    holdout.write_text(
        json.dumps({"queries": [{"id": "x", "query": "test q", "min_score": 0.1}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(ev, "HOLDOUT_PATH", holdout)
    queries = ev.load_holdout_queries()
    assert len(queries) == 1
    assert queries[0]["query"] == "test q"


def test_run_holdout_eval_no_index(monkeypatch):
    import backend.app.core.eval_holdout as ev

    monkeypatch.setattr(ev, "load_holdout_queries", lambda: [{"id": "a", "query": "q1", "min_score": 0.2}])
    with patch("app.index_exists", return_value=False):
        result = ev.run_holdout_eval("user-no-index")
    assert result["passed"] is False
    assert result["passed_count"] == 0
    assert result["results"][0]["reason"] == "no_index"


def test_run_holdout_eval_passes_with_scores(monkeypatch, tmp_path):
    import backend.app.core.eval_holdout as ev

    monkeypatch.setattr(ev, "ROOT", tmp_path)
    baseline_dir = tmp_path / "Data" / "eval_baselines"
    monkeypatch.setattr(
        ev,
        "load_holdout_queries",
        lambda: [
            {"id": "a", "query": "murder punishment", "min_score": 0.15, "expect_keywords": ["murder"]},
            {"id": "b", "query": "breach contract", "min_score": 0.15, "expect_keywords": ["breach"]},
        ],
    )

    def fake_query_kb(query, k=5, index_dir=None):
        return [
            {
                "content": f"Answer about {query} murder breach contract remedy evidence",
                "score": 0.45,
            }
        ]

    with patch("app.index_exists", return_value=True):
        with patch("app.resolve_rag_index_dir", return_value="/fake/index"):
            with patch("rag.query_kb", side_effect=fake_query_kb):
                result = ev.run_holdout_eval("user-pass")
    assert result["passed"] is True
    assert result["passed_count"] == 2
    assert (baseline_dir / "user-pass.json").exists()


def test_regression_blocks_pass(monkeypatch, tmp_path):
    import backend.app.core.eval_holdout as ev

    monkeypatch.setattr(ev, "ROOT", tmp_path)
    monkeypatch.setattr(ev, "REGRESSION_MAX_DROP", 0.12)
    baseline_dir = tmp_path / "Data" / "eval_baselines"
    baseline_dir.mkdir(parents=True)
    (baseline_dir / "user-reg.json").write_text(
        json.dumps({"avg_score": 0.8, "pass_ratio": 1.0}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        ev,
        "load_holdout_queries",
        lambda: [{"id": "a", "query": "q", "min_score": 0.1}],
    )

    with patch("app.index_exists", return_value=True):
        with patch("app.resolve_rag_index_dir", return_value="/fake"):
            with patch(
                "rag.query_kb",
                return_value=[{"content": "low relevance text", "score": 0.25}],
            ):
                result = ev.run_holdout_eval("user-reg")
    assert result.get("regression") is True
    assert result["passed"] is False


def test_learning_progress_milestone(monkeypatch):
    from backend.app.core.learning_progress import _next_milestone, get_learning_progress

    with patch(
        "backend.app.core.improvement_automation.automation_status",
        return_value={"export_ready": False, "active_tuned_model": None},
    ):
        with patch("backend.app.core.improvement_automation.count_thumbs_up", return_value=5):
            with patch(
                "backend.app.core.improvement_automation.MIN_THUMBS_FOR_EXPORT",
                20,
            ):
                with patch(
                    "backend.app.core.export_quality_gate.check_export_quality_gate",
                    return_value={"passed": False, "reasons": ["Need eval pass."]},
                ):
                    with patch(
                        "backend.app.core.learning_signals.signal_stats",
                        return_value={},
                    ):
                        with patch(
                            "backend.app.core.human_training.training_pipeline_status",
                            return_value={},
                        ):
                            with patch(
                                "backend.app.core.coach_scheduler.get_schedule_prefs",
                                return_value={},
                            ):
                                with patch(
                                    "backend.app.core.user_preferences.get_preference_profile",
                                    return_value={},
                                ):
                                    with patch(
                                        "backend.app.core.retrieval_learning.retrieval_learning_stats",
                                        return_value={},
                                    ):
                                        prog = get_learning_progress("u1")
    assert prog["thumbs_up"] == 5
    assert "15 more" in prog["next_milestone"]
    assert _next_milestone({"thumbs_up": 25, "min_thumbs_for_export": 20, "quality_gate": {"passed": False, "reasons": ["Eval failed."]}}) == "Eval failed."
