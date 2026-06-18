"""Case-locked chunk filtering — no cross-case contamination."""
from __future__ import annotations

from backend.app.core.kb_case_context_lock import (
    lock_chunks_to_query,
    strip_query_context_suffix,
)


def test_strip_context_suffix():
    q = "Riya Banerjee vs State Medical Board (context: Case 5: Securetech)"
    assert "context:" not in strip_query_context_suffix(q)
    assert "Riya Banerjee" in strip_query_context_suffix(q)


def test_lock_riya_case_only():
    chunks = [
        {
            "content": (
                "Case 5: Medisure Hospital vs Former Consultant\n"
                "Confidentiality breach NDA former employee."
            ),
            "metadata": {"filename": "cases.pdf"},
        },
        {
            "content": (
                "Case 6: Riya Banerjee vs State Medical Board\n"
                "Petitioner Riya Banerjee challenged denial of emergency medical assistance."
            ),
            "metadata": {"filename": "cases.pdf"},
        },
        {
            "content": (
                "Witness Statement: Priya Das\nIPC Section 307 Attempt to Murder CCTV footage."
            ),
            "metadata": {"filename": "cases.pdf"},
        },
    ]
    locked = lock_chunks_to_query("Riya Banerjee vs State Medical Board", chunks)
    assert locked
    combined = " ".join(c.get("content", "") for c in locked).lower()
    assert "riya banerjee" in combined
    assert "medisure" not in combined
    assert "priya das" not in combined
    assert "ipc section 307" not in combined
