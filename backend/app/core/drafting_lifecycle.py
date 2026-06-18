"""Drafting Studio V4 — document lifecycle, precedents, filing, collaboration."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.drafting_v3 import (
    V3_WORKFLOW_STATUSES,
    ensure_workspace_v3_schema,
    export_document_v3,
    html_to_plain,
    transition_status,
)
from backend.app.core.drafting_workspace import (
    create_document,
    get_document,
    list_documents,
    update_document,
)
from backend.app.core.practice_schema import ensure_practice_schema

# In-memory presence for draft editing (single-process; Redis optional later)
_DRAFT_PRESENCE: Dict[str, Dict[str, Dict[str, Any]]] = {}

LIFECYCLE_STATUSES = V3_WORKFLOW_STATUSES


def ensure_v4_schema() -> None:
    ensure_workspace_v3_schema()
    ensure_practice_schema()
    conn = connect_data_db()
    stmts = [
        """
        CREATE TABLE IF NOT EXISTS firm_precedents (
            precedent_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            document_type TEXT NOT NULL DEFAULT 'custom',
            content TEXT NOT NULL,
            tags_json TEXT NOT NULL DEFAULT '[]',
            court TEXT NOT NULL DEFAULT '',
            judge TEXT NOT NULL DEFAULT '',
            practice_area TEXT NOT NULL DEFAULT '',
            outcome TEXT NOT NULL DEFAULT '',
            author TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            source_draft_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_precedents_user ON firm_precedents(user_id)",
        "CREATE INDEX IF NOT EXISTS idx_precedents_type ON firm_precedents(document_type)",
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_timeline (
            event_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_draft_timeline_draft ON workspace_draft_timeline(draft_id)",
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_assignments (
            assignment_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            assignee_user_id TEXT NOT NULL,
            assignee_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL DEFAULT 'reviewer',
            due_date TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_draft_assign_draft ON workspace_draft_assignments(draft_id)",
        "CREATE INDEX IF NOT EXISTS idx_draft_assign_user ON workspace_draft_assignments(assignee_user_id)",
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_annexures (
            annexure_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            label TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_signatures (
            signature_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            party_label TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'signer',
            order_num INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'pending',
            signed_at TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_locks (
            draft_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            user_name TEXT NOT NULL DEFAULT '',
            locked_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS workspace_review_suggestions (
            suggestion_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            author_name TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """,
        "ALTER TABLE workspace_drafts ADD COLUMN filing_readiness_score INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE workspace_drafts ADD COLUMN health_score INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE workspace_drafts ADD COLUMN review_due_date TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE workspace_drafts ADD COLUMN approval_deadline TEXT NOT NULL DEFAULT ''",
    ]
    for stmt in stmts:
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_draft_event(
    user_id: str,
    draft_id: str,
    action: str,
    *,
    detail: str = "",
    user_name: str = "",
) -> None:
    ensure_v4_schema()
    doc = get_document(user_id, draft_id)
    if not doc:
        return
    eid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_draft_timeline
        (event_id, draft_id, user_id, user_name, action, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (eid, draft_id, str(user_id), user_name or "User", action, detail[:2000], now),
    )
    conn.commit()
    conn.close()
    mid = doc.get("matter_id") or ""
    if mid:
        try:
            from backend.app.core.matter_workflow import add_timeline_event

            add_timeline_event(
                user_id,
                mid,
                title=f"Draft: {action}",
                description=f"{doc.get('title', '')} — {detail[:200]}" if detail else doc.get("title", ""),
                event_type="drafting",
            )
        except Exception:
            pass


def list_draft_timeline(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_v4_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT event_id, user_id, user_name, action, detail, created_at
        FROM workspace_draft_timeline WHERE draft_id = ?
        ORDER BY created_at DESC LIMIT 200
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "event_id": r[0],
            "user_id": r[1],
            "user_name": r[2],
            "action": r[3],
            "detail": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def control_center(user_id: str) -> Dict[str, Any]:
    ensure_v4_schema()
    docs = list_documents(user_id, limit=200)
    by_status: Dict[str, List[Dict[str, Any]]] = {s: [] for s in LIFECYCLE_STATUSES}
    awaiting: List[Dict[str, Any]] = []
    near_deadline: List[Dict[str, Any]] = []
    reviewer_queue: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)

    conn = connect_data_db()
    assign_rows = conn.execute(
        """
        SELECT a.assignment_id, a.draft_id, a.role, a.due_date, a.status, d.title, d.status
        FROM workspace_draft_assignments a
        JOIN workspace_drafts d ON d.draft_id = a.draft_id
        WHERE a.assignee_user_id = ? AND a.status = 'pending'
        ORDER BY a.due_date ASC LIMIT 50
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()

    for r in assign_rows:
        reviewer_queue.append(
            {
                "assignment_id": r[0],
                "draft_id": r[1],
                "role": r[2],
                "due_date": r[3],
                "assignment_status": r[4],
                "title": r[5],
                "document_status": r[6],
            }
        )

    recent_activity: List[Dict[str, Any]] = []
    conn = connect_data_db()
    act_rows = conn.execute(
        """
        SELECT t.action, t.detail, t.user_name, t.created_at, t.draft_id, d.title
        FROM workspace_draft_timeline t
        JOIN workspace_drafts d ON d.draft_id = t.draft_id
        WHERE d.user_id = ?
        ORDER BY t.created_at DESC LIMIT 25
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    for r in act_rows:
        recent_activity.append(
            {
                "action": r[0],
                "detail": r[1],
                "user_name": r[2],
                "created_at": r[3],
                "draft_id": r[4],
                "title": r[5],
            }
        )

    for d in docs:
        st = d.get("status") or "draft"
        if st in by_status:
            by_status[st].append(_doc_card(d))
        if st in ("in_review", "partner_review", "needs_revision"):
            awaiting.append(_doc_card(d))
        due = d.get("review_due_date") or d.get("approval_deadline") or ""
        if due:
            try:
                dt = datetime.fromisoformat(due.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt - now < timedelta(days=3):
                    near_deadline.append(_doc_card(d))
            except Exception:
                pass

    health_avg = 0
    scores = [int(d.get("health_score") or 0) for d in docs if d.get("health_score")]
    if scores:
        health_avg = sum(scores) // len(scores)

    return {
        "columns": {s: by_status[s][:20] for s in LIFECYCLE_STATUSES},
        "counts": {s: len(by_status[s]) for s in LIFECYCLE_STATUSES},
        "awaiting_action": awaiting[:15],
        "reviewer_queue": reviewer_queue,
        "near_deadline": near_deadline[:15],
        "recent_activity": recent_activity,
        "health_score_avg": health_avg,
        "analytics": document_analytics(user_id),
    }


def _quick_doc_scores(d: Dict[str, Any]) -> tuple:
    hs = int(d.get("health_score") or 0)
    fs = int(d.get("filing_readiness_score") or 0)
    if hs > 0 and fs > 0:
        return hs, fs
    try:
        from backend.app.core.drafting_clause_intel import analyze_document
        from backend.app.core.drafting_v3 import html_to_plain

        text = html_to_plain(d.get("content") or "")
        if len(text) < 40:
            return hs, fs
        analysis = analyze_document(text, document_type=d.get("document_type") or "contract")
        score = int(analysis.get("clause_risk_score") or 0)
        return score or hs, score or fs
    except Exception:
        return hs, fs


def _doc_snippet(d: Dict[str, Any], limit: int = 100) -> str:
    try:
        from backend.app.core.drafting_v3 import html_to_plain

        plain = html_to_plain(d.get("content") or "").replace("\n", " ").strip()
        if len(plain) <= limit:
            return plain
        return plain[: limit - 1] + "…"
    except Exception:
        return ""


def _doc_card(d: Dict[str, Any]) -> Dict[str, Any]:
    health, filing = _quick_doc_scores(d)
    return {
        "draft_id": d.get("draft_id"),
        "title": d.get("title"),
        "status": d.get("status"),
        "document_type": d.get("document_type"),
        "matter_id": d.get("matter_id"),
        "updated_at": d.get("updated_at"),
        "health_score": health,
        "filing_readiness_score": filing,
        "version_count": d.get("version_count", 1),
        "snippet": _doc_snippet(d),
    }


def document_analytics(user_id: str) -> Dict[str, Any]:
    docs = list_documents(user_id, limit=500)
    by_type: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for d in docs:
        by_type[d.get("document_type") or "custom"] = by_type.get(d.get("document_type") or "custom", 0) + 1
        by_status[d.get("status") or "draft"] = by_status.get(d.get("status") or "draft", 0) + 1
    ensure_v4_schema()
    conn = connect_data_db()
    prec_count = conn.execute(
        "SELECT COUNT(*) FROM firm_precedents WHERE user_id = ?", (str(user_id),)
    ).fetchone()[0]
    conn.close()
    return {
        "document_volume": len(docs),
        "by_practice_type": by_type,
        "by_status": by_status,
        "precedent_count": prec_count,
    }


def create_precedent(
    user_id: str,
    *,
    title: str,
    content: str,
    document_type: str = "custom",
    matter_id: str = "",
    tags: Optional[List[str]] = None,
    court: str = "",
    judge: str = "",
    practice_area: str = "",
    outcome: str = "",
    author: str = "",
    source_draft_id: str = "",
) -> Dict[str, Any]:
    ensure_v4_schema()
    pid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO firm_precedents
        (precedent_id, user_id, matter_id, title, document_type, content, tags_json,
         court, judge, practice_area, outcome, author, version, source_draft_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            pid,
            str(user_id),
            matter_id or "",
            title.strip(),
            document_type or "custom",
            content,
            json.dumps(tags or []),
            court,
            judge,
            practice_area,
            outcome,
            author,
            source_draft_id,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    return get_precedent(user_id, pid) or {}


def promote_draft_to_precedent(
    user_id: str,
    draft_id: str,
    *,
    tags: Optional[List[str]] = None,
    outcome: str = "approved",
) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    p = create_precedent(
        user_id,
        title=doc["title"],
        content=doc["content"],
        document_type=doc.get("document_type") or "custom",
        matter_id=doc.get("matter_id") or "",
        tags=tags,
        outcome=outcome,
        source_draft_id=draft_id,
    )
    log_draft_event(user_id, draft_id, "promoted_precedent", detail=p.get("precedent_id", ""))
    return {"precedent": p}


def get_precedent(user_id: str, precedent_id: str) -> Optional[Dict[str, Any]]:
    ensure_v4_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT precedent_id, user_id, matter_id, title, document_type, content, tags_json,
               court, judge, practice_area, outcome, author, version, source_draft_id, created_at, updated_at
        FROM firm_precedents WHERE precedent_id = ? AND user_id = ?
        """,
        (precedent_id, str(user_id)),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return _precedent_row(row)


def _precedent_row(row: tuple) -> Dict[str, Any]:
    return {
        "precedent_id": row[0],
        "user_id": row[1],
        "matter_id": row[2],
        "title": row[3],
        "document_type": row[4],
        "content": row[5],
        "tags": json.loads(row[6] or "[]"),
        "court": row[7],
        "judge": row[8],
        "practice_area": row[9],
        "outcome": row[10],
        "author": row[11],
        "version": row[12],
        "source_draft_id": row[13],
        "created_at": row[14],
        "updated_at": row[15],
    }


def list_precedents(
    user_id: str,
    *,
    q: str = "",
    document_type: str = "",
    practice_area: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    ensure_v4_schema()
    conn = connect_data_db()
    sql = """
        SELECT precedent_id, user_id, matter_id, title, document_type, content, tags_json,
               court, judge, practice_area, outcome, author, version, source_draft_id, created_at, updated_at
        FROM firm_precedents WHERE user_id = ?
    """
    params: List[Any] = [str(user_id)]
    if document_type:
        sql += " AND document_type = ?"
        params.append(document_type)
    if practice_area:
        sql += " AND practice_area = ?"
        params.append(practice_area)
    if q.strip():
        sql += " AND (title LIKE ? OR content LIKE ? OR tags_json LIKE ?)"
        like = f"%{q.strip()}%"
        params.extend([like, like, like])
    sql += " ORDER BY updated_at DESC LIMIT ?"
    params.append(min(limit, 100))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_precedent_row(r) for r in rows]


def search_precedents_ai(user_id: str, query: str, *, limit: int = 8) -> Dict[str, Any]:
    """Similarity search over firm precedents — no hallucination."""
    q = (query or "").strip().lower()
    if not q:
        return {"results": [], "query": query}
    all_p = list_precedents(user_id, limit=200)
    tokens = set(re.findall(r"\w{3,}", q))
    scored: List[Tuple[float, Dict[str, Any]]] = []
    for p in all_p:
        text = f"{p.get('title', '')} {p.get('document_type', '')} {p.get('practice_area', '')} {html_to_plain(p.get('content', ''))[:3000]}".lower()
        ptokens = set(re.findall(r"\w{3,}", text))
        if not tokens:
            continue
        overlap = len(tokens & ptokens) / max(len(tokens), 1)
        type_bonus = 0.2 if any(t in (p.get("document_type") or "") for t in tokens) else 0
        score = overlap + type_bonus
        if score > 0.15:
            scored.append((score, {**p, "content": (p.get("content") or "")[:500], "confidence": round(min(score, 1.0), 2), "source": f"precedent:{p.get('precedent_id')}"}))
    scored.sort(key=lambda x: -x[0])
    return {"results": [s[1] for s in scored[:limit]], "query": query}


def filing_readiness(user_id: str, draft_id: str) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    text = html_to_plain(doc.get("content") or "")
    checks: List[Dict[str, Any]] = []
    score = 100

    def fail(key: str, msg: str, penalty: int = 10):
        nonlocal score
        checks.append({"check": key, "passed": False, "message": msg})
        score = max(0, score - penalty)

    def ok(key: str, msg: str = "OK"):
        checks.append({"check": key, "passed": True, "message": msg})

    if not re.search(r"\bsign|execut|witness\b", text, re.I):
        fail("signatures", "Missing signature / execution block")
    else:
        ok("signatures")

    if not re.search(r"\bparty|petitioner|respondent|plaintiff|defendant\b", text, re.I):
        fail("parties", "Parties not clearly identified")
    else:
        ok("parties")

    if not re.search(r"\bdate|\d{1,2}\s+\w+\s+\d{4}\b", text, re.I):
        fail("dates", "Dates may be missing")
    else:
        ok("dates")

    undefined = re.findall(r"\b(TBD|____+|\[.*?\]|XXX)\b", text, re.I)
    if undefined:
        fail("undefined_terms", f"Placeholder terms found: {', '.join(undefined[:5])}", 15)
    else:
        ok("undefined_terms")

    if len(text) < 400:
        fail("sections", "Document appears incomplete (very short)", 20)
    else:
        ok("sections")

    if not re.search(r"^#|\n##", text) and "<h" not in (doc.get("content") or ""):
        fail("formatting", "Consider structured headings")
    else:
        ok("formatting")

    annexures = list_annexures(user_id, draft_id)
    if doc.get("document_type") in ("petition", "affidavit", "court_filing") and not annexures:
        fail("attachments", "No annexures attached for court filing", 10)
    else:
        ok("attachments", f"{len(annexures)} annexure(s)")

    if not (doc.get("jurisdiction") or re.search(r"\bcourt|tribunal|jurisdiction\b", text, re.I)):
        fail("jurisdiction", "Jurisdiction / court not specified")
    else:
        ok("jurisdiction")

    if not doc.get("matter_id"):
        fail("matter_link", "Document not linked to a matter", 5)
    else:
        ok("matter_link")

    ensure_v4_schema()
    conn = connect_data_db()
    try:
        conn.execute(
            "UPDATE workspace_drafts SET filing_readiness_score = ?, health_score = ? WHERE draft_id = ? AND user_id = ?",
            (score, score, draft_id, str(user_id)),
        )
        conn.commit()
    except Exception:
        pass
    conn.close()
    log_draft_event(user_id, draft_id, "filing_readiness_check", detail=f"score={score}")
    return {
        "filing_readiness_score": score,
        "checks": checks,
        "ready_to_file": score >= 75 and not any(not c["passed"] for c in checks if c["check"] in ("signatures", "parties", "matter_link")),
    }


def assign_reviewer(
    user_id: str,
    draft_id: str,
    *,
    assignee_user_id: str,
    assignee_name: str = "",
    role: str = "reviewer",
    due_date: str = "",
) -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_v4_schema()
    aid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_draft_assignments
        (assignment_id, draft_id, assignee_user_id, assignee_name, role, due_date, status, created_by, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (aid, draft_id, assignee_user_id, assignee_name or "Reviewer", role, due_date or "", str(user_id), now),
    )
    if due_date:
        try:
            conn.execute(
                "UPDATE workspace_drafts SET review_due_date = ? WHERE draft_id = ?",
                (due_date, draft_id),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "assigned", detail=f"{role}:{assignee_user_id}")
    update_document(user_id, draft_id, status="in_review", change_summary="Sent for review")
    return {"assignment_id": aid, "role": role}


def list_annexures(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_v4_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT annexure_id, label, content, sort_order, created_at
        FROM workspace_draft_annexures WHERE draft_id = ?
        ORDER BY sort_order ASC, created_at ASC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {"annexure_id": r[0], "label": r[1], "content": r[2], "sort_order": r[3], "created_at": r[4]}
        for r in rows
    ]


def add_annexure(user_id: str, draft_id: str, *, label: str, content: str = "", sort_order: int = 0) -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_v4_schema()
    aid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_draft_annexures (annexure_id, draft_id, label, content, sort_order, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (aid, draft_id, label.strip(), content, sort_order, _utc()),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "annexure_added", detail=label)
    return {"annexure_id": aid, "label": label}


def add_review_suggestion(user_id: str, draft_id: str, body: str, *, author_name: str = "") -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_v4_schema()
    sid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_review_suggestions
        (suggestion_id, draft_id, user_id, author_name, body, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'open', ?)
        """,
        (sid, draft_id, str(user_id), author_name or "Reviewer", body.strip(), now),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "suggestion", detail=body[:100])
    return {"suggestion_id": sid}


def resolve_suggestion(user_id: str, draft_id: str, suggestion_id: str, accept: bool) -> Dict[str, Any]:
    ensure_v4_schema()
    status = "accepted" if accept else "rejected"
    conn = connect_data_db()
    conn.execute(
        "UPDATE workspace_review_suggestions SET status = ? WHERE suggestion_id = ? AND draft_id = ?",
        (status, suggestion_id, draft_id),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, f"suggestion_{status}", detail=suggestion_id)
    return {"ok": True, "status": status}


def list_review_workspace(user_id: str, draft_id: str) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    ensure_v4_schema()
    conn = connect_data_db()
    suggestions = conn.execute(
        """
        SELECT suggestion_id, user_id, author_name, body, status, created_at
        FROM workspace_review_suggestions WHERE draft_id = ?
        ORDER BY created_at ASC
        """,
        (draft_id,),
    ).fetchall()
    assignments = conn.execute(
        """
        SELECT assignment_id, assignee_user_id, assignee_name, role, due_date, status, created_at
        FROM workspace_draft_assignments WHERE draft_id = ?
        ORDER BY created_at ASC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    from backend.app.core.drafting_workspace import list_comments

    readiness = filing_readiness(user_id, draft_id)
    checklist = [
        {"id": "parties", "label": "Parties identified", "done": any(c["passed"] for c in readiness.get("checks", []) if c["check"] == "parties")},
        {"id": "signatures", "label": "Execution block", "done": any(c["passed"] for c in readiness.get("checks", []) if c["check"] == "signatures")},
        {"id": "jurisdiction", "label": "Jurisdiction stated", "done": any(c["passed"] for c in readiness.get("checks", []) if c["check"] == "jurisdiction")},
        {"id": "matter", "label": "Linked to matter", "done": bool(doc.get("matter_id"))},
    ]
    return {
        "document": doc,
        "suggestions": [
            {"suggestion_id": s[0], "user_id": s[1], "author_name": s[2], "body": s[3], "status": s[4], "created_at": s[5]}
            for s in suggestions
        ],
        "assignments": [
            {"assignment_id": a[0], "assignee_user_id": a[1], "assignee_name": a[2], "role": a[3], "due_date": a[4], "status": a[5], "created_at": a[6]}
            for a in assignments
        ],
        "comments": list_comments(user_id, draft_id),
        "timeline": list_draft_timeline(user_id, draft_id),
        "checklist": checklist,
        "filing_readiness": readiness,
    }


def set_signature_workflow(
    user_id: str,
    draft_id: str,
    signers: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_v4_schema()
    conn = connect_data_db()
    conn.execute("DELETE FROM workspace_draft_signatures WHERE draft_id = ?", (draft_id,))
    for i, s in enumerate(signers):
        conn.execute(
            """
            INSERT INTO workspace_draft_signatures
            (signature_id, draft_id, party_label, role, order_num, status, signed_at)
            VALUES (?, ?, ?, ?, ?, 'pending', '')
            """,
            (str(uuid.uuid4()), draft_id, s.get("party_label", f"Party {i+1}"), s.get("role", "signer"), int(s.get("order", i + 1))),
        )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "signature_workflow", detail=f"{len(signers)} signers")
    return {"signers": len(signers)}


def list_signatures(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_v4_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT signature_id, party_label, role, order_num, status, signed_at
        FROM workspace_draft_signatures WHERE draft_id = ?
        ORDER BY order_num ASC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {"signature_id": r[0], "party_label": r[1], "role": r[2], "order_num": r[3], "status": r[4], "signed_at": r[5]}
        for r in rows
    ]


def mark_signed(user_id: str, draft_id: str, signature_id: str) -> Dict[str, Any]:
    ensure_v4_schema()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        "UPDATE workspace_draft_signatures SET status = 'signed', signed_at = ? WHERE signature_id = ?",
        (now, signature_id),
    )
    conn.commit()
    conn.close()
    sigs = list_signatures(user_id, draft_id)
    if sigs and all(s["status"] == "signed" for s in sigs):
        transition_status(user_id, draft_id, "executed")
        log_draft_event(user_id, draft_id, "executed", detail="All signatures complete")
    return {"ok": True}


def acquire_lock(user_id: str, draft_id: str, *, user_name: str = "") -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_v4_schema()
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(minutes=15)).isoformat()
    conn = connect_data_db()
    row = conn.execute("SELECT user_id, user_name, expires_at FROM workspace_draft_locks WHERE draft_id = ?", (draft_id,)).fetchone()
    if row and row[0] != str(user_id):
        try:
            exp = datetime.fromisoformat(str(row[2]).replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if exp > now:
                conn.close()
                return {"locked": True, "locked_by": row[1] or row[0], "error": "Document locked by another user"}
        except Exception:
            pass
    conn.execute(
        """
        INSERT INTO workspace_draft_locks (draft_id, user_id, user_name, locked_at, expires_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(draft_id) DO UPDATE SET user_id=excluded.user_id, user_name=excluded.user_name,
        locked_at=excluded.locked_at, expires_at=excluded.expires_at
        """,
        (draft_id, str(user_id), user_name or "Editor", now.isoformat(), expires),
    )
    conn.commit()
    conn.close()
    _DRAFT_PRESENCE.setdefault(draft_id, {})[str(user_id)] = {"user_name": user_name or "Editor", "at": now.isoformat()}
    return {"locked": True, "locked_by_you": True}


def release_lock(user_id: str, draft_id: str) -> Dict[str, Any]:
    ensure_v4_schema()
    conn = connect_data_db()
    conn.execute("DELETE FROM workspace_draft_locks WHERE draft_id = ? AND user_id = ?", (draft_id, str(user_id)))
    conn.commit()
    conn.close()
    _DRAFT_PRESENCE.get(draft_id, {}).pop(str(user_id), None)
    return {"ok": True}


def draft_presence(draft_id: str) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    active = []
    for uid, meta in list(_DRAFT_PRESENCE.get(draft_id, {}).items()):
        try:
            at = datetime.fromisoformat(meta["at"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if now - at < timedelta(seconds=45):
                active.append({"user_id": uid, "user_name": meta.get("user_name", "User")})
        except Exception:
            pass
    ensure_v4_schema()
    conn = connect_data_db()
    lock = conn.execute(
        "SELECT user_id, user_name, expires_at FROM workspace_draft_locks WHERE draft_id = ?", (draft_id,)
    ).fetchone()
    conn.close()
    lock_info = None
    if lock:
        lock_info = {"user_id": lock[0], "user_name": lock[1], "expires_at": lock[2]}
    return {"editors": active, "lock": lock_info}


def heartbeat_presence(user_id: str, draft_id: str, *, user_name: str = "") -> Dict[str, Any]:
    _DRAFT_PRESENCE.setdefault(draft_id, {})[str(user_id)] = {
        "user_name": user_name or "Editor",
        "at": _utc(),
    }
    return draft_presence(draft_id)


def matter_drafting_hub(user_id: str, matter_id: str) -> Dict[str, Any]:
    from backend.app.core.matter_repo import get_matter

    if not get_matter(user_id, matter_id):
        return {"error": "Matter not found"}
    docs = [d for d in list_documents(user_id, limit=100) if d.get("matter_id") == matter_id]
    by_status: Dict[str, List[Dict[str, Any]]] = {}
    for d in docs:
        st = d.get("status") or "draft"
        by_status.setdefault(st, []).append(_doc_card(d))
    return {
        "matter_id": matter_id,
        "documents": [_doc_card(d) for d in docs],
        "by_status": by_status,
        "timeline": _matter_draft_timeline(user_id, matter_id),
    }


def _matter_draft_timeline(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    ensure_v4_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT t.action, t.detail, t.user_name, t.created_at, t.draft_id, d.title
        FROM workspace_draft_timeline t
        JOIN workspace_drafts d ON d.draft_id = t.draft_id
        WHERE d.user_id = ? AND d.matter_id = ?
        ORDER BY t.created_at DESC LIMIT 40
        """,
        (str(user_id), matter_id),
    ).fetchall()
    conn.close()
    return [
        {"action": r[0], "detail": r[1], "user_name": r[2], "created_at": r[3], "draft_id": r[4], "title": r[5]}
        for r in rows
    ]


def create_matter_draft(
    user_id: str,
    matter_id: str,
    *,
    title: str = "",
    document_type: str = "custom",
    template_id: str = "",
) -> Dict[str, Any]:
    from backend.app.core.drafting_v3 import matter_variables, render_v3_template

    vars_ = matter_variables(user_id, matter_id)
    content = f"# {title or 'Matter draft'}\n\n"
    if template_id:
        out = render_v3_template(user_id, template_id, matter_id=matter_id, extra_vars=vars_)
        content = out.get("rendered") or content
    else:
        content = (
            f"# {title or vars_.get('MatterName') or 'Draft'}\n\n"
            f"**Client:** {vars_.get('ClientName', '')}\n"
            f"**Case No.:** {vars_.get('CaseNumber', '')}\n"
            f"**Court:** {vars_.get('CourtName', '')}\n\n"
        )
    doc = create_document(
        user_id,
        title=title or f"{vars_.get('MatterName', 'Matter')} — Draft",
        document_type=document_type,
        content=content,
        matter_id=matter_id,
        status="draft",
    )
    log_draft_event(user_id, doc["draft_id"], "created", detail=f"matter={matter_id}")
    return {"document": doc}


def build_court_package(
    user_id: str,
    matter_id: str,
    draft_ids: List[str],
    *,
    include_cover: bool = True,
    pack_format: str = "zip",
) -> Tuple[bytes, str, str]:
    import zipfile
    from io import BytesIO

    from backend.app.core.drafting_v3 import matter_variables
    from backend.app.core.drafting_export_v4 import export_court_pdf

    vars_ = matter_variables(user_id, matter_id)
    pdfs: List[Tuple[str, bytes]] = []
    if include_cover:
        cover = f"COURT FILING PACKAGE\n\nMatter: {vars_.get('MatterName', '')}\nClient: {vars_.get('ClientName', '')}\nCase: {vars_.get('CaseNumber', '')}\nCourt: {vars_.get('CourtName', '')}\n"
        data, fname, _ = export_court_pdf(cover, title="Cover Page", matter_meta=vars_)
        pdfs.append((fname, data))
    index_lines = ["INDEX\n"]
    for i, did in enumerate(draft_ids, 1):
        doc = get_document(user_id, did)
        if not doc:
            continue
        annexures = list_annexures(user_id, did)
        data, fname, _ = export_court_pdf(
            doc["content"],
            title=doc["title"],
            matter_meta=vars_,
            annexures=annexures,
        )
        pdfs.append((fname, data))
        index_lines.append(f"{i}. {doc['title']}")
        for j, ax in enumerate(annexures, 1):
            ax_data, ax_name, _ = export_court_pdf(
                ax.get("content") or "",
                title=ax.get("label", f"Annexure {j}"),
                matter_meta=vars_,
            )
            pdfs.append((ax_name, ax_data))
            index_lines.append(f"   {i}.{j} {ax.get('label', 'Annexure')}")
    idx_body = "\n".join(index_lines)
    idx_data, idx_name, _ = export_court_pdf(idx_body, title="Index", matter_meta=vars_)
    pdfs.insert(1 if include_cover else 0, (idx_name, idx_data))

    if not pdfs:
        raise ValueError("No documents in package")

    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname, data in pdfs:
            zf.writestr(fname, data)
    buf.seek(0)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d")
    return buf.read(), f"court_package_{matter_id[:8]}_{ts}.zip", "application/zip"


def matter_court_bundle_automation(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Create petition + affidavit + vakalatnama drafts linked to matter."""
    from backend.app.core.drafting_v3 import render_v3_template

    created = []
    for tpl_id, dtype in [
        ("petition", "petition"),
        ("affidavit", "affidavit"),
        ("legal_notice", "notice"),
    ]:
        out = create_matter_draft(user_id, matter_id, document_type=dtype, template_id=tpl_id)
        if out.get("document"):
            created.append(out["document"])
    if created:
        log_draft_event(user_id, created[0]["draft_id"], "bundle_automation", detail=f"{len(created)} docs")
    return {"documents": created, "matter_id": matter_id}
