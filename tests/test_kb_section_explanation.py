"""Section explanation must not return law-replacement boilerplate or other sections."""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.legacy_kb

KB_TEST_DOC = """
Legal Knowledge Base Testing Document

The Indian Penal Code (IPC), 1860 has been replaced by Bharatiya Nyaya Sanhita (BNS), 2023.

IPC Section 299 — Culpable Homicide
Whoever causes death by doing an act with the intention of causing death, or with the intention of causing such bodily injury as is likely to cause death, commits culpable homicide.

IPC Section 300 — Murder
Murder is culpable homicide when it is committed with certain aggravating circumstances defined in this section.

IPC Section 302 — Punishment for Murder
Whoever commits murder shall be punished with death or imprisonment for life, and shall also be liable to fine.

IPC Section 307 — Attempt to Murder
Whoever does any act with such intention or knowledge, and under such circumstances, that if he by that act caused death, he would be guilty of murder, shall be punished with imprisonment which may extend to ten years, and shall also be liable to fine.
If a person attempts to kill another with intention or knowledge, but the victim survives, punishment may extend to 10 years and fine.

IPC Section 420 — Cheating
Whoever cheats and thereby dishonestly induces the person deceived to deliver any property, commits the offence of cheating.
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "kb_sec.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


def _index_doc(uid: str):
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    index_dir = get_unlinked_index_dir(uid)
    ok, msg, n = index_documents(
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "legal_kb_test_document.pdf",
                "text": KB_TEST_DOC,
            }
        ],
        index_dir=index_dir,
    )
    assert ok, msg
    assert n > 0
    return index_dir


def test_is_section_focus_query():
    from kb_query_types import is_section_focus_query

    assert is_section_focus_query("Explain IPC 307 in simple language")
    assert not is_section_focus_query("What replaced IPC?")


def test_extract_law_mapping_skips_section_explain():
    from kb_legal_query_rewrite import extract_law_mapping_answer

    chunks = [{"content": KB_TEST_DOC}]
    assert extract_law_mapping_answer("Explain IPC 307 in simple language", chunks) is None


def test_kb_pipeline_ipc_307_explanation():
    from kb_pipeline import kb_pipeline
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    index_dir = _index_doc(uid)

    answer, chunks, diag = kb_pipeline(
        uid,
        "Explain IPC 307 in simple language",
        [],
        index_dir=index_dir,
    )
    assert answer
    upper = answer.upper()
    assert "307" in upper
    assert "ATTEMPT" in upper or "MURDER" in upper
    assert "299" not in answer
    assert "302" not in answer
    assert "420" not in answer
    assert "replaced by Bharatiya Nyaya Sanhita" not in answer
    assert diag.get("mode") or diag.get("retrieval_mode")
    assert "307" in str(
        diag.get("section_entities") or diag.get("entities") or diag.get("sections_requested") or []
    )
