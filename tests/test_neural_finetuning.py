"""Neural embedding fine-tuning — pair collection and training."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.adaptive_learning import ensure_learning_schema, record_feedback, record_interaction
from backend.app.core.neural_finetuning import (
    add_pairs_from_interaction,
    add_training_pair,
    collect_pairs_from_feedback,
    count_unused_pairs,
    ensure_neural_tuning_schema,
    train_embedding_model,
    tuning_status,
)


@pytest.fixture(autouse=True)
def _neural_db(tmp_path, monkeypatch):
    db = tmp_path / "neural.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    ensure_learning_schema()
    ensure_neural_tuning_schema()
    return db


def test_add_training_pair_rejects_short_inputs():
    assert add_training_pair("short", "also short") is None
    assert count_unused_pairs("u1") == 0


def test_add_training_pair_and_status():
    pid = add_training_pair(
        "What is the new law replacing IPC?",
        "The Bharatiya Nyaya Sanhita (BNS) replaces the Indian Penal Code (IPC) for substantive criminal law.",
        user_id="u1",
        source="test",
    )
    assert pid
    assert count_unused_pairs("u1") == 1
    status = tuning_status("u1")
    assert status["enabled"] is True
    assert status["unused_pairs"] == 1


def test_add_pairs_from_interaction():
    chunks = [
        {"content": "IPC Section 300 defines murder under the old penal code framework."},
        {"content": "BNS Section 103 corresponds to murder provisions in the new code."},
    ]
    added = add_pairs_from_interaction(
        "u1",
        "difference between IPC 300 and BNS murder section",
        chunks,
    )
    assert added == 2
    assert count_unused_pairs("u1") == 2


def test_collect_pairs_from_feedback():
    iid = record_interaction(
        "u1",
        "knowledge_base",
        "What replaced IPC?",
        answer="The Bharatiya Nyaya Sanhita (BNS) replaced IPC for substantive criminal offences in India.",
        found_in_kb=True,
        best_score=0.81,
        chunks=[{"content": "IPC maps to BNS under the new criminal law reforms."}],
    )
    record_feedback("u1", interaction_id=iid, signal="thumbs_up")
    added = collect_pairs_from_feedback("u1", limit=50)
    assert added >= 1
    assert count_unused_pairs("u1") >= 1


def test_train_requires_minimum_pairs():
    from contextlib import contextmanager

    @contextmanager
    def _open_slot(*_a, **_k):
        yield {"ok": True}

    for i in range(3):
        add_training_pair(
            f"legal query number {i} about bns ipc mapping",
            "Detailed passage about criminal law reform and IPC to BNS transition in India.",
            user_id="u1",
        )
    with patch("backend.app.core.resource_scheduler.acquire", _open_slot):
        out = train_embedding_model("u1", min_pairs=8)
    assert out["ok"] is False
    assert "Need at least 8" in out["error"]


def test_train_success_mocked(tmp_path, monkeypatch):
    monkeypatch.setenv("NEURAL_FINETUNE_MIN_PAIRS", "2")
    import backend.app.core.neural_finetuning as nft

    monkeypatch.setattr(nft, "MODELS_DIR", tmp_path / "models")

    for i in range(3):
        add_training_pair(
            f"query {i} ipc bns replacement law",
            "Long positive passage describing how BNS replaces IPC under Indian criminal law reform.",
            user_id="u1",
        )

    mock_model = MagicMock()
    mock_model.fit = MagicMock()

    from contextlib import contextmanager

    @contextmanager
    def _open_slot(*_a, **_k):
        yield {"ok": True}

    with patch("backend.app.core.resource_scheduler.acquire", _open_slot):
        with patch("sentence_transformers.SentenceTransformer", return_value=mock_model):
            with patch("sentence_transformers.InputExample", side_effect=lambda texts: texts):
                with patch("sentence_transformers.losses.MultipleNegativesRankingLoss"):
                    with patch("torch.utils.data.DataLoader", side_effect=lambda examples, **kw: examples):
                        out = train_embedding_model("u1", min_pairs=2, epochs=1)

    assert out["ok"] is True
    assert out["pair_count"] >= 2
    assert mock_model.fit.called
    status = tuning_status("u1")
    assert status["last_run"]["status"] == "completed"
