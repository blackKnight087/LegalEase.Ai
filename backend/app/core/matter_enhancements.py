"""Matter workspace enhancements — audit, suggestions, profiles, contradictions, export."""
from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.matter_repo import get_matter, list_matter_documents
from backend.app.core.practice_schema import ensure_practice_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_matter_audit(
    user_id: str,
    matter_id: str,
    action: str,
    detail: str = "",
) -> None:
    ensure_practice_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO matter_audit_log (log_id, matter_id, user_id, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), matter_id, str(user_id), action, detail[:500], _utc()),
    )
    conn.commit()
    conn.close()


def list_matter_audit(user_id: str, matter_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT log_id, action, detail, created_at, user_id
        FROM matter_audit_log WHERE matter_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (matter_id, limit),
    ).fetchall()
    conn.close()
    return [
        {"log_id": r[0], "action": r[1], "detail": r[2], "created_at": r[3], "user_id": r[4]}
        for r in rows
    ]


def add_timeline_suggestion(
    matter_id: str,
    *,
    title: str,
    event_date: str,
    description: str = "",
    source_doc_id: str = "",
) -> str:
    ensure_practice_schema()
    sid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO matter_timeline_suggestions
        (suggestion_id, matter_id, event_date, title, description, source_doc_id, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (sid, matter_id, event_date[:10], title.strip(), description.strip(), source_doc_id, _utc()),
    )
    conn.commit()
    conn.close()
    return sid


def list_timeline_suggestions(user_id: str, matter_id: str, status: str = "pending") -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    q = "SELECT suggestion_id, event_date, title, description, source_doc_id, status, created_at FROM matter_timeline_suggestions WHERE matter_id = ?"
    params: List[Any] = [matter_id]
    if status:
        q += " AND status = ?"
        params.append(status)
    q += " ORDER BY event_date ASC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "suggestion_id": r[0],
            "event_date": r[1],
            "title": r[2],
            "description": r[3],
            "source_doc_id": r[4],
            "status": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def approve_timeline_suggestion(user_id: str, matter_id: str, suggestion_id: str) -> bool:
    from backend.app.core.matter_workflow import add_timeline_event

    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT event_date, title, description FROM matter_timeline_suggestions
        WHERE suggestion_id = ? AND matter_id = ? AND status = 'pending'
        """,
        (suggestion_id, matter_id),
    ).fetchone()
    if not row:
        conn.close()
        return False
    add_timeline_event(
        user_id,
        matter_id,
        title=row[1],
        description=row[2] or "",
        event_date=row[0],
        event_type="auto",
    )
    conn.execute(
        "UPDATE matter_timeline_suggestions SET status = 'approved' WHERE suggestion_id = ?",
        (suggestion_id,),
    )
    conn.commit()
    conn.close()
    log_matter_audit(user_id, matter_id, "timeline_approved", row[1])
    return True


def reject_timeline_suggestion(matter_id: str, suggestion_id: str) -> bool:
    conn = connect_data_db()
    cur = conn.execute(
        "UPDATE matter_timeline_suggestions SET status = 'rejected' WHERE suggestion_id = ? AND matter_id = ?",
        (suggestion_id, matter_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def post_index_matter_hooks(user_id: str, matter_id: str, document_id: str, filename: str) -> None:
    """After document index: mark ready and enqueue full matter intelligence pipeline."""
    if not matter_id or not get_matter(user_id, matter_id):
        return
    conn = connect_data_db()
    conn.execute(
        "UPDATE documents SET index_status = ? WHERE id = ?",
        ("ready", document_id),
    )
    conn.commit()
    conn.close()
    log_matter_audit(user_id, matter_id, "document_indexed", filename)
    try:
        from backend.app.core.matter_intel_pipeline import enqueue_matter_intelligence

        enqueue_matter_intelligence(user_id, matter_id, document_id=document_id)
    except Exception:
        logger.exception("Failed to enqueue matter intelligence for %s", matter_id)


def _suggest_timeline_from_doc(user_id: str, matter_id: str, filename: str) -> None:
    prompt = (
        f"From document '{filename}', list up to 3 key dated events as lines: "
        "YYYY-MM-DD | title | short description"
    )
    from app import rag_query

    answer, _ = rag_query(str(user_id), prompt, k=6, matter_id=matter_id)
    import re

    for line in (answer or "").splitlines()[:5]:
        m = re.match(
            r"(\d{4}-\d{2}-\d{2})\s*[|\-–]\s*(.+?)(?:\s*[|\-–]\s*(.+))?$",
            line.strip(),
        )
        if m:
            add_timeline_suggestion(
                matter_id,
                title=m.group(2).strip()[:200],
                event_date=m.group(1),
                description=(m.group(3) or "").strip()[:400],
            )


def get_entity_profiles(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    """Entities with sample quotes from matter KB."""
    from backend.app.core.matter_entities import list_entities

    profiles: List[Dict[str, Any]] = []
    for ent in list_entities(user_id, matter_id):
        label = ent.get("label") or ""
        quotes: List[Dict[str, str]] = []
        if label:
            try:
                from backend.app.core.matter_intelligence import search_matter

                hits = search_matter(user_id, matter_id, label, k=3).get("results") or []
                for h in hits[:3]:
                    quotes.append(
                        {
                            "text": str(h.get("content", ""))[:400],
                            "filename": str(h.get("filename", "")),
                        }
                    )
            except Exception:
                pass
        profiles.append({**ent, "quotes": quotes, "role": ent.get("entity_type", "person")})
    return profiles


def list_contradictions(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    ensure_practice_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT contradiction_id, contradiction_type, topic, statement_a, statement_b,
               note, confidence, source_hint, created_at
        FROM matter_contradictions WHERE matter_id = ?
        ORDER BY confidence DESC, created_at DESC
        """,
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "contradiction_id": r[0],
            "contradiction_type": r[1],
            "topic": r[2],
            "statement_a": r[3],
            "statement_b": r[4],
            "note": r[5],
            "confidence": r[6],
            "source_hint": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


