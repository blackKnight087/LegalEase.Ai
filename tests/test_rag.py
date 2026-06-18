import types

import rag
from rag import FAISS_BASE_DIR


class DummyEmb:
    def embed_documents(self, texts):
        return [[0.1] * 3 for _ in texts]

    def embed_query(self, text):
        return [0.1] * 3


class DummyStore:
    def __init__(self, texts=None, metadatas=None):
        self.texts = texts or []
        self.metadatas = metadatas or []
        self.saved = False
        self.index_to_docstore_id = {0: "0"}
        self.docstore = types.SimpleNamespace(
            search=lambda _id: types.SimpleNamespace(
                page_content="Section 66C – Identity theft under IT Act.",
                metadata={
                    "filename": "legal.pdf",
                    "chunk_index": "0",
                    "section_numbers": "66c",
                    "law_tags": "it act",
                },
            )
        )
        self.index = types.SimpleNamespace(search=lambda vector, k: ([[0.1]], [[0]]))

    @classmethod
    def from_texts(cls, texts, embedding=None, metadatas=None):
        return cls(texts, metadatas)

    def add_texts(self, texts, metadatas=None):
        self.texts.extend(texts)
        self.metadatas.extend(metadatas or [])

    def save_local(self, path, index_name="index"):
        self.saved = True
        path = __import__("pathlib").Path(path)
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{index_name}.faiss").write_text("dummy", encoding="utf-8")
        (path / f"{index_name}.pkl").write_text("dummy", encoding="utf-8")

    @classmethod
    def load_local(cls, path, embeddings=None, index_name="index", allow_dangerous_deserialization=False):
        return cls(["hello"], [{"filename": "legal.pdf", "chunk_index": "0"}])

    def similarity_search_with_score(self, query, k=4):
        return [
            (
                types.SimpleNamespace(
                    page_content="Section 66C – Identity theft under IT Act.",
                    metadata={
                        "filename": "legal.pdf",
                        "chunk_index": "0",
                        "section_numbers": "66c",
                        "law_tags": "it act",
                    },
                ),
                0.1,
            )
        ]


def test_detect_query_type_section():
    assert rag._detect_query_type("What is Section 66C of the IT Act?") == "exact_identifier"


def test_detect_query_type_entity():
    assert rag._detect_query_type("Which case recognized the Right to Privacy?") == "entity"


def test_detect_query_type_cross_document():
    assert rag._detect_query_type("Difference between theft and robbery") == "cross_document"


def test_expand_queries_section():
    qtype = "exact_identifier"
    signals = rag._extract_query_signals("What is Section 66C of the IT Act?")
    expanded = rag._expand_queries("What is Section 66C of the IT Act?", qtype, signals)
    assert any("66c" in e.lower() for e in expanded)
    assert any("section 66c" in e.lower() for e in expanded)


def test_validate_context_requires_exact_section():
    signals = rag._extract_query_signals("What is Section 66C of the IT Act?")
    good = [{"content": "Section 66C – Identity theft."}]
    bad = [{"content": "Section 299 – Culpable homicide."}]
    valid_good, _, _ = rag._validate_context("What is Section 66C?", "exact_identifier", signals, good)
    valid_bad, _, _ = rag._validate_context("What is Section 66C?", "exact_identifier", signals, bad)
    assert valid_good
    assert not valid_bad


def test_extract_query_signals_section():
    signals = rag._extract_query_signals("What is Section 66C of the IT Act?")
    assert "66c" in signals.get("bare_identifiers", []) or "66c" in [
        s.lower() for s in signals.get("sections", [])
    ]


def test_handle_legal_query_section():
    chunks = [
        {
            "content": "Section 66C – Identity theft: dishonestly using electronic means.",
            "metadata": {"filename": "legal.pdf", "chunk_index": "3"},
        }
    ]
    answer = rag.handle_legal_query("What is Section 66C of the IT Act?", chunks)
    assert answer
    assert "66c" in answer.lower()


def test_index_documents(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "_get_langchain_embeddings", lambda: DummyEmb())
    monkeypatch.setattr(rag, "FAISS", DummyStore)
    index_dir = FAISS_BASE_DIR / "pytest_index"
    index_dir.mkdir(parents=True, exist_ok=True)
    ok, msg, total = rag.index_documents(
        [{"doc_id": "1", "filename": "doc.pdf", "text": "hello world with enough content " * 5}],
        index_dir=index_dir,
    )
    assert ok
    assert total > 0
    assert rag.index_exists(index_dir)


def test_query_kb(monkeypatch, tmp_path):
    monkeypatch.setattr(rag, "_get_langchain_embeddings", lambda: DummyEmb())
    monkeypatch.setattr(rag, "FAISS", DummyStore)
    monkeypatch.setattr(rag, "_sparse_scores", lambda _vs, _q, top_n=40: [])
    index_dir = FAISS_BASE_DIR / "pytest_query"
    index_dir.mkdir(parents=True, exist_ok=True)
    rag.index_documents(
        [{"doc_id": "1", "filename": "doc.pdf", "text": "Section 66C identity theft " * 5}],
        index_dir=index_dir,
    )
    results = rag.query_kb("Section 66C IT Act", index_dir=index_dir)
    assert results
    assert "66c" in results[0]["content"].lower()


def test_retrieval_has_signal():
    assert rag.retrieval_has_signal([{"final_score": 0.72}])
    assert not rag.retrieval_has_signal([{"final_score": 0.1}])
