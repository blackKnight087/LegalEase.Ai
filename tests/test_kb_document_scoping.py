"""KB document scoping, NDA entity extraction, and contamination tests."""
from __future__ import annotations

import uuid

import pytest

NDA_TEXT = """
NON-DISCLOSURE AGREEMENT

This Non-Disclosure Agreement ("Agreement") is entered into on the Effective Date.

Disclosing Party: ____________________
Receiving Party: ____________________

The Receiving Party agrees to hold Confidential Information in strict confidence.
Confidential Information means all non-public information disclosed by the Disclosing Party.

Upon termination of this Agreement, the Receiving Party shall return all Confidential Information.
Governing Law: laws of India
"""

CRIMINAL_TEXT = """
IPC Section BNS Section
IPC 34 BNS 3(5) Common intention
IPC 120B BNS 61 Criminal conspiracy
IPC 141 BNS 187 Unlawful assembly
IPC 302 BNS 103 Murder
What replaced IPC? Bharatiya Nyaya Sanhita BNS
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "kb_scope.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


def _index_two_docs(uid: str, index_dir=None):
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    if index_dir is None:
        index_dir = get_unlinked_index_dir(uid)

    docs = [
        {
            "doc_id": str(uuid.uuid4()),
            "filename": "NDA.jpeg",
            "text": NDA_TEXT * 3,
        },
        {
            "doc_id": str(uuid.uuid4()),
            "filename": "Indian Old Vs New Criminal Laws Chart.pdf",
            "text": CRIMINAL_TEXT * 5,
        },
    ]
    ok, msg, n = index_documents(docs, index_dir=index_dir)
    assert ok, msg
    assert n > 0
    return docs


def test_document_classifier_nda():
    from document_classifier import classify_document

    assert classify_document(NDA_TEXT, "NDA.jpeg") == "nda"
    assert classify_document(CRIMINAL_TEXT, "chart.pdf") == "criminal_law"


def test_contract_entity_parties_answer():
    from contract_entity_extractor import answer_entity_lookup, extract_contract_entities

    entities = extract_contract_entities(NDA_TEXT, "nda")
    answer = answer_entity_lookup("Who are the parties involved in this agreement?", entities)
    assert answer
    assert "Disclosing Party" in answer
    assert "Receiving Party" in answer
    assert "IPC" not in answer
    assert "BNS" not in answer


def test_query_kb_scoped_to_nda_only():
    from rag import query_kb

    uid = f"u-{uuid.uuid4().hex[:8]}"
    docs = _index_two_docs(uid)
    from backend.app.core.matter_index import get_unlinked_index_dir

    index_dir = get_unlinked_index_dir(uid)

    scope = {
        "doc_id": docs[0]["doc_id"],
        "filename": "NDA.jpeg",
        "document_type": "nda",
        "strict": True,
        "reason": "test",
    }
    hits = query_kb(
        "Who are the parties involved in this agreement?",
        k=5,
        index_dir=index_dir,
        document_scope=scope,
    )
    assert hits
    combined = " ".join(c.get("content", "") for c in hits).upper()
    assert "DISCLOSING" in combined or "RECEIVING" in combined or "CONFIDENTIAL" in combined
    assert "IPC 302" not in combined
    assert "CRIMINAL CONSPIRACY" not in combined


def test_query_kb_criminal_not_contaminated_by_nda():
    from rag import query_kb
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    docs = _index_two_docs(uid)
    index_dir = get_unlinked_index_dir(uid)

    scope = {
        "doc_id": docs[1]["doc_id"],
        "filename": "Indian Old Vs New Criminal Laws Chart.pdf",
        "document_type": "criminal_law",
        "strict": True,
        "reason": "test",
    }
    hits = query_kb("What replaced IPC?", k=5, index_dir=index_dir, document_scope=scope)
    assert hits
    combined = " ".join(c.get("content", "") for c in hits).upper()
    assert "BNS" in combined or "IPC" in combined
    assert "NON-DISCLOSURE" not in combined


def test_resolve_scope_prefers_contract_for_party_query():
    from backend.app.core.kb_doc_scope import resolve_document_scope
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    _index_two_docs(uid)
    index_dir = get_unlinked_index_dir(uid)

    scope = resolve_document_scope(
        uid,
        "Who are the parties involved in this agreement?",
        index_dir,
    )
    assert scope.get("strict") is True
    assert scope.get("document_type") in {"nda", "contract", "agreement", "scanned_image"}


def test_contamination_rejection():
    from backend.app.core.kb_doc_scope import reject_cross_document_contamination

    scope = {"strict": True, "document_type": "nda", "filename": "NDA.jpeg"}
    bad_chunks = [{"content": CRIMINAL_TEXT, "metadata": {"document_type": "criminal_law"}}]
    ok, reason = reject_cross_document_contamination(
        "Who are the parties?", bad_chunks, scope
    )
    assert not ok
    assert "contamination" in reason


def test_kb_pipeline_entity_lookup():
    from kb_pipeline import kb_pipeline
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    _index_two_docs(uid)
    index_dir = get_unlinked_index_dir(uid)

    answer, chunks, diag = kb_pipeline(
        uid,
        "Who are the parties involved in this agreement?",
        [],
        index_dir=index_dir,
    )
    assert answer
    assert "Disclosing Party" in answer or "Receiving Party" in answer
    assert "IPC 34" not in answer
    assert diag.get("document_scope", {}).get("strict") is True
