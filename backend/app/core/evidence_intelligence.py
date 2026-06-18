"""
Evidence Intelligence Center — OCR analysis, classification, entities, timeline,
statute finder, privilege detection, contradiction analysis, court-order matching.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.ediscovery_service import triage_document

# --- Classification categories ---
_EVIDENCE_CATEGORIES: List[Tuple[str, re.Pattern, str]] = [
    ("FINANCIAL", re.compile(r"\b(invoice|payment|ledger|bank|transaction|gst|tds|audit|balance)\b", re.I), "Financial document"),
    ("CONTRACT", re.compile(r"\b(agreement|contract|indemnity|clause|party|consideration|terminate)\b", re.I), "Contract or agreement"),
    ("COMMUNICATION", re.compile(r"\b(email|whatsapp|message|dear|regards|forwarded|chat)\b", re.I), "Communication record"),
    ("INVOICE", re.compile(r"\b(invoice|bill no|tax invoice|amount due|payment terms)\b", re.I), "Invoice or billing"),
    ("COURT_ORDER", re.compile(r"\b(order dated|hon'ble|court|judgment|petition|wp\(|crl\.|bench)\b", re.I), "Court order or pleading"),
    ("MEDICAL", re.compile(r"\b(patient|diagnosis|hospital|prescription|medical|doctor)\b", re.I), "Medical record"),
    ("IDENTITY", re.compile(r"\b(aadhaar|pan card|passport|voter id|driving licence|kyc)\b", re.I), "Identity document"),
    ("EVIDENCE", re.compile(r"\b(witness|affidavit|exhibit|forensic|seized|panchnama)\b", re.I), "Evidentiary material"),
]

# --- Risk indicators ---
_RISK_RULES: List[Tuple[str, re.Pattern, str, float]] = [
    ("FRAUD", re.compile(r"\b(fraud|forgery|fake|misappropriat|siphoned|embezzl)\b", re.I), "Potential fraud indicator", 0.88),
    ("BRIBERY", re.compile(r"\b(bribe|kickback|under the table|envelope|undisclosed benefit)\b", re.I), "Bribery or undue influence", 0.9),
    ("MONEY_TRAIL", re.compile(r"\b(wire transfer|cash withdrawal|shell company|offshore|layering)\b", re.I), "Suspicious money movement", 0.85),
    ("CONSPIRACY", re.compile(r"\b(conspir|plot|co-?ordinated|in concert|do not tell anyone)\b", re.I), "Conspiracy indicator", 0.87),
    ("HARASSMENT", re.compile(r"\b(harass|stalk|unwanted|hostile work|sexual)\b", re.I), "Harassment indicator", 0.82),
    ("THREAT", re.compile(r"\b(threat|kill|harm|retaliat|intimidat|consequences)\b", re.I), "Threat or intimidation", 0.86),
    ("CONTRACT_BREACH", re.compile(r"\b(breach|default|failed to deliver|non[\s-]?performance)\b", re.I), "Contract breach indicator", 0.75),
]

# --- Privilege patterns ---
_PRIVILEGE_RULES: List[Tuple[str, re.Pattern, str]] = [
    ("ATTORNEY_CLIENT", re.compile(r"\b(attorney[\s-]?client|legal advice|privileged|confidential legal)\b", re.I), "Possible attorney-client communication"),
    ("WORK_PRODUCT", re.compile(r"\b(litigation strategy|work product|trial prep|without prejudice)\b", re.I), "Possible work-product material"),
    ("CONFIDENTIAL", re.compile(r"\b(strictly confidential|eyes only|not for production)\b", re.I), "Marked confidential"),
]

# --- Statute mapping (evidence text → BNS/BNSS) ---
_STATUTE_RULES: List[Tuple[str, re.Pattern, List[Dict[str, str]]]] = [
    (
        "Cheating",
        re.compile(r"\b(cheat|cheating|deceiv|fraudulent inducement|vendor.*money)\b", re.I),
        [{"offence": "Cheating", "section": "BNS 318", "act": "Bharatiya Nyaya Sanhita"}],
    ),
    (
        "Criminal Breach of Trust",
        re.compile(r"\b(breach of trust|entrust|misappropriat|embezzl)\b", re.I),
        [{"offence": "Criminal Breach of Trust", "section": "BNS 316", "act": "Bharatiya Nyaya Sanhita"}],
    ),
    (
        "Forgery",
        re.compile(r"\b(forg|fabricat|false document|counterfeit)\b", re.I),
        [{"offence": "Forgery", "section": "BNS 336", "act": "Bharatiya Nyaya Sanhita"}],
    ),
    (
        "Criminal Conspiracy",
        re.compile(r"\b(conspir|agreement to commit|common intention)\b", re.I),
        [{"offence": "Criminal Conspiracy", "section": "BNS 61", "act": "Bharatiya Nyaya Sanhita"}],
    ),
    (
        "Breach of Contract (civil)",
        re.compile(r"\b(breach of contract|damages|liquidated|specific relief)\b", re.I),
        [{"offence": "Breach of Contract — damages", "section": "Section 73", "act": "Indian Contract Act 1872"}],
    ),
    (
        "Bail / arrest procedure",
        re.compile(r"\b(bail|arrest|custody|remand)\b", re.I),
        [{"offence": "Bail provisions", "section": "BNSS 480+", "act": "Bharatiya Nagarik Suraksha Sanhita"}],
    ),
]

# --- Entity regex ---
_RE_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
_RE_PHONE = re.compile(r"(?:\+91[\s-]?)?[6-9]\d{9}\b|(?:\+91[\s-]?)?\d{2,4}[\s-]?\d{6,8}")
_RE_IFSC = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_RE_ACCOUNT = re.compile(r"\b(?:a/c|account)[\s#:.-]*(\d{9,18})\b", re.I)
_RE_CASE_NO = re.compile(
    r"\b(?:WP|CRL|CRLP|SLP|FAO|RSA|CR|ARB|PIL|MAT|MACA|COM|CO|CP|CS|ITA|WPA|TRP|"
    r"CMA|CRP|CRMP|MC|RC|RP|SA|TR|UA|WA|WP\(C\)|WP\(Crl\)|Crl\.?\s*Rev\.?|"
    r"Crl\.?\s*MP\.?)\s*[\(\[]?\s*\d+[\s/\-]*\d{2,4}\s*[\)\]]?\b",
    re.I,
)
_RE_DATE = re.compile(
    r"\b(\d{1,2}[\s/.-](?:\d{1,2}|[A-Za-z]{3,9})[\s/.-]\d{2,4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})\b",
    re.I,
)
_RE_ORG = re.compile(
    r"\b([A-Z][A-Za-z0-9&\s]{2,40}(?:Pvt\.?\s*Ltd\.?|Private Limited|LLP|Ltd\.?|Limited|Inc\.?|Corp\.?|Company|Enterprises|Industries))\b"
)
_RE_PERSON = re.compile(
    r"\b(?:Mr\.|Mrs\.|Ms\.|Dr\.|Shri|Smt\.|Adv\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b"
)
_RE_LOCATION = re.compile(
    r"\b(Mumbai|Delhi|New Delhi|Bengaluru|Bangalore|Chennai|Kolkata|Hyderabad|Pune|Ahmedabad|Jaipur|Lucknow|Noida|Gurugram|Gurgaon|Chandigarh|Kochi|Surat|Indore|Nagpur|Patna|Bhopal|Thane|Navi Mumbai)\b"
)


def _parse_date(raw: str) -> Optional[str]:
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y", "%d/%m/%y"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def classify_evidence(text: str) -> Dict[str, Any]:
    """AI-style document classification from content."""
    content = (text or "").strip()
    categories: List[str] = []
    labels: List[str] = []
    for code, pat, label in _EVIDENCE_CATEGORIES:
        if pat.search(content):
            categories.append(code)
            labels.append(label)
    if not categories:
        categories = ["GENERAL"]
        labels = ["General document — manual review recommended"]
    return {
        "primary_category": categories[0],
        "categories": categories[:5],
        "category_labels": labels[:5],
    }


def detect_risks(text: str) -> List[Dict[str, Any]]:
    content = text or ""
    risks: List[Dict[str, Any]] = []
    for code, pat, desc, weight in _RISK_RULES:
        if pat.search(content):
            risks.append({"code": code, "description": desc, "confidence": weight})
    return sorted(risks, key=lambda x: -x["confidence"])


def detect_privilege(text: str) -> Dict[str, Any]:
    content = text or ""
    flags: List[Dict[str, str]] = []
    for code, pat, desc in _PRIVILEGE_RULES:
        if pat.search(content):
            flags.append({"type": code, "description": desc})
    return {
        "privileged": bool(flags),
        "flags": flags,
        "recommendation": "Hold for privilege review before production." if flags else "No privilege markers detected.",
    }


def extract_entities(text: str) -> Dict[str, List[str]]:
    content = text or ""
    people = list(dict.fromkeys(m.group(1).strip() for m in _RE_PERSON.finditer(content)))[:20]
    orgs = list(dict.fromkeys(m.group(1).strip() for m in _RE_ORG.finditer(content)))[:20]
    locations = list(dict.fromkeys(m.group(1) for m in _RE_LOCATION.finditer(content)))[:15]
    emails = list(dict.fromkeys(_RE_EMAIL.findall(content)))[:20]
    phones = list(dict.fromkeys(_RE_PHONE.findall(content)))[:15]
    accounts = list(dict.fromkeys(m.group(1) for m in _RE_ACCOUNT.finditer(content)))[:10]
    ifsc = list(dict.fromkeys(_RE_IFSC.findall(content)))[:10]
    case_numbers = list(dict.fromkeys(m.group(0).strip() for m in _RE_CASE_NO.finditer(content)))[:10]
    dates = list(dict.fromkeys(m.group(1) for m in _RE_DATE.finditer(content)))[:30]
    return {
        "people": people,
        "organizations": orgs,
        "locations": locations,
        "emails": emails,
        "phones": phones,
        "bank_accounts": accounts,
        "ifsc_codes": ifsc,
        "case_numbers": case_numbers,
        "dates": dates,
    }


def build_timeline(text: str, *, source: str = "") -> List[Dict[str, Any]]:
    """Chronological events extracted from dated sentences."""
    content = (text or "").strip()
    if not content:
        return []
    sentences = re.split(r"(?<=[.!?])\s+|\n+", content)
    events: List[Dict[str, Any]] = []
    for sent in sentences:
        if len(sent.strip()) < 12:
            continue
        for m in _RE_DATE.finditer(sent):
            iso = _parse_date(m.group(1))
            events.append(
                {
                    "date_raw": m.group(1),
                    "date_iso": iso or m.group(1),
                    "event": sent.strip()[:280],
                    "source": source,
                }
            )
    events.sort(key=lambda e: (e.get("date_iso") or "9999", e.get("date_raw", "")))
    return events[:40]


def identify_statutes(text: str) -> List[Dict[str, str]]:
    content = text or ""
    found: List[Dict[str, str]] = []
    seen: set = set()
    for _label, pat, statutes in _STATUTE_RULES:
        if pat.search(content):
            for s in statutes:
                key = f"{s['section']}|{s['offence']}"
                if key not in seen:
                    seen.add(key)
                    found.append({**s, "relevance": "high"})
    return found


def evidence_strength(
    text: str,
    *,
    user_id: str = "",
    matter_id: str = "",
    risks: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Legal relevance score combining triage + risk signals."""
    triage = triage_document(text, user_id=user_id, matter_id=matter_id)
    base = float(triage.get("relevance_score") or 0.5)
    risk_list = risks or detect_risks(text)
    if risk_list:
        base = min(0.98, base + 0.08 * min(len(risk_list), 3))
    pct = int(round(base * 100))
    if pct >= 80:
        label = "Highly Relevant"
    elif pct >= 60:
        label = "Moderately Relevant"
    elif pct >= 40:
        label = "Low Relevance"
    else:
        label = "Minimal Relevance"
    return {
        "score": round(base, 3),
        "percent": pct,
        "label": label,
        "classification": triage.get("classification"),
        "tags": triage.get("tags") or [],
        "rationale": triage.get("rationale"),
    }


