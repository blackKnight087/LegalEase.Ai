"""KB trust CI gate — golden manifest regression without LLM or FAISS."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.app.core.kb_claim_audit import (
    answer_has_legal_definition_leak,
    build_statute_mention_only_answer,
    chunk_defines_section,
    is_statute_explanation_query,
    should_block_llm_for_statute_query,
    try_statute_safe_answer,
)
from backend.app.core.kb_hybrid_gate import assess_kb_for_hybrid
from backend.app.core.case_narrative_engine import build_case_answer_from_chunks
from kb_response_state import KB_NOT_FOUND_MESSAGE, contains_not_found_phrase

MANIFEST_PATH = Path(__file__).resolve().parent / "data" / "kb_golden_manifest.json"


def _load_manifest() -> dict:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def _chunks(manifest: dict, key: str) -> list:
    return list(manifest["chunk_sets"].get(key, []))


def _case(manifest: dict, case_id: str) -> dict:
    for c in manifest["cases"]:
        if c["id"] == case_id:
            return c
    raise KeyError(case_id)


@pytest.fixture(scope="module")
def manifest():
    return _load_manifest()


@pytest.mark.ci_gate
def test_manifest_statute_explain_detected(manifest):
    case = _case(manifest, "statute_explain_detected")
    assert is_statute_explanation_query(case["query"])
    assert is_statute_explanation_query("Explain IPC 379")


@pytest.mark.ci_gate
def test_manifest_charge_only_blocks_llm(manifest):
    case = _case(manifest, "charge_only_blocks_llm")
    chunks = _chunks(manifest, case["chunk_set"])
    assert not chunk_defines_section(chunks, case["sections"][0])
    block, reason = should_block_llm_for_statute_query(case["query"], chunks)
    assert block
    assert "mention_only" in reason or reason == "no_chunks"


@pytest.mark.ci_gate
def test_manifest_full_definition_allows_llm(manifest):
    case = _case(manifest, "full_definition_allows_llm")
    chunks = _chunks(manifest, case["chunk_set"])
    assert chunk_defines_section(chunks, case["sections"][0])
    block, _ = should_block_llm_for_statute_query(case["query"], chunks)
    assert not block


@pytest.mark.ci_gate
def test_manifest_mention_only_answer(manifest):
    case = _case(manifest, "mention_only_answer_shape")
    chunks = _chunks(manifest, case["chunk_set"])
    out = build_statute_mention_only_answer(case["query"], chunks, case["sections"])
    assert out
    assert "does not contain" in out.lower()
    assert "379" in out
    assert "whoever" not in out.lower()
    safe = try_statute_safe_answer(case["query"], chunks)
    assert safe
    assert "definition" in safe.lower() or "does not contain" in safe.lower()


@pytest.mark.ci_gate
def test_manifest_definition_leak_blocked(manifest):
    case = _case(manifest, "definition_leak_detected")
    chunks = _chunks(manifest, case["chunk_set"])
    assert answer_has_legal_definition_leak(case["leak_text"], chunks)


@pytest.mark.ci_gate
def test_manifest_case_segment_isolation(manifest):
    case = _case(manifest, "green_builders_isolation")
    chunks = _chunks(manifest, case["chunk_set"])
    ans = build_case_answer_from_chunks(case["query"], chunks)
    assert ans
    low = ans.lower()
    for token in case["expect_contains"]:
        assert token in low
    for token in case["expect_excludes"]:
        assert token not in low


@pytest.mark.ci_gate
def test_manifest_hybrid_not_found_patterns(manifest):
    empty = _case(manifest, "hybrid_not_found_empty")
    chunks = _chunks(manifest, empty["chunk_set"])
    use_kb, reason = assess_kb_for_hybrid(empty["query"], empty.get("kb_answer", ""), chunks)
    assert not use_kb
    assert reason in ("no_chunks", "kb_not_found")

    phrase = _case(manifest, "hybrid_not_found_phrase")
    chunks_p = _chunks(manifest, phrase["chunk_set"])
    use_kb2, reason2 = assess_kb_for_hybrid(
        phrase["query"], phrase["kb_answer"], chunks_p
    )
    assert not use_kb2
    assert reason2 == "kb_not_found"
    assert contains_not_found_phrase(phrase["kb_answer"])
    assert KB_NOT_FOUND_MESSAGE in phrase["kb_answer"]


@pytest.mark.ci_gate
def test_manifest_matter_scope_routing(manifest):
    matter_case = _case(manifest, "matter_scope_routing")
    captured: dict = {}

    def fake_check(user_id, matter_id=None, retrieval_scope="global"):
        captured["retrieval_scope"] = retrieval_scope
        captured["matter_id"] = matter_id
        return False, "blocked-for-test"

    with patch("backend.app.core.kb_index_gate.check_kb_ready_for_query", fake_check):
        with patch("backend.app.services.chat_service.kb_log", lambda *a, **k: None):
            with patch(
                "backend.app.core.kb_gemini_safety.enforce_kb_gemini_policy",
                lambda **k: None,
            ):
                from backend.app.services.chat_service import _run_kb_turn

                _run_kb_turn(
                    "user-1",
                    "What evidence supports the alibi?",
                    [],
                    matter_id=matter_case["matter_id"],
                    matter_mode=matter_case["matter_mode"],
                )

    assert captured.get("retrieval_scope") == matter_case["expect_retrieval_scope"]
    assert captured.get("matter_id") == matter_case["matter_id"]


@pytest.mark.ci_gate
def test_manifest_global_scope_default(manifest):
    global_case = _case(manifest, "global_scope_default")
    captured: dict = {}

    def fake_check(user_id, matter_id=None, retrieval_scope="global"):
        captured["retrieval_scope"] = retrieval_scope
        captured["matter_id"] = matter_id
        return False, "blocked-for-test"

    with patch("backend.app.core.kb_index_gate.check_kb_ready_for_query", fake_check):
        with patch("backend.app.services.chat_service.kb_log", lambda *a, **k: None):
            with patch(
                "backend.app.core.kb_gemini_safety.enforce_kb_gemini_policy",
                lambda **k: None,
            ):
                from backend.app.services.chat_service import _run_kb_turn

                _run_kb_turn("user-1", global_case["query"], [])

    assert captured.get("retrieval_scope") == global_case["expect_retrieval_scope"]
    assert captured.get("matter_id") is None
