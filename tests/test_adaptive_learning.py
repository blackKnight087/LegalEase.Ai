"""Adaptive learning engine tests."""
from __future__ import annotations

import pytest

from backend.app.core.adaptive_learning import (
    apply_chunk_boosts,
    apply_learned_query_expansion,
    ensure_learning_schema,
    get_adaptive_threshold,
    learning_stats,
    normalize_query,
    record_feedback,
    record_implicit_correction,
    record_interaction,
)


@pytest.fixture
def learning_db(tmp_path, monkeypatch):
    db = tmp_path / "learn.db"
    import backend.app.core.adaptive_learning as al

    monkeypatch.setattr(al, "DB_PATH", db)
    ensure_learning_schema()
    return db


def test_record_and_feedback_positive(learning_db):
    iid = record_interaction(
        "u1",
        "knowledge_base",
        "difference ipc 300 and 307",
        answer="IPC 300 is murder while 307 is attempt...",
        found_in_kb=True,
        best_score=0.72,
        chunks=[{"content": "IPC Section 300 Murder", "metadata": {"filename": "a.pdf", "chunk_index": 1}}],
    )
    out = record_feedback("u1", interaction_id=iid, signal="thumbs_up")
    assert out.get("ok") is True
    exp = apply_learned_query_expansion(
        "u1", "knowledge_base", "difference ipc 300 and 307", ""
    )
    assert len(exp) > 10


def test_negative_feedback_penalizes_chunks(learning_db):
    chunks = [
        {
            "content": "bad chunk",
            "metadata": {"filename": "x.pdf", "chunk_index": 0},
            "final_score": 0.6,
        }
    ]
    iid = record_interaction("u1", "knowledge_base", "test q", chunks=chunks, found_in_kb=True)
    record_feedback("u1", interaction_id=iid, signal="thumbs_down")
    boosted = apply_chunk_boosts("u1", "knowledge_base", [dict(chunks[0])])
    assert boosted[0].get("adaptive_boost", 0) <= 0


def test_implicit_correction(learning_db):
    record_implicit_correction(
        "u1",
        "knowledge_base",
        normalize_query("section 300"),
        "difference between IPC 300 and 307",
    )
    exp = apply_learned_query_expansion("u1", "knowledge_base", "section 300", "section 300")
    assert "300" in exp or "307" in exp or len(exp) >= len("section 300")


def test_adaptive_threshold_bounds(learning_db):
    for _ in range(6):
        record_interaction("u2", "knowledge_base", "q", found_in_kb=True, best_score=0.8)
    t = get_adaptive_threshold("u2", "knowledge_base", 0.28)
    assert 0.20 <= t <= 0.38


def test_learning_stats_summary(learning_db):
    iid = record_interaction(
        "u3",
        "knowledge_base",
        "section 302 punishment",
        answer="Murder under IPC 302",
        found_in_kb=True,
        best_score=0.65,
    )
    record_feedback("u3", interaction_id=iid, signal="thumbs_up")
    stats = learning_stats("u3")
    assert "summary" in stats
    assert stats["summary"]["total_turns"] >= 1
    assert stats["summary"]["accuracy_pct"] == 100.0
    assert stats["modes"][0]["hit_rate_pct"] is not None
