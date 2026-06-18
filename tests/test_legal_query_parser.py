"""Mandatory routing tests — section entities must always beat IPC replacement."""
from __future__ import annotations

import uuid

import pytest

KB_TEST_DOC = """
Legal Knowledge Base Testing Document

The Indian Penal Code (IPC), 1860 has been replaced by Bharatiya Nyaya Sanhita (BNS), 2023.

IPC Section 299 — Culpable Homicide
Whoever causes death by doing an act with the intention of causing death commits culpable homicide.

IPC Section 300 — Murder
Culpable homicide becomes murder when the act is committed with clear intent, dangerous circumstances, or exceptional brutality.

IPC Section 302 — Punishment for Murder
Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine.

IPC Section 307 — Attempt to Murder
Whoever does any act with such intention or knowledge that if he by that act caused death, he would be guilty of murder, shall be punished with imprisonment which may extend to ten years, and shall also be liable to fine.

IPC Section 420 — Cheating
Whoever cheats and thereby dishonestly induces the person deceived to deliver any property, commits cheating.

BNS Section 103 — Punishment for Murder
Provides punishment for murder under the new criminal law framework.
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "legal_route.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


class TestLegalQueryParser:
    def test_extract_legal_entities_ipc(self):
        from backend.app.services.legal_query_parser import extract_legal_entities

        ents = extract_legal_entities("Explain IPC 299")
        assert any(e["number"] == "299" for e in ents)

    def test_extract_reverse_ipc(self):
        from backend.app.services.legal_query_parser import extract_legal_entities

        ents = extract_legal_entities("307 IPC")
        assert any(e["number"] == "307" for e in ents)

    def test_extract_comparison_both_sections(self):
        from backend.app.services.legal_query_parser import extract_legal_entities, section_numbers_from_query

        nums = section_numbers_from_query("Difference between IPC 299 and 300")
        assert "299" in nums and "300" in nums

    def test_compare_ipc_and_bare_number(self):
        from backend.app.services.legal_query_parser import section_numbers_from_query

        nums = section_numbers_from_query("Compare IPC 302 and 307")
        assert "302" in nums and "307" in nums

    def test_what_replaced_ipc_not_section(self):
        from backend.app.services.legal_query_parser import extract_legal_entities, parse_legal_query

        assert parse_legal_query("What replaced IPC?") is None
        assert extract_legal_entities("What replaced IPC?") == []

    def test_is_law_replacement_not_section(self):
        from kb_legal_query_rewrite import is_law_replacement_query

        assert not is_law_replacement_query("IPC 307")
        assert not is_law_replacement_query("Explain IPC 299")
        assert not is_law_replacement_query("Difference between IPC 299 and 300")
        assert not is_law_replacement_query("IPC 420 vs BNS equivalent")
        assert is_law_replacement_query("What replaced IPC?")

    def test_route_legal_query_modes(self):
        from backend.app.services.legal_query_parser import route_legal_query

        assert route_legal_query("What punishment under IPC 307?") == "punishment"
        assert route_legal_query("Explain IPC 299") == "section_explanation"
        assert route_legal_query("Difference between IPC 299 and 300") == "comparison"
        assert route_legal_query("What replaced IPC?") == "law_replacement"

    def test_307_punishment_parsed(self):
        from backend.app.services.legal_query_parser import (
            parse_legal_query_structured,
            section_numbers_from_query,
        )

        assert "307" in section_numbers_from_query("307 punishment")
        p = parse_legal_query_structured("307 punishment")
        assert p["section"] == "307"
        assert p["intent"] == "punishment"
        assert p["law"] == "ipc"

    def test_299_vs_300_same_law_comparison(self):
        from backend.app.services.legal_query_parser import (
            is_same_law_comparison,
            parse_legal_query_structured,
            section_numbers_from_query,
        )
        from kb_retrieval import extract_comparison_sections

        nums = section_numbers_from_query("299 vs 300")
        assert nums == ["299", "300"] or set(nums) == {"299", "300"}
        assert extract_comparison_sections("299 vs 300") == ["299", "300"]
        assert is_same_law_comparison("299 vs 300")
        cmp = parse_legal_query_structured("299 vs 300")["comparison"]
        assert cmp["left_section"] == "299"
        assert cmp["right_section"] == "300"
        assert cmp["same_law"] is True
        assert cmp["mapping_mode"] is False

    def test_detect_query_type_routing(self):
        from kb_query_types import QueryType, detect_query_type

        assert detect_query_type("Explain IPC 299") == QueryType.SECTION_EXPLANATION
        assert detect_query_type("Difference between IPC 299 and 300") == QueryType.COMPARISON
        assert detect_query_type("Compare IPC 302 and 307") == QueryType.COMPARISON
        assert detect_query_type("What punishment under IPC 307?") == QueryType.PUNISHMENT_QUERY
        assert detect_query_type("What replaced IPC?") == QueryType.LAW_REPLACEMENT
        assert detect_query_type("IPC 420 vs BNS equivalent") == QueryType.COMPARISON

    def test_memory_blocks_replacement_for_section_query(self):
        from backend.app.core.learning_engine import (
            lookup_answer_memory,
            store_answer_memory,
        )

        uid = f"u-{uuid.uuid4().hex[:8]}"
        store_answer_memory(
            uid,
            "What replaced IPC?",
            "The Indian Penal Code (IPC), 1860 has been replaced by Bharatiya Nyaya Sanhita (BNS), 2023.",
            source="test",
            confidence=0.95,
        )
        hit = lookup_answer_memory(uid, "IPC 307")
        assert hit is None


def _index(uid: str):
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    index_dir = get_unlinked_index_dir(uid)
    ok, msg, n = index_documents(
        [{"doc_id": str(uuid.uuid4()), "filename": "legal_kb_test_document.pdf", "text": KB_TEST_DOC}],
        index_dir=index_dir,
    )
    assert ok, msg
    return index_dir


def _run(uid: str, query: str) -> str:
    from kb_pipeline import kb_pipeline

    answer, _, _ = kb_pipeline(uid, query, [], index_dir=_index(uid))
    return answer


class TestKbRoutingIntegration:
    def test_1_ipc_299(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "IPC 299")
        assert "299" in answer
        assert "culpable homicide" in answer.lower()
        assert "replaced by Bharatiya Nyaya Sanhita" not in answer

    def test_2_explain_ipc_299(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Explain IPC 299")
        assert "299" in answer
        assert "culpable homicide" in answer.lower()
        assert "replaced by Bharatiya Nyaya Sanhita" not in answer

    def test_3_difference_299_300(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Difference between IPC 299 and 300")
        assert "299" in answer and "300" in answer
        assert "replaced by Bharatiya Nyaya Sanhita" not in answer

    def test_4_ipc_307(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "IPC 307")
        assert "307" in answer
        assert "attempt" in answer.lower()
        assert "replaced by Bharatiya Nyaya Sanhita" not in answer

    def test_5_punishment_ipc_307(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "What punishment under IPC 307?")
        assert "307" in answer
        assert "replaced by Bharatiya Nyaya Sanhita" not in answer

    def test_6_what_replaced_ipc(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "What replaced IPC?")
        assert "BNS" in answer or "Bharatiya Nyaya" in answer

    def test_7_ipc_420_vs_bns(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "IPC 420 vs BNS equivalent")
        assert "420" in answer
        assert "replaced by Bharatiya Nyaya Sanhita" not in answer or "Comparison" in answer

    def test_8_307_punishment_kb(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "307 punishment")
        assert "307" in answer
        assert "420" not in answer.split("Section")[0] if "Section" in answer else True
        al = answer.lower()
        assert "attempt" in al or "murder" in al or "imprison" in al
        assert "replaced by bharatiya" not in al

    def test_9_299_vs_300_kb(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "299 vs 300")
        assert "299" in answer and "300" in answer
        assert "bns 299" not in answer.lower() or "ipc 299" in answer.lower()

    def test_10_302_punishment(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "302 punishment")
        assert "302" in answer
        assert "murder" in answer.lower() or "punish" in answer.lower()

    def test_11_420_punishment(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "420 punishment")
        assert "420" in answer
        assert "cheat" in answer.lower() or "dishonest" in answer.lower()

    def test_replacement_only_answer_rejected(self):
        from backend.app.services.legal_query_parser import (
            answer_satisfies_section_query,
            is_law_replacement_only_answer,
        )

        bad = "The Indian Penal Code (IPC), 1860 has been replaced by Bharatiya Nyaya Sanhita (BNS), 2023."
        assert is_law_replacement_only_answer(bad)
        assert not answer_satisfies_section_query("Explain IPC 299", bad)

    def test_contamination_waived_for_section_query(self):
        from backend.app.core.kb_doc_scope import reject_cross_document_contamination

        chunks = [
            {
                "content": "IPC Section 307 — Attempt to Murder\nPunishment may extend to ten years.",
                "metadata": {"document_type": "criminal_law"},
            }
        ]
        scope = {"strict": True, "document_type": "nda"}
        ok, reason = reject_cross_document_contamination("Explain IPC 299", chunks, scope)
        assert ok
        assert "section" in reason.lower()


CONSTITUTION_TEST_DOC = """
Five Constitutional Rights (from test document)

