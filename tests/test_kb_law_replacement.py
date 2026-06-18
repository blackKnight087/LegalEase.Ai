"""Regression tests for IPC→BNS / CrPC→BNSS law-replacement RAG pipeline."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from kb_query_types import QueryType, detect_query_type

LAW_CHART_TEXT = """
INDIAN OLD VS NEW CRIMINAL LAWS

Indian Penal Code (IPC), 1860 → Bharatiya Nyaya Sanhita (BNS), 2023
Code of Criminal Procedure (CrPC), 1973 → Bharatiya Nagarik Suraksha Sanhita (BNSS), 2023
Indian Evidence Act, 1872 → Bharatiya Sakshya Adhiniyam (BSA), 2023

Section mappings:
IPC 302 → BNS 103
IPC 307 → BNS 109

Key reforms: Digital evidence admissibility, online FIR registration, forensic investigation expansion.
"""


@pytest.fixture
def law_mapping_chunks():
    from kb_preprocess import split_semantic_legal_chunks

    chunks = []
    for i, (text, start, end) in enumerate(
        split_semantic_legal_chunks(LAW_CHART_TEXT, chunk_size=900, chunk_overlap=200, max_chunk=1200)
    ):
        chunks.append(
            {
                "content": text,
                "metadata": {
                    "filename": "Indian Old Vs New Criminal Laws Chart.pdf",
                    "chunk_index": str(i),
                    "start_char": str(start),
                    "end_char": str(end),
                },
                "final_score": 0.62,
                "hybrid_score": 0.62,
            }
        )
    return chunks


@pytest.mark.parametrize(
    "query,expected_type",
    [
        ("What is the new law replacing IPC?", QueryType.LAW_REPLACEMENT),
        ("Which law replaced CrPC?", QueryType.LAW_REPLACEMENT),
        ("What replaced Indian Evidence Act?", QueryType.LAW_REPLACEMENT),
        ("What changed in new criminal laws?", QueryType.LAW_REPLACEMENT),
    ],
)
def test_detect_law_replacement_query_type(query, expected_type):
    assert detect_query_type(query) == expected_type


def test_normalize_ipc_replacement_query():
    from kb_legal_query_rewrite import normalize_legal_query

    rewritten = normalize_legal_query("What is the new law replacing IPC?")
    assert "IPC" in rewritten
    assert "BNS" in rewritten


def test_mapping_chunks_stay_intact(law_mapping_chunks):
    combined = "\n".join(c["content"] for c in law_mapping_chunks)
    assert "IPC), 1860 → Bharatiya Nyaya Sanhita (BNS)" in combined.replace("->", "→")
    assert "IPC 302" in combined and "BNS 103" in combined
    from kb_preprocess import is_intro_or_generic_chunk

    ipc_chunk = next(c for c in law_mapping_chunks if "Indian Penal Code (IPC)" in c["content"])
    assert not is_intro_or_generic_chunk(ipc_chunk["content"])


@pytest.mark.parametrize(
    "query,expected_snippet",
    [
        ("What is the new law replacing IPC?", "BNS"),
        ("Which law replaced CrPC?", "BNSS"),
        ("What replaced Indian Evidence Act?", "BSA"),
        ("IPC 302 became what?", "103"),
    ],
)
def test_extract_law_mapping_answer(query, expected_snippet, law_mapping_chunks):
    from kb_legal_query_rewrite import extract_law_mapping_answer

    answer = extract_law_mapping_answer(query, law_mapping_chunks)
    assert answer is not None
    assert expected_snippet.lower() in answer.lower()


def test_evaluate_retrieval_finds_law_mapping(law_mapping_chunks):
    from kb_rag_decision import evaluate_retrieval

    found, score, decision, _ = evaluate_retrieval(
        "What is the new law replacing IPC?",
        law_mapping_chunks,
        threshold=0.35,
        query_type="law_replacement",
    )
    assert found is True
    assert decision == "FOUND"
    assert score >= 0.35


@patch("app.get_user_index_dir")
@patch("rag.query_kb")
def test_kb_pipeline_law_replacement_not_not_found(mock_query, mock_index, law_mapping_chunks):
    from kb_pipeline import kb_pipeline

    mock_index.return_value = "/tmp/fake"
    mock_query.return_value = law_mapping_chunks

    answer, chunks, diag = kb_pipeline("user-1", "What is the new law replacing IPC?")
    assert answer != "NOT_FOUND_IN_KB"
    assert "couldn't find" not in answer.lower()
    assert "BNS" in answer
    assert diag.get("found") is True


def test_keyword_fallback_finds_mapping_row():
    from langchain_core.documents import Document
    from langchain_community.vectorstores import FAISS
    from langchain_core.embeddings import Embeddings

    from kb_legal_query_rewrite import keyword_fallback_from_vectorstore

    class _StubEmb(Embeddings):
        def embed_documents(self, texts):
            return [[0.0] * 8 for _ in texts]

        def embed_query(self, text):
            return [0.0] * 8

    docs = [
        Document(
            page_content="Indian Penal Code (IPC), 1860 → Bharatiya Nyaya Sanhita (BNS), 2023",
            metadata={"filename": "chart.pdf", "chunk_index": "0"},
        )
    ]
    vs = FAISS.from_texts(
        [d.page_content for d in docs],
        embedding=_StubEmb(),
        metadatas=[d.metadata for d in docs],
    )
    hits = keyword_fallback_from_vectorstore(vs, "What is the new law replacing IPC?", top_k=3)
    assert hits
    assert "BNS" in hits[0]["content"]
