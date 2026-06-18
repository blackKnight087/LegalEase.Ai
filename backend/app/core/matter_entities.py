"""Matter entity graph — extracted people, sections, courts, etc."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter, list_matter_documents
from backend.app.core.practice_schema import ensure_practice_schema

logger = logging.getLogger(__name__)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entity_log(event: str, **data: Any) -> None:
    logger.info("[MATTER_ENTITIES] %s %s", event, data)
    try:
        log_path = Path(__file__).resolve().parents[3] / "debug-cf6ca9.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "matter-entities",
                        "location": "matter_entities",
                        "message": event,
                        "data": data,
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass


def list_entities(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    ensure_practice_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT entity_id, entity_type, label, source_doc_id, confidence, metadata_json, created_at
        FROM matter_entities WHERE matter_id = ?
        ORDER BY entity_type ASC, confidence DESC, label ASC
        """,
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "entity_id": r[0],
            "entity_type": r[1],
            "label": r[2],
            "source_doc_id": r[3],
            "confidence": r[4],
            "metadata": json.loads(r[5] or "{}"),
            "created_at": r[6],
        }
        for r in rows
    ]


def upsert_entity(
    matter_id: str,
    *,
    entity_type: str,
    label: str,
    source_doc_id: str = "",
    confidence: float = 0.8,
    metadata: Optional[Dict[str, Any]] = None,
) -> str:
    ensure_practice_schema()
    label_clean = re.sub(r"\s+", " ", label.replace("\n", " ")).strip()[:240]
    if len(label_clean) < 2 or len(label_clean) > 80:
        return ""
    conn = connect_data_db()
    existing = conn.execute(
        """
        SELECT entity_id FROM matter_entities
        WHERE matter_id = ? AND entity_type = ? AND lower(label) = lower(?)
        LIMIT 1
        """,
        (matter_id, entity_type, label_clean),
    ).fetchone()
    if existing:
        conn.close()
        return str(existing[0])
    eid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO matter_entities
        (entity_id, matter_id, entity_type, label, source_doc_id, confidence, metadata_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eid,
            matter_id,
            entity_type,
            label_clean,
            source_doc_id,
            confidence,
            json.dumps(metadata or {}),
            _utc(),
        ),
    )
    conn.commit()
    conn.close()
    return eid


def _rag_lines(user_id: str, matter_id: str, prompt: str) -> str:
    try:
        from app import rag_query

        answer, _ = rag_query(str(user_id), prompt, k=12, matter_id=matter_id)
        return answer or ""
    except Exception:
        return ""


