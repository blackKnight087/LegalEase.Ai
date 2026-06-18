"""Matter hearings — scheduling, extraction from documents, persistence."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import table_columns_set
from backend.app.core.matter_repo import get_matter, list_matter_documents
from backend.app.core.practice_schema import ensure_practice_schema

logger = logging.getLogger(__name__)

_HEARING_PHRASES = re.compile(
    r"(?:court hearing|hearing held|next hearing|listed on|matter adjourned|"
    r"court observed|judge stated|order dated|hearing on|adjourned to|posted for)",
    re.I,
)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hearing_log(event: str, **data: Any) -> None:
    logger.info("[MATTER_HEARING] %s %s", event, data)
    try:
        from pathlib import Path

        log_path = Path(__file__).resolve().parents[3] / "debug-cf6ca9.log"
        with open(log_path, "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "hearings",
                        "hypothesisId": "H-hearing",
                        "location": "matter_hearings_intel",
                        "message": event,
                        "data": data,
                        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass


def _hearing_columns() -> set:
    ensure_practice_schema()
    conn = connect_data_db()
    cols = table_columns_set(conn, "matter_hearings")
    conn.close()
    return cols


def _normalize_date(raw: str) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m_dmy = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", s)
    if m_dmy:
        day, mon = int(m_dmy.group(1)), int(m_dmy.group(2))
        yr = m_dmy.group(3)
        if len(yr) == 2:
            yr = f"20{yr}" if int(yr) < 70 else f"19{yr}"
        if 1 <= day <= 31 and 1 <= mon <= 12:
            return f"{yr}-{mon:02d}-{day:02d}"
    months = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    m2 = re.search(
        r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})",
        s,
        re.I,
    )
    if m2:
        day = int(m2.group(1))
        if day < 1 or day > 31:
            return ""
        mon = months.get(m2.group(2).lower()[:3], "")
        if not mon:
            return ""
        return f"{m2.group(3)}-{mon}-{day:02d}"
    return ""


def _valid_date(d: str) -> bool:
    return bool(d and re.match(r"^\d{4}-\d{2}-\d{2}$", d))


def _row_to_dict(r: tuple, hcols: set) -> Dict[str, Any]:
    base = {
        "hearing_id": r[0],
        "hearing_date": r[1],
        "court_name": r[2],
        "purpose": r[3],
        "notes": r[4],
        "status": r[5],
        "created_at": r[6],
        "judge_name": "",
        "judge": "",
        "summary": "",
        "prosecution_argument": "",
        "defense_argument": "",
        "judge_observation": "",
        "observations": "",
        "arguments": "",
        "next_hearing_date": "",
        "document_source": "",
        "page_number": "",
        "source": "manual",
    }
    if "judge" in hcols and len(r) > 11:
        base.update(
            {
                "judge": r[7] or "",
                "judge_name": r[7] or "",
                "arguments": r[8] or "",
                "observations": r[9] or "",
                "judge_observation": r[9] or "",
                "next_hearing_date": r[10] or "",
                "summary": r[11] or "",
            }
        )
    if "prosecution_argument" in hcols and len(r) > 15:
        base.update(
            {
                "prosecution_argument": r[12] or "",
                "defense_argument": r[13] or "",
                "document_source": r[14] or "",
                "page_number": r[15] or "",
                "source": r[16] if len(r) > 16 else "manual",
            }
        )
    elif "source" in hcols and len(r) > 12:
        base["source"] = r[12] if len(r) > 12 else "manual"
    return base


def list_hearings(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    ensure_practice_schema()
    hcols = _hearing_columns()
    conn = connect_data_db()
    if "prosecution_argument" in hcols:
        rows = conn.execute(
            """
            SELECT hearing_id, hearing_date, court_name, purpose, notes, status, created_at,
                   judge, arguments, observations, next_hearing_date, summary,
                   prosecution_argument, defense_argument, document_source, page_number,
                   COALESCE(source, 'manual')
            FROM matter_hearings WHERE matter_id = ?
            ORDER BY hearing_date ASC
            """,
            (matter_id,),
        ).fetchall()
    elif "judge" in hcols:
        rows = conn.execute(
            """
            SELECT hearing_id, hearing_date, court_name, purpose, notes, status, created_at,
                   judge, arguments, observations, next_hearing_date, summary,
                   '', '', '', '', COALESCE(source, 'manual')
            FROM matter_hearings WHERE matter_id = ?
            ORDER BY hearing_date ASC
            """,
            (matter_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT hearing_id, hearing_date, court_name, purpose, notes, status, created_at
            FROM matter_hearings WHERE matter_id = ?
            ORDER BY hearing_date ASC
            """,
            (matter_id,),
        ).fetchall()
    conn.close()
    items = [_row_to_dict(r, hcols) for r in rows]
    _hearing_log("hearing_rendered", matter_id=matter_id, count=len(items))
    return items


