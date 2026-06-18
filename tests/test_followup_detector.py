"""Session memory reset for explicit legal section queries."""
from __future__ import annotations

import uuid

import pytest

from backend.app.core.kb_query_memory import expand_kb_query
from backend.app.services.followup_detector import (
    get_effective_session_memory,
    is_new_legal_query,
)
from conversation_context import enrich_query_with_context
from intent_engine import _is_follow_up

KB_TEST_DOC = """
Legal Knowledge Base Testing Document

The Indian Penal Code (IPC), 1860 has been replaced by Bharatiya Nyaya Sanhita (BNS), 2023.

IPC Section 299 — Culpable Homicide
Whoever causes death by doing an act with the intention of causing death commits culpable homicide.

IPC Section 300 — Murder
Murder is culpable homicide when committed with aggravating circumstances.

IPC Section 302 — Punishment for Murder
Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine.

IPC Section 307 — Attempt to Murder
Whoever does any act with such intention or knowledge that if he by that act caused death, he would be guilty of murder, shall be punished with imprisonment which may extend to ten years, and shall also be liable to fine.

IPC Section 420 — Cheating
Whoever cheats and thereby dishonestly induces the person deceived to deliver any property, commits cheating.
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "kb_followup.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


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


class TestFollowupDetector:
    def test_is_new_legal_query_patterns(self):
        assert is_new_legal_query("Explain IPC 307")
        assert is_new_legal_query("What is punishment under IPC 302?")
        assert is_new_legal_query("BNS 103 punishment")
        assert is_new_legal_query("Article 21 rights")
        assert is_new_legal_query("section 420 cheating")
        assert not is_new_legal_query("What punishment?")
        assert not is_new_legal_query("Explain simply")

    def test_effective_session_memory_resets_for_new_section(self):
        mem = {"last_section": "302", "last_law": "IPC", "last_topic": "IPC Section 302"}
        assert get_effective_session_memory("Explain IPC 307", mem) == {}
        assert get_effective_session_memory("What punishment?", mem) == mem


class TestSessionMemoryContamination:
    """Mandatory regression tests for session context bleed."""

    def test_ipc_302_then_ipc_307_different_answers(self):
        from kb_pipeline import kb_pipeline
        from backend.app.core.matter_index import get_unlinked_index_dir

        uid = f"u-{uuid.uuid4().hex[:8]}"
        index_dir = _index(uid)
        history = []

        a1, _, _ = kb_pipeline(uid, "What is punishment under IPC 302?", history, index_dir=index_dir)
        assert "302" in a1
        assert "murder" in a1.lower() or "punishment" in a1.lower()
        history.extend([
            {"role": "user", "content": "What is punishment under IPC 302?"},
            {"role": "assistant", "content": a1},
        ])

        a2, _, _ = kb_pipeline(uid, "Explain IPC 307", history, index_dir=index_dir)
        assert "307" in a2
        assert "Attempt" in a2 or "attempt" in a2.lower()
        assert "302" not in a2 or "Punishment for Murder" not in a2

    def test_vague_punishment_follow_up_stays_on_ipc_307(self):
        from kb_pipeline import kb_pipeline
        from backend.app.core.matter_index import get_unlinked_index_dir

        uid = f"u-{uuid.uuid4().hex[:8]}"
        index_dir = _index(uid)
        history = []

        a1, _, _ = kb_pipeline(uid, "Explain IPC 307", history, index_dir=index_dir)
        history.extend([
            {"role": "user", "content": "Explain IPC 307"},
            {"role": "assistant", "content": a1},
        ])

        expanded = expand_kb_query("What punishment?", history, session_mem={
            "last_section": "307",
            "last_law": "IPC",
            "last_topic": "IPC Section 307",
        })
        assert "307" in expanded
        assert "302" not in expanded

        a2, _, _ = kb_pipeline(uid, "What punishment?", history, index_dir=index_dir)
        assert "307" in a2 or "attempt" in a2.lower()
        assert "302" not in a2 or "Punishment for Murder" not in a2

    def test_ipc_299_then_ipc_420_no_contamination(self):
        from kb_pipeline import kb_pipeline
        from backend.app.core.matter_index import get_unlinked_index_dir

        uid = f"u-{uuid.uuid4().hex[:8]}"
        index_dir = _index(uid)
        history = []

        a1, _, _ = kb_pipeline(uid, "Explain IPC 299", history, index_dir=index_dir)
        assert "299" in a1
        history.extend([
            {"role": "user", "content": "Explain IPC 299"},
            {"role": "assistant", "content": a1},
        ])

        a2, _, _ = kb_pipeline(uid, "Explain IPC 420", history, index_dir=index_dir)
        assert "420" in a2
        assert "cheating" in a2.lower() or "Cheating" in a2
        assert "299" not in a2 or "Culpable" not in a2

    def test_law_replacement_then_ipc_307_fresh_retrieval(self):
        from kb_pipeline import kb_pipeline
        from backend.app.core.matter_index import get_unlinked_index_dir

        uid = f"u-{uuid.uuid4().hex[:8]}"
        index_dir = _index(uid)
        history = []

        a1, _, _ = kb_pipeline(uid, "What replaced IPC?", history, index_dir=index_dir)
        assert "BNS" in a1 or "bns" in a1.lower()
        history.extend([
            {"role": "user", "content": "What replaced IPC?"},
            {"role": "assistant", "content": a1},
        ])

        enriched = enrich_query_with_context("Explain IPC 307", history)
        assert enriched == "Explain IPC 307"
        assert "302" not in enriched
        assert not _is_follow_up("Explain IPC 307", history)

        a2, _, _ = kb_pipeline(uid, "Explain IPC 307", history, index_dir=index_dir)
        assert "307" in a2
        assert "Attempt" in a2 or "attempt" in a2.lower()


class TestCaseFollowUpContext:
    def test_explain_follow_up_uses_case_not_article_section(self):
        from backend.app.core.conversation_memory import resolve_follow_up_query
        from conversation_context import enrich_query_with_context

        case_q = (
            "Riya Banerjee vs State Medical Board (Article 21 – Right to Life & Dignity)"
        )
        history = [
            {"role": "user", "content": case_q},
            {
                "role": "assistant",
                "content": f"## {case_q}\n\nPetitioner challenged denial of care.",
            },
        ]
        mem = {
            "last_case": "Riya Banerjee vs State Medical Board",
            "last_topic": "Riya Banerjee vs State Medical Board",
            "last_user_query": case_q,
        }
        expanded = resolve_follow_up_query("Explain", mem)
        assert "riya banerjee" in expanded.lower()
        assert "state medical board" in expanded.lower()
        assert "ipc section 21" not in expanded.lower()

        enriched = enrich_query_with_context("Explain", history)
        assert "riya banerjee" in enriched.lower()
        assert "case" in enriched.lower()
