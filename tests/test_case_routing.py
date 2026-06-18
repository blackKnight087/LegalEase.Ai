"""Case-file queries — State vs X and uploaded case PDFs."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from backend.app.core.case_entity_resolver import (
    extract_case_needles,
    extract_case_parties,
    extract_entity_needles,
    is_entity_focus_query,
)
from kb_query_types import is_case_query


def test_state_vs_rohan_detected():
    assert is_case_query("Explain State vs Rohan Mehta case")
    a, b = extract_case_parties("Explain State vs Rohan Mehta case")
    assert "rohan" in b
    needles = extract_case_needles("Explain State vs Rohan Mehta case")
    assert any("rohan mehta" in n for n in needles)


def test_detailed_party_name_stripped():
    a, b = extract_case_parties("State vs Rohan Mehta detailed")
    assert "detailed" not in b
    assert "rohan" in b


def test_single_token_entity_extraction():
    needles = extract_entity_needles("Rahul")
    assert "rahul" in needles
    assert is_entity_focus_query("Rahul")


@pytest.fixture
def _case_kb(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "db"))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss"))
    monkeypatch.setenv("LEARNING_ENGINE_ENABLED", "0")
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    case_text = Path(
        "Data/20260526192706_e6130bb5_LegalEase_Realistic_Indian_Case_KB_Test.auto.extracted.txt"
    ).read_text(encoding="utf-8")
    dense = Path(
        "Data/20260525180458_37027eb3_LegalEase_Dense_KB_Test_Document.auto.extracted.txt"
    ).read_text(encoding="utf-8")[:8000]
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = "case-route"
    index_dir = get_unlinked_index_dir(uid)
    index_documents(
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "LegalEase_Realistic_Indian_Case_KB_Test.pdf",
                "text": case_text,
            },
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "LegalEase_Dense_KB_Test_Document.pdf",
                "text": dense,
            },
        ],
        index_dir=index_dir,
    )
    return uid, index_dir


def test_e2e_state_vs_rohan_mehta(_case_kb):
    uid, index_dir = _case_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(
        uid,
        "Explain State vs Rohan Mehta case",
        [],
        index_dir=index_dir,
    )
    assert diag.get("query_class") == "case_law"
    assert "rohan mehta" in ans.lower() or "Rohan Mehta" in ans
    assert "IPC Section 499" not in ans
    assert "307" in ans or "attempt" in ans.lower()
    assert "Park Street" in ans or "FIR" in ans or "metal rod" in ans.lower()


def test_e2e_state_vs_rohan_detailed_no_faq(_case_kb):
    uid, index_dir = _case_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(
        uid,
        "State vs Rohan Mehta detailed",
        [],
        index_dir=index_dir,
    )
    assert diag.get("query_class") == "case_law"
    assert "(cid:127)" not in ans
    assert "Summarize the domestic violence case" not in ans
    assert "rohan mehta" in ans.lower() or "Rohan Mehta" in ans
    assert "Park Street" in ans or "FIR" in ans or "metal rod" in ans.lower()
    assert "307" in ans or "attempt" in ans.lower()


def test_e2e_other_case_name(_case_kb):
    uid, index_dir = _case_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(
        uid,
        "Summarize Priya Verma vs Rajesh Verma domestic violence case",
        [],
        index_dir=index_dir,
    )
    assert diag.get("query_class") == "case_law"
    assert "Priya" in ans or "domestic" in ans.lower()
    assert "(cid:127)" not in ans
    assert "metal rod" not in ans.lower()


def test_e2e_ananya_sen_entity(_case_kb):
    uid, index_dir = _case_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(uid, "Ananya Sen", [], index_dir=index_dir)
    assert diag.get("query_class") == "case_law"
    assert "From your uploaded documents" not in ans[:120]
    assert "(cid:127)" not in ans
    assert "ananya" in ans.lower() or "Article 14" in ans or "equality" in ans.lower()
    assert "SecureTech" not in ans and "Rohan Mehta" not in ans


def test_e2e_securetech_entity(_case_kb):
    uid, index_dir = _case_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(uid, "SecureTech Pvt Ltd", [], index_dir=index_dir)
    assert diag.get("query_class") == "case_law"
    assert "From your uploaded documents" not in ans[:120]
    assert "(cid:127)" not in ans
    assert "securetech" in ans.lower() or "NDA" in ans or "confidential" in ans.lower()
    assert "Singh Developers" not in ans and "Rohan Mehta" not in ans


@pytest.fixture
def _rahul_vs_state_kb(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "db"))
    monkeypatch.setenv("FAISS_BASE_DIR", str(tmp_path / "faiss"))
    monkeypatch.setenv("LEARNING_ENGINE_ENABLED", "0")
    from backend.app.core.practice_schema import ensure_practice_schema

    ensure_practice_schema()
    from app import init_db

    init_db()
    case_text = """
Case 1: Rahul vs State (IPC 307 - Attempt to Murder)
FIR No. 12/2026 at Delhi. The complainant alleged that Rahul attacked accused during dispute.

Hearing 1: prosecution argued intention to kill from repeated blows to the head; defense argued self-defense.
Witness: Priya Das said she saw Rahul near the scene.

Suggested KB Testing Questions
(cid:127) What happened during Hearing 1 in Rahul vs State?
(cid:127) Summarize the case.
""".strip()
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    uid = "rahul-case"
    index_dir = get_unlinked_index_dir(uid)
    index_documents(
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": "Rahul_vs_State.pdf",
                "text": case_text,
            }
        ],
        index_dir=index_dir,
    )
    return uid, index_dir


def test_e2e_single_token_name_rahul(_rahul_vs_state_kb):
    uid, index_dir = _rahul_vs_state_kb
    from kb_pipeline import kb_pipeline

    ans, _, diag = kb_pipeline(uid, "Rahul", [], index_dir=index_dir)
    assert diag.get("query_class") == "case_law"
    assert "(cid:127)" not in ans
    assert "Hearing 1" in ans or "FIR" in ans
    assert "Suggested KB Testing Questions" not in ans
