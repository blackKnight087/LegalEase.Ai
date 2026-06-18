"""Unified learning engine — memory, KB rescue, rapid adaptation."""
from __future__ import annotations

import pytest

from backend.app.core.learning_engine import (
    ensure_learning_engine_schema,
    learn_from_kb_success,
    lookup_answer_memory,
    rescue_broken_kb,
    store_answer_memory,
)


@pytest.fixture(autouse=True)
def _learn_db(tmp_path, monkeypatch):
    db = tmp_path / "learn_engine.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_learning_engine_schema()
    return db


def test_answer_memory_store_and_recall():
    q = "What is the new law replacing IPC?"
    a = (
        "The Indian Penal Code (IPC), 1860 has been replaced by the "
        "Bharatiya Nyaya Sanhita (BNS), 2023 for substantive criminal law."
    )
    store_answer_memory("u1", q, a, confidence=0.9)
    hit = lookup_answer_memory("u1", "What is the new law replacing IPC?")
    assert hit is not None
    assert "BNS" in hit["answer"]
    assert hit["layer"] == "answer_memory"


def test_baseline_law_rescue_without_index():
    from kb_legal_query_rewrite import build_baseline_law_answer

    ans = build_baseline_law_answer("What is the new law replacing IPC?")
    assert ans
    assert "BNS" in ans
    assert "IPC" in ans


def test_rescue_broken_kb_baseline_law():
    result = rescue_broken_kb("u1", "What is the new law replacing IPC?", index_dir=None)
    assert result is not None
    answer, chunks, diag = result
    assert "BNS" in answer
    assert diag.get("found_reason") in {"baseline_law", "answer_memory"}


def test_learn_from_success_then_memory_hit():
    q = "Difference between IPC 300 and BNS murder section"
    a = (
        "IPC Section 300 defines murder under the old code. Under BNS reforms, "
        "the corresponding murder provision appears in BNS Section 103 in mapping charts."
    )
    learn_from_kb_success("u2", q, a, chunks=[{"content": a}], confidence=0.88)
    hit = lookup_answer_memory("u2", "Difference between IPC 300 and BNS murder")
    assert hit is not None
    assert "300" in hit["answer"] or "103" in hit["answer"]


def test_memory_blocks_307_replay_for_302_query():
    bad = (
        "# IPC Section 307 — Attempt to Murder\n\n"
        "## Meaning\nIf a person attempts to kill another with intention or knowledge..."
    )
    store_answer_memory(
        "u3",
        "What is the punishment or penalty prescribed for IPC Section",
        bad,
        confidence=0.84,
    )
    hit = lookup_answer_memory("u3", "What is punishment under IPC 302?")
    assert hit is None