def analyze_evidence(
    text: str,
    *,
    user_id: str = "",
    matter_id: str = "",
    source: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full evidence intelligence pipeline for one document."""
    content = (text or "").strip()
    meta = metadata or {}
    classification = classify_evidence(content)
    risks = detect_risks(content)
    privilege = detect_privilege(content)
    entities = extract_entities(content)
    timeline = build_timeline(content, source=source or meta.get("filename", ""))
    statutes = identify_statutes(content)
    strength = evidence_strength(content, user_id=user_id, matter_id=matter_id, risks=risks)
    return {
        "source": source,
        "metadata": meta,
        "classification": classification,
        "evidence_strength": strength,
        "risks": risks,
        "privilege": privilege,
        "entities": entities,
        "timeline": timeline,
        "statutes": statutes,
        "text_length": len(content),
        "excerpt": content[:600],
    }


def detect_contradictions(text_a: str, text_b: str) -> Dict[str, Any]:
    """Compare two witness statements / documents for conflicting claims."""
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if len(a) < 30 or len(b) < 30:
        return {"contradictions": [], "summary": "Insufficient text for comparison."}

    contra: List[Dict[str, str]] = []

    neg_a = re.search(r"\b(not aware|no knowledge|did not|never|denied|refused)\b", a, re.I)
    neg_b = re.search(r"\b(not aware|no knowledge|did not|never|denied|refused)\b", b, re.I)
    pos_a = re.search(r"\b(approved|authorized|signed|agreed|confirmed|was present|knew)\b", a, re.I)
    pos_b = re.search(r"\b(approved|authorized|signed|agreed|confirmed|was present|knew)\b", b, re.I)
    if neg_a and pos_b:
        contra.append(
            {
                "type": "awareness_conflict",
                "document_a": neg_a.group(0),
                "document_b": pos_b.group(0),
                "note": "Document A denies awareness while Document B asserts affirmative action.",
            }
        )
    if pos_a and neg_b:
        contra.append(
            {
                "type": "awareness_conflict",
                "document_a": pos_a.group(0),
                "document_b": neg_b.group(0),
                "note": "Document A asserts action while Document B denies knowledge.",
            }
        )

    date_a = set(_RE_DATE.findall(a))
    date_b = set(_RE_DATE.findall(b))
    for da in date_a:
        for db in date_b:
            if da != db and abs(len(da) - len(db)) < 4:
                contra.append(
                    {
                        "type": "date_conflict",
                        "document_a": da,
                        "document_b": db,
                        "note": "Conflicting dates mentioned across documents.",
                    }
                )

    amount_a = re.findall(r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d{2})?", a, re.I)
    amount_b = re.findall(r"(?:₹|Rs\.?|INR)\s*[\d,]+(?:\.\d{2})?", b, re.I)
    if amount_a and amount_b and amount_a[0] != amount_b[0]:
        contra.append(
            {
                "type": "amount_conflict",
                "document_a": amount_a[0],
                "document_b": amount_b[0],
                "note": "Different monetary amounts cited.",
            }
        )

    shared_people = set(extract_entities(a)["people"]) & set(extract_entities(b)["people"])
    for person in list(shared_people)[:5]:
        pat = re.compile(re.escape(person), re.I)
        if pat.search(a) and pat.search(b):
            ctx_a = next((s.strip() for s in re.split(r"[.!?]", a) if pat.search(s)), "")
            ctx_b = next((s.strip() for s in re.split(r"[.!?]", b) if pat.search(s)), "")
            if ctx_a and ctx_b and ctx_a[:80] != ctx_b[:80]:
                contra.append(
                    {
                        "type": "witness_conflict",
                        "subject": person,
                        "document_a": ctx_a[:200],
                        "document_b": ctx_b[:200],
                        "note": f"Conflicting statements regarding {person}.",
                    }
                )

    summary = (
        f"Found {len(contra)} potential contradiction(s)."
        if contra
        else "No major contradictions detected — review manually for nuance."
    )
    return {"contradictions": contra[:15], "summary": summary, "shared_entities": list(shared_people)}


def match_court_orders(
    user_id: str,
    text: str,
    *,
    matter_id: str = "",
    limit: int = 8,
) -> List[Dict[str, Any]]:
    """Search firm court orders / KB for similar precedents."""
    content = (text or "").strip()
    if len(content) < 40:
        return []
    query = content[:500]
    results: List[Dict[str, Any]] = []

    try:
        from backend.app.core.enterprise_workspace import search_court_orders

        for o in search_court_orders(user_id, query, matter_id=matter_id, limit=limit):
            results.append(
                {
                    "order_id": o.get("order_id"),
                    "case_number": o.get("case_number"),
                    "court": o.get("court"),
                    "judge": o.get("judge"),
                    "summary": (o.get("summary") or "")[:240],
                    "source": "court_orders",
                }
            )
    except Exception:
        pass

    if len(results) < limit:
        try:
            from backend.app.core.enterprise_workspace import search_knowledge

            for k in search_knowledge(user_id, query, limit=limit):
                if k.get("entry_type") in ("court_order", "precedent", "judgment", "order"):
                    results.append(
                        {
                            "entry_id": k.get("entry_id"),
                            "title": k.get("title"),
                            "court": k.get("court"),
                            "snippet": k.get("snippet"),
                            "source": "knowledge_base",
                        }
                    )
        except Exception:
            pass

    if not results:
        tokens = [t for t in re.findall(r"\w{4,}", query.lower()) if t not in {"that", "this", "with", "from", "have", "been"}][:8]
        if tokens:
            results.append(
                {
                    "title": "Knowledge Base search suggested",
                    "snippet": f"Search your KB for: {' '.join(tokens[:5])}",
                    "source": "suggestion",
                    "search_terms": tokens[:5],
                }
            )
    return results[:limit]


def merge_timelines(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge timeline events from multiple evidence items."""
    merged: List[Dict[str, Any]] = []
    for item in items:
        for ev in item.get("timeline") or []:
            merged.append({**ev, "evidence_source": item.get("source_identifier") or item.get("source", "")})
    merged.sort(key=lambda e: (e.get("date_iso") or "9999", e.get("date_raw", "")))
    return merged[:80]
