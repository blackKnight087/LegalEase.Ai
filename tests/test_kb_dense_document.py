"""LegalEase dense / 20-page KB test PDF extractors."""
from __future__ import annotations

DENSE_TAIL = """
Constitutional Rights
1. Right to Equality (Article 14)
2. Right to Freedom (Article 19)
Important Cases
Nirbhaya Case (2012 Delhi Gang Rape Case): Led to major anti-rape reforms and stricter criminal provisions.
Kesavananda Bharati Case: Introduced the Basic Structure Doctrine, limiting Parliament from altering the Constitution's core identity.
Sample NDA Clauses
Parties involved: Disclosing Party and Receiving Party. Confidential information must not be disclosed without permission. Upon termination of agreement, confidential information must be returned.
"""

IPC_379 = """
IPC Section 379
Meaning: Punishment for theft.
Explanation: This section is included for testing section retrieval, exact matching, punishment extraction, semantic understanding, and follow-up reasoning in a legal AI system.
Example: Example legal scenario involving IPC 379 interpreted according to legal intent, evidence, and punishment.
"""


def test_kesavananda_has_doctrine_text():
    from backend.app.core.kb_dense_document import enrich_landmark_passage
    from backend.app.core.kb_landmark_case import build_landmark_case_answer

    passage = enrich_landmark_passage(DENSE_TAIL, "kesavananda")
    assert "Basic Structure" in passage
    assert "Sample NDA" not in passage

    ans = build_landmark_case_answer(
        "explain Kesavananda Bharati Case",
        [{"content": DENSE_TAIL, "metadata": {}}],
    )
    assert ans
    assert "basic structure" in ans.lower()
    assert "sample nda" not in ans.lower()


def test_nda_parties_from_mixed_pdf():
    from backend.app.core.kb_dense_document import build_nda_topic_answer

    ans = build_nda_topic_answer(
        "Who are the parties involved in the NDA?",
        [{"content": DENSE_TAIL, "metadata": {}}],
    )
    assert ans
    assert "disclosing" in ans.lower()


def test_ipc_379_explain_from_dense_fields():
    from backend.app.core.kb_dense_document import build_dense_section_explain

    ans = build_dense_section_explain(
        "Explain IPC 379",
        [{"content": IPC_379, "metadata": {}}],
    )
    assert ans
    assert "379" in ans
    assert "theft" in ans.lower()
    assert "rigorously test" not in ans.lower()


def test_try_dense_entry():
    from backend.app.core.kb_dense_document import try_dense_document_answer

    ans = try_dense_document_answer("explain Kesavananda Bharati Case", [{"content": DENSE_TAIL}])
    assert ans and "basic structure" in ans.lower()
