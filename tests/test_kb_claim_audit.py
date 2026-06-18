"""KB claim audit — statute mention-only and sentence grounding."""
from __future__ import annotations

from backend.app.core.kb_claim_audit import (
    answer_has_legal_definition_leak,
    build_statute_mention_only_answer,
    chunk_defines_section,
    is_statute_explanation_query,
    should_block_llm_for_statute_query,
    try_statute_safe_answer,
)


CHARGE_ONLY = [
    {
        "content": (
            "Case 3: State vs Dev Mallick (Theft – IPC 379)\n"
            "The accused Dev Mallick was charged under IPC Section 379 after CCTV footage."
        ),
        "metadata": {"filename": "cases.pdf"},
        "final_score": 0.9,
    }
]

FULL_DEF = [
    {
        "content": (
            "IPC Section 379 — Theft\n"
            "Whoever commits theft shall be punished with imprisonment up to three years."
        ),
        "metadata": {"filename": "ipc.pdf"},
    }
]

GREEN_BUILDERS = [
    {
        "content": (
            "Case 4: Green Builders Pvt Ltd vs Municipal Authority\n"
            "The petitioner Green Builders challenged the stop-work notice issued by the authority."
        ),
        "metadata": {"filename": "cases.pdf"},
        "final_score": 0.95,
    },
    {
        "content": (
            "Case 3: State vs Dev Mallick (Theft – IPC 379)\n"
            "The accused Dev Mallick was charged under IPC 379."
        ),
        "metadata": {"filename": "cases.pdf"},
        "final_score": 0.7,
    },
]


def test_statute_explain_detected():
    assert is_statute_explanation_query("explain the (Theft - IPC 379)")
    assert is_statute_explanation_query("Explain IPC 379")


def test_charge_only_not_definition():
    assert not chunk_defines_section(CHARGE_ONLY, "379")
    block, reason = should_block_llm_for_statute_query("Explain IPC 379", CHARGE_ONLY)
    assert block
    assert "mention_only" in reason or reason == "no_chunks"


def test_full_definition_allowed():
    assert chunk_defines_section(FULL_DEF, "379")
    block, _ = should_block_llm_for_statute_query("Explain IPC 379", FULL_DEF)
    assert not block


def test_mention_only_answer_text():
    out = build_statute_mention_only_answer("Explain IPC 379", CHARGE_ONLY, ["379"])
    assert out
    assert "does not contain" in out.lower()
    assert "379" in out
    assert "whoever" not in out.lower()


def test_try_statute_safe_blocks_hallucination():
    out = try_statute_safe_answer("explain Theft IPC 379", CHARGE_ONLY)
    assert out
    assert "definition" in out.lower() or "does not contain" in out.lower()


def test_detect_pretrained_theft_definition():
    bad = (
        "IPC Section 379 defines theft. Whoever moves property dishonestly "
        "with intention to take shall be punished with imprisonment."
    )
    assert answer_has_legal_definition_leak(bad, CHARGE_ONLY)


def test_green_builders_case_segment():
    from backend.app.core.case_narrative_engine import build_case_answer_from_chunks

    ans = build_case_answer_from_chunks(
        "explain Green Builders Pvt Ltd vs Municipal Authority",
        GREEN_BUILDERS,
    )
    assert ans
    assert "green builders" in ans.lower()
    assert "dev mallick" not in ans.lower()
