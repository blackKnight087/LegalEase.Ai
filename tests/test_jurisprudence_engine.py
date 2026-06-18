"""Jurisprudence Engine — KB + Gemini fusion tests."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def kb_chunks():
    return [
        {
            "content": "Section 302 IPC murder punishment life imprisonment.",
            "metadata": {"filename": "ipc_act.pdf", "chunk_index": 3},
            "final_score": 0.82,
        }
    ]


def test_format_kb_evidence(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    import backend.app.core.web_intelligence as wi

    monkeypatch.setattr(wi, "GEMINI_API_KEY", "test")
    text = wi._format_kb_evidence("Murder under 302.", kb_chunks=[{
        "content": "IPC 302 text",
        "metadata": {"filename": "a.pdf"},
        "final_score": 0.9,
    }])
    assert "KB-1" in text
    assert "a.pdf" in text


def test_hybrid_parallel_merge(monkeypatch, kb_chunks):
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("HYBRID_FAST", "1")
    monkeypatch.setenv("HYBRID_SKIP_PREFETCH_WEB", "1")

    kb_answer = "IPC Section 302 applies."
    web_sources = [{"title": "IK", "href": "https://indiankanoon.org/doc/1/", "body": "", "provider": "Gemini"}]
    report = "## Executive Summary\n\nFull jurisprudence report."

    with patch(
        "backend.app.services.hybrid_orchestrator._fetch_kb_hybrid",
        return_value=(kb_answer, kb_chunks),
    ):
        with patch("backend.app.core.web_intelligence.gemini_configured", return_value=True):
            with patch(
                "backend.app.core.web_intelligence.synthesize_jurisprudence_report",
                return_value=(report, web_sources, []),
            ) as synth:
                from backend.app.services.hybrid_orchestrator import run_hybrid_turn

                ans, similar, sources = run_hybrid_turn("u1", "IPC 302 punishment")
    assert "Executive Summary" in ans
    assert similar
    assert sources
    synth.assert_called_once()
    assert synth.call_args.kwargs.get("use_google_search") is True


def test_hybrid_legacy_merge_when_no_gemini(monkeypatch, kb_chunks):
    monkeypatch.setenv("HYBRID_FAST", "1")
    monkeypatch.setenv("HYBRID_SKIP_PREFETCH_WEB", "0")
    kb_answer = "From documents: Section 302."
    web_answer = "From web: murder statute."

    with patch(
        "backend.app.services.hybrid_orchestrator._fetch_kb_hybrid",
        return_value=(kb_answer, kb_chunks),
    ):
        with patch(
            "app.web_search_query",
            return_value=(web_answer, []),
        ):
            with patch("backend.app.core.web_intelligence.gemini_configured", return_value=False):
                from backend.app.services.hybrid_orchestrator import run_hybrid_turn

                ans, similar, _ = run_hybrid_turn("u1", "IPC 302")
    assert "documents" in ans.lower() or "302" in ans
    assert similar
