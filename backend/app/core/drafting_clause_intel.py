"""Clause intelligence — missing clauses, risk hints, KB/template references."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

CLAUSE_CHECKS = [
    ("confidentiality", r"\bconfidential|non[- ]disclosure|nda\b", "Consider a confidentiality clause."),
    ("indemnity", r"\bindemnif", "Indemnity clause may be required for commercial agreements."),
    ("termination", r"\bterminat|notice period", "Define termination rights and notice."),
    ("force_majeure", r"\bforce majeure", "Force majeure clause often expected in contracts."),
    ("arbitration", r"\barbitrat|dispute resolution", "Specify dispute resolution (arbitration/courts)."),
    ("jurisdiction", r"\bjurisdiction|governing law|courts at", "Governing law and jurisdiction should be explicit."),
    ("payment", r"\bpayment|consideration|fee", "Payment terms should be clear."),
    ("liability", r"\blimitation of liability|liable", "Liability cap or exclusion may be needed."),
    ("definitions", r"\bdefinitions\b|means\s", "Definitions section improves clarity."),
    ("execution", r"\bwitness|execut|signed", "Include execution / signature block."),
]

RISK_PATTERNS = [
    (r"\bunlimited liability\b", "high", "Unlimited liability exposure."),
    (r"\bperpetual\b", "medium", "Perpetual obligation — confirm intent."),
    (r"\bsole discretion\b", "medium", "Broad discretion — may favor one party."),
    (r"\bwaiver of .{0,40} rights\b", "high", "Rights waiver — review carefully."),
]


def analyze_document(content: str, *, document_type: str = "contract") -> Dict[str, Any]:
    text = (content or "").lower()
    missing: List[Dict[str, str]] = []
    for tag, pattern, hint in CLAUSE_CHECKS:
        if not re.search(pattern, text, re.I):
            missing.append({"clause": tag, "suggestion": hint})
    risks: List[Dict[str, str]] = []
    for pattern, level, msg in RISK_PATTERNS:
        if re.search(pattern, content or "", re.I):
            risks.append({"level": level, "message": msg})
    score = max(0, min(100, 100 - len(missing) * 8 - len(risks) * 12))
    return {
        "clause_risk_score": score,
        "missing_clauses": missing[:12],
        "risk_flags": risks[:10],
        "inconsistencies": _find_inconsistencies(content),
        "formatting_issues": _formatting_issues(content),
        "jurisdiction_notes": _jurisdiction_notes(content),
        "execution_notes": [] if re.search(r"\bexecut|signature|witness\b", content or "", re.I) else [
            {"message": "Add execution block with date and party signatures."}
        ],
    }


def legal_review_report(content: str, *, document_type: str = "contract") -> Dict[str, Any]:
    base = analyze_document(content, document_type=document_type)
    base["report_title"] = "Legal Review Report"
    base["summary"] = (
        f"Risk score {base['clause_risk_score']}/100. "
        f"{len(base['missing_clauses'])} suggested clauses, {len(base['risk_flags'])} risk flags."
    )
    return base


def enrich_with_clause_refs(
    user_id: str,
    content: str,
    jurisdiction: str,
) -> Tuple[str, List[str]]:
    """Append approved clause snippets from library (no hallucination)."""
    sources: List[str] = []
    try:
        from backend.app.core.clause_repo import list_clauses

        clauses = list_clauses(user_id)[:3]
        if not clauses:
            return content, sources
        appendix = "\n\n## Reference clauses (firm library)\n"
        for c in clauses:
            tag = c.get("clause_tag") or "clause"
            appendix += f"\n### {tag}\n{c.get('clause_text_content', '')[:800]}\n"
            sources.append(f"clause:{c.get('clause_id', tag)}")
        return content + appendix, sources
    except Exception:
        return content, sources


def _find_inconsistencies(content: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    if re.search(r"\b30 days\b", content, re.I) and re.search(r"\b60 days\b", content, re.I):
        issues.append({"message": "Conflicting notice periods (30 vs 60 days) — align terms."})
    return issues


def _formatting_issues(content: str) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    if len((content or "").strip()) < 200:
        issues.append({"message": "Document is very short — add substantive sections."})
    if not re.search(r"^#\s", content or "", re.M):
        issues.append({"message": "Consider adding markdown headings for structure."})
    return issues


def _jurisdiction_notes(content: str) -> List[Dict[str, str]]:
    if not re.search(r"\bindia|indian|section \d+|ipc|bns\b", content or "", re.I):
        return [{"message": "Jurisdiction / Indian law reference not detected — confirm governing law."}]
    return []


def clause_recommendations_v3(
    user_id: str,
    content: str,
    *,
    document_type: str = "contract",
) -> Dict[str, Any]:
    """Recommend clauses from firm library only — never hallucinate."""
    from backend.app.core.drafting_v3 import html_to_plain

    text = html_to_plain(content or "")
    analysis = analyze_document(text, document_type=document_type)
    recommendations: List[Dict[str, Any]] = []
    risky: List[Dict[str, Any]] = []
    alternatives: List[Dict[str, Any]] = []

    try:
        from backend.app.core.clause_repo import list_clauses

        library = list_clauses(user_id) if user_id else list_clauses("")
    except Exception:
        library = []

    missing_tags = {m["clause"]: m["suggestion"] for m in analysis.get("missing_clauses") or []}
    for tag, hint in missing_tags.items():
        match = next(
            (c for c in library if tag.replace("_", " ") in (c.get("clause_tag") or "").lower()),
            None,
        )
        if match:
            recommendations.append(
                {
                    "clause": tag,
                    "action": "insert",
                    "source": f"clause:{match.get('clause_id', tag)}",
                    "text": (match.get("clause_text_content") or "")[:1200],
                    "explanation": hint,
                }
            )
        else:
            recommendations.append(
                {
                    "clause": tag,
                    "action": "draft_needed",
                    "source": "analysis",
                    "text": "",
                    "explanation": hint,
                }
            )

    for flag in analysis.get("risk_flags") or []:
        risky.append({**flag, "suggestion": "Review and consider limiting language."})
        alt = next(
            (c for c in library if "liability" in (c.get("clause_tag") or "").lower()),
            None,
        )
        if alt:
            alternatives.append(
                {
                    "for_risk": flag.get("message"),
                    "source": f"clause:{alt.get('clause_id')}",
                    "alternative_text": (alt.get("clause_text_content") or "")[:800],
                }
            )

    weak = []
    if re.search(r"\bas soon as practicable\b", text, re.I):
        weak.append(
            {
                "phrase": "as soon as practicable",
                "suggestion": "Specify a definite period (e.g. 15 business days).",
            }
        )
    if re.search(r"\breasonable efforts\b", text, re.I):
        weak.append(
            {
                "phrase": "reasonable efforts",
                "suggestion": "Define objective standards for 'reasonable efforts'.",
            }
        )

    return {
        "recommendations": recommendations,
        "risky_clauses": risky,
        "weak_phrases": weak,
        "alternatives": alternatives,
        "clause_risk_score": analysis.get("clause_risk_score"),
        "sources": [r["source"] for r in recommendations if r.get("source", "").startswith("clause:")],
    }
