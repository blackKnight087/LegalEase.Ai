"""Tests for Gemini quota fallback and KB term overlap accuracy."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from backend.app.core.gemini_errors import is_gemini_quota_error
from backend.app.services.chat_turn_types import ChatTurnResult
from backend.app.services.open_law_executor import fetch_open_law_answer
from kb_rag_decision import _query_terms_in_chunk, evaluate_retrieval


def test_is_gemini_quota_error_detects_429():
    assert is_gemini_quota_error("429 RESOURCE_EXHAUSTED quota exceeded")
    assert not is_gemini_quota_error("connection reset")


def test_query_terms_in_chunk_rejects_tangential_hit():
    query = "Explain anticipatory bail requirements"
    chunk = "CrPC 41 arrest without warrant BNSS 35 arrest procedure"
    assert _query_terms_in_chunk(query, chunk) is False


def test_query_terms_in_chunk_accepts_relevant_hit():
    query = "Explain anticipatory bail requirements"
    chunk = "Section 438 CrPC anticipatory bail may be granted when..."
    assert _query_terms_in_chunk(query, chunk) is True


def test_evaluate_retrieval_weak_overlap_is_not_found():
    chunks = [{"content": "Arrest without warrant procedure CrPC 41", "score": 0.7}]
    found, score, decision, debug = evaluate_retrieval(
        "Explain anticipatory bail requirements",
        chunks,
        threshold=0.28,
    )
    assert found is False
    assert decision == "NOT_FOUND"
    assert debug.get("reason") == "weak_term_overlap"
    assert score > 0.28


@patch("backend.app.services.open_law_executor._from_legacy_web_search")
@patch("backend.app.services.open_law_executor._from_grounded_research")
@patch("backend.app.core.learning_engine.lookup_answer_memory", return_value=None)
def test_fetch_open_law_skips_gemini_on_quota(mock_mem, mock_grounded, mock_legacy):
    mock_grounded.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED quota exceeded")
    mock_legacy.return_value = ChatTurnResult(content="Bail is conditional release from custody.")

    result = fetch_open_law_answer(
        "u1",
        "What is bail?",
        "What is bail?",
        [],
        skip_gemini=True,
    )

    assert "Bail is conditional release" in result.content
    mock_grounded.assert_not_called()
    mock_legacy.assert_called_once()
