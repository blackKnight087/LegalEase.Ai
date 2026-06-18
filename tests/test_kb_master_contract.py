"""
Single contract test module — all critical KB behaviors in one place.

Run: py -m pytest tests/test_kb_master_contract.py -q

If this file passes, indexing, routing, memory, and matter separation are healthy.
"""
from __future__ import annotations

import uuid

import pytest

from intent_engine import classify_intent
from kb_retrieval import is_comparison_query
from backend.app.core.case_entity_resolver import chunk_matches_case, extract_case_needles
from backend.app.core.kb_context_resolver import detect_topic_shift, extract_query_signals
from backend.app.core.learning_engine import _answer_matches_case_needles
from backend.app.services.legal_orchestrator_v2 import _is_constitutional_text, parse_query
from kb_query_types import is_case_query, is_document_fact_query
from kb_preprocess import extract_primary_section


class TestKBMasterContract:
    """One module = one checklist for Global KB correctness."""

    def test_indexing_metadata_tuple(self):
        code, sec = extract_primary_section("IPC Section 307 — Attempt to Murder\nWhoever…")
        assert code == "IPC"
        assert sec == "307"

    def test_litigation_not_comparison(self):
        q = "Medisure Hospital vs Former Consultant"
        assert is_case_query(q)
        assert not is_comparison_query(q)
        assert classify_intent(q, []).primary.value != "comparison"

    def test_case_not_constitutional(self):
        q = "Riya Banerjee vs State Medical Board (Article 21 – Right to Life)"
        assert not _is_constitutional_text(q)
        assert parse_query(q).query_class.value == "case_law"

    def test_two_party_chunk_match(self):
        needles = extract_case_needles("Medisure Hospital vs Former Consultant")
        bad = {"content": "SecureTech Pvt Ltd vs Former Employee (NDA)"}
        good = {"content": "Medisure Hospital vs Former Consultant confidentiality breach"}
        assert not chunk_matches_case(bad, needles)
        assert chunk_matches_case(good, needles)

    def test_memory_rejects_wrong_case(self):
        q = "State vs Dev Mallick"
        assert not _answer_matches_case_needles(
            q, "## Right to Life (Article 21)\nCase 6: Riya Banerjee vs State Medical Board"
        )

    def test_document_fact_query(self):
        assert is_document_fact_query("Who sought child custody?")

    def test_topic_shift_new_company(self):
        session = {"last_topic": "NDA Alpha Corp", "last_user_query": "Summarize NDA"}
        signals = extract_query_signals("SecureTech Pvt Ltd indemnity clause")
        assert detect_topic_shift(signals, session)

    def test_constitutional_rights_not_case_fragment(self):
        from answer_orchestrator import format_constitutional_rights_answer

        case_chunk = {
            "content": (
                "Case 6: Riya Banerjee vs State Medical Board (Article 21 – Right to Life & Dignity) "
                "FIR No. 12/2024. Hearing 1: petitioner argued Article 21."
            ),
            "metadata": {"filename": "LegalEase_Realistic_Indian_Cases_Vol2.pdf"},
        }
        const_chunk = {
            "content": (
                "Fundamental Rights under the Constitution include: "
                "Right to Equality (Article 14), Right to Freedom (Article 19), "
                "Right to Life (Article 21), Right against Exploitation (Article 23)."
            ),
            "metadata": {"filename": "Indian_Constitution_Reference.pdf"},
        }
        assert format_constitutional_rights_answer("Fundamental Rights", [case_chunk]) == ""
        assert format_constitutional_rights_answer(
            "explain Fundamental Rights", [const_chunk, case_chunk]
        ) == ""
        ans = format_constitutional_rights_answer(
            "what are the fundamental rights", [const_chunk, case_chunk]
        )
        assert ans
        assert "Article 14" in ans
        assert "Article 19" in ans
        assert len(ans) > 80

    def test_section_explanation_strips_test_meta(self):
        from kb_content_cleaner import format_statute_section_fields

        block = (
            "IPC Section 499 — Defamation\n"
            "Meaning: Defamation.\n"
            "Explanation: This section is included to rigorously test retrieval accuracy.\n"
            "Example: A practical scenario involving"
        )
        out = format_statute_section_fields(block, section="499", law="IPC")
        assert "rigorously test" not in out.lower()
        assert "Defamation" in out
