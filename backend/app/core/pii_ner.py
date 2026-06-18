"""spaCy NER layer for hybrid PII redaction (PERSON, ORG, GPE)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_nlp = None
_nlp_failed = False

LABEL_MAP = {
    "PERSON": "REDACTED_NAME",
    "ORG": "REDACTED_ORG",
    "GPE": "REDACTED_LOCATION",
    "LOC": "REDACTED_LOCATION",
    "FAC": "REDACTED_ADDRESS",
}


def get_nlp():
    global _nlp, _nlp_failed
    if _nlp_failed:
        return None
    if _nlp is not None:
        return _nlp
    try:
        import spacy

        try:
            _nlp = spacy.load("en_core_web_sm")
        except OSError:
            logger.info("Downloading en_core_web_sm for PII NER...")
            from spacy.cli import download

            download("en_core_web_sm")
            _nlp = spacy.load("en_core_web_sm")
        return _nlp
    except Exception as exc:
        _nlp_failed = True
        logger.warning("spaCy NER unavailable: %s", exc)
        return None


def ner_detect(text: str) -> List[Dict[str, Any]]:
    nlp = get_nlp()
    if not nlp or not text:
        return []
    doc = nlp(text[:50000])
    findings = []
    counters: Dict[str, int] = {}
    for ent in doc.ents:
        if ent.label_ not in LABEL_MAP:
            continue
        tag = LABEL_MAP[ent.label_]
        counters[tag] = counters.get(tag, 0) + 1
        findings.append(
            {
                "type": ent.label_.lower(),
                "start": ent.start_char,
                "end": ent.end_char,
                "replacement": f"[{tag}_{counters[tag]}]",
                "text_preview": ent.text[:40],
            }
        )
    return findings


def ner_redact(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Replace NER entities right-to-left to preserve offsets."""
    findings = ner_detect(text)
    if not findings:
        return text, []
    redacted = text
    for f in sorted(findings, key=lambda x: x["start"], reverse=True):
        redacted = redacted[: f["start"]] + f["replacement"] + redacted[f["end"] :]
    return redacted, findings