def extract_and_persist_contradictions(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Run contradiction analysis and persist pairs to matter_contradictions."""
    if not get_matter(user_id, matter_id):
        return {"pairs": [], "summary": ""}

    result = analyze_contradictions(user_id, matter_id)
    pairs = result.get("pairs") or []

    conn = connect_data_db()
    conn.execute("DELETE FROM matter_contradictions WHERE matter_id = ?", (matter_id,))
    for p in pairs:
        cid = str(uuid.uuid4())
        conn.execute(
            """
            INSERT INTO matter_contradictions
            (contradiction_id, matter_id, contradiction_type, topic, statement_a, statement_b,
             note, confidence, source_hint, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cid,
                matter_id,
                "statement",
                (p.get("topic") or "Contradiction")[:200],
                (p.get("statement_a") or "")[:1000],
                (p.get("statement_b") or "")[:1000],
                (p.get("note") or "")[:500],
                0.75,
                "",
                _utc(),
            ),
        )
    conn.commit()
    conn.close()
    result["pairs"] = list_contradictions(user_id, matter_id)
    return result


def analyze_contradictions(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Hearing-prep: witness contradictions from matter docs."""
    if not get_matter(user_id, matter_id):
        return {"pairs": [], "summary": ""}
    prompt = (
        "Identify contradictions between witness statements or documents in this matter. "
        "For each pair, state: Witness/topic | Statement A (with source hint) | Statement B | Why it matters."
    )
    try:
        from app import rag_query

        answer, chunks = rag_query(str(user_id), prompt, k=10, matter_id=matter_id)
        sources = [
            {
                "content": (c.get("content") or "")[:350],
                "filename": (c.get("metadata") or {}).get("filename", ""),
            }
            for c in (chunks or [])[:6]
        ]
        log_matter_audit(user_id, matter_id, "contradiction_analysis", "ran")
        return {"summary": answer or "", "sources": sources, "pairs": _parse_contradiction_pairs(answer or "")}
    except Exception as exc:
        return {"summary": str(exc), "sources": [], "pairs": []}


def _parse_contradiction_pairs(text: str) -> List[Dict[str, str]]:
    pairs: List[Dict[str, str]] = []
    for line in text.splitlines():
        if "|" in line and len(line) > 20:
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                pairs.append(
                    {
                        "topic": parts[0],
                        "statement_a": parts[1],
                        "statement_b": parts[2] if len(parts) > 2 else "",
                        "note": parts[3] if len(parts) > 3 else "",
                    }
                )
    return pairs[:12]


def export_matter_pack(user_id: str, matter_id: str) -> bytes:
    """ZIP: matter metadata JSON + timeline + doc list (+ file paths note)."""
    m = get_matter(user_id, matter_id)
    if not m:
        raise ValueError("Matter not found")
    from backend.app.core.matter_workflow import (
        get_matter_dashboard,
    )

    dash = get_matter_dashboard(user_id, matter_id)
    log_matter_audit(user_id, matter_id, "export_pack", "zip")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("matter.json", json.dumps(m, indent=2))
        zf.writestr("dashboard.json", json.dumps(dash, indent=2, default=str))
        readme = (
            f"Matter: {m.get('matter_name')}\n"
            f"Exported: {_utc()}\n"
            f"Documents: {len(dash.get('documents') or [])}\n"
        )
        zf.writestr("README.txt", readme)
        conn = connect_data_db()
        for doc in dash.get("documents") or []:
            row = conn.execute(
                "SELECT saved_path, filename FROM documents WHERE id = ?",
                (doc.get("document_id"),),
            ).fetchone()
            if row and row[0]:
                p = Path(row[0])
                if p.is_file():
                    zf.write(p, f"documents/{row[1] or p.name}")
        conn.close()
    buf.seek(0)
    return buf.getvalue()


def list_matter_members(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    rows = conn.execute(
        "SELECT member_id, user_id, role, created_at FROM matter_members WHERE matter_id = ?",
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {"member_id": r[0], "user_id": r[1], "role": r[2], "created_at": r[3]} for r in rows
    ]


def add_matter_member(
    owner_id: str,
    matter_id: str,
    *,
    member_user_id: str,
    role: str = "viewer",
) -> Dict[str, Any]:
    if not get_matter(owner_id, matter_id):
        raise ValueError("Matter not found")
    ensure_practice_schema()
    mid = str(uuid.uuid4())
    now = _utc()
    from backend.app.core.sql_compat import upsert_matter_member

    conn = connect_data_db()
    upsert_matter_member(
        conn,
        member_id=mid,
        matter_id=matter_id,
        user_id=member_user_id,
        role=role,
        created_at=now,
    )
    conn.commit()
    conn.close()
    log_matter_audit(owner_id, matter_id, "member_added", f"{member_user_id}:{role}")
    return {"member_id": mid, "user_id": member_user_id, "role": role}


def get_matter_notifications(user_id: str) -> List[Dict[str, Any]]:
    """Upcoming hearings/deadlines + pending index across matters."""
    from backend.app.core.matter_repo import list_matters
    from backend.app.core.matter_workflow import list_deadlines, list_hearings

    out: List[Dict[str, Any]] = []
    today = _utc()[:10]
    for m in list_matters(user_id, limit=50):
        mid = m["matter_id"]
        for h in list_hearings(user_id, mid):
            hd = (h.get("hearing_date") or "")[:10]
            if hd >= today:
                out.append(
                    {
                        "type": "hearing",
                        "matter_id": mid,
                        "matter_name": m.get("matter_name"),
                        "date": hd,
                        "title": h.get("purpose") or h.get("court_name") or "Hearing",
                    }
                )
        for d in list_deadlines(user_id, mid):
            if d.get("status") == "pending":
                dd = (d.get("due_date") or "")[:10]
                if dd >= today:
                    out.append(
                        {
                            "type": "deadline",
                            "matter_id": mid,
                            "matter_name": m.get("matter_name"),
                            "date": dd,
                            "title": d.get("title"),
                        }
                    )
        pending = list_timeline_suggestions(user_id, mid, status="pending")
        if pending:
            out.append(
                {
                    "type": "timeline_suggestions",
                    "matter_id": mid,
                    "matter_name": m.get("matter_name"),
                    "count": len(pending),
                    "title": f"{len(pending)} timeline suggestion(s) to review",
                }
            )
    out.sort(key=lambda x: x.get("date", "9999"))
    return out[:30]


def update_document_meta(
    user_id: str,
    document_id: str,
    *,
    privileged: Optional[bool] = None,
) -> bool:
    conn = connect_data_db()
    if privileged is not None:
        cur = conn.execute(
            "UPDATE documents SET privileged = ? WHERE id = ? AND uploader_id = ?",
            (1 if privileged else 0, document_id, str(user_id)),
        )
    else:
        cur = conn.execute("SELECT 1")
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok
