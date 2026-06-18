"""
Full 3-page legal_kb_test_document regression suite.

Covers IPC sections (page 1), constitutional/cases/NDA (page 2), and cross-topic
queries from the document's suggested testing list.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.legacy_kb

ROOT = Path(__file__).resolve().parents[1]
FULL_DOC_PATH = ROOT / "Data" / "20260523211315_915ca1c5_legal_kb_test_document.auto.extracted.txt"

FULL_TEST_DOC = FULL_DOC_PATH.read_text(encoding="utf-8") if FULL_DOC_PATH.exists() else ""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "kb_full.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    monkeypatch.setenv("LEARNING_ENGINE_ENABLED", "0")
    monkeypatch.setenv("RAPID_LEARN_MEMORY", "0")
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
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "legal_kb_test_document.pdf",
                "text": FULL_TEST_DOC,
            }
        ],
        index_dir=index_dir,
    )
    assert ok, msg
    assert n > 0
    return index_dir


@pytest.fixture
def indexed_user():
    uid = f"full-doc-{uuid.uuid4().hex[:8]}"
    index_dir = _index(uid)
    return uid, index_dir


@pytest.mark.integration
@pytest.mark.parametrize(
    "query,must_contain,must_not_contain",
    [
        (
            "What replaced IPC in India?",
            ["BNS", "Bharatiya Nyaya"],
            ["Disclosing Party", "NON-DISCLOSURE"],
        ),
        (
            "Explain IPC Section 307",
            ["307", "attempt"],
            ["420", "Disclosing Party"],
        ),
        (
            "BNS Section 103 – Punishment for Murder explain",
            ["103", "BNS", "murder"],
            ["303", "IPC Section 303", "Disclosing Party"],
        ),
        (
            "What is the punishment for murder?",
            ["302", "murder"],
            ["420", "NDA"],
        ),
        (
            "Compare IPC 302 and BNS 103",
            ["302", "103"],
            ["Disclosing Party"],
        ),
        (
            "Difference between IPC 299 and IPC 300",
            ["299", "300"],
            ["420", "NDA"],
        ),
        (
            "Who are the parties involved in the NDA?",
            ["Disclosing", "Receiving"],
            ["IPC Section 299", "IPC 307"],
        ),
        (
            "What happens to confidential information after termination?",
            ["termination", "return"],
            ["IPC Section 299", "murder"],
        ),
        (
            "what is Sample Non-Disclosure Agreement (NDA)",
            ["NDA", "Agreement"],
            ["IPC Section 299", "culpable homicide"],
        ),
        (
            "Explain the Nirbhaya case in simple language",
            ["Nirbhaya", "reform"],
            ["IPC Section 420", "Disclosing Party"],
        ),
        (
            "Name five constitutional rights",
            ["Article", "Equality"],
            ["Disclosing Party", "IPC Section 307"],
        ),
    ],
)
def test_kb_full_document_queries(indexed_user, query, must_contain, must_not_contain):
    from kb_pipeline import kb_pipeline

    uid, index_dir = indexed_user
    answer, _chunks, diag = kb_pipeline(uid, query, [], index_dir=index_dir)
    assert answer, f"Empty answer for {query!r}: {diag}"
    assert "NOT_FOUND_IN_KB" not in answer, diag
    al = answer.lower()
    for token in must_contain:
        assert token.lower() in al, f"{query!r}: expected {token!r} in answer:\n{answer[:600]}"
    for bad in must_not_contain:
        assert bad.lower() not in al, f"{query!r}: unwanted {bad!r} in answer:\n{answer[:600]}"


@pytest.mark.integration
def test_nda_after_ipc_history_not_rewritten(indexed_user):
    from kb_pipeline import kb_pipeline

    uid, index_dir = indexed_user
    history = [
        {"role": "user", "content": "Explain IPC Section 299"},
        {"role": "assistant", "content": "IPC Section 299 defines culpable homicide."},
        {"role": "user", "content": "Explain IPC Section 307"},
        {"role": "assistant", "content": "IPC Section 307 covers attempt to murder."},
    ]
    answer, _, diag = kb_pipeline(
        uid,
        "what is Sample Non-Disclosure Agreement (NDA)",
        history,
        index_dir=index_dir,
    )
    assert answer
    al = answer.lower()
    assert "nda" in al or "non-disclosure" in al or "agreement" in al
    assert "culpable homicide" not in al
    assert "299" not in al or "nda" in al


@pytest.mark.unit
def test_per_chunk_classification_mixed_doc():
    from rag import _documents_to_chunk_batches

    texts, metas = _documents_to_chunk_batches(
        [
            {
                "doc_id": "x",
                "filename": "legal_kb_test_document.pdf",
                "text": FULL_TEST_DOC,
            }
        ]
    )
    types = {m.get("document_type") for m in metas}
    assert types
    nda_hits = [
        m
        for text, m in zip(texts, metas)
        if "non-disclosure" in text.lower() or "disclosing party" in text.lower()
    ]
    assert nda_hits, "Expected NDA chunk in mixed document"
    assert any(m.get("document_type") in {"nda", "contract", "agreement"} for m in nda_hits)
