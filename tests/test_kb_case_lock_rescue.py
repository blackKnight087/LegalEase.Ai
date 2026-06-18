"""KB case lock rescue and party pinning."""
from __future__ import annotations

from backend.app.core.kb_case_context_lock import (
    lock_chunks_to_query,
    normalize_case_query,
    pin_party_matched_chunks,
)
from backend.app.core.case_entity_resolver import (
    chunk_matches_case,
    extract_case_needles,
    segment_matches_case_needles,
)


def test_normalize_trailing_explain():
    assert "explain" not in normalize_case_query("State vs Dev Mallick explain").lower().split()[-1:]


def test_state_vs_requires_only_accused_party():
    text = "Case 3: State vs Dev Mallick (Theft – IPC 379)\nThe accused Dev Mallick was charged."
    needles = extract_case_needles("State vs Dev Mallick")
    assert segment_matches_case_needles(text, needles)
    assert chunk_matches_case({"content": text}, needles)


def test_pin_party_restores_dropped_chunk():
    good = {
        "content": "Case 3: State vs Dev Mallick\nDev Mallick charged under IPC 379.",
        "final_score": 1.4,
    }
    bad = {"content": "Suggested KB Testing Questions", "final_score": 0.6}
    scoped = pin_party_matched_chunks(
        "State vs Dev Mallick",
        [good, bad],
        [bad],
    )
    assert any("Dev Mallick" in (c.get("content") or "") for c in scoped)


def test_lock_keeps_top_when_filters_empty():
    chunk = {
        "content": "Case 2: Meera Joshi vs Aryan Joshi\nPetitioner Meera Joshi sought divorce.",
        "final_score": 1.2,
        "metadata": {},
    }
    locked = lock_chunks_to_query("Meera Joshi vs Aryan Joshi", [chunk])
    assert locked
    assert "Meera" in locked[0]["content"]
