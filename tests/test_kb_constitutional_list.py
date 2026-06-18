"""Constitutional rights list — no chunk dump / FAQ bleed from mixed KB PDFs."""
from __future__ import annotations

from answer_orchestrator import format_constitutional_rights_answer
from backend.app.core.constitutional_concept_map import (
    extract_constitutional_rights_block,
    is_constitutional_rights_list_query,
)

MIXED_KB_CHUNK = """
BNS Section 103 – Punishment for Murder
Provides punishment for murder under the new criminal law framework.

Five Constitutional Rights
1. Right to Equality (Article 14)
2. Right to Freedom (Article 19)
3. Right against Exploitation (Article 23)
4. Right to Freedom of Religion (Article 25)
5. Right to Constitutional Remedies (Article 32)

(cid:127) IPC Section 307
(cid:127) Explain the Nirbhaya case in simple language
(cid:127) Name five constitutional rights
(cid:127) Who are the parties involved in the NDA?
(cid:127) Compare IPC 302 and BNS 103
"""


def test_list_query_detected():
    assert is_constitutional_rights_list_query("Five Constitutional Rights")
    assert is_constitutional_rights_list_query("name five constitutional rights")


def test_extract_rights_block():
    block = extract_constitutional_rights_block(MIXED_KB_CHUNK)
    assert "Right to Equality" in block
    assert "BNS Section 103" not in block
    assert "Nirbhaya" not in block


def test_bns_section_103_not_constitutional_dump():
    from backend.app.core.kb_document_first import try_statute_section_lookup_answer

    ans = try_statute_section_lookup_answer("BNS Section 103", [{"content": MIXED_KB_CHUNK}])
    assert ans
    al = ans.lower()
    assert "103" in al
    assert "murder" in al or "punishment" in al
    assert "right to equality" not in al
    assert "five constitutional" not in al


def test_format_mixed_chunk_no_faq():
    chunks = [{"content": MIXED_KB_CHUNK, "metadata": {"filename": "legal_kb_test_document.pdf"}}]
    ans = format_constitutional_rights_answer("Five Constitutional Rights", chunks)
    assert ans
    al = ans.lower()
    assert "article 14" in al
    assert "article 32" in al
    assert "bns section 103" not in al
    assert "nirbhaya" not in al
    assert "cid:127" not in ans
    assert "ipc section 307" not in al
    assert "nda" not in al or "parties" not in al
