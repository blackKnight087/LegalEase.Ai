"""Integration tests using user's dense KB PDF fixtures (optional — skip if files missing)."""
from __future__ import annotations

import uuid
from pathlib import Path

import pytest

pytestmark = pytest.mark.legacy_kb

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DENSE_PDF = FIXTURES / "LegalEase_Dense_KB_Test_Document.pdf"
PAGE20_PDF = FIXTURES / "LegalEase_20_Page_KB_Test_Document.pdf"


def _index_pdf(uid: str, pdf_path: Path):
    from rag import index_documents
    from backend.app.core.matter_index import get_unlinked_index_dir

    text = pdf_path.read_bytes()
    try:
        from pypdf import PdfReader
        import io

        reader = PdfReader(io.BytesIO(text))
        text = "\n".join((p.extract_text() or "") for p in reader.pages)
    except Exception:
        pytest.skip("pypdf unavailable for PDF text extraction")

    if len(text.strip()) < 200:
        pytest.skip("PDF text extraction too short")

    index_dir = get_unlinked_index_dir(uid)
    ok, msg, n = index_documents(
        [
            {
                "doc_id": str(uuid.uuid4()),
                "filename": pdf_path.name,
                "text": text,
            }
        ],
        index_dir=index_dir,
    )
    assert ok, msg
    assert n > 0
    return index_dir


@pytest.mark.integration
@pytest.mark.skipif(not DENSE_PDF.exists(), reason="Dense KB PDF fixture not present")
def test_dense_pdf_comparison_299_300():
    from kb_pipeline import kb_pipeline

    uid = f"pdf-{uuid.uuid4().hex[:8]}"
    index_dir = _index_pdf(uid, DENSE_PDF)
    answer, _, diag = kb_pipeline(
        uid,
        "Difference between IPC 299 and IPC 300",
        [],
        index_dir=index_dir,
    )
    assert answer
    assert "299" in answer and "300" in answer
    assert "rigorously test" not in answer.lower()
    assert diag.get("found") is not False


@pytest.mark.integration
@pytest.mark.skipif(not DENSE_PDF.exists(), reason="Dense KB PDF fixture not present")
def test_dense_pdf_section_307():
    from kb_pipeline import kb_pipeline

    uid = f"pdf-{uuid.uuid4().hex[:8]}"
    index_dir = _index_pdf(uid, DENSE_PDF)
    answer, _, _ = kb_pipeline(uid, "Explain IPC Section 307", [], index_dir=index_dir)
    assert "307" in answer
    assert "Attempt" in answer or "attempt" in answer.lower()
    assert "rigorously test" not in answer.lower()


@pytest.mark.integration
@pytest.mark.skipif(not PAGE20_PDF.exists(), reason="20-page PDF fixture not present")
def test_20page_pdf_indexes():
    from backend.app.core.faiss_index_stats import count_index_vectors

    uid = f"pdf-{uuid.uuid4().hex[:8]}"
    index_dir = _index_pdf(uid, PAGE20_PDF)
    assert count_index_vectors(index_dir) > 10
