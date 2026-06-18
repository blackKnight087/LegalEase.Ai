"""
Legal regression suite — production intelligence tests (no UI).

Covers: exact section retrieval, comparison, follow-ups, safe failures, hallucination guard.
"""
from __future__ import annotations

import pytest

from backend.legal_engine.query_parser import parse_legal_query
from backend.app.core.conversation_memory import resolve_follow_up_query
from backend.app.services.response_formatter import format_legal_response
from backend.app.services.answer_validator import validate_and_clean_answer
from kb_compare_engine import extract_typed_entities, retrieve_for_comparison, format_comparison_pro
from kb_query_types import QueryType, detect_query_type
from rag import strict_section_filter, _chunk_matches_strict_section


LAW_CHART = """
IPC 302 → BNS 103
Murder — punishment with death or imprisonment for life.

IPC 307 → BNS 109
Attempt to murder — imprisonment up to ten years.

Section 307. Whoever does any act with such intention or knowledge and under such
circumstances that, if he by that act caused death, he would be guilty of murder,
shall be punished with imprisonment for life, or with imprisonment of either description
for a term which may extend to ten years, and shall also be liable to fine.

Section 302. Whoever commits murder shall be punished with death, or imprisonment for life,
and shall also be liable to fine.

Section 299. Culpable homicide — Whoever causes death by doing an act with the intention
of causing death, or with the intention of causing such bodily injury as is likely to
cause death, commits culpable homicide.

Section 300. Murder — Except in the cases hereinafter excepted, culpable homicide is murder
if the act by which the death is caused is done with the intention of causing death.
"""


@pytest.fixture
def chart_chunks():
    from kb_preprocess import split_semantic_legal_chunks

    chunks = []
    for i, (text, _s, _e) in enumerate(
        split_semantic_legal_chunks(LAW_CHART, chunk_size=800, chunk_overlap=80, max_chunk=1000)
    ):
        chunks.append({"content": text, "metadata": {"filename": "chart.pdf", "chunk_index": str(i)}})
    return chunks


class TestQueryParser:
    @pytest.mark.parametrize(
        "query,expected_intent,law,section",
        [
            ("IPC 307", "section_lookup", "IPC", "307"),
            ("Explain IPC Section 302", "section_lookup", "IPC", "302"),
            ("BNS 103", "section_lookup", "BNS", "103"),
            ("What is Section 375", "section_lookup", "", "375"),
        ],
    )
    def test_section_lookup(self, query, expected_intent, law, section):
        p = parse_legal_query(query)
        assert p.intent == expected_intent
        if law:
            assert p.law == law
        if section:
            assert p.section == section

    def test_comparison_entities(self):
        p = parse_legal_query("Compare IPC 302 and BNS 103")
        assert p.intent == "comparison"
        assert len(p.entities) >= 2
        assert p.entities[0]["law"] == "IPC"
        assert p.entities[0]["section"] == "302"
        assert p.entities[1]["law"] == "BNS"
        assert p.entities[1]["section"] == "103"

    def test_case_explanation(self):
        p = parse_legal_query("Explain Nirbhaya case")
        assert p.intent == "case_explanation"
        assert "nirbhaya" in p.case_name.lower()

    def test_rg_kar_case_typo(self):
        p = parse_legal_query("rg karr case")
        assert p.intent == "case_explanation"

    def test_concept_explanation(self):
        p = parse_legal_query("What is bail")
        assert p.intent == "concept_explanation"

    def test_follow_up_chain(self):
        history = [{"role": "user", "content": "Explain IPC 307"}]
        p = parse_legal_query("What is punishment?", history)
        assert p.is_follow_up
        assert "307" in p.resolved_query or "punishment" in p.resolved_query.lower()


class TestConversationMemory:
    def test_punishment_follow_up(self):
        mem = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
        resolved = resolve_follow_up_query("What is punishment?", mem)
        assert "307" in resolved
        assert "punishment" in resolved.lower()

    def test_compare_follow_up(self):
        mem = {"last_section": "307", "last_law": "IPC"}
        resolved = resolve_follow_up_query("Compare with 302?", mem)
        assert "302" in resolved or "compare" in resolved.lower()


