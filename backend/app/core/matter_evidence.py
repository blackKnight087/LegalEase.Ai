"""Matter evidence registry and extraction."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import table_columns_set
from backend.app.core.matter_repo import get_matter, list_matter_documents
from backend.app.core.practice_schema import ensure_practice_schema

logger = logging.getLogger(__name__)

_EVIDENCE_PATTERNS: Tuple[Tuple[str, str, str, str], ...] = (
    (r"\bCCTV\b[^.\n]{0,120}", "cctv", "CCTV footage", "high"),
    (r"\bWhatsApp\b[^.\n]{0,120}", "digital", "WhatsApp chats", "high"),
    (r"\b(?:call\s+records?|phone\s+records?)\b[^.\n]{0,100}", "digital", "Call logs", "medium"),
    (r"\b(?:email|e-mail)\b[^.\n]{0,100}", "digital", "Email correspondence", "medium"),
    (
        r"\b(?:fingerprint|forensic)\s+(?:report|analysis)?[^.\n]{0,140}",
        "forensic",
        "Fingerprint / forensic report",
        "critical",
    ),
    (r"\bpostmortem\b[^.\n]{0,120}", "medical", "Postmortem report", "critical"),
    (r"\b(?:bank|UPI|financial)\s+(?:transfer|statement|record)[^.\n]{0,120}", "financial", "Bank / financial records", "high"),
    (r"\bblood[- ]stained\b[^.\n]{0,100}", "physical", "Blood-stained evidence", "high"),
    (r"\b(?:photograph|photo|CCTV footage)\b[^.\n]{0,100}", "physical", "Photograph / image", "medium"),
    (r"\b(?:audio|voice)\s+recording\b[^.\n]{0,100}", "digital", "Audio recording", "medium"),
    (r"\b(?:contract|agreement)\b[^.\n]{0,100}", "contract", "Contract / agreement", "medium"),
    (r"\b(?:signature|signed)\b[^.\n]{0,100}", "document", "Signature evidence", "medium"),
    (r"\bmedical\s+report\b[^.\n]{0,120}", "medical", "Medical report", "high"),
)

_FILENAME_EVIDENCE_HINTS = (
    ("whatsapp", "digital", "WhatsApp Chat"),
    ("chat", "digital", "Chat Log"),
    ("cctv", "cctv", "CCTV Footage"),
    ("witness", "witness", "Witness Statement"),
    ("forensic", "forensic", "Forensic Report"),
    ("fingerprint", "forensic", "Fingerprint Report"),
    ("medical", "medical", "Medical Report"),
    ("fir", "police", "FIR"),
    ("bank", "financial", "Bank Record"),
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _evidence_log(event: str, **data: Any) -> None:
    logger.info("[MATTER_EVIDENCE] %s %s", event, data)
    try:
        log_path = Path(__file__).resolve().parents[3] / "debug-cf6ca9.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "matter-evidence",
                        "location": "matter_evidence",
                        "message": event,
                        "data": data,
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass


def _evidence_columns() -> set:
    ensure_practice_schema()
    conn = connect_data_db()
    cols = table_columns_set(conn, "matter_evidence")
    conn.close()
    return cols


def _row_to_dict(r: tuple, ecols: set) -> Dict[str, Any]:
    base = {
        "evidence_id": r[0],
        "category": r[1],
        "type": r[1],
        "document_id": r[2],
        "title": r[3],
        "tags": r[4],
        "notes": r[5],
        "description": r[5],
        "strength": r[6],
        "importance": r[6],
        "created_at": r[7],
        "source_document": "",
        "page_number": "",
        "person_related": "",
    }
    if "description" in ecols and len(r) > 11:
        base.update(
            {
                "description": r[8] or r[5],
                "notes": r[8] or r[5],
                "source_document": r[9] or "",
                "page_number": r[10] or "",
                "importance": r[11] or r[6],
                "strength": r[11] or r[6],
                "person_related": r[12] or "",
                "type": (r[13] if len(r) > 13 else r[1]) or r[1],
                "category": (r[13] if len(r) > 13 else r[1]) or r[1],
            }
        )
    return base


def list_evidence(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    ensure_practice_schema()
    ecols = _evidence_columns()
    conn = connect_data_db()
    if "description" in ecols:
        rows = conn.execute(
            """
            SELECT evidence_id, category, document_id, title, tags, notes, strength, created_at,
                   description, source_document, page_number, importance, person_related,
                   COALESCE(evidence_type, category)
            FROM matter_evidence WHERE matter_id = ?
            ORDER BY created_at DESC
            """,
            (matter_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT evidence_id, category, document_id, title, tags, notes, strength, created_at
            FROM matter_evidence WHERE matter_id = ?
            ORDER BY created_at DESC
            """,
            (matter_id,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r, ecols) for r in rows]