def schedule_hearing(
    user_id: str,
    matter_id: str,
    *,
    hearing_date: str,
    court_name: str = "",
    purpose: str = "",
    notes: str = "",
    judge_name: str = "",
    summary: str = "",
    prosecution_argument: str = "",
    defense_argument: str = "",
    judge_observation: str = "",
    next_hearing_date: str = "",
    document_source: str = "",
    page_number: str = "",
) -> Dict[str, Any]:
    if not get_matter(user_id, matter_id):
        raise ValueError("Matter not found")
    hdate = _normalize_date(hearing_date)
    if not _valid_date(hdate):
        raise ValueError("Hearing date is required")

    ensure_practice_schema()
    hcols = _hearing_columns()
    hid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()

    if "prosecution_argument" in hcols:
        conn.execute(
            """
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at,
             judge, arguments, observations, next_hearing_date, summary,
             prosecution_argument, defense_argument, document_source, page_number, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hid,
                matter_id,
                hdate,
                court_name.strip(),
                purpose.strip(),
                notes.strip(),
                "scheduled",
                now,
                judge_name.strip(),
                "",
                judge_observation.strip(),
                _normalize_date(next_hearing_date),
                summary.strip(),
                prosecution_argument.strip(),
                defense_argument.strip(),
                document_source.strip(),
                page_number.strip(),
                "manual",
            ),
        )
    elif "judge" in hcols:
        src_col = ", source" if "source" in hcols else ""
        src_val = ", 'manual'" if "source" in hcols else ""
        src_bind = ", ?" if "source" in hcols else ""
        conn.execute(
            f"""
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at,
             judge, arguments, observations, next_hearing_date, summary{src_col})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?{src_bind})
            """,
            (
                hid,
                matter_id,
                hdate,
                court_name,
                purpose,
                notes,
                "scheduled",
                now,
                judge_name,
                "",
                judge_observation,
                _normalize_date(next_hearing_date),
                summary,
            )
            + (("manual",) if "source" in hcols else ()),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
            """,
            (hid, matter_id, hdate, court_name, purpose, notes, now),
        )
    conn.commit()
    conn.close()

    try:
        from backend.app.core.matter_workflow import add_timeline_event

        add_timeline_event(
            user_id,
            matter_id,
            title=f"Hearing: {purpose or court_name or 'Scheduled'}",
            description=notes or summary,
            event_date=hdate[:10],
            event_type="hearing",
        )
    except Exception:
        pass

    _hearing_log("hearing_saved", matter_id=matter_id, hearing_id=hid, source="manual")
    for h in list_hearings(user_id, matter_id):
        if str(h.get("hearing_id")) == hid:
            return h
    return {
        "hearing_id": hid,
        "hearing_date": hdate,
        "court_name": court_name,
        "purpose": purpose,
        "status": "scheduled",
        "source": "manual",
    }


def _save_extracted_hearing(
    user_id: str,
    matter_id: str,
    item: Dict[str, str],
) -> Optional[str]:
    hdate = _normalize_date(item.get("hearing_date", ""))
    if not hdate:
        return None
    key = f"{hdate}|{item.get('court_name','')[:40]}|{item.get('purpose','')[:40]}"
    existing = list_hearings(user_id, matter_id)
    for h in existing:
        ek = f"{h.get('hearing_date')}|{str(h.get('court_name',''))[:40]}|{str(h.get('purpose',''))[:40]}"
        if ek == key:
            return str(h.get("hearing_id"))

    ensure_practice_schema()
    hcols = _hearing_columns()
    hid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()

    if "prosecution_argument" in hcols:
        conn.execute(
            """
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at,
             judge, arguments, observations, next_hearing_date, summary,
             prosecution_argument, defense_argument, document_source, page_number, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                hid,
                matter_id,
                hdate,
                item.get("court_name", "")[:200],
                item.get("purpose", "")[:200],
                item.get("summary", "")[:500],
                "extracted",
                now,
                item.get("judge_name", "")[:120],
                "",
                item.get("judge_observation", "")[:500],
                _normalize_date(item.get("next_hearing_date", "")),
                item.get("summary", "")[:500],
                item.get("prosecution_argument", "")[:800],
                item.get("defense_argument", "")[:800],
                item.get("document_source", "")[:200],
                item.get("page_number", "")[:20],
                "auto",
            ),
        )
    elif "judge" in hcols:
        src_col = ", source" if "source" in hcols else ""
        src_bind = ", ?" if "source" in hcols else ""
        conn.execute(
            f"""
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at,
             judge, arguments, observations, next_hearing_date, summary{src_col})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?{src_bind})
            """,
            (
                hid,
                matter_id,
                hdate,
                item.get("court_name", ""),
                item.get("purpose", ""),
                item.get("summary", ""),
                "extracted",
                now,
                item.get("judge_name", ""),
                "",
                item.get("judge_observation", ""),
                _normalize_date(item.get("next_hearing_date", "")),
                item.get("summary", ""),
            )
            + (("auto",) if "source" in hcols else ()),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'extracted', ?)
            """,
            (
                hid,
                matter_id,
                hdate,
                item.get("court_name", ""),
                item.get("purpose", ""),
                item.get("summary", ""),
                now,
            ),
        )
    conn.commit()
    conn.close()
    _hearing_log("hearing_found", matter_id=matter_id, hearing_id=hid, date=hdate)
    return hid


