"""Per-matter FAISS isolation — Case A must not retrieve Case B chunks."""
from __future__ import annotations

import uuid

import pytest

from backend.app.core.matter_repo import create_matter
from backend.app.core.practice_schema import ensure_practice_schema


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "matter_faiss.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


def _build_matter_index(user_id: str, matter_id: str, unique_phrase: str, filename: str):
    from rag import index_documents
    from backend.app.core.matter_index import get_matter_index_dir

    docs = [{"doc_id": str(uuid.uuid4()), "filename": filename, "text": unique_phrase * 25}]
    index_dir = get_matter_index_dir(user_id, matter_id)
    ok, msg, n = index_documents(docs, index_dir=index_dir)
    assert ok, msg
    assert n > 0


def test_matter_indexes_are_separate_paths():
    from backend.app.core.matter_index import get_matter_index_dir, resolve_rag_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    m1 = create_matter(uid, matter_name="Alpha Corp")["matter_id"]
    m2 = create_matter(uid, matter_name="Beta Ltd")["matter_id"]
    p1 = get_matter_index_dir(uid, m1)
    p2 = get_matter_index_dir(uid, m2)
    assert p1 != p2
    assert resolve_rag_index_dir(uid, m1) == p1
    assert resolve_rag_index_dir(uid, m2) == p2


def test_query_kb_scoped_to_matter_only():
    from rag import query_kb
    from backend.app.core.matter_index import get_matter_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    m_a = create_matter(uid, matter_name="Matter Alpha")["matter_id"]
    m_b = create_matter(uid, matter_name="Matter Beta")["matter_id"]

    phrase_a = "UNIQUE_ALPHA_ZEBRA_77441 bail application under section 437 BNSS"
    phrase_b = "UNIQUE_BETA_OCTOPUS_99221 contract breach indemnity clause arbitration"

    _build_matter_index(uid, m_a, phrase_a, "alpha.pdf")
    _build_matter_index(uid, m_b, phrase_b, "beta.pdf")

    hits_a = query_kb("bail application ZEBRA 77441", k=5, index_dir=get_matter_index_dir(uid, m_a))
    hits_b = query_kb("contract breach OCTOPUS 99221", k=5, index_dir=get_matter_index_dir(uid, m_b))

    assert hits_a
    assert hits_b
    text_a = " ".join(c.get("content", "") for c in hits_a).upper()
    text_b = " ".join(c.get("content", "") for c in hits_b).upper()
    assert "ZEBRA" in text_a or "ALPHA" in text_a
    assert "OCTOPUS" in text_b or "BETA" in text_b
    assert "OCTOPUS" not in text_a
    assert "ZEBRA" not in text_b


def test_resolve_rag_index_dir_requires_valid_matter():
    from backend.app.core.matter_index import resolve_rag_index_dir, get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    m = create_matter(uid, matter_name="Valid")["matter_id"]
    assert resolve_rag_index_dir(uid, m).name.startswith("matter_")
    assert resolve_rag_index_dir(uid, "fake-matter-id") == get_unlinked_index_dir(uid)
