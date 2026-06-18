"""Evidence readiness — detect evidence types in intake corpus."""
from __future__ import annotations

import re
from typing import Any, Dict, List

_EVIDENCE_TYPES = [
    ("witnesses", r"\b(witness|eyewitness|saw|testimony)\b"),
    ("photos", r"\b(photo|photograph|picture|cctv)\b"),
    ("videos", r"\b(video|recording|footage)\b"),
    ("chats", r"\b(whatsapp|chat|message|sms|telegram)\b"),
    ("emails", r"\b(email|mail|gmail|outlook)\b"),
    ("bank_transfers", r"\b(bank|neft|rtgs|upi|transfer|payment)\b"),
    ("call_records", r"\b(call log|phone record|cdr)\b"),
    ("contracts", r"\b(contract|agreement|deed|mou)\b"),
]


def assess_evidence_readiness(intake_text: str, doc_texts: List[str] | None = None) -> Dict[str, Any]:
    corpus = (intake_text or "").lower()
    for t in doc_texts or []:
        corpus += "\n" + (t or "").lower()

    types: List[Dict[str, Any]] = []
    present = 0
    for name, pat in _EVIDENCE_TYPES:
        hit = bool(re.search(pat, corpus, re.I))
        if hit:
            present += 1
        types.append({"type": name, "present": hit})

    total = len(_EVIDENCE_TYPES) or 1
    pct = int(round(100 * present / total))
    return {
        "percent": pct,
        "types": types,
        "has_witness_mention": any(t["type"] == "witnesses" and t["present"] for t in types),
    }