def add_evidence(
    user_id: str,
    matter_id: str,
    *,
    title: str,
    category: str = "document",
    document_id: str = "",
    tags: str = "",
    notes: str = "",
    strength: str = "unknown",
    description: str = "",
    source_document: str = "",
    page_number: str = "",
    importance: str = "",
    person_related: str = "",
    evidence_type: str = "",
) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        raise ValueError("Matter not found")
    ensure_practice_schema()
    ecols = _evidence_columns()
    eid = str(uuid.uuid4())
    now = _utc()
    imp = (importance or strength or "medium").lower()
    desc = (description or notes or "").strip()
    etype = (evidence_type or category or "document").lower()
    conn = connect_data_db()

    if "description" in ecols:
        conn.execute(
            """
            INSERT INTO matter_evidence
            (evidence_id, matter_id, category, document_id, title, tags, notes, strength, created_at,
             description, source_document, page_number, importance, person_related, evidence_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                matter_id,
                etype,
                document_id,
                title.strip()[:200],
                tags,
                desc[:2000],
                imp,
                now,
                desc[:2000],
                source_document[:200],
                page_number[:20],
                imp,
                person_related[:120],
                etype,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_evidence
            (evidence_id, matter_id, category, document_id, title, tags, notes, strength, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (eid, matter_id, etype, document_id, title.strip(), tags, desc, imp, now),
        )
    conn.commit()
    conn.close()
    _evidence_log("matter_evidence_saved", matter_id=matter_id, evidence_id=eid, title=title[:80])
    return {"evidence_id": eid, "title": title, "category": etype, "strength": imp}


def _infer_from_filename(filename: str) -> Optional[Dict[str, str]]:
    fn = (filename or "").lower()
    for key, category, title in _FILENAME_EVIDENCE_HINTS:
        if key in fn:
            return {"category": category, "title": title, "strength": "high"}
    if fn.endswith(".pdf"):
        return {"category": "document", "title": filename, "strength": "medium"}
    return None


def _parse_evidence_lines(answer: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    for line in (answer or "").splitlines():
        line = line.strip().lstrip("-•*").strip()
        if "|" not in line or len(line) < 10:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        items.append(
            {
                "title": parts[0][:200],
                "category": (parts[1] if len(parts) > 1 else "document").lower()[:40],
                "strength": (parts[2] if len(parts) > 2 else "medium").lower()[:20],
                "notes": (parts[3] if len(parts) > 3 else "")[:800],
                "tags": (parts[4] if len(parts) > 4 else "")[:200],
            }
        )
    return items


def _parse_numbered_evidence_list(text: str, filename: str = "") -> List[Dict[str, str]]:
    """Parse '1. CCTV footage from warehouse road. 2. WhatsApp...' style lists."""
    found: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for m in re.finditer(
        r"\d+\.\s*((?:CCTV|WhatsApp|Call|Fingerprint|Forensic|Witness|Postmortem|Bank|Blood|Mobile|Financial)[^.\n]{8,160})",
        text,
        re.I,
    ):
        raw = m.group(1).strip()
        key = raw.lower()[:60]
        if key in seen:
            continue
        seen.add(key)
        etype = "document"
        imp = "medium"
        title = raw[:120]
        if re.search(r"cctv", raw, re.I):
            etype, imp, title = "cctv", "high", "CCTV footage"
        elif re.search(r"whatsapp", raw, re.I):
            etype, imp, title = "digital", "high", "WhatsApp chats"
        elif re.search(r"fingerprint|forensic", raw, re.I):
            etype, imp, title = "forensic", "critical", "Fingerprint report"
        elif re.search(r"witness", raw, re.I):
            etype, imp, title = "witness", "high", "Witness statement"
        elif re.search(r"postmortem", raw, re.I):
            etype, imp, title = "medical", "critical", "Postmortem report"
        elif re.search(r"bank|financial|upi", raw, re.I):
            etype, imp, title = "financial", "high", "Financial records"
        found.append(
            {
                "title": title,
                "category": etype,
                "strength": imp,
                "notes": raw[:500],
                "tags": filename,
                "person_related": "",
            }
        )
    return found


def _extract_witness_evidence(text: str, filename: str = "") -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for m in re.finditer(
        r"WITNESS\s+STATEMENT\s*[–\-]\s*([A-Z][A-Za-z\s\.]{2,48})\s*(.*?)(?=WITNESS\s+STATEMENT|\[PAGE:|$)",
        text,
        re.I | re.S,
    ):
        name = m.group(1).strip()
        body = re.sub(r"\s+", " ", m.group(2)).strip()[:400]
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        found.append(
            {
                "title": f"Witness statement — {name}",
                "category": "witness",
                "strength": "high",
                "notes": body or f"Witness statement of {name}.",
                "tags": filename,
                "person_related": name,
            }
        )
    return found


def _regex_extract_evidence(text: str, filename: str = "") -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for pat, etype, title, imp in _EVIDENCE_PATTERNS:
        m = re.search(pat, text, re.I)
        if not m:
            continue
        snippet = re.sub(r"\s+", " ", m.group(0)).strip()[:400]
        key = etype
        if key in seen:
            continue
        seen.add(key)
        found.append(
            {
                "title": title,
                "category": etype,
                "strength": imp,
                "notes": snippet,
                "tags": filename,
                "person_related": "",
            }
        )
    found.extend(_parse_numbered_evidence_list(text, filename))
    found.extend(_extract_witness_evidence(text, filename))
    return found


def _dedupe_evidence(items: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: Set[str] = set()
    for item in items:
        key = f"{item.get('category','')}:{item.get('title','').lower()[:50]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_evidence_from_docs(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    """Extract evidence from matter documents — regex + RAG, persisted to DB."""
    if not get_matter(user_id, matter_id):
        return []

    _evidence_log("matter_evidence_started", matter_id=matter_id)

    conn = connect_data_db()
    conn.execute("DELETE FROM matter_evidence WHERE matter_id = ?", (matter_id,))
    conn.commit()
    conn.close()

    docs = list_matter_documents(user_id, matter_id)
    if not docs:
        raise ValueError("No documents linked to this matter. Upload PDFs first.")

    from backend.app.core.matter_autopilot import load_matter_doc_texts

    chunks = load_matter_doc_texts(user_id, matter_id)
    combined = "\n\n".join(ch.get("content", "") for ch in chunks)
    if len(combined) < 80:
        raise ValueError(
            "Not enough document text. Upload PDFs or wait for extraction/indexing to finish."
        )

    candidates: List[Dict[str, str]] = []
    for ch in chunks:
        fn = ch.get("filename", "")
        did = ch.get("document_id", "")
        body = ch.get("content", "")
        candidates.extend(_regex_extract_evidence(body, fn))
        hint = _infer_from_filename(fn)
        if hint:
            candidates.append(
                {
                    **hint,
                    "notes": f"Detected from uploaded file: {fn}",
                    "tags": fn,
                    "person_related": "",
                    "document_id": did,
                }
            )

    candidates.extend(_regex_extract_evidence(combined))
    candidates = _dedupe_evidence(candidates)

    for item in candidates:
        add_evidence(
            user_id,
            matter_id,
            title=item["title"],
            category=item.get("category") or "document",
            document_id=str(item.get("document_id") or ""),
            tags=item.get("tags", ""),
            notes=item.get("notes", ""),
            strength=item.get("strength", "medium"),
            description=item.get("notes", ""),
            source_document=item.get("tags", ""),
            importance=item.get("strength", "medium"),
            person_related=item.get("person_related", ""),
            evidence_type=item.get("category") or "document",
        )
        _evidence_log("matter_evidence_found", matter_id=matter_id, title=item["title"][:80])

    prompt = (
        "List all evidence in these matter documents only. One per line:\n"
        "Title | Type | Importance | Description | Source\n"
        "Types: cctv, digital, witness, forensic, medical, financial, police, physical\n"
        "Importance: critical, high, medium, weak"
    )
    try:
        from app import rag_query

        answer, _ = rag_query(str(user_id), prompt, k=14, matter_id=matter_id)
        for item in _parse_evidence_lines(answer or ""):
            if "NOT_FOUND" in (item.get("title") or "").upper():
                continue
            imp = item.get("strength", "medium")
            if imp not in ("critical", "high", "medium", "weak", "strong"):
                imp = "medium"
            if imp == "strong":
                imp = "high"
            add_evidence(
                user_id,
                matter_id,
                title=item["title"],
                category=item.get("category") or "document",
                tags=item.get("tags", ""),
                notes=item.get("notes", ""),
                strength=imp,
                description=item.get("notes", ""),
                source_document=item.get("tags", ""),
                importance=imp,
                evidence_type=item.get("category") or "document",
            )
    except Exception as exc:
        _evidence_log("matter_evidence_rag_error", matter_id=matter_id, error=str(exc))

    result = list_evidence(user_id, matter_id)
    if not result:
        raise ValueError(
            "No evidence could be extracted. Ensure documents mention CCTV, witnesses, forensic reports, etc."
        )
    _evidence_log("matter_evidence_complete", matter_id=matter_id, count=len(result))
    return result
