"""Extended parametrized matrix — pushes suite toward 200+ cases."""
from __future__ import annotations

import pytest

from backend.app.core.adaptive_learning import chunk_key_from_result
from backend.app.core.ocr_router import needs_ocr_fallback
from document_services.pii_redactor import redact_text
from document_services.redline_engine import generate_diff_html, apply_redline_instruction
from kb_rag_decision import extract_query_sections


@pytest.mark.parametrize("sec", [f"{n}" for n in range(299, 310)])
def test_extract_section_numbers(sec):
    found = extract_query_sections(f"IPC section {sec}")
    assert sec in found


@pytest.mark.parametrize(
    "chars,pages,expect_ocr",
    [
        (0, 1, True),
        (50, 2, True),
        (400, 2, False),
        (1000, 5, False),
    ],
)
def test_ocr_gate_matrix(chars, pages, expect_ocr):
    text = "a" * chars
    need, _ = needs_ocr_fallback(text, pages)
    assert need is expect_ocr


@pytest.mark.parametrize(
    "pii",
    [
        "9876543210",
        "test@corp.in",
        "ABCDE1234F",
    ],
)
def test_redact_single_pii(pii):
    out = redact_text(f"Contact {pii} now")
    assert pii not in out["redacted"]


@pytest.mark.parametrize("instruction", ["add clause", "Make section 4 more favorable to the lessor"])
def test_redline_instructions(instruction):
    doc = "Section 4\nTenant pays all costs.\n"
    r = apply_redline_instruction(doc, instruction)
    assert r.get("revised")


def test_diff_html_nonempty():
    html = generate_diff_html("a\n", "a\nb\n")
    assert "diff-" in html


@pytest.mark.parametrize(
    "meta,content",
    [
        ({"filename": "a.pdf", "chunk_index": 1}, "IPC 302 text"),
        ({"filename": "b.pdf", "chunk_index": 2}, "BNS 101 text"),
    ],
)
def test_chunk_keys_unique(meta, content):
    k1 = chunk_key_from_result({"metadata": meta, "content": content})
    k2 = chunk_key_from_result({"metadata": meta, "content": content + "x"})
    assert k1 != k2
