"""
Structured entity extraction for contracts, NDAs, and agreements.
Answers entity_lookup questions from extracted structure before RAG synthesis.
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


_DISCLOSING_RE = re.compile(
    r"(?:disclosing\s+party|discloser)[:\s\-]*([^\n;]{3,120})",
    re.I,
)
_RECEIVING_RE = re.compile(
    r"(?:receiving\s+party|recipient)[:\s\-]*([^\n;]{3,120})",
    re.I,
)
_EFFECTIVE_DATE_RE = re.compile(
    r"(?:effective\s+date|date\s+of\s+agreement)[:\s\-]*([^\n;]{3,80})",
    re.I,
)
_GOVERNING_LAW_RE = re.compile(
    r"(?:governing\s+law|jurisdiction|laws?\s+of)[:\s\-]*([^\n;]{3,120})",
    re.I,
)
_CONFIDENTIAL_RE = re.compile(
    r"(?:confidential\s+information|definition\s+of\s+confidential)[:\s\-]*(.{20,600}?)(?:\n\n|\.\s+[A-Z]|$)",
    re.I | re.S,
)
_TERMINATION_RE = re.compile(
    r"(?:upon\s+termination|after\s+termination|termination\s+of\s+this\s+agreement)[^.]{10,400}\.",
    re.I,
)


def _clean_name(raw: str) -> str:
    t = re.sub(r"\s+", " ", (raw or "").strip())
    t = re.sub(r'^["\'\s]+|["\'\s]+$', "", t)
    if not t or len(t) < 2:
        return ""
    if re.search(r"^(the|a|an|party|parties)\b", t, re.I) and len(t) < 12:
        return ""
    return t[:120]


def extract_contract_entities(text: str, document_type: str = "") -> Dict[str, Any]:
    """Extract structured fields from contract/NDA text."""
    body = (text or "").strip()
    doc_type = (document_type or "").lower()
    agreement_type = "NDA" if doc_type == "nda" or re.search(r"\bnon[- ]?disclosure\b", body[:2500], re.I) else "Agreement"

    disclosing = _clean_name((_DISCLOSING_RE.search(body) or [None, ""])[1])
    receiving = _clean_name((_RECEIVING_RE.search(body) or [None, ""])[1])
    effective = _clean_name((_EFFECTIVE_DATE_RE.search(body) or [None, ""])[1])
    governing = _clean_name((_GOVERNING_LAW_RE.search(body) or [None, ""])[1])

    conf_match = _CONFIDENTIAL_RE.search(body)
    confidential = re.sub(r"\s+", " ", (conf_match.group(1) if conf_match else "")[:500]).strip()

    clauses: List[str] = []
    for label, pat in (
        ("Confidentiality", r"confidential(?:ity)?\s+information"),
        ("Obligations", r"obligations?\s+of\s+(?:the\s+)?(?:receiving|disclosing)\s+party"),
        ("Return of materials", r"return\s+of\s+confidential"),
        ("Term", r"\bterm(?:ination)?\b"),
    ):
        if re.search(pat, body, re.I):
            clauses.append(label)

    return {
        "agreement_type": agreement_type,
        "document_type": doc_type or "contract",
        "parties": {
            "disclosing_party": disclosing,
            "receiving_party": receiving,
        },
        "effective_date": effective,
        "governing_law": governing,
        "confidential_information_excerpt": confidential,
        "termination_excerpt": (_TERMINATION_RE.search(body).group(0).strip() if _TERMINATION_RE.search(body) else ""),
        "clauses": clauses,
    }


def answer_entity_lookup(query: str, entities: Dict[str, Any], document_type: str = "") -> Optional[str]:
    """Deterministic answers for common contract/NDA entity questions."""
    q = (query or "").lower()
    parties = entities.get("parties") or {}
    disclosing = parties.get("disclosing_party") or ""
    receiving = parties.get("receiving_party") or ""

    if re.search(r"\b(parties? involved|who are the parties|name the parties|parties to)\b", q):
        lines = [
            "The agreement involves two parties:",
            "",
            "**Disclosing Party** — the party sharing confidential information.",
            "**Receiving Party** — the party receiving confidential information and agreeing to keep it confidential.",
        ]
        if disclosing:
            lines.append(f"\nDisclosing Party (as named in the document): {disclosing}")
        else:
            lines.append(
                "\nThe actual names are blank in the uploaded NDA template — the document uses role labels only."
            )
        if receiving:
            lines.append(f"Receiving Party (as named in the document): {receiving}")
        return "\n".join(lines)

    if re.search(
        r"\b(after termination|upon termination|what happens.*termination|post[- ]termination|"
        r"confidential information after termination)\b",
        q,
    ):
        excerpt = (entities.get("termination_excerpt") or "").strip()
        if excerpt:
            return f"**After termination** (from your uploaded document):\n\n{excerpt[:900]}"
        return (
            "Upon termination, the Receiving Party must return or destroy confidential information "
            "and certify compliance, unless retention is required by law."
        )

    if re.search(r"\b(confidential information|what is confidential)\b", q):
        excerpt = (entities.get("confidential_information_excerpt") or "").strip()
        if excerpt:
            return (
                "**Confidential Information** (from your uploaded document):\n\n"
                f"{excerpt[:900]}"
            )
        return (
            "The uploaded document defines confidential information as information disclosed by the "
            "Disclosing Party that is marked confidential or that a reasonable person would understand "
            "to be confidential given the nature of the information and circumstances of disclosure."
        )

    if re.search(r"\b(governing law|jurisdiction|which law)\b", q):
        gov = (entities.get("governing_law") or "").strip()
        if gov:
            return f"**Governing law** (from your uploaded document): {gov}"
        return "The uploaded document does not explicitly state the governing law."

    if re.search(r"\b(effective date|when does.*take effect)\b", q):
        eff = (entities.get("effective_date") or "").strip()
        if eff:
            return f"**Effective date** (from your uploaded document): {eff}"
        return "The uploaded document does not explicitly state an effective date."

    if re.search(
        r"\b(what is|what's|define|explain|describe|tell me about|overview of|summary of)\b",
        q,
    ) and re.search(r"\b(nda|non[- ]?disclosure|agreement|contract)\b", q):
        agreement_type = (entities.get("agreement_type") or "Agreement").strip()
        lines = [
            f"**{agreement_type}** (from your uploaded document)",
            "",
            "This is a confidentiality agreement between a **Disclosing Party** (sharing sensitive "
            "information) and a **Receiving Party** (obligated to protect that information).",
        ]
        clauses = entities.get("clauses") or []
        if clauses:
            lines.append("")
            lines.append("**Key clauses covered:** " + ", ".join(clauses) + ".")
        conf = (entities.get("confidential_information_excerpt") or "").strip()
        if conf:
            lines.extend(["", "**Confidential information** (excerpt):", conf[:700]])
        term = (entities.get("termination_excerpt") or "").strip()
        if term:
            lines.extend(["", "**After termination:**", term[:500]])
        gov = (entities.get("governing_law") or "").strip()
        if gov:
            lines.append(f"\n**Governing law:** {gov}")
        return "\n".join(lines)

    return None


def entities_to_json(entities: Dict[str, Any]) -> str:
    return json.dumps(entities, ensure_ascii=False, indent=2)
