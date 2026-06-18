import types

import rag
from prompts import kb_prompt


class EmptyStore:
    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def from_texts(cls, texts, embedding=None, metadatas=None):
        return cls()

    def add_texts(self, texts, metadatas=None):
        return None

    def save_local(self, path):
        return None

    @classmethod
    def load_local(cls, path, embeddings=None, allow_dangerous_deserialization=False):
        return cls()

    def similarity_search_with_score(self, query, k=4):
        return []


class DummyEmb:
    def embed_documents(self, texts):
        return [[0.0] * 3 for _ in texts]

    def embed_query(self, text):
        return [0.0] * 3


def test_not_found_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "_get_langchain_embeddings", lambda: DummyEmb())
    monkeypatch.setattr(rag, "FAISS", EmptyStore)
    monkeypatch.setattr(rag, "FAISS_DIR", tmp_path)
    rag.index_documents([{"doc_id": "1", "filename": "t.pdf", "text": "hello world"}])
    results = rag.query_kb("unrelated")
    assert results == []
    prompt = kb_prompt([], "What is asked?")
    assert "NOT_FOUND" in prompt or "not found" in prompt.lower()

