"""Tests for Modelfile export quality gate."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.core.adaptive_learning import (
    ensure_learning_schema,
    record_feedback,
    record_interaction,
)


@pytest.fixture
def gate_db(tmp_path, monkeypatch):
    db = tmp_path / "gate.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_learning_schema()
    return db


def test_force_skips_gate():
    from backend.app.core.export_quality_gate import check_export_quality_gate

    result = check_export_quality_gate("user-force", force=True)
    assert result["passed"] is True
    assert result.get("forced") is True
    assert result["reasons"] == []


def test_fails_without_distinct_queries(monkeypatch):
    import backend.app.core.export_quality_gate as gate

    monkeypatch.setattr(gate, "MIN_DISTINCT_SFT_QUERIES", 5)
    monkeypatch.setattr(gate, "REQUIRE_EVAL_PASS", False)
    with patch.object(gate, "count_distinct_positive_queries", return_value=1):
        with patch.object(
            gate,
            "week_feedback_balance",
            return_value={"positive": 10, "negative": 0, "net": 10, "ratio": 1.0, "days": 7},
        ):
            result = gate.check_export_quality_gate("user-low")
    assert result["passed"] is False
    assert any("distinct" in r.lower() for r in result["reasons"])


def test_fails_on_negative_week_balance(monkeypatch):
    import backend.app.core.export_quality_gate as gate

    monkeypatch.setattr(gate, "REQUIRE_EVAL_PASS", False)
    with patch.object(gate, "count_distinct_positive_queries", return_value=10):
        with patch.object(
            gate,
            "week_feedback_balance",
            return_value={"positive": 1, "negative": 5, "net": -4, "ratio": 0.17, "days": 7},
        ):
            result = gate.check_export_quality_gate("user-neg")
    assert result["passed"] is False
    assert any("negative" in r.lower() for r in result["reasons"])


def test_passes_when_checks_ok(monkeypatch):
    import backend.app.core.export_quality_gate as gate

    monkeypatch.setattr(gate, "REQUIRE_EVAL_PASS", True)
    with patch.object(gate, "count_distinct_positive_queries", return_value=8):
        with patch.object(
            gate,
            "week_feedback_balance",
            return_value={"positive": 12, "negative": 2, "net": 10, "ratio": 0.86, "days": 7},
        ):
            with patch(
                "backend.app.core.eval_holdout.run_holdout_eval",
                return_value={"passed": True, "summary": "Holdout: 5/5 passed"},
            ):
                result = gate.check_export_quality_gate("user-ok")
    assert result["passed"] is True
    assert result["reasons"] == []


def test_count_distinct_positive_queries(gate_db):
    from backend.app.core.export_quality_gate import count_distinct_positive_queries

    uid = "gate-user-1"
    for q in ("ipc 300", "ipc 307", "ipc 300"):
        iid = record_interaction(uid, "knowledge_base", q, found_in_kb=True)
        record_feedback(uid, interaction_id=iid, signal="thumbs_up")
    assert count_distinct_positive_queries(uid) == 2


def test_auto_export_blocked_by_quality_gate(monkeypatch):
    import backend.app.core.improvement_automation as auto

    monkeypatch.setattr(auto, "MIN_THUMBS_FOR_EXPORT", 5)
    with patch.object(auto, "count_thumbs_up", return_value=25):
        with patch(
            "backend.app.core.export_quality_gate.check_export_quality_gate",
            return_value={"passed": False, "reasons": ["Holdout eval did not pass."]},
        ):
            result = auto.auto_export_and_create_ollama("user-gated")
    assert result.get("skipped") is True
    assert result.get("reason") == "quality_gate_failed"