def _regex_extract_hearings(text: str, filename: str = "") -> List[Dict[str, str]]:
    found: List[Dict[str, str]] = []
    if not text:
        return found

    court_m = re.search(
        r"(?:Court\s*\n\s*)?((?:Supreme Court|High Court|District Court|Sessions Court|Magistrate)[^.\n]{0,80})",
        text,
        re.I,
    )
    default_court = court_m.group(1).strip() if court_m else ""

    for m in _HEARING_PHRASES.finditer(text):
        start = max(0, m.start() - 40)
        end = min(len(text), m.end() + 420)
        window = text[start:end]
        dm = re.search(
            r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})",
            window,
            re.I,
        )
        if not dm:
            continue
        hdate = _normalize_date(dm.group(1))
        if not _valid_date(hdate):
            continue
        judge_m = re.search(
            r"(?:Justice|Hon'ble|Honble|Judge)\s+([A-Z][A-Za-z\s\.]{2,40})",
            window,
            re.I,
        )
        next_m = re.search(
            r"next hearing[^.\n]{0,40}?(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2})",
            window,
            re.I,
        )
        pros_m = re.search(
            r"Prosecution\s+(?:argued|submitted|stated)\s+([^.\n]{10,200})",
            window,
            re.I,
        )
        def_m = re.search(
            r"Defen[cs]e\s+(?:argued|denied|submitted|stated)\s+([^.\n]{10,200})",
            window,
            re.I,
        )
        obs_m = re.search(
            r"Court\s+observed\s+([^.\n]{10,220})",
            window,
            re.I,
        )
        found.append(
            {
                "hearing_date": hdate,
                "court_name": default_court,
                "purpose": "Court hearing",
                "judge_name": judge_m.group(1).strip() if judge_m else "",
                "summary": window.strip()[:400],
                "prosecution_argument": pros_m.group(1).strip() if pros_m else "",
                "defense_argument": def_m.group(1).strip() if def_m else "",
                "judge_observation": obs_m.group(1).strip() if obs_m else "",
                "next_hearing_date": _normalize_date(next_m.group(1)) if next_m else "",
                "document_source": filename,
                "page_number": "",
            }
        )

    return found