1. Right to Equality (Article 14).
2. Right to Freedom of Speech (Article 19).
3. Right against Exploitation (Article 23).
4. Right to Freedom of Religion (Article 25).
5. Right to Life and Personal Liberty (Article 21).
"""


class TestLegalQueryEngine:
    def test_compare_ipc_302_307_same_law(self):
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            analyze_legal_query,
        )

        plan = analyze_legal_query("Compare IPC 302 and IPC 307")
        assert plan.kind == LegalQueryKind.SAME_LAW_COMPARISON
        assert plan.mapping_mode is False
        assert "302" in plan.sections and "307" in plan.sections
        assert all(e.get("type") == "IPC" for e in plan.typed_entities)

    def test_299_vs_300_same_law(self):
        from backend.app.services.legal_query_engine import analyze_legal_query

        plan = analyze_legal_query("299 vs 300")
        assert plan.comparison is True
        assert plan.mapping_mode is False
        assert plan.sections == ["299", "300"] or set(plan.sections) == {"299", "300"}

    def test_explain_multi_section(self):
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            analyze_legal_query,
        )

        plan = analyze_legal_query("Explain 300 and 307")
        assert plan.kind == LegalQueryKind.MULTI_SECTION_EXPLANATION
        assert plan.multi_entity is True
        assert "300" in plan.sections and "307" in plan.sections
        assert plan.comparison is False

    def test_constitutional_query(self):
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            analyze_legal_query,
        )

        plan = analyze_legal_query("What are constitutional rights")
        assert plan.kind == LegalQueryKind.CONSTITUTIONAL_QUERY
        assert plan.mapping_mode is False

    def test_mapping_comparison(self):
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            analyze_legal_query,
        )

        plan = analyze_legal_query("IPC 302 vs BNS equivalent")
        assert plan.mapping_mode is True
        assert plan.kind in (
            LegalQueryKind.LAW_MAPPING_COMPARISON,
            LegalQueryKind.SAME_LAW_COMPARISON,
        )

    def test_article_21_constitutional(self):
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            analyze_legal_query,
        )

        plan = analyze_legal_query("Explain Article 21")
        assert plan.kind == LegalQueryKind.CONSTITUTIONAL_QUERY

    def test_punishment_ipc_307(self):
        from backend.app.services.legal_query_engine import (
            LegalQueryKind,
            analyze_legal_query,
        )

        plan = analyze_legal_query("Punishment under IPC 307")
        assert plan.kind == LegalQueryKind.SINGLE_SECTION_PUNISHMENT
        assert plan.sections == ["307"]

    def test_validate_rejects_bns_in_same_law_compare(self):
        from backend.app.services.legal_query_engine import (
            analyze_legal_query,
            validate_response_against_plan,
        )

        plan = analyze_legal_query("Compare IPC 302 and IPC 307")
        bad = "Under the mapping in your document, IPC Section 302 corresponds to BNS Section 103."
        ok, reason = validate_response_against_plan(bad, plan)
        assert not ok
        assert reason == "unwanted_bns_mapping"

    def test_explain_not_comparison_route(self):
        from backend.app.services.legal_query_parser import is_comparison_query

        assert not is_comparison_query("explain 307 and 300")


class TestKbPhase8Integration:
    def test_compare_302_307_no_bns(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Compare IPC 302 and IPC 307")
        al = answer.lower()
        assert "302" in answer and "307" in answer
        assert "corresponds to bns" not in al

    def test_299_vs_300_no_bns(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "299 vs 300")
        assert "299" in answer and "300" in answer
        assert "corresponds to bns" not in answer.lower()

    def test_explain_300_and_307_blocks(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Explain 300 and 307")
        assert "300" in answer and "307" in answer
        assert answer.lower().count("section 300") >= 1 or "300" in answer
        assert answer.lower().count("307") >= 1

    def test_constitutional_five_rights(self):
        from rag import index_documents
        from backend.app.core.matter_index import get_unlinked_index_dir
        from kb_pipeline import kb_pipeline

        uid = f"u-{uuid.uuid4().hex[:8]}"
        index_dir = get_unlinked_index_dir(uid)
        ok, msg, _ = index_documents(
            [
                {
                    "doc_id": str(uuid.uuid4()),
                    "filename": "legal_kb_constitution.pdf",
                    "text": CONSTITUTION_TEST_DOC,
                }
            ],
            index_dir=index_dir,
        )
        assert ok, msg
        answer, _, _ = kb_pipeline(uid, "What are the five constitutional rights?", [], index_dir=index_dir)
        al = answer.lower()
        assert "article 14" in al or "equality" in al
        assert "article 21" in al or "life" in al
        assert "corresponds to bns" not in al

    def test_punishment_307_only(self):
        uid = f"u-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Punishment under IPC 307")
        assert "307" in answer
        assert "420" not in answer[:200]
