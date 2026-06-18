"""Prompt budget caps."""
from backend.app.core.prompt_budget import (
    MAX_MEMORY_CHARS,
    MAX_RAG_DOCUMENT_CHARS,
    budget_memory_block,
    budget_rag_chunks,
)


def test_memory_cap():
    huge = "x" * 10000
    assert len(budget_memory_block(huge)) <= MAX_MEMORY_CHARS


def test_rag_chunk_cap():
    chunks = [{"content": "a" * 3000} for _ in range(10)]
    out = budget_rag_chunks(chunks)
    total = sum(len(c["content"]) for c in out)
    assert total <= MAX_RAG_DOCUMENT_CHARS
