"""Guaranteed KB answer from chunks."""
from __future__ import annotations

import pytest

from backend.app.core.kb_force_answer import guarantee_kb_answer


@pytest.mark.unit
def test_guarantee_answer_from_chunks():
    chunks = [
        {
            "content": "IPC Section 406 — Criminal breach of trust. Whoever dishonestly misappropriates property.",
            "metadata": {"filename": "ipc.pdf"},
            "final_score": 0.8,
        }
    ]
    ans = guarantee_kb_answer("IPC Section 406", chunks)
    assert "406" in ans
    assert "breach" in ans.lower() or "trust" in ans.lower()


@pytest.mark.unit
def test_guarantee_constitutional():
    chunks = [
        {
            "content": "Article 14 — Right to Equality. The State shall not deny equality before the law.",
            "metadata": {"filename": "constitution.pdf"},
            "final_score": 0.7,
        }
    ]
    ans = guarantee_kb_answer("Explain Right to Equality", chunks)
    assert "equality" in ans.lower() or "article" in ans.lower()
