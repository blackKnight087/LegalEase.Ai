"""Strict statute retrieval — exact section must match, no cross-section bleed."""
from __future__ import annotations

import uuid

import pytest

pytestmark = pytest.mark.legacy_kb

KB_STATUTE_DOC = """
Legal Knowledge Base Testing Document

IPC Section 299 — Culpable Homicide
Whoever causes death by doing an act with the intention of causing death commits culpable homicide.

IPC Section 300 — Murder
Murder is culpable homicide when committed with aggravating circumstances.

IPC Section 302 — Punishment for Murder
Whoever commits murder shall be punished with death or imprisonment for life.

IPC Section 307 — Attempt to Murder
Whoever does any act with intention to cause death but the victim survives may be punished up to ten years.

IPC Section 320 — Grievous Hurt
Whoever voluntarily causes hurt which is grievous, except in the cases provided for below, is guilty of grievous hurt.

IPC Section 420 — Cheating
Whoever cheats and thereby dishonestly induces delivery of property commits cheating.
"""


@pytest.fixture(autouse=True)
def _db(tmp_path, monkeypatch):
    db = tmp_path / "kb_strict.db"
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(db))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss_indexes"))
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    yield


def _index_doc(uid: str):
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    index_dir = get_unlinked_index_dir(uid)
    ok, msg, n = index_documents(
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "legal_kb_statute_test.pdf",
                "text": KB_STATUTE_DOC,
            }
        ],
        index_dir=index_dir,
    )
    assert ok, msg
    assert n > 0
    return index_dir


def test_parse_structured_ipc_320():
    from backend.app.core.kb_strict_retrieval import parse_structured_query

    s = parse_structured_query("Explain IPC Section 320")
    assert "320" in s.sections
    assert s.legal_code == "IPC"


def test_strict_retrieve_returns_only_requested_section():
    from backend.app.core.kb_strict_retrieval import (
        strict_retrieve_statute_sections,
        validate_section_chunks,
    )

    uid = f"u-{uuid.uuid4().hex[:8]}"
    index_dir = _index_doc(uid)
    chunks, mode, diag = strict_retrieve_statute_sections(
        index_dir,
        query="Explain IPC Section 320",
        sections=["320"],
        law="IPC",
        top_k=6,
    )
    assert chunks, f"expected hits, diag={diag}"
    assert mode.startswith("strict")
    validated = validate_section_chunks(chunks, ["320"], "IPC")
    assert validated
    combined = " ".join(c.get("content", "") for c in validated).lower()
    assert "320" in combined
    assert "grievous" in combined or "hurt" in combined
    assert "299" not in combined or "grievous" in combined
    wrong = re_find_other_ipc_sections(combined, exclude="320")
    assert not wrong, f"contamination from sections {wrong}"


def test_kb_pipeline_ipc_320_not_302():
    from kb_pipeline import kb_pipeline

    uid = f"u-{uuid.uuid4().hex[:8]}"
    index_dir = _index_doc(uid)
    answer, chunks, diag = kb_pipeline(
        uid,
        "Explain IPC Section 320",
        [],
        index_dir=index_dir,
    )
    import re

    assert answer
    assert "320" in answer.upper()
    assert not re.search(r"\bipc\s+section\s+302\b", answer, re.I)
    assert not re.search(r"\bipc\s+section\s+299\b", answer, re.I)
    assert diag.get("query_class") in ("single_section", None) or "320" in str(
        diag.get("sections_requested") or diag.get("section_entities") or ""
    )


def test_strict_retrieve_420():
    from backend.app.core.kb_strict_retrieval import strict_retrieve_statute_sections

    uid = f"u-{uuid.uuid4().hex[:8]}"
    index_dir = _index_doc(uid)
    chunks, _, _ = strict_retrieve_statute_sections(
        index_dir,
        query="IPC Section 420 explain",
        sections=["420"],
        law="IPC",
    )
    assert chunks
    body = (chunks[0].get("content") or "").lower()
    assert "420" in body
    assert "cheat" in body


def re_find_other_ipc_sections(text: str, exclude: str) -> list:
    import re

    found = []
    for m in re.finditer(r"\bipc\s+section\s+(\d{1,4})\b", text, re.I):
        if m.group(1) != exclude:
            found.append(m.group(1))
    return found
