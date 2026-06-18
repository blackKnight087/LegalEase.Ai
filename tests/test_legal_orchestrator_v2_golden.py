"""
Golden test suite — Legal Orchestrator V2 (mandatory pass).
"""
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

CONSTITUTION_TEST_DOC = """
Five Constitutional Rights (from test document)

1. Right to Equality (Article 14).
2. Right to Freedom of Speech (Article 19).
3. Right against Exploitation (Article 23).
4. Right to Freedom of Religion (Article 25).
5. Right to Life and Personal Liberty (Article 21).
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "golden_v2.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


def _index(uid: str, text: str = KB_TEST_DOC, filename: str = "legal_kb_test_document.pdf"):
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    index_dir = get_unlinked_index_dir(uid)
    ok, msg, _ = index_documents(
        [{"doc_id": str(uuid.uuid4()), "filename": filename, "text": text}],
        index_dir=index_dir,
    )
    assert ok, msg
    return index_dir


def _run(uid: str, query: str, *, doc: str = KB_TEST_DOC, filename: str = "legal_kb_test_document.pdf") -> str:
    from kb_pipeline import kb_pipeline

    answer, _, _ = kb_pipeline(uid, query, [], index_dir=_index(uid, doc, filename))
    return answer


class TestGoldenOrchestratorV2:
    def test_1_multi_section_307_300(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Explain IPC 307 and IPC 300")
        al = answer.lower()
        assert "307" in al and "300" in al
        assert al.count("section 307") >= 1 or "307" in al
        assert "section 300" in al or ("300" in al and "murder" in al)
        assert "corresponds to bns" not in al

    def test_2_compare_299_300_no_bns(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Compare IPC 299 and IPC 300")
        al = answer.lower()
        assert "299" in answer and "300" in answer
        assert "corresponds to bns" not in al
        assert "bns section 10" not in al

    def test_3_constitutional_rights_list(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(
            uid,
            "What are constitutional rights",
            doc=CONSTITUTION_TEST_DOC,
            filename="legal_kb_constitution.pdf",
        )
        al = answer.lower()
        assert "constitutional" in al or "fundamental" in al or "right" in al
        assert "corresponds to bns" not in al
        assert "transition chart" not in al

    def test_4_right_to_equality_article_14(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(
            uid,
            "Explain Right to Equality",
            doc=CONSTITUTION_TEST_DOC,
            filename="legal_kb_constitution.pdf",
        )
        al = answer.lower()
        assert "article 14" in al or "equality" in al
        assert "transition chart" not in al
        assert "bns" not in al[:200] or "article" in al

    def test_5_punishment_ipc_307_only(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Punishment under IPC 307")
        assert "307" in answer
        assert "420" not in answer[:250]
        assert "corresponds to bns" not in answer.lower()

    def test_6_ipc_302_vs_bns_mapping_allowed(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "IPC 302 vs BNS equivalent")
        assert "302" in answer
        al = answer.lower()
        assert "bns" in al or "103" in al or "mapping" in al or "equivalent" in al

    def test_7_compare_302_307_same_law(self):
        uid = f"g-{uuid.uuid4().hex[:8]}"
        answer = _run(uid, "Compare IPC 302 and IPC 307")
        al = answer.lower()
        assert "302" in answer and "307" in answer
        assert "corresponds to bns" not in al