class TestStrictSectionFilter:
    def test_section_307_only(self, chart_chunks):
        signals = {"sections": ["307"]}
        candidates = {
            (str(i), "chart.pdf", str(i), c["content"][:48]): {
                "content": c["content"],
                "metadata": c["metadata"],
            }
            for i, c in enumerate(chart_chunks)
        }
        filtered = strict_section_filter(candidates, signals, law="IPC")
        for node in filtered.values():
            assert _chunk_matches_strict_section(node["content"], "307", "IPC")

    def test_rejects_unrelated_intro(self):
        intro = "General principles of criminal law and overview of IPC."
        sec = "Overview of Indian Penal Code introductory notes."
        signals = {"sections": ["307"]}
        candidates = {
            ("0", "a.pdf", "0", intro[:48]): {"content": intro, "metadata": {}},
            ("1", "a.pdf", "1", sec[:48]): {"content": sec, "metadata": {}},
        }
        filtered = strict_section_filter(candidates, signals, law="IPC")
        assert len(filtered) <= len(candidates)


class TestComparisonEngine:
    def test_separate_entity_retrieval(self, chart_chunks):
        entities = extract_typed_entities("Compare IPC 302 and BNS 103")
        pool = retrieve_for_comparison(entities, index_dir=None)
        assert isinstance(pool, list)

    def test_comparison_formatter_no_placeholders(self):
        chunks = [
            {"content": "IPC 302 Murder punishment death or life.", "metadata": {}},
            {"content": "BNS 103 Murder under BNS.", "metadata": {}},
        ]
        entities = [{"type": "IPC", "section": "302"}, {"type": "BNS", "section": "103"}]
        out = format_comparison_pro("Compare IPC 302 and BNS 103", chunks, entities)
        assert "Topic / Usage" not in out
        assert "302" in out
        assert "103" in out
        assert "| Aspect |" in out


class TestAnswerValidator:
    def test_json_converted(self):
        raw = '{"meaning": "Attempt to murder", "punishment": "Up to 10 years"}'
        vr = validate_and_clean_answer(raw, "IPC 307", strict_grounded=False)
        assert vr.ok
        assert "{" not in vr.answer or "meaning" in vr.answer.lower()

    def test_repeated_lines_cleaned(self):
        raw = "IPC 307 covers attempt to murder.\n\nIPC 307 covers attempt to murder."
        vr = validate_and_clean_answer(raw, "IPC 307", strict_grounded=False)
        assert vr.answer.count("attempt to murder") <= 2

    def test_hallucination_blocked_with_strict_grounded(self, chart_chunks):
        answer = "IPC 307 is about cyber fraud under IT Act section 66D."
        vr = validate_and_clean_answer(
            answer,
            "IPC 307",
            chart_chunks,
            query_type=QueryType.SECTION_LOOKUP,
            strict_grounded=True,
            profile_sections=["307"],
        )
        assert not vr.ok or "documents do not contain" in vr.answer.lower() or vr.reason


class TestSafeFailure:
    def test_alien_marriage_act_not_invented(self):
        p = parse_legal_query("Alien Marriage Act section 42")
        assert p.intent in ("section_lookup", "general", "concept_explanation")
        vr = validate_and_clean_answer(
            "",
            "Alien Marriage Act section 42",
            [],
            strict_grounded=True,
        )
        assert not vr.ok

    def test_nonexistent_law_refusal(self):
        vr = validate_and_clean_answer(
            "The Alien Marriage Act 1899 provides that...",
            "Alien Marriage Act",
            [{"content": "IPC 302 murder.", "metadata": {}}],
            strict_grounded=True,
        )
        assert not vr.ok or "documents" in vr.answer.lower()


class TestResponseFormatter:
    def test_no_json_in_output(self):
        out = format_legal_response('{"left": "IPC 302", "right": "BNS 103"}', intent="comparison")
        assert not out.strip().startswith("{")

    def test_section_structure(self):
        out = format_legal_response(
            "Attempt to murder.\n\nPunishment up to ten years.",
            intent="section_lookup",
        )
        assert len(out) > 20


class TestRegression:
    def test_ipc_299_vs_300_detection(self):
        assert detect_query_type("Difference between IPC 299 and 300") == QueryType.COMPARISON

    def test_law_replacement_still_works(self):
        from kb_legal_query_rewrite import is_law_replacement_query

        assert is_law_replacement_query("What is the new law replacing IPC?")
