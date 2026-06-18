"""Court Day Command Center — parse and matter matching."""
from __future__ import annotations

from backend.app.core.court_day import _score_matter, parse_and_match_cause_list


def test_score_matter_case_number_high():
    matter = {
        "matter_id": "m1",
        "matter_name": "State v Kumar",
        "case_number": "CRL/1234/2024",
        "client_name": "",
        "opposing_party": "",
        "venue": "",
    }
    line = "CRL/1234/2024 listed for arguments before Hon'ble Justice"
    score, conf = _score_matter(line, matter)
    assert score >= 0.9
    assert conf == "high"


def test_parse_and_match_empty_text():
    out = parse_and_match_cause_list("user-1", "")
    assert out["ok"] is True
    assert out["parsed_count"] == 0
    assert out["rows"] == []


def test_parse_and_match_with_sample(monkeypatch):
    monkeypatch.setattr(
        "backend.app.core.court_day.list_matters",
        lambda uid, **kw: [
            {
                "matter_id": "mid-1",
                "matter_name": "Sharma v State",
                "case_number": "WP 99/2024",
                "client_name": "Sharma",
                "opposing_party": "State",
                "venue": "Delhi HC",
            }
        ],
    )
    text = (
        "15-03-2025\n"
        "Before Hon'ble Justice Singh\n"
        "WP 99/2024 Sharma v State — listed for admission\n"
    )
    out = parse_and_match_cause_list("user-1", text)
    assert out["parsed_count"] >= 1
    row = out["rows"][0]
    assert row.get("hearing_date")
    assert row.get("confidence") in ("high", "medium", "low", "none")
