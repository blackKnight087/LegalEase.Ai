"""Page-break chunk stitching for multi-page lists."""
from __future__ import annotations

from backend.app.core.kb_chunk_stitch import (
    build_stitched_mega_chunk,
    count_numbered_rights,
    merge_chunk_texts,
    rights_list_truncated,
)


def test_truncated_three_of_five():
    page1 = """
Five Constitutional Rights
1. Right to Equality (Article 14)
2. Right to Freedom (Article 19)
3. Right against Exploitation (Article 23)
"""
    assert rights_list_truncated(page1, "Five Constitutional Rights")
    assert count_numbered_rights(page1) == 3


def test_complete_five_not_truncated():
    full = """
Five Constitutional Rights
1. Right to Equality (Article 14)
2. Right to Freedom (Article 19)
3. Right against Exploitation (Article 23)
4. Right to Freedom of Religion (Article 25)
5. Right to Constitutional Remedies (Article 32)
"""
    assert not rights_list_truncated(full, "Five Constitutional Rights")
    assert count_numbered_rights(full) == 5


def test_merge_page_break_chunks():
    c1 = {
        "content": "Five Constitutional Rights\n1. Right to Equality (Article 14)\n2. Right to Freedom (Article 19)\n3. Right against Exploitation (Article 23)",
        "metadata": {"filename": "kb.pdf", "chunk_index": "4", "page_number": "2"},
    }
    c2 = {
        "content": "[Page 3]\n4. Right to Freedom of Religion (Article 25)\n5. Right to Constitutional Remedies (Article 32)",
        "metadata": {"filename": "kb.pdf", "chunk_index": "5", "page_number": "3"},
    }
    merged = merge_chunk_texts([c1, c2])
    assert count_numbered_rights(merged) == 5
    mega = build_stitched_mega_chunk([c1, c2], "Five Constitutional Rights")
    assert mega
    assert count_numbered_rights(mega["content"]) == 5