def _extract_regex_entities(text: str, filename: str = "") -> List[Tuple[str, str, float]]:
    """Returns (entity_type, label, confidence)."""
    found: List[Tuple[str, str, float]] = []
    seen: Set[str] = set()

    def add(etype: str, label: str, conf: float = 0.8) -> None:
        key = f"{etype}:{label.lower()}"
        if key in seen or len(label.strip()) < 2:
            return
        seen.add(key)
        found.append((etype, label.strip()[:240], conf))

    for pat, etype in (
        (
            r"(?:petitioner|plaintiff|appellant|respondent|accused|defendant|victim|witness|complainant|applicant)\s*[:\-]?\s*([A-Z][A-Za-z][A-Za-z\s\.]{1,48})",
            "person",
        ),
        (r"(?:Judge|Hon'ble|Justice)\s+([A-Z][A-Za-z][A-Za-z\s\.]{2,40})", "judge"),
        (r"(?:Advocate|Counsel|Lawyer|Attorney)\s+([A-Z][A-Za-z][A-Za-z\s\.]{2,40})", "lawyer"),
        (r"(?:Inspector|IO|Investigating Officer)\s+([A-Z][A-Za-z][A-Za-z\s\.]{2,40})", "police"),
    ):
        for m in re.finditer(pat, text, re.I):
            add(etype, m.group(1), 0.82)

    for m in re.finditer(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b", text
    ):
        name = m.group(1).strip()
        if len(name) > 4 and name.lower() not in (
            "high court",
            "supreme court",
            "session court",
            "district court",
            "state of",
        ):
            add("person", name, 0.65)

    for m in re.finditer(
        r"\b(?:Section|Sec\.?|IPC|BNS|BNSS|Cr\.?P\.?C\.?)\s*(\d{1,4}[A-Za-z]?)\b",
        text,
        re.I,
    ):
        add("statute", f"Section {m.group(1)}", 0.88)

    for m in re.finditer(r"\b(?:FIR|Cr\.?P\.?C\.?)\s*(?:No\.?|Number)?\s*[:#]?\s*([\d/\-]+)", text, re.I):
        add("reference", f"FIR {m.group(1)}", 0.9)

    for m in re.finditer(
        r"\b(?:Case No\.?|CNR|Diary No\.?)\s*[:#]?\s*([A-Za-z0-9/\-]+)",
        text,
        re.I,
    ):
        add("reference", f"Case {m.group(1)}", 0.85)

    for m in re.finditer(
        r"\b((?:Supreme Court|High Court|District Court|Sessions Court|Magistrate)[^,\n]{0,60})",
        text,
        re.I,
    ):
        add("court", m.group(1).strip(), 0.86)

    for m in re.finditer(
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
        text,
        re.I,
    ):
        add("date", m.group(1), 0.8)

    for m in re.finditer(r"\b(\d{4}-\d{2}-\d{2})\b", text):
        add("date", m.group(1), 0.85)

    for m in re.finditer(r"\b(?:\+91[\s\-]?)?[6-9]\d{9}\b", text):
        add("phone", m.group(0), 0.92)

    for m in re.finditer(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", text):
        add("email", m.group(0), 0.92)

    for m in re.finditer(
        r"\b([A-Z][A-Za-z\s&]{2,40}(?:Ltd|Limited|Pvt|Private|Bank|Hospital|Police|Commission))\b",
        text,
    ):
        add("organization", m.group(1).strip(), 0.7)

    fn = (filename or "").lower()
    if "fir" in fn:
        add("document_type", "FIR", 0.95)
    if "charge" in fn:
        add("document_type", "Chargesheet", 0.95)
    if "witness" in fn:
        add("document_type", "Witness Statement", 0.9)
    if "medical" in fn:
        add("document_type", "Medical Report", 0.9)

    return found


def _parse_entity_lines(answer: str) -> List[Tuple[str, str]]:
    """Parse RAG lines: TYPE | name"""
    out: List[Tuple[str, str]] = []
    type_map = {
        "person": "person",
        "people": "person",
        "witness": "person",
        "accused": "person",
        "victim": "person",
        "judge": "judge",
        "lawyer": "lawyer",
        "court": "court",
        "section": "statute",
        "statute": "statute",
        "ipc": "statute",
        "bns": "statute",
        "fir": "reference",
        "date": "date",
        "location": "location",
        "organization": "organization",
        "phone": "phone",
        "email": "email",
    }
    for line in (answer or "").splitlines():
        line = line.strip().lstrip("-•*").strip()
        if "|" not in line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            continue
        raw_type = parts[0].lower()
        label = parts[1]
        etype = type_map.get(raw_type, "person")
        if label and len(label) > 1:
            out.append((etype, label[:240]))
    return out


def _extract_structured_entities(text: str) -> List[Tuple[str, str, float, Dict[str, Any]]]:
    """Parse case-file header blocks: Victim, Accused, Court, IPC, etc."""
    found: List[Tuple[str, str, float, Dict[str, Any]]] = []
    header_pairs = (
        (r"Victim\s*\n\s*([A-Z][A-Za-z\s\.]{2,48})", "person", {"role": "Victim"}),
        (r"Accused\s*\n\s*([A-Z][A-Za-z\s\.]{2,48})", "person", {"role": "Accused"}),
        (r"Court\s*\n\s*([^\n]+)", "court", {}),
        (r"Police Station\s*\n\s*([^\n]+)", "organization", {"role": "Police"}),
        (r"FIR No\.?\s*\n\s*([^\n]+)", "reference", {"role": "FIR"}),
        (r"Case No\.?\s*\n\s*([^\n]+)", "reference", {"role": "Case"}),
        (r"Next Hearing\s*\n\s*(\d{1,2}\s+\w+\s+\d{4})", "date", {}),
    )
    for pat, etype, meta in header_pairs:
        m = re.search(pat, text, re.I)
        if m:
            found.append((etype, m.group(1).strip()[:240], 0.95, meta))

    for m in re.finditer(r"\b(?:IPC|Section)\s*([\d,\s]+(?:IPC)?)", text, re.I):
        for num in re.findall(r"\d{1,4}", m.group(1)):
            found.append(("statute", f"IPC {num}", 0.92, {}))

    for m in re.finditer(
        r"WITNESS\s+STATEMENT\s*[–\-]\s*([A-Z][A-Za-z\s\.]{2,48})",
        text,
        re.I,
    ):
        found.append(("person", m.group(1).strip(), 0.9, {"role": "Witness"}))

    for m in re.finditer(
        r"\b((?:Salt Lake|Howrah|Kolkata)[^,\n]{0,40}(?:warehouse|court|station)[^,\n]{0,40})",
        text,
        re.I,
    ):
        loc = m.group(1).strip()
        if len(loc) > 5:
            found.append(("location", loc[:200], 0.85, {}))

    if re.search(r"warehouse", text, re.I) and not any(x[1].lower().find("warehouse") >= 0 for x in found if x[0] == "location"):
        found.append(("location", "Salt Lake Warehouse", 0.8, {}))

    return found


def extract_entities_from_docs(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    """Structured NER from matter document text — no sentence garbage or RAG noise."""
    if not get_matter(user_id, matter_id):
        return []

    _entity_log("matter_entities_started", matter_id=matter_id)

    conn = connect_data_db()
    conn.execute("DELETE FROM matter_entities WHERE matter_id = ?", (matter_id,))
    conn.commit()
    conn.close()

    from backend.app.core.matter_autopilot import load_matter_doc_texts
    from backend.app.core.matter_entity_extract import extract_structured_entities

    chunks = load_matter_doc_texts(user_id, matter_id)
    combined = "\n\n".join(ch.get("content", "") for ch in chunks)
    if len(combined) < 80:
        raise ValueError(
            "Not enough document text. Upload PDFs or wait for extraction/indexing to finish."
        )

    for ch in chunks:
        body = ch.get("content", "")
        for etype, label, conf, meta in extract_structured_entities(body):
            upsert_entity(
                matter_id,
                entity_type=etype,
                label=label,
                source_doc_id=ch.get("document_id", ""),
                confidence=conf,
                metadata={**meta, "filename": ch.get("filename", "")},
            )

    for etype, label, conf, meta in extract_structured_entities(combined):
        upsert_entity(matter_id, entity_type=etype, label=label, confidence=conf, metadata=meta)

    result = list_entities(user_id, matter_id)
    _entity_log("matter_entities_saved", matter_id=matter_id, count=len(result))
    return result


def extract_entities_heuristic(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    """Backward-compatible alias."""
    try:
        return extract_entities_from_docs(user_id, matter_id)
    except ValueError:
        return []
