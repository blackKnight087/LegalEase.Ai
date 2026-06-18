"""Phase 2 bundle — engine status, export redaction, strict citations, clusters."""
from __future__ import annotations


def test_engine_status_shape():
    from backend.app.core.engine_status import get_engine_status

    st = get_engine_status("test-user", membership="Pro")
    assert "gemini" in st
    assert "kb" in st
    assert "usage" in st
    assert "strict_citations" in st


def test_client_safe_export_redacts_kb_markers():
    from backend.app.core.report_export import export_report_bytes, redact_for_client

    raw = "## Report\n\nSection 302 under [KB-1] and [WEB-2].\n\n## Citation Verification\n\n- bad"
    clean = redact_for_client(raw)
    assert "[KB-1]" not in clean
    assert "[WEB-2]" not in clean
    assert "Citation Verification" not in clean

    data, name, _ = export_report_bytes(raw, "Test", "md", client_safe=True)
    text = data.decode("utf-8")
    assert "[KB-1]" not in text
    assert "Client Memo" in name or "Test" in name


def test_strict_citations_strips_failed_markers():
    from backend.app.core import citation_verifier as cv

    original = cv.STRICT_CITATIONS
    cv.STRICT_CITATIONS = True
    try:
        text = "Claim [KB-1] and phantom [KB-9]."
        chunks = [{"metadata": {"filename": "a.pdf"}, "content": "x"}]
        out, _stats = cv.apply_strict_citations(text, chunks, [])
        assert "[KB-9]" not in out
        assert "[KB-1]" in out or "KB-1" in out
    finally:
        cv.STRICT_CITATIONS = original


def test_oral_argument_intent():
    from backend.app.core.oral_argument import is_oral_argument_request

    assert is_oral_argument_request("Prepare oral argument questions bench may ask")
    assert not is_oral_argument_request("What is Section 302 IPC?")


def test_matter_autopilot_empty():
    from backend.app.core.matter_autopilot import analyze_matter

    r = analyze_matter("nobody", "no-matter")
    assert r["ok"] is False
    assert r["suggested_queries"] == []


def test_contradiction_checker():
    from backend.app.core.contradiction_checker import find_contradictions

    chunks = [
        {"content": "The accused denied injury.", "metadata": {"filename": "a.pdf"}},
        {"content": "Medical report shows injury.", "metadata": {"filename": "b.pdf"}},
    ]
    hits = find_contradictions(chunks)
    assert isinstance(hits, list)


def test_similar_case_clusters():
    from backend.app.core.research_service import similar_case_clusters

    rows = similar_case_clusters("test-user-phase2")
    assert isinstance(rows, list)


def test_quick_fact_dimension():
    from backend.app.core.web_intelligence import detect_research_dimension, DIMENSION_QUICK

    assert detect_research_dimension("who is cji of india") == DIMENSION_QUICK


def test_filter_open_law_history_drops_kb():
    from backend.app.core.web_intelligence import _filter_open_law_history

    hist = [
        {"role": "user", "content": "section 300"},
        {"role": "assistant", "content": "From Your Documents (Knowledge Base) IPC list"},
        {"role": "user", "content": "explain rg kar case"},
    ]
    out = _filter_open_law_history(hist)
    assert len(out) == 2
    assert out[-1]["content"] == "explain rg kar case"

    from backend.app.core.source_badges import enrich_web_sources

    out = enrich_web_sources([{"title": "SCI", "href": "https://main.sci.gov.in/x", "date": "2024-01-01"}])
    assert out[0]["trust_badge"] == "Official"
    assert out[0]["freshness"] == "2024-01-01"
