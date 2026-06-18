"""Hybrid PII — RegEx (pass 1) + spaCy NER (pass 2)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_PATTERNS: List[Tuple[str, str, str]] = [
    ("aadhaar", r"\b[2-9]\d{3}\s?\d{4}\s?\d{4}\b", "[AADHAAR REDACTED]"),
    ("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", "[PAN REDACTED]"),
    ("phone", r"\b(?:\+91[\s-]?)?[6-9]\d{9}\b", "[PHONE REDACTED]"),
    ("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[EMAIL REDACTED]"),
    ("bank_account", r"\b(?:A/C|Account)\s*(?:No\.?|Number)?\s*:?\s*\d{9,18}\b", "[BANK ACCOUNT REDACTED]"),
    ("ifsc", r"\b[A-Z]{4}0[A-Z0-9]{6}\b", "[IFSC REDACTED]"),
    ("inr_amount", r"(?:₹|Rs\.?)\s*[\d,]+(?:\.\d{2})?", "[AMOUNT REDACTED]"),
    (
        "address",
        r"\b(?:Flat|House|Plot|H\.?\s*No\.?)\s*[\w\d/\-]+[^.\n]{10,80}(?:Road|Street|Nagar|Colony|Pincode|PIN)[^.\n]{0,40}",
        "[ADDRESS REDACTED]",
    ),
    ("pincode", r"\bPIN(?:CODE)?\s*:?\s*\d{6}\b", "[PINCODE REDACTED]"),
]


def detect_pii(text: str, user_id: str = "") -> Dict[str, Any]:
    text = text or ""
    findings: List[Dict[str, Any]] = []
    for pii_type, pattern, _ in _PATTERNS:
        for m in re.finditer(pattern, text, re.I):
            findings.append(
                {
                    "type": pii_type,
                    "start": m.start(),
                    "end": m.end(),
                    "masked_preview": _mask_preview(m.group(0)),
                    "layer": "regex",
                }
            )
    try:
        from backend.app.core.pii_ner import ner_detect

        for f in ner_detect(text):
            findings.append({**f, "layer": "ner"})
    except Exception:
        pass
    return {
        "pii_count": len(findings),
        "findings": findings,
        "types_found": sorted({f["type"] for f in findings}),
    }


def whitelist_pii_phrase(user_id: str, phrase: str) -> Dict[str, Any]:
    return {"recorded": True, "phrase": (phrase or "").strip()}


def redact_text(
    text: str,
    types: Optional[List[str]] = None,
    enabled: bool = True,
) -> Dict[str, Any]:
    if not enabled:
        return {"redacted": text, "redaction_count": 0, "map": [], "layers": []}

    allowed = set(types) if types else {p[0] for p in _PATTERNS}
    redacted = text or ""
    redaction_map: List[Dict[str, Any]] = []
    count = 0
    layers = []

    for pii_type, pattern, replacement in _PATTERNS:
        if pii_type not in allowed:
            continue

        def _repl(m: re.Match, pt=pii_type, rep=replacement) -> str:
            nonlocal count
            count += 1
            redaction_map.append({"type": pt, "layer": "regex", "replacement": rep})
            return rep

        redacted = re.sub(pattern, _repl, redacted, flags=re.I)
    if count:
        layers.append("regex")

    try:
        from backend.app.core.pii_ner import ner_redact

        ner_out, ner_findings = ner_redact(redacted)
        if ner_findings:
            redacted = ner_out
            count += len(ner_findings)
            layers.append("ner")
            for f in ner_findings:
                redaction_map.append(
                    {"type": f["type"], "layer": "ner", "replacement": f["replacement"]}
                )
    except Exception:
        pass

    return {
        "redacted": redacted,
        "redaction_count": count,
        "map": redaction_map,
        "types_redacted": sorted(allowed),
        "layers": layers,
    }


def _mask_preview(value: str) -> str:
    if len(value) <= 4:
        return "****"
    return value[:2] + "*" * (len(value) - 4) + value[-2:]
