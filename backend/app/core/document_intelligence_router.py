"""
Document-type intelligence router — classify uploads for scoped retrieval.

Wraps and extends document_classifier for the universal legal intelligence architecture.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, Optional

from document_classifier import DocumentType, classify_document


class DocIntelType(str, Enum):
    STATUTE = "statute"
    CASE_FILE = "case_file"
    COURT_JUDGMENT = "court_judgment"
    CONTRACT = "contract"
    NDA = "nda"
    FIR = "fir"
    PROPERTY_DOC = "property_doc"
    MEDICAL_LEGAL = "medical_legal"
    PERSONAL_DOC = "personal_doc"
    EVIDENCE = "evidence"
    BUSINESS_DOC = "business_doc"
    MIXED_FOLDER = "mixed_folder"
    UNKNOWN = "unknown"


_LEGACY_MAP = {
    DocumentType.NDA: DocIntelType.NDA,
    DocumentType.CONTRACT: DocIntelType.CONTRACT,
    DocumentType.AGREEMENT: DocIntelType.CONTRACT,
    DocumentType.CRIMINAL_LAW: DocIntelType.STATUTE,
    DocumentType.CONSTITUTIONAL: DocIntelType.STATUTE,
    DocumentType.COURT_JUDGMENT: DocIntelType.COURT_JUDGMENT,
    DocumentType.FIR: DocIntelType.FIR,
    DocumentType.PROPERTY: DocIntelType.PROPERTY_DOC,
    DocumentType.AFFIDAVIT: DocIntelType.PERSONAL_DOC,
    DocumentType.LEGAL_NOTICE: DocIntelType.BUSINESS_DOC,
    DocumentType.POLICY: DocIntelType.BUSINESS_DOC,
    DocumentType.TAX: DocIntelType.BUSINESS_DOC,
    DocumentType.CORPORATE: DocIntelType.BUSINESS_DOC,
    DocumentType.GENERAL: DocIntelType.UNKNOWN,
    DocumentType.UNKNOWN: DocIntelType.UNKNOWN,
    DocumentType.SCANNED_IMAGE: DocIntelType.UNKNOWN,
}

_MEDICAL_RE = re.compile(
    r"\b(medical\s+board|post[- ]?mortem|injury\s+report|medico[- ]?legal|"
    r"forensic\s+medicine|autopsy)\b",
    re.I,
)
_EVIDENCE_RE = re.compile(
    r"\b(forensic\s+report|chain of custody|exhibit\s+[a-z]\d*|"
    r"digital\s+evidence|seized\s+articles)\b",
    re.I,
)
_CASE_FILE_RE = re.compile(
    r"\b(petitioner|respondent|plaintiff|defendant|cause\s+title|"
    r"case\s+no\.?|diary\s+no\.?)\b",
    re.I,
)


def classify_document_intel(text: str, filename: str = "") -> DocIntelType:
    """Classify a single document for metadata and retrieval scoping."""
    body = (text or "")[:15000]
    if _MEDICAL_RE.search(body):
        return DocIntelType.MEDICAL_LEGAL
    if _EVIDENCE_RE.search(body):
        return DocIntelType.EVIDENCE
    if _CASE_FILE_RE.search(body) and not re.search(r"\bipc\s+section\b", body, re.I):
        return DocIntelType.CASE_FILE

    legacy = classify_document(text, filename)
    try:
        dt = DocumentType(legacy)
    except ValueError:
        dt = DocumentType.UNKNOWN
    return _LEGACY_MAP.get(dt, DocIntelType.UNKNOWN)


def document_intel_metadata(text: str, filename: str = "") -> Dict[str, Any]:
    """Metadata blob stored on index / matter records."""
    doc_type = classify_document_intel(text, filename)
    return {
        "doc_type": doc_type.value,
        "doc_intel_router": "v1",
        "filename": filename or "",
    }
