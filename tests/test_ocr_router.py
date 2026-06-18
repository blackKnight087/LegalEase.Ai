"""OCR dual-path router tests."""
from __future__ import annotations

import pytest

from backend.app.core.ocr_router import (
    MIN_CHARS_PER_PAGE,
    needs_ocr_fallback,
    non_printable_ratio,
    page_char_counts,
)


@pytest.mark.parametrize(
    "text,pages,expected",
    [
        ("", 3, True),
        ("x" * 50, 5, True),
        ("x" * 500, 2, False),
        ("\n\n".join(f"[Page {i}]\n{'word ' * 80}" for i in range(1, 4)), 3, False),
    ],
)
def test_needs_ocr_fallback(text, pages, expected):
    need, _ = needs_ocr_fallback(text, pages)
    assert need is expected


def test_page_char_counts():
    t = "[Page 1]\nshort\n\n[Page 2]\n" + "a" * 200
    counts = page_char_counts(t)
    assert len(counts) >= 1


def test_non_printable_ratio_clean():
    assert non_printable_ratio("IPC Section 302 murder") < 0.1


def test_min_chars_threshold():
    assert MIN_CHARS_PER_PAGE >= 40
