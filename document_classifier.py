"""
Classify uploaded legal documents for retrieval routing and prompt adaptation.
"""
from __future__ import annotations

import re
from enum import Enum
from pathlib import Path
from typing import Optional


class DocumentType(str, Enum):
    NDA = "nda"
    CONTRACT = "contract"
    AGREEMENT = "agreement"
    LEGAL_NOTICE = "legal_notice"
    CRIMINAL_LAW = "criminal_law"
    CONSTITUTIONAL = "constitutional"
    COURT_JUDGMENT = "court_judgment"
    POLICY = "policy_document"
    FIR = "fir"
    AFFIDAVIT = "affidavit"
    PROPERTY = "property"
    TAX = "tax"
    CORPORATE = "corporate"
    GENERAL = "general"
    SCANNED_IMAGE = "scanned_image"
    UNKNOWN = "unknown"


_NDA_RE = re.compile(
    r"\b(non[- ]?disclosure|nda|confidential(?:ity)?\s+information|disclosing\s+party|receiving\s+party)\b",
    re.I,
)
_CONTRACT_RE = re.compile(
    r"\b(breach of contract|indemnity|consideration|party of the first|party of the second|"
    r"terms and conditions|whereas|hereby agrees)\b",
    re.I,
)
_NOTICE_RE = re.compile(r"\b(legal notice|demand notice|cease and desist|show cause)\b", re.I)
_CRIMINAL_RE = re.compile(
    r"\b(ipc|bns|bnss|bsa|crpc|indian penal code|bharatiya nyaya|criminal conspiracy|"
    r"offence|offense|punishment|bail|anticipatory bail)\b",
    re.I,
)
_JUDGMENT_RE = re.compile(
    r"\b(hon'?ble|judgment|judgement|petitioner|respondent|versus|v\.|court held|"
    r"learned counsel|impugned order)\b",
    re.I,
)
_FIR_RE = re.compile(r"\b(first information report|\bfir\b|police station|complainant)\b", re.I)
_AFFIDAVIT_RE = re.compile(r"\b(affidavit|solemnly affirm|deponent|sworn)\b", re.I)
_POLICY_RE = re.compile(r"\b(policy|privacy policy|terms of service|employee handbook)\b", re.I)
_CONSTITUTION_RE = re.compile(
    r"\b(constitution of india|fundamental rights?|directive principles|"
    r"preamble|article\s+\d{1,3}[a-z]?|part\s+iii|part\s+iv)\b",
    re.I,
)
_PROPERTY_RE = re.compile(
    r"\b(immovable property|sale deed|title deed|registration act|"
    r"transfer of property|easement|mortgage|lease deed)\b",
    re.I,
)
_TAX_RE = re.compile(
    r"\b(income tax|gst|cgst|igst|customs act|tax audit|assessment year)\b",
    re.I,
)
_CORPORATE_RE = re.compile(
    r"\b(companies act|board of directors|shareholder|moa|aoa|"
    r"corporate governance|sebi|roc filing)\b",
    re.I,
)
_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def classify_document(text: str, filename: str = "") -> str:
    """Return DocumentType value for chunk metadata and routing."""
    body = (text or "")[:12000]
    name = (filename or "").lower()
    ext = Path(name).suffix.lower()

    if _CONSTITUTION_RE.search(body) or any(
        k in name for k in ("constitution", "fundamental", "constitutional")
    ):
        return DocumentType.CONSTITUTIONAL.value
    if _NDA_RE.search(body) or "nda" in name or "non-disclosure" in name or "non disclosure" in name:
        return DocumentType.NDA.value
    if _FIR_RE.search(body) or "fir" in name:
        return DocumentType.FIR.value
    if _AFFIDAVIT_RE.search(body) or "affidavit" in name:
        return DocumentType.AFFIDAVIT.value
    if _NOTICE_RE.search(body) or "notice" in name:
        return DocumentType.LEGAL_NOTICE.value
    if _JUDGMENT_RE.search(body) or "judgment" in name or "judgement" in name:
        return DocumentType.COURT_JUDGMENT.value
    if _CRIMINAL_RE.search(body) or any(
        k in name for k in ("ipc", "bns", "criminal", "penal", "bnss", "crpc")
    ):
        return DocumentType.CRIMINAL_LAW.value
    if _CONTRACT_RE.search(body) or any(k in name for k in ("contract", "agreement", "mou")):
        if "nda" in name or _NDA_RE.search(body[:2000]):
            return DocumentType.NDA.value
        return DocumentType.CONTRACT.value
    if _PROPERTY_RE.search(body) or "property" in name or "deed" in name:
        return DocumentType.PROPERTY.value
    if _TAX_RE.search(body) or "tax" in name or "gst" in name:
        return DocumentType.TAX.value
    if _CORPORATE_RE.search(body) or "companies" in name:
        return DocumentType.CORPORATE.value
    if _POLICY_RE.search(body):
        return DocumentType.POLICY.value
    if ext in _IMAGE_EXT:
        if _NDA_RE.search(body) or "agreement" in body.lower()[:1500]:
            return DocumentType.NDA.value
        return DocumentType.SCANNED_IMAGE.value
    if "agreement" in name:
        return DocumentType.AGREEMENT.value
    if len(body) > 500:
        return DocumentType.GENERAL.value
    return DocumentType.UNKNOWN.value


