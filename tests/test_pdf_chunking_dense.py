"""Large dense PDF must produce hundreds of chunks, not ~12."""
from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DENSE = ROOT / "Data" / "20260525180458_37027eb3_LegalEase_Dense_KB_Test_Document.pdf"


@pytest.mark.skipif(not DENSE.is_file(), reason="dense test PDF not in Data/")
def test_dense_pdf_native_extraction_and_chunk_count():
    from backend.app.core.pdf_extraction import extract_native_pages, _merge_pages
    from kb_preprocess import clean_legal_text

    pages, total = extract_native_pages(DENSE)
    assert total >= 50
    text = _merge_pages(pages)
    assert len(text) > 50_000

    cleaned = clean_legal_text(text)

    # Inline statute split (avoid importing full rag / embeddings)
    import re
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    parts = re.split(r"(?=\bIPC Section \d{1,4}[a-z]?\b)", cleaned, flags=re.I)
    chunks = []
    splitter = RecursiveCharacterTextSplitter(chunk_size=600, chunk_overlap=100)
    for part in parts:
        block = (part or "").strip()
        if len(block) < 40:
            continue
        if len(block) <= 600:
            chunks.append(block)
        else:
            chunks.extend(splitter.split_text(block))
    assert len(chunks) >= 200, f"expected hundreds of chunks, got {len(chunks)}"
