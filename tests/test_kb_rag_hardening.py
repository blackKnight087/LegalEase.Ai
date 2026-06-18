"""KB RAG hardening: chunk metadata, claim validation, cache invalidation."""
from __future__ import annotations

import re
import uuid

import pytest

LAW_DOC = """
[Page 1]
Legal Knowledge Base Testing Document

IPC Section 299 — Culpable Homicide
Whoever causes death with intention of causing death commits culpable homicide.

IPC Section 302 — Punishment for Murder
Whoever commits murder shall be punished with death or imprisonment for life.

IPC Section 307 — Attempt to Murder
Whoever does any act with intention to cause death shall be punished up to ten years.

IPC 302 → BNS 101 | Murder
IPC 307 → BNS 109 | Attempt to murder
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "harden.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


def test_section_chunks_have_metadata():
    from rag import _documents_to_chunk_batches

    texts, metas = _documents_to_chunk_batches(
        [{"doc_id": "d1", "filename": "law.pdf", "text": LAW_DOC}]
    )
    assert texts
    sec302 = [m for m in metas if "302" in m.get("section_numbers", "")]
    assert sec302, "Section 302 should appear in chunk metadata"
    assert sec302[0].get("page_range") or sec302[0].get("page_number")
    assert "ipc" in sec302[0].get("law_tags", "")


def test_mapping_rows_indexed():
    from rag import _documents_to_chunk_batches

    texts, metas = _documents_to_chunk_batches(
        [{"doc_id": "d1", "filename": "map.pdf", "text": LAW_DOC}]
    )
    has_mapping = any(
        re.search(r"302.*BNS|BNS.*302", t or "", re.I) for t in texts
    ) or any("bns" in (m.get("law_tags") or "") for m in metas)
    assert has_mapping


def test_claim_validator_rejects_hallucinated_section():
    from kb_validate import validate_answer
    from kb_query_types import QueryType

    chunks = [{"content": "IPC Section 307 — Attempt to Murder. Punishment up to ten years."}]
    bad = "IPC Section 420 defines cheating with imprisonment up to seven years."
    ok, reason = validate_answer(
        bad,
        "Explain IPC 307",
        chunks,
        QueryType.SECTION_EXPLANATION,
        profile_sections=["307"],
    )
    assert not ok
    assert "unsupported" in reason or "420" in reason or "missing_section" in reason


def test_cache_invalidates_on_reindex(tmp_path):
    from backend.app.core import kb_cache
    from backend.app.core.kb_cache import get_cached_chunks, invalidate_index_cache, set_cached_chunks

    kb_cache._store.clear()
    kb_cache._index_epoch.clear()
    index_dir = tmp_path / "idx"
    index_dir.mkdir()
    (index_dir / "index.faiss").write_bytes(b"fake")
    (index_dir / "index.pkl").write_bytes(b"fake")

    chunks = [{"content": "IPC 307", "metadata": {}}]
    set_cached_chunks("ipc 307", index_dir, 5, chunks)
    v1 = kb_cache.index_version(index_dir)
    hit = get_cached_chunks("ipc 307", index_dir, 5)
    assert hit is not None

    invalidate_index_cache(index_dir)
    v2 = kb_cache.index_version(index_dir)
    assert v2 != v1
    miss = get_cached_chunks("ipc 307", index_dir, 5)
    assert miss is None


def test_synthesize_from_chunks_accepts_user_id():
    from answer_orchestrator import synthesize_from_chunks
    import inspect

    sig = inspect.signature(synthesize_from_chunks)
    assert "user_id" in sig.parameters


@pytest.mark.slow
def test_kb_pipeline_302_not_307(tmp_path, monkeypatch):
    from rag import index_documents
    from kb_pipeline import kb_pipeline
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = f"u-{uuid.uuid4().hex[:8]}"
    index_dir = get_unlinked_index_dir(uid)
    ok, msg, n = index_documents(
        [{"doc_id": str(uuid.uuid4()), "filename": "law.pdf", "text": LAW_DOC}],
        index_dir=index_dir,
    )
    assert ok, msg
    answer, _, diag = kb_pipeline(uid, "What is punishment under IPC 302?", [], index_dir=index_dir)
    assert "302" in answer
    assert "Attempt to Murder" not in answer
    assert diag.get("validation", {}).get("ok", True) is not False
