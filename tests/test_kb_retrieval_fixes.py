"""KB retrieval pipeline fixes — unlinked scope, query clean, off-topic gate."""
from __future__ import annotations

import pytest


def test_strip_chat_routing_prefix():
    from backend.app.core.kb_query_clean import strip_chat_routing_prefix

    raw = (
        "MATTER AI RULES: Answer in clear structured prose.\n\n"
        "User question: Explain in simple language"
    )
    assert strip_chat_routing_prefix(raw) == "Explain in simple language"
    assert strip_chat_routing_prefix("IPC Section 323") == "IPC Section 323"


def test_matter_mode_instruction_empty_without_mode():
    from backend.app.services.chat_service import _matter_mode_instruction

    assert _matter_mode_instruction(None) == ""
    assert _matter_mode_instruction("") == ""
    assert "MATTER AI RULES" in _matter_mode_instruction("matter_only")


def test_off_topic_general_knowledge():
    from kb_rag_decision import evaluate_retrieval, is_off_topic_general_knowledge

    assert is_off_topic_general_knowledge("What is the capital of France?")
    assert not is_off_topic_general_knowledge("IPC Section 323")
    found, score, decision, debug = evaluate_retrieval(
        "What is the capital of France?", []
    )
    assert not found
    assert debug.get("reason") == "off_topic_general_knowledge"


def test_filter_chunks_unlinked_only(monkeypatch):
    from backend.app.core.kb_doc_scope import filter_chunks_unlinked_only

    chunks = [
        {
            "content": "linked matter",
            "metadata": {"filename": "Matter_Case.pdf", "doc_id": "linked-1"},
        },
        {
            "content": "statute kb",
            "metadata": {"filename": "Dense_KB.pdf", "doc_id": "free-1"},
        },
    ]

    class FakeConn:
        def execute(self, *args, **kwargs):
            return self

        def fetchall(self):
            return [("linked-1", "Matter_Case.pdf")]

        def close(self):
            pass

    monkeypatch.setattr(
        "backend.app.core.database.connect_data_db",
        lambda: FakeConn(),
    )
    kept = filter_chunks_unlinked_only("u1", chunks)
    assert len(kept) == 1
    assert kept[0]["metadata"]["filename"] == "Dense_KB.pdf"


def test_normalize_chat_scope_kb_ignores_matter():
    from backend.app.core.matter_policy import normalize_chat_scope, normalize_matter_ai_scope

    assert normalize_chat_scope("knowledge_base", "matter-123") is None
    assert normalize_chat_scope("hybrid", "matter-123") == "matter-123"
    assert normalize_matter_ai_scope("matter-123", "matter_only") == "matter-123"
    assert normalize_matter_ai_scope("matter-123", None) is None


def test_fresh_query_does_not_inherit_prior_section():
    from backend.app.services.followup_detector import requires_fresh_retrieval

    assert requires_fresh_retrieval("Important Case Law")
    assert requires_fresh_retrieval("Sample NDA Agreement")
    assert not requires_fresh_retrieval("explain in simple language")


def test_enrich_parsed_skips_context_for_case_law():
    from backend.app.services.legal_orchestrator_v2 import (
        ParsedQuery,
        QueryClass,
        _enrich_parsed_from_context,
    )

    parsed = ParsedQuery(
        raw="Important Case Law",
        normalized="Important Case Law",
        query_class=QueryClass.CASE_LAW,
        law_systems=[],
        sections=[],
    )
    out = _enrich_parsed_from_context(
        parsed,
        original_query="Important Case Law",
        search_q="Important Case Law",
        history=[
            {"role": "user", "content": "Section 300"},
            {"role": "assistant", "content": "IPC Section 300 murder..."},
        ],
        session_id="test-session",
    )
    assert out.query_class == QueryClass.CASE_LAW
    assert out.sections == []


def test_nda_query_not_promoted_to_prior_section():
    from backend.app.services.legal_orchestrator_v2 import QueryClass, parse_query

    parsed = parse_query("Sample NDA Agreement")
    assert parsed.query_class == QueryClass.DOCUMENT_QA
    assert parsed.sections == []


def test_format_statute_section_answer_includes_explanation():
    from answer_orchestrator import format_statute_section_answer

    block = """
IPC Section 354
Meaning: Assault or criminal force against a woman.
Explanation: This section is included for testing section retrieval, exact matching, punishment
extraction, semantic understanding, and follow-up reasoning in a legal AI system.
Example: Example legal scenario involving IPC 354 interpreted according to legal intent, evidence,
and punishment.
"""
    chunks = [{"content": block, "metadata": {"filename": "Dense_KB.pdf"}}]
    out = format_statute_section_answer("explanation of IPC Section 354", chunks, "354", "ipc")
    assert "354" in out
    assert "Assault or criminal force" in out
    assert "Explanation" in out
    assert "Example" in out
    assert "testing section retrieval" in out


