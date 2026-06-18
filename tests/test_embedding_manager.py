"""EmbeddingManager state machine and non-blocking load."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from backend.app.core.embedding_manager import EmbeddingManager, EmbeddingState


@pytest.fixture
def fresh_manager():
    EmbeddingManager._instance = None
    return EmbeddingManager.instance()


def test_start_background_load_idempotent(fresh_manager):
    fresh_manager.start_background_load()
    st1 = fresh_manager.get_status()
    fresh_manager.start_background_load()
    st2 = fresh_manager.get_status()
    assert st2["state"] in (EmbeddingState.LOADING_MODEL.value, EmbeddingState.READY.value, EmbeddingState.FAILED.value)


@patch.object(EmbeddingManager, "_do_load", return_value=True)
def test_load_transitions_to_ready(mock_load, fresh_manager):
    fresh_manager._load_worker()
    st = fresh_manager.get_status()
    assert st["ready"] is True
    assert st["state"] == EmbeddingState.READY.value


@patch("backend.app.core.embedding_manager.threading.Timer")
@patch.object(EmbeddingManager, "_do_load", return_value=False)
def test_failed_state_retries(mock_load, mock_timer, fresh_manager):
    fresh_manager._load_attempts = 0
    fresh_manager._load_worker()
    assert fresh_manager.get_status()["state"] == EmbeddingState.FAILED.value
    mock_timer.assert_called()
