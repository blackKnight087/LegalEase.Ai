"""Multi-turn KB: each new section query must not bleed prior section answers."""
from __future__ import annotations

import uuid

import pytest

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
    db = tmp_path / "kb_conv.db"
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


def test_extract_entities_302_not_307_from_history():
    from kb_query_types import extract_entities, QueryType

    history = [
        {"role": "user", "content": "Explain IPC 307"},
        {"role": "assistant", "content": "IPC Section 307 — Attempt to Murder"},
    ]
    info = extract_entities("What is punishment under IPC 302?", history)
    assert info["intent"] == QueryType.PUNISHMENT_QUERY
    assert info["entities"] == ["302"]


@pytest.mark.slow
def test_kb_conversation_section_sequence():
    from kb_pipeline import kb_pipeline
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    index_dir = _index(uid)
    history = []

    a1, _, _ = kb_pipeline(uid, "Explain IPC 307", history, index_dir=index_dir)
    assert "307" in a1
    assert "Attempt" in a1 or "attempt" in a1.lower()
    history.extend([
        {"role": "user", "content": "Explain IPC 307"},
        {"role": "assistant", "content": a1},
    ])

    a2, _, _ = kb_pipeline(uid, "What is punishment under IPC 302?", history, index_dir=index_dir)
    assert "302" in a2
    assert "307" not in a2 or "Attempt to Murder" not in a2
    assert "murder" in a2.lower() or "Punishment" in a2 or "punishment" in a2.lower()
    history.extend([
        {"role": "user", "content": "What is punishment under IPC 302?"},
        {"role": "assistant", "content": a2},
    ])

    a3, _, _ = kb_pipeline(uid, "Explain IPC 299", history, index_dir=index_dir)
    assert "299" in a3
    assert "Culpable" in a3 or "culpable" in a3.lower()
    assert "420" not in a3
    assert "replaced by Bharatiya Nyaya Sanhita" not in a3
