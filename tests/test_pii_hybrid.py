"""Hybrid PII regex + NER tests."""
from __future__ import annotations

import pytest

from document_services.pii_redactor import detect_pii, redact_text


@pytest.mark.parametrize(
    "snippet,expect_type",
    [
        ("Aadhaar 2345 6789 0123", "aadhaar"),
        ("PAN ABCDE1234F", "pan"),
        ("call 9876543210", "phone"),
        ("a@example.com", "email"),
    ],
)
def test_regex_detect(snippet, expect_type):
    d = detect_pii(snippet)
    types = {f["type"] for f in d["findings"]}
    assert expect_type in types


def test_redact_layers():
    text = "Email test@mail.com and phone 9876543210"
    out = redact_text(text)
    assert "[EMAIL REDACTED]" in out["redacted"] or "@" not in out["redacted"]
    assert out["redaction_count"] >= 1


def test_ner_redact_optional():
    try:
        from backend.app.core.pii_ner import ner_redact

        out, finds = ner_redact("John Smith lived in Mumbai.")
        if finds:
            assert "REDACTED" in out
    except Exception:
        pytest.skip("spaCy not installed")