def _extract_structured_hearings(text: str, filename: str = "") -> List[Dict[str, str]]:
    """Parse hearing blocks from case-file headers and HEARING NOTES sections."""
    if not text:
        return []
    items: List[Dict[str, str]] = []
    court_m = re.search(r"Court\s*\n\s*([^\n]+)", text, re.I)
    court = court_m.group(1).strip() if court_m else ""
    if court and "court" not in court.lower():
        court = ""
    if not court:
        cm = re.search(
            r"((?:Supreme Court|High Court|District Court|Sessions Court)[^.\n]{0,80})",
            text,
            re.I,
        )
        court = cm.group(1).strip() if cm else ""

    next_hdr = re.search(
        r"Next\s+Hearing\s*\n\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})",
        text,
        re.I,
    )
    next_date = _normalize_date(next_hdr.group(1)) if next_hdr else ""

    hearing_notes = re.search(r"HEARING\s+NOTES\s*(.+?)(?:\[PAGE:|JUDGE\s+OBSERVATION|$)", text, re.I | re.S)
    notes_body = hearing_notes.group(1) if hearing_notes else text

    obs_block = re.search(r"JUDGE\s+OBSERVATION\s*(.+?)(?:\[PAGE:|TIMELINE|$)", text, re.I | re.S)
    judge_obs = ""
    if obs_block:
        obs_line = re.search(r"Court\s+observed\s+([^.\n]{10,240})", obs_block.group(1), re.I)
        judge_obs = obs_line.group(1).strip() if obs_line else obs_block.group(1).strip()[:240]

    seen_dates: set = set()
    for m in re.finditer(
        r"Court\s+hearing\s+on\s+(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\s*:\s*"
        r"Prosecution\s+(?:argued|submitted)\s+([^.\n]{10,200})\.\s*"
        r"Defen[cs]e\s+(?:denied|argued|submitted)\s+([^.\n]{10,200})",
        notes_body,
        re.I,
    ):
        hdate = _normalize_date(m.group(1))
        if not _valid_date(hdate) or hdate in seen_dates:
            continue
        seen_dates.add(hdate)
        items.append(
            {
                "hearing_date": hdate,
                "court_name": court,
                "purpose": "Initial hearing" if len(seen_dates) == 1 else "Court hearing",
                "judge_name": "",
                "summary": f"Court hearing on {m.group(1)}.",
                "prosecution_argument": m.group(2).strip(),
                "defense_argument": m.group(3).strip(),
                "judge_observation": judge_obs,
                "next_hearing_date": next_date if next_date and next_date != hdate else "",
                "document_source": filename,
                "page_number": "10",
            }
        )

    if next_date and _valid_date(next_date) and next_date not in seen_dates:
        items.append(
            {
                "hearing_date": next_date,
                "court_name": court,
                "purpose": "Next hearing",
                "judge_name": "",
                "summary": "Adjourned / listed for next hearing.",
                "prosecution_argument": "",
                "defense_argument": "",
                "judge_observation": "",
                "next_hearing_date": "",
                "document_source": filename,
                "page_number": "1",
            }
        )

    return items