def is_contract_family(doc_type: Optional[str]) -> bool:
    return (doc_type or "") in {
        DocumentType.NDA.value,
        DocumentType.CONTRACT.value,
        DocumentType.AGREEMENT.value,
    }


def is_criminal_law_doc(doc_type: Optional[str]) -> bool:
    return (doc_type or "") == DocumentType.CRIMINAL_LAW.value


_CONTRACT_TOPIC_RE = re.compile(
    r"\b(?:nda|non[- ]?disclosure|confidential(?:ity)?|disclosing\s+party|receiving\s+party|"
    r"breach\s+of\s+contract|sample\s+(?:nda|non[- ]?disclosure|agreement|contract)|"
    r"sample\s+.*\s+agreement|(?:employment|service|license|subscription)\s+agreement)\b",
    re.I,
)


def is_contract_topic_query(query: str) -> bool:
    """True when the user asks about a contract/NDA topic (not a statute section)."""
    q = (query or "").strip()
    if not q:
        return False
    if _CONTRACT_TOPIC_RE.search(q):
        return True
    dt = document_type_for_query(q)
    return bool(dt and is_contract_family(dt))


def document_type_for_query(query: str) -> Optional[str]:
    """Infer which document family the query targets."""
    q = (query or "").lower()
    if re.search(
        r"\b(parties?|disclosing party|receiving party|confidential|nda|non[- ]?disclosure|"
        r"termination|governing law|effective date|breach of contract|remedies|"
        r"sample\s+(?:nda|non[- ]?disclosure|agreement|contract)|sample\s+.*\s+agreement)\b",
        q,
    ):
        return DocumentType.NDA.value if "nda" in q or "confidential" in q or "non-disclosure" in q else DocumentType.CONTRACT.value
    if re.search(
        r"\b(constitutional rights?|five constitutional|name\s+(?:five|5)\s+.*rights|article\s+\d+|"
        r"fundamental rights?|right to equality|right to freedom|right to life|right to religion|"
        r"right against exploitation|equality|liberty)\b",
        q,
    ):
        return "constitutional"
    if re.search(r"\b(nirbhaya|kesavananda|judgment|judgement|petitioner|respondent|court)\b", q):
        return DocumentType.COURT_JUDGMENT.value
    if re.search(r"\b(fir|complainant|police station)\b", q):
        return DocumentType.FIR.value
    if re.search(r"\b(affidavit|deponent|sworn)\b", q):
        return DocumentType.AFFIDAVIT.value
    if re.search(r"\b(property|sale deed|lease|mortgage|title)\b", q):
        return DocumentType.PROPERTY.value
    if re.search(r"\b(income tax|gst|tax)\b", q):
        return DocumentType.TAX.value
    if re.search(r"\b(companies act|director|shareholder|corporate)\b", q):
        return DocumentType.CORPORATE.value
    if re.search(r"\b(policy|privacy|terms of service)\b", q):
        return DocumentType.POLICY.value
    if re.search(r"\b(ipc|bns|crpc|bnss|bsa|criminal|offence|offense|bail|murder|section\s+\d)\b", q):
        return DocumentType.CRIMINAL_LAW.value
    return None