def test_global_kb_index_filters_matter_and_orphan_chunks(monkeypatch):
    from pathlib import Path

    from backend.app.core.kb_doc_scope import (
        apply_unlinked_only_scope,
        filter_chunks_unlinked_only,
        is_global_kb_index_dir,
        is_unlinked_index_dir,
    )

    global_idx = Path("C:/faiss/user1/global_kb")
    legacy_idx = Path("C:/faiss/user1/_unlinked")
    assert is_global_kb_index_dir(global_idx)
    assert not is_unlinked_index_dir(global_idx)
    assert is_unlinked_index_dir(legacy_idx)

    scope = apply_unlinked_only_scope("u1", {"strict": True}, global_idx)
    assert not scope.get("unlinked_only")

    class FakeConn:
        def execute(self, sql, *args):
            self._sql = str(sql)
            return self

        def fetchall(self):
            if "!= ''" in self._sql:
                return [("linked-1", "linked.pdf")]
            if "= ''" in self._sql:
                return [("global-1", "statute.pdf")]
            return []

        def close(self):
            pass

    monkeypatch.setattr(
        "backend.app.core.database.connect_data_db",
        lambda: FakeConn(),
    )

    chunks = [
        {
            "content": "matter leak",
            "metadata": {"filename": "linked.pdf", "doc_id": "linked-1"},
        },
        {
            "content": "deleted orphan",
            "metadata": {"filename": "gone.pdf", "doc_id": "orphan-9"},
        },
        {
            "content": "IPC Section 467",
            "metadata": {"filename": "statute.pdf", "doc_id": "global-1"},
        },
    ]
    kept = filter_chunks_unlinked_only("u1", chunks, index_dir=global_idx)
    assert len(kept) == 1
    assert kept[0]["metadata"]["doc_id"] == "global-1"


def test_comprehensive_topic_not_expanded_to_prior_section():
    from conversation_context import enrich_query_with_context

    history = [
        {"role": "user", "content": "IPC Section 299"},
        {"role": "assistant", "content": "IPC Section 299 culpable homicide"},
    ]
    out = enrich_query_with_context(
        "Comprehensive Criminal Law Testing Material", history
    )
    assert "Section 299" not in out
    assert "Comprehensive Criminal Law Testing Material" in out


def test_comparison_table_includes_both_sections():
    from kb_compare_engine import format_comparison_pro

    block_299 = """
IPC Section 299
Meaning: Culpable Homicide — causing death with intention or knowledge that an act may cause death.
"""
    block_300 = """
IPC Section 300
Meaning: Murder — culpable homicide becomes murder when intent, brutality, or dangerous circumstances exist.
"""
    chunks = [{"content": block_299 + "\n" + block_300}]
    entities = [{"type": "IPC", "section": "299"}, {"type": "IPC", "section": "300"}]
    out = format_comparison_pro("Difference between IPC 299 and IPC 300", chunks, entities)
    assert "Comparison" in out
    assert "299" in out
    assert "300" in out
    assert "|" in out
    assert "Key Difference" in out


def test_kb_synthesis_meta_tracks_ollama():
    from backend.app.services.legal_orchestrator_v2 import (
        get_last_kb_synthesis_meta,
        reset_kb_synthesis_meta,
    )

    reset_kb_synthesis_meta()
    assert get_last_kb_synthesis_meta().get("ollama_invoked") is False


def test_litigation_vs_not_comparison():
    from intent_engine import classify_intent
    from kb_retrieval import is_comparison_query

    q = "explain Medisure Hospital vs Former Consultant"
    assert not is_comparison_query(q)
    profile = classify_intent(q, [])
    assert profile.primary.value != "comparison"


def test_case_caption_not_constitutional():
    from backend.app.services.legal_orchestrator_v2 import _is_constitutional_text, parse_query

    q = "Riya Banerjee vs State Medical Board (Article 21 – Right to Life)"
    assert not _is_constitutional_text(q)
    parsed = parse_query(q)
    assert parsed.query_class.value == "case_law"


def test_both_parties_required_for_chunk_match():
    from backend.app.core.case_entity_resolver import chunk_matches_case, extract_case_needles

    needles = extract_case_needles("Medisure Hospital vs Former Consultant")
    wrong = {
        "content": "Case 5: SecureTech Pvt Ltd vs Former Employee (NDA Breach) Medisure unrelated",
    }
    right = {
        "content": "Case 5: Medisure Hospital vs Former Consultant (Confidentiality Breach) alleged breach",
    }
    assert not chunk_matches_case(wrong, needles)
    assert chunk_matches_case(right, needles)


def test_document_fact_query_detected():
    from kb_query_types import is_document_fact_query

    assert is_document_fact_query("Who sought child custody?")


def test_memory_rejects_wrong_case_answer():
    from backend.app.core.learning_engine import _answer_matches_case_needles

    q = "State vs Dev Mallick"
    wrong = "## Right to Life (Article 21)\nCase 6: Riya Banerjee vs State Medical Board"
    right = "Case 3: State vs Dev Mallick (Theft – IPC 379) Complainant filed FIR"
    assert not _answer_matches_case_needles(q, wrong)
    assert _answer_matches_case_needles(q, right)
