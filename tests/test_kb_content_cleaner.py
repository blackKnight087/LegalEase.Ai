"""KB test-document boilerplate stripping and comparison fields."""
from __future__ import annotations

DENSE_BLOCK = """
IPC Section 299
Meaning: Culpable Homicide — causing death with intention or knowledge that an act may cause death.
Explanation: This section is included to rigorously test retrieval accuracy, section mapping,
punishment extraction, semantic search, and legal comparison features in LegalEase. Queries such
as "Explain IPC 299", "Punishment under IPC 299", "Difference between IPC 299 and other
sections", and follow-up questions should return relevant answers.
Example: A practical scenario involving IPC Section 299 should be interpreted based on intent.
"""

DENSE_300 = """
IPC Section 300
Meaning: Murder — culpable homicide becomes murder when intent, brutality, or dangerous circumstances exist.
Explanation: This section is included to rigorously test retrieval accuracy.
"""


def test_strip_boilerplate():
    from kb_content_cleaner import extract_meaning_from_block, is_kb_test_boilerplate

    assert is_kb_test_boilerplate("Queries such as Explain IPC 299")
    assert not is_kb_test_boilerplate("Explanation: This section is included to rigorously test retrieval")
    meaning = extract_meaning_from_block(DENSE_BLOCK)
    assert "Culpable Homicide" in meaning
    assert "rigorously test" not in meaning
    assert "Explain IPC 299" not in meaning


def test_format_statute_section_fields_includes_explanation():
    from kb_content_cleaner import format_statute_section_fields

    out = format_statute_section_fields(DENSE_BLOCK, section="299", law="IPC")
    assert "## IPC Section 299" in out
    assert "**Meaning:**" in out
    assert "Culpable Homicide" in out
    assert "**Explanation:**" in out
    assert "rigorously test" in out
    assert "**Example:**" in out
    assert "Explain IPC 299" not in out


def test_comparison_meaning_and_punishment():
    from kb_compare_engine import _extract_meaning, _extract_punishment

    ent299 = {"type": "IPC", "section": "299"}
    ent300 = {"type": "IPC", "section": "300"}
    m299 = _extract_meaning(DENSE_BLOCK, ent299)
    m300 = _extract_meaning(DENSE_300, ent300)
    assert "Culpable" in m299
    assert "Murder" in m300
    assert "Explain IPC" not in m299
    p300 = _extract_punishment(DENSE_300, ent300)
    assert "302" in p300 or "punish" in p300.lower()


def test_format_comparison_pro_same_law():
    from kb_compare_engine import format_comparison_pro

    chunks = [{"content": DENSE_BLOCK + "\n" + DENSE_300}]
    entities = [{"type": "IPC", "section": "299"}, {"type": "IPC", "section": "300"}]
    out = format_comparison_pro("Difference between IPC 299 and IPC 300", chunks, entities)
    assert "Comparison" in out
    assert "Culpable" in out or "Murder" in out
    assert "rigorously test" not in out
    assert "Explain IPC 299" not in out
    assert "IPC 299" in out
    assert "IPC 300" in out