def _dedupe_hearing_candidates(candidates: List[Dict[str, str]]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    seen: set = set()
    for item in candidates:
        d = _normalize_date(item.get("hearing_date", ""))
        if not _valid_date(d):
            continue
        key = d
        if key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["hearing_date"] = d
        if item.get("next_hearing_date"):
            item["next_hearing_date"] = _normalize_date(item["next_hearing_date"])
        out.append(item)
    return out


def _parse_rag_hearings(answer: str) -> List[Dict[str, str]]:
    items: List[Dict[str, str]] = []
    blocks = re.split(r"\n---+\n|\n(?=HEARING\b)", answer or "", flags=re.I)
    for block in blocks:
        if not block.strip():
            continue
        item: Dict[str, str] = {}
        for line in block.splitlines():
            line = line.strip()
            if ":" not in line:
                if "|" in line:
                    parts = [p.strip() for p in line.split("|")]
                    if len(parts) >= 2 and re.search(r"\d{4}", parts[0]):
                        item.setdefault("hearing_date", parts[0])
                        item.setdefault("court_name", parts[1] if len(parts) > 1 else "")
                        item.setdefault("purpose", parts[2] if len(parts) > 2 else "")
                        item.setdefault("judge_observation", parts[3] if len(parts) > 3 else "")
                        item.setdefault("next_hearing_date", parts[4] if len(parts) > 4 else "")
                        item.setdefault("summary", parts[5] if len(parts) > 5 else "")
                continue
            key, _, val = line.partition(":")
            k = key.strip().lower().replace(" ", "_")
            val = val.strip()
            mapping = {
                "date": "hearing_date",
                "hearing_date": "hearing_date",
                "court": "court_name",
                "court_name": "court_name",
                "purpose": "purpose",
                "judge": "judge_name",
                "judge_name": "judge_name",
                "summary": "summary",
                "prosecution": "prosecution_argument",
                "prosecution_argument": "prosecution_argument",
                "defense": "defense_argument",
                "defense_argument": "defense_argument",
                "judge_observation": "judge_observation",
                "observations": "judge_observation",
                "next_hearing": "next_hearing_date",
                "next_hearing_date": "next_hearing_date",
                "source": "document_source",
                "page": "page_number",
            }
            if k in mapping:
                item[mapping[k]] = val
        if item.get("hearing_date"):
            items.append(item)
    return items


def extract_hearings_from_docs(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Extract hearings from matter KB and persist."""
    if not get_matter(user_id, matter_id):
        raise ValueError("Matter not found")

    docs = list_matter_documents(user_id, matter_id)
    if not docs:
        raise ValueError("No documents linked to this matter. Upload PDFs first.")

    _hearing_log("hearing_extraction_started", matter_id=matter_id, doc_count=len(docs))

    from backend.app.core.matter_autopilot import load_matter_doc_texts

    chunks = load_matter_doc_texts(user_id, matter_id)
    combined = "\n\n".join(ch.get("content", "") for ch in chunks)[:80000]
    if len(combined) < 80:
        raise ValueError(
            "Not enough document text. Upload PDFs or wait for indexing to finish, then try again."
        )

    ensure_practice_schema()
    hcols = _hearing_columns()
    if "source" in hcols:
        conn = connect_data_db()
        conn.execute(
            "DELETE FROM matter_hearings WHERE matter_id = ? AND source = 'auto'",
            (matter_id,),
        )
        conn.commit()
        conn.close()

    candidates: List[Dict[str, str]] = []
    for ch in chunks:
        body = ch.get("content", "")
        fn = ch.get("filename", "")
        candidates.extend(_extract_structured_hearings(body, fn))
        candidates.extend(_regex_extract_hearings(body, fn))
    candidates.extend(_extract_structured_hearings(combined))
    candidates.extend(_regex_extract_hearings(combined))
    candidates = _dedupe_hearing_candidates(candidates)

    prompt = (
        "From the matter documents ONLY, list every court hearing. "
        "For each hearing use this block format (repeat for each hearing):\n"
        "HEARING\n"
        "Date: YYYY-MM-DD or DD Month YYYY\n"
        "Court: full court name\n"
        "Purpose: e.g. Initial hearing, Bail, Arguments\n"
        "Judge: judge name\n"
        "Summary: what happened\n"
        "Prosecution: prosecution argument\n"
        "Defense: defense argument\n"
        "Judge Observation: court observations\n"
        "Next Hearing: next date if mentioned\n"
        "---\n"
        "Include phrases like 'hearing held on', 'listed on', 'adjourned to', 'court observed'."
    )
    try:
        from app import rag_query

        answer, _ = rag_query(str(user_id), prompt, k=14, matter_id=matter_id)
        if answer and "NOT_FOUND" not in (answer or "").upper()[:60]:
            candidates.extend(_parse_rag_hearings(answer))
    except Exception as exc:
        _hearing_log("hearing_rag_error", matter_id=matter_id, error=str(exc))

    saved = 0
    for item in candidates:
        if _save_extracted_hearing(user_id, matter_id, item):
            saved += 1

    result_list = list_hearings(user_id, matter_id)
    if saved == 0 and not result_list:
        raise ValueError(
            "No hearings found in documents. Ensure PDFs mention court dates/hearings and are fully indexed."
        )

    _hearing_log("hearing_extraction_complete", matter_id=matter_id, saved=saved, total=len(result_list))
    return {
        "ok": True,
        "hearings": result_list,
        "inserted": saved,
        "count": len(result_list),
    }


def parse_voice_hearing_note(transcript: str) -> Dict[str, str]:
    """Extract hearing fields from dictated court note."""
    t = (transcript or "").strip()
    out: Dict[str, str] = {
        "hearing_date": "",
        "court_name": "",
        "purpose": "",
        "judge": "",
        "next_hearing_date": "",
        "summary": t[:400],
    }
    dm = re.search(
        r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}|\d{4}-\d{2}-\d{2})",
        t,
        re.I,
    )
    if dm:
        out["hearing_date"] = _normalize_date(dm.group(1))
    nm = re.search(
        r"next\s+hearing\s+(?:on\s+)?(\d{1,2}\s+\w+\s+\d{4}|\d{4}-\d{2}-\d{2})",
        t,
        re.I,
    )
    if nm:
        out["next_hearing_date"] = _normalize_date(nm.group(1))
    jm = re.search(r"(?:Hon'ble|Justice)\s+([A-Z][A-Za-z\s\.]{2,40})", t)
    if jm:
        out["judge"] = jm.group(1).strip()
    cm = re.search(r"(?:High Court|Sessions Court|District Court|Magistrate)[^\n,]{0,60}", t, re.I)
    if cm:
        out["court_name"] = cm.group(0).strip()
    if re.search(r"adjourn", t, re.I):
        out["purpose"] = "Adjourned"
    elif re.search(r"bail", t, re.I):
        out["purpose"] = "Bail hearing"
    return out
