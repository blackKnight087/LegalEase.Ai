"""Hybrid / Web Intel answers must not repeat the same bullet blocks."""
from __future__ import annotations

from backend.app.core.web_answer_cleaner import polish_research_answer

DUP_WEB = """
## Direct Answer

The RG Kar case concerns the 2024 Kolkata hospital incident.

- **Incident:** On August 9, 2024, a trainee doctor was found dead [cite: 2, 5].
- **Initial Conviction:** Sanjay Roy received a life sentence [cite: 3].
- **Parents' Allegations:** Family cited a larger conspiracy [cite: 4].
- **Court Intervention:** Calcutta High Court ordered an SIT [cite: 2, 4, 5, ## Direct Answer [cite: 2, 5, 7].

- **Incident:** On August 9, 2024, a trainee doctor was found dead [cite: 5, 7, 9].
- **Initial Conviction:** Sanjay Roy received a life sentence [cite: 3, 5, 7].
- **Parents' Allegations:** Family cited a larger conspiracy [cite: 4, 5, 7].
- **Court Intervention:** Calcutta High Court ordered an SIT [cite: 3, 5, 7].
"""


def test_polish_removes_duplicate_bullets_and_cite_garbage():
    out = polish_research_answer(DUP_WEB)
    assert out.lower().count("incident:") <= 1 or out.lower().count("**incident:**") <= 1
    assert "[cite:" not in out.lower()
    assert "direct answer [cite" not in out.lower()
