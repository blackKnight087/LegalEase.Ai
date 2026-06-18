"""Question-aware KB answering layer."""
from __future__ import annotations

from backend.app.core.kb_question_aware import (
    KBQuestionKind,
    answer_addresses_question,
    classify_kb_question,
    generate_question_aware_answer,
    is_mostly_chunk_repetition,
    structure_landmark_passage,
)

MIXED_KB = """
BNS Section 103 – Punishment for Murder
Five Constitutional Rights
1. Right to Equality (Article 14)
2. Right to Freedom (Article 19)
3. Right against Exploitation (Article 23)
4. Right to Freedom of Religion (Article 25)
5. Right to Constitutional Remedies (Article 32)
Kesavananda Bharati Case The Supreme Court introduced the Basic Structure Doctrine and ruled that Parliament cannot alter the Constitution's basic structure.
Sample NDA Agreement Parties involved: Disclosing Party and Receiving Party. Confidential information must not be disclosed without consent. Upon termination all confidential materials must be returned.
"""

NDA_CHUNK = {
    "content": (
        "Sample NDA Agreement\n"
        "Parties involved: Disclosing Party and Receiving Party. "
        "Confidential information must not be disclosed. "
        "Upon termination all materials must be returned."
    ),
    "metadata": {"filename": "nda.pdf"},
    "final_score": 0.9,
}


def test_classify_constitutional_list():
    assert classify_kb_question("Five Constitutional Rights") == KBQuestionKind.LIST_REQUEST


def test_classify_kesavananda():
    assert classify_kb_question("Kesavananda Bharati Case") == KBQuestionKind.CASE_EXPLANATION


def test_five_rights_not_case_dump():
    chunks = [{"content": MIXED_KB, "metadata": {"filename": "kb.pdf"}, "final_score": 0.9}]
    ans = generate_question_aware_answer("Five Constitutional Rights", chunks)
    assert ans
    al = ans.lower()
    assert "article 14" in al
    assert "article 32" in al
    assert "imran" not in al
    assert "nirbhaya" not in al
    assert "kesavananda" not in al


def test_kesavananda_structured():
    chunks = [{"content": MIXED_KB, "metadata": {"filename": "kb.pdf"}}]
    ans = generate_question_aware_answer("Kesavananda Bharati Case", chunks)
    assert ans
    al = ans.lower()
    assert "basic structure" in al
    assert "court" in al or "summary" in al
    assert ans.strip() != "Kesavananda Bharati Case"


def test_structure_landmark():
    body = structure_landmark_passage(
        "kesavananda",
        "Kesavananda Bharati Case The Supreme Court introduced the Basic Structure Doctrine.",
    )
    assert "Basic Structure" in body
    assert "###" in body


def test_nda_summary():
    ans = generate_question_aware_answer("Sample NDA Agreement", [NDA_CHUNK])
    assert ans
    al = ans.lower()
    assert "disclosing" in al or "parties" in al
    assert "confidential" in al


def test_chunk_repetition_detected():
    chunk = "Right to Equality Article 14 only text here for testing repetition detection."
    ans = chunk
    assert is_mostly_chunk_repetition(ans, [{"content": chunk}])


def test_title_only_fails_quality():
    assert not answer_addresses_question(
        "Kesavananda Bharati Case",
        "## Kesavananda Bharati Case",
        KBQuestionKind.CASE_EXPLANATION,
    )
