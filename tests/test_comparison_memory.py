"""Regression tests — independent comparison retrieval + follow-up memory chain."""
from __future__ import annotations

import pytest

from backend.app.core.conversation_memory import (
    get_session_legal_memory,
    resolve_follow_up_query,
    update_session_legal_memory,
)
from backend.app.core.kb_query_memory import expand_kb_query
from backend.app.core.session_store import set_session
from kb_compare_engine import (
    ComparisonBundle,
    extract_all_comparison_entities,
    format_comparison_pro,
)


LAW_CHART = """
IPC 302 → BNS 103
Murder — punishment with death or imprisonment for life.
IPC 307 → BNS 109
Attempt to murder — imprisonment up to ten years.
Section 299. Culpable homicide.
Section 300. Murder.
Section 307. Attempt to murder — imprisonment up to ten years.
"""


@pytest.fixture
def mapping_chunks():
    from kb_preprocess import split_semantic_legal_chunks

    chunks = []
    for i, (text, _s, _e) in enumerate(
        split_semantic_legal_chunks(LAW_CHART, chunk_size=900, chunk_overlap=80, max_chunk=1000)
    ):
        chunks.append(
            {
                "content": text,
                "metadata": {"filename": "chart.pdf", "chunk_index": str(i)},
                "final_score": 0.75,
            }
        )
    return chunks


class TestIndependentComparison:
    def test_extract_ipc_bns_pair(self):
        ents = extract_all_comparison_entities("Compare IPC 302 and BNS 103")
        assert len(ents) >= 2
        assert ents[0]["type"] == "IPC"
        assert ents[0]["section"] == "302"
        assert ents[1]["type"] == "BNS"
        assert ents[1]["section"] == "103"

    def test_extract_multi_ipc_sections(self):
        ents = extract_all_comparison_entities("Compare IPC 299, 300 and 307")
        assert len(ents) >= 3
        secs = [e["section"] for e in ents]
        assert "299" in secs and "300" in secs and "307" in secs

    def test_comparison_table_output(self, mapping_chunks):
        ents = extract_all_comparison_entities("Compare IPC 302 and BNS 103")
        out = format_comparison_pro("Compare IPC 302 and BNS 103", mapping_chunks, ents)
        assert "| Aspect |" in out
        assert "IPC 302" in out
        assert "BNS 103" in out
        assert "Topic / Usage" not in out

    def test_bundle_has_left_right(self):
        ents = extract_all_comparison_entities("Compare IPC 302 and BNS 103")
        bundle = ComparisonBundle(entities=ents)
        bundle.entity_chunks["IPC:302"] = [{"content": "IPC 302 Murder", "entity": "IPC:302"}]
        bundle.entity_chunks["BNS:103"] = [{"content": "BNS 103 Murder", "entity": "BNS:103"}]
        assert bundle.left_entity["section"] == "302"
        assert bundle.right_entity["section"] == "103"
        assert len(bundle.left_chunks) == 1
        assert len(bundle.right_chunks) == 1


class TestFollowUpMemoryChain:
    def test_punishment_applies_follow_up(self):
        mem = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
        resolved = resolve_follow_up_query("What punishment applies?", mem)
        assert "307" in resolved
        assert "punishment" in resolved.lower()

    def test_bare_section_300_not_polluted_by_memory(self):
        """After IPC 302 vs BNS 103 comparison, 'section 300' must stay a single lookup."""
        from kb_query_types import QueryType, detect_query_type, extract_entities

        history = [
            {"role": "user", "content": "Compare IPC 302 and BNS 103"},
            {"role": "assistant", "content": "Comparison of IPC 302 and BNS 103."},
        ]
        mem = {
            "last_section": "302",
            "last_law": "IPC",
            "last_topic": "IPC Section 302",
            "last_entities": [
                {"law": "IPC", "section": "302"},
                {"law": "BNS", "section": "103"},
            ],
        }
        assert resolve_follow_up_query("section 300", mem) == "section 300"
        assert detect_query_type("section 300", history) == QueryType.SECTION_LOOKUP
        ent = extract_entities("section 300", history)
        assert ent["entities"] == ["300"]
        assert ent["intent"] == QueryType.SECTION_LOOKUP

    def test_compare_with_302_follow_up(self):
        mem = {"last_section": "307", "last_law": "IPC"}
        resolved = resolve_follow_up_query("Compare with IPC 302", mem)
        assert "307" in resolved or "302" in resolved
        assert "compare" in resolved.lower()

    def test_expand_kb_query_chain(self):
        history = [
            {"role": "user", "content": "Explain IPC 307"},
            {"role": "assistant", "content": "IPC Section 307 covers attempt to murder."},
        ]
        mem = {"last_section": "307", "last_law": "IPC", "last_topic": "IPC Section 307"}
        expanded = expand_kb_query("What punishment applies?", history, session_mem=mem)
        assert "307" in expanded
        assert "punishment" in expanded.lower()

    def test_session_memory_persists_across_turns(self):
        sid = "test-memory-chain-001"
        set_session(sid, {"history": [], "state": {}, "legal_memory": {}})
        update_session_legal_memory(
            sid,
            query="Explain IPC 307",
            parse={"section": "307", "law": "IPC", "intent": "section_lookup"},
        )
        mem = get_session_legal_memory(sid)
        assert mem.get("last_section") == "307"
        resolved = resolve_follow_up_query("What punishment applies?", mem)
        assert "307" in resolved
