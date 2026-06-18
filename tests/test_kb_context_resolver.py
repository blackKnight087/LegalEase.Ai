"""Generalized KB context — topic shift vs continuity (no case-specific hardcoding)."""
from __future__ import annotations

import pytest

from backend.app.core.kb_context_resolver import (
    classify_retrieval_context,
    detect_topic_shift,
    extract_query_signals,
    effective_session_for_query,
)
from backend.app.core.kb_query_memory import expand_kb_query
from backend.app.services.followup_detector import get_effective_session_memory, requires_fresh_retrieval


class TestTopicShiftDetection:
    def test_custody_after_cyber_fraud_session_is_fresh(self):
        session = {
            "last_topic": "cyber fraud FIR hearing",
            "last_user_query": "Explain cyber fraud case",
            "last_assistant_summary": "FIR 112/2024 cyber fraud accused Rahul",
        }
        ctx = classify_retrieval_context("Who sought child custody?", session)
        assert ctx["fresh_retrieval"] or ctx["topic_shift"]
        assert get_effective_session_memory("Who sought child custody?", session) == {}

    def test_witness_name_not_expanded_to_prior_ipc_section(self):
        session = {
            "last_section": "420",
            "last_law": "IPC",
            "last_topic": "IPC Section 420",
        }
        expanded = expand_kb_query("What did witness Priya Malhotra say?", session_mem=session)
        assert "420" not in expanded
        assert requires_fresh_retrieval("What did witness Priya Malhotra say?", session)

    def test_deictic_witness_allows_continuity(self):
        session = {
            "last_case": "State vs Imran Khan",
            "last_topic": "State vs Imran Khan",
            "last_assistant_summary": "Witness deposition in Imran Khan matter",
        }
        ctx = classify_retrieval_context("What did the witness say?", session)
        assert ctx["continuity_allowed"] or not ctx["topic_shift"]

    def test_constitutional_after_ipc_session(self):
        session = {
            "last_section": "299",
            "last_law": "IPC",
            "last_topic": "IPC Section 299",
        }
        signals = extract_query_signals("Explain Right to Equality")
        assert detect_topic_shift(signals, session) or requires_fresh_retrieval(
            "Explain Right to Equality", session
        )

    def test_entity_in_query_absent_from_session_triggers_shift(self):
        session = {"last_topic": "NDA Alpha Corp", "last_user_query": "Summarize NDA"}
        signals = extract_query_signals("SecureTech Pvt Ltd indemnity clause")
        assert detect_topic_shift(signals, session)

    def test_punishment_follow_up_keeps_session(self):
        session = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
        assert effective_session_for_query("What punishment?", session) == session
        expanded = expand_kb_query("What punishment?", session_mem=session)
        assert "307" in expanded
