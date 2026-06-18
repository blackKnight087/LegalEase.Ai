"""Tests for Gemini grounded web intelligence module."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_FREE_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("WEB_INTELLIGENCE_DEBUG", "0")
    import backend.app.core.web_intelligence as wi

    monkeypatch.setattr(wi, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(wi, "GEMINI_FREE_MODEL", "gemini-2.5-flash")
    return wi


def test_gemini_configured(_gemini_env):
    assert _gemini_env.gemini_configured() is True


def test_detect_research_dimension_statutory(_gemini_env):
    assert _gemini_env.detect_research_dimension("IPC section 302 punishment") == "statutory_lookup"


def test_detect_research_dimension_hearings(_gemini_env):
    assert _gemini_env.detect_research_dimension("RG Kar case next hearing date") == "hearing_schedule"


def test_detect_research_dimension_similar(_gemini_env):
    assert _gemini_env.detect_research_dimension("similar cases like Nirbhaya") == "similar_cases"


def test_classify_open_law_quick_fact(_gemini_env):
    p = _gemini_env.classify_open_law_request("who is cji of india")
    assert p["depth"] == "quick"
    assert p["dimension"] == "quick_fact"
    assert p["word_cap"] <= 120


def test_classify_open_law_comparison(_gemini_env):
    p = _gemini_env.classify_open_law_request("compare IPC 300 vs 307")
    assert p["depth"] == "comparison"
    assert p["dimension"] == "comparison"
    assert p["word_cap"] <= 350


def test_classify_open_law_standard(_gemini_env):
    p = _gemini_env.classify_open_law_request("explain rg kar case")
    assert p["depth"] == "standard"
    assert p["word_cap"] <= 380


def test_classify_open_law_detailed(_gemini_env):
    p = _gemini_env.classify_open_law_request("explain IPC 302 in detail")
    assert p["depth"] == "detailed"
    assert p["word_cap"] <= 480


def test_web_intel_status(_gemini_env):
    st = _gemini_env.web_intel_status()
    assert st["gemini_configured"] is True
    assert st["model"] == "gemini-2.5-flash"
    assert st["provider"] == "gemini_grounded_search"


def test_classify_open_law_constitutional_list(_gemini_env):
    p = _gemini_env.classify_open_law_request("5 constitutional rights")
    assert p["depth"] == _gemini_env.DEPTH_QUICK
    assert p["dimension"] == _gemini_env.DIMENSION_STATUTORY


def test_stream_grounded_legal_research_mock(_gemini_env):
    mock_web = MagicMock()
    mock_web.uri = "https://indiankanoon.org/doc/1/"
    mock_web.title = "Article 32"

    mock_chunk = MagicMock()
    mock_chunk.web = mock_web

    mock_gm = MagicMock()
    mock_gm.grounding_chunks = [mock_chunk]

    mock_cand = MagicMock()
    mock_cand.grounding_metadata = mock_gm

    chunk1 = MagicMock()
    chunk1.text = "## Direct Answer\n\n"
    chunk1.candidates = [mock_cand]

    chunk2 = MagicMock()
    chunk2.text = "Five fundamental rights include equality and freedom."
    chunk2.candidates = [mock_cand]

    mock_client = MagicMock()
    mock_client.models.generate_content_stream.return_value = iter([chunk1, chunk2])

    with patch.object(_gemini_env, "_get_client", return_value=mock_client):
        events = list(
            _gemini_env.stream_grounded_legal_research("5 constitutional rights")
        )

    token_events = [e for e in events if e.get("type") == "token"]
    assert token_events, f"expected token events, got: {[e.get('type') for e in events]}"
    assert events[-1]["type"] == "done"
    assert "fundamental" in events[-1]["answer"].lower()
    mock_client.models.generate_content_stream.assert_called_once()


def test_run_grounded_legal_research_mock(_gemini_env):
    mock_web = MagicMock()
    mock_web.uri = "https://indiankanoon.org/doc/1/"
    mock_web.title = "IPC 302"

    mock_chunk = MagicMock()
    mock_chunk.web = mock_web

    mock_gm = MagicMock()
    mock_gm.grounding_chunks = [mock_chunk]

    mock_cand = MagicMock()
    mock_cand.grounding_metadata = mock_gm

    mock_response = MagicMock()
    mock_response.text = "## Summary\n\nMurder under IPC 302.\n\n## Sources\n\n- [IK](https://indiankanoon.org/doc/1/)"
    mock_response.candidates = [mock_cand]

    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(_gemini_env, "_get_client", return_value=mock_client):
        answer, sources, follow_ups = _gemini_env.run_grounded_legal_research(
            "IPC section 302 punishment"
        )

    assert "302" in answer
    assert len(sources) == 1
    assert sources[0]["href"].startswith("https://")
    assert sources[0]["provider"] == "Open Law Web Search"
    assert follow_ups
    mock_client.models.generate_content.assert_called_once()


def test_grounded_search_snippets_on_error(_gemini_env):
    with patch.object(_gemini_env, "run_grounded_legal_research", side_effect=RuntimeError("quota")):
        rows = _gemini_env.grounded_search_snippets("test query")
    assert rows[0]["provider"] == "Unavailable"


def test_search_web_delegates_to_gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    import llms

    monkeypatch.setattr(llms, "GEMINI_API_KEY", "test-key", raising=False)

    fake = [{"title": "T", "href": "https://x", "body": "b", "provider": "Open Law Web Search"}]
    with patch("backend.app.core.web_intelligence.gemini_configured", return_value=True):
        with patch("backend.app.core.web_intelligence.grounded_search_snippets", return_value=fake):
            out = llms.search_web("IPC 302", max_results=3)
    assert out == fake
