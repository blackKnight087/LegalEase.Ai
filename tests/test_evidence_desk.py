"""Litigation Evidence Desk — cross-matter aggregation."""
from __future__ import annotations

from backend.app.core.evidence_desk import get_evidence_desk


def test_evidence_desk_empty_matters(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.evidence_desk.list_matters",
        lambda uid, **kw: [],
    )
    out = get_evidence_desk("user-test")
    assert out["ok"] is True
    assert out["summary"]["total_matters"] == 0
    assert out["contradictions"] == []
    assert out["blind_spots"] == []


def test_evidence_desk_aggregates_contradictions(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.evidence_desk.list_matters",
        lambda uid, **kw: [
            {"matter_id": "m1", "matter_name": "Test Matter"},
        ],
    )
    monkeypatch.setattr(
        "backend.app.core.evidence_desk.list_matter_documents",
        lambda uid, mid: [{"document_id": "d1"}],
    )
    monkeypatch.setattr(
        "backend.app.core.evidence_desk.list_contradictions",
        lambda uid, mid: [
            {
                "contradiction_id": "c1",
                "contradiction_type": "statement",
                "topic": "Timeline",
                "statement_a": "At 9pm",
                "statement_b": "At 11pm",
                "confidence": 0.8,
                "source_hint": "",
                "created_at": "",
            }
        ],
    )
    out = get_evidence_desk("user-test")
    assert out["summary"]["contradiction_count"] == 1
    assert out["contradictions"][0]["matter_name"] == "Test Matter"
