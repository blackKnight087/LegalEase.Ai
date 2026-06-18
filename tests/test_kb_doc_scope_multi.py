"""KB document scope must not pin to the first file when several uploads match."""
from __future__ import annotations

import uuid

import pytest


@pytest.mark.unit
def test_multi_criminal_docs_no_strict_pin():
    from backend.app.core.kb_doc_scope import resolve_document_scope

    index_dir = "/tmp/fake"
    docs = [
        {"doc_id": "a", "filename": "ipc_a.pdf", "document_type": "criminal_law"},
        {"doc_id": "b", "filename": "ipc_b.pdf", "document_type": "criminal_law"},
    ]

    import backend.app.core.kb_doc_scope as scope_mod

    scope_mod.list_index_documents = lambda _d: docs  # type: ignore[attr-defined]
    scope = resolve_document_scope("user", "IPC Section 406", index_dir)
    assert scope.get("strict") is False
    assert scope.get("reason") == "query_document_type_multi"
    assert scope.get("content_family") == "criminal_law"


@pytest.mark.unit
def test_single_doc_stays_strict():
    from backend.app.core.kb_doc_scope import resolve_document_scope

    index_dir = "/tmp/fake"
    docs = [{"doc_id": "only", "filename": "law.pdf", "document_type": "criminal_law"}]

    import backend.app.core.kb_doc_scope as scope_mod

    scope_mod.list_index_documents = lambda _d: docs  # type: ignore[attr-defined]
    scope = resolve_document_scope("user", "IPC Section 302", index_dir)
    assert scope.get("strict") is True
    assert scope.get("doc_id") == "only"


@pytest.mark.unit
def test_chunk_matches_section_ipc_section_phrase():
    from kb_rag_decision import chunk_matches_section

    body = "IPC Section 406 — Criminal breach of trust. Whoever dishonestly misappropriates property."
    assert chunk_matches_section(body, "406")
