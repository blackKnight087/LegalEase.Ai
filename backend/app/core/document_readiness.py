"""Document readiness checklists by matter type."""
from __future__ import annotations

import re
from typing import Any, Dict, List

_TEMPLATES: Dict[str, List[str]] = {
    "PROPERTY_REAL_ESTATE": [
        "Sale deed / title document",
        "Property tax receipt",
        "Mutation certificate",
        "Encumbrance certificate",
        "Aadhaar / identity proof",
        "Possession proof / photos",
    ],
    "CRIMINAL_DEFENSE": [
        "FIR copy",
        "Bail order (if any)",
        "Charge sheet",
        "Identity proof",
        "Witness statements",
        "Medical records (if injury)",
    ],
    "FAMILY_LAW": [
        "Marriage certificate",
        "Identity proofs",
        "Income proof",
        "Prior court orders",
        "Domestic incident records",
    ],
    "COMMERCIAL_LITIGATION": [
        "Contract / agreement",
        "Invoices / payment proof",
        "Correspondence with counterparty",
        "Company registration",
        "Bank statements",
    ],
    "EMPLOYMENT_LABOUR": [
        "Appointment letter",
        "Salary slips",
        "Termination letter",
        "PF / ESIC records",
        "Workplace correspondence",
    ],
    "GENERAL": [
        "Identity proof",
        "Key agreement or notice",
        "Correspondence with other party",
        "Timeline of events (written)",
    ],
}


def _mentioned(label: str, corpus: str) -> bool:
    words = re.findall(r"[a-z]{4,}", label.lower())
    if not words:
        return False
    hits = sum(1 for w in words if w in corpus)
    return hits >= max(1, len(words) // 2)


def assess_document_readiness(
    intent: str,
    intake_text: str,
    doc_texts: List[str] | None = None,
) -> Dict[str, Any]:
    key = intent if intent in _TEMPLATES else "GENERAL"
    required_labels = _TEMPLATES.get(key, _TEMPLATES["GENERAL"])
    corpus = (intake_text or "").lower()
    for t in doc_texts or []:
        corpus += "\n" + (t or "").lower()

    items: List[Dict[str, Any]] = []
    present = 0
    for label in required_labels:
        ok = _mentioned(label, corpus)
        if ok:
            present += 1
        items.append(
            {
                "label": label,
                "status": "present" if ok else "missing",
            }
        )
    total = len(required_labels) or 1
    pct = int(round(100 * present / total))
    return {
        "percent": pct,
        "required": items,
        "matter_type": key,
    }
