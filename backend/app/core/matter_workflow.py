"""Matter dashboard workflow — timeline, hearings, tasks, deadlines."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import table_columns_set
from backend.app.core.matter_repo import (
    get_matter,
    list_matter_documents,
    list_matter_notes,
    list_matters,
)
from backend.app.core.practice_schema import ensure_practice_schema


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_matter(user_id: str, matter_id: str) -> Dict[str, Any]:
    m = get_matter(user_id, matter_id)
    if not m:
        raise ValueError("Matter not found")
    return m


def add_timeline_event(
    user_id: str,
    matter_id: str,
    *,
    title: str,
    description: str = "",
    event_date: str = "",
    event_type: str = "general",
) -> Dict[str, Any]:
    _require_matter(user_id, matter_id)
    ensure_practice_schema()
    eid = str(uuid.uuid4())
    now = _utc()
    when = (event_date or now)[:10]
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO matter_timeline
        (event_id, matter_id, event_date, title, description, event_type, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (eid, matter_id, when, title.strip(), description.strip(), event_type, now),
    )
    conn.execute("UPDATE matters SET updated_at = ? WHERE matter_id = ?", (now, matter_id))
    conn.commit()
    conn.close()
    return {"event_id": eid, "matter_id": matter_id, "event_date": when, "title": title}


def list_timeline(user_id: str, matter_id: str, limit: int = 80) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT event_id, event_date, title, description, event_type, created_at
        FROM matter_timeline WHERE matter_id = ?
        ORDER BY event_date DESC, created_at DESC LIMIT ?
        """,
        (matter_id, limit),
    ).fetchall()
    conn.close()
    return [
        {
            "event_id": r[0],
            "event_date": r[1],
            "title": r[2],
            "description": r[3],
            "event_type": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def add_hearing(
    user_id: str,
    matter_id: str,
    *,
    hearing_date: str,
    court_name: str = "",
    purpose: str = "",
    notes: str = "",
    judge: str = "",
    arguments: str = "",
    observations: str = "",
    next_hearing_date: str = "",
    summary: str = "",
) -> Dict[str, Any]:
    _require_matter(user_id, matter_id)
    ensure_practice_schema()
    hid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    hcols = table_columns_set(conn, "matter_hearings")
    if "judge" in hcols:
        conn.execute(
            """
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at,
             judge, arguments, observations, next_hearing_date, summary)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?, ?, ?, ?, ?, ?)
            """,
            (
                hid,
                matter_id,
                hearing_date,
                court_name,
                purpose,
                notes,
                now,
                judge,
                arguments,
                observations,
                next_hearing_date,
                summary,
            ),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_hearings
            (hearing_id, matter_id, hearing_date, court_name, purpose, notes, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'scheduled', ?)
            """,
            (hid, matter_id, hearing_date, court_name, purpose, notes, now),
        )
    conn.commit()
    conn.close()
    add_timeline_event(
        user_id,
        matter_id,
        title=f"Hearing: {purpose or court_name or 'Scheduled'}",
        description=notes,
        event_date=hearing_date[:10],
        event_type="hearing",
    )
    return {"hearing_id": hid, "matter_id": matter_id, "hearing_date": hearing_date}


def list_hearings(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    hcols = table_columns_set(conn, "matter_hearings")
    if "judge" in hcols:
        rows = conn.execute(
            """
            SELECT hearing_id, hearing_date, court_name, purpose, notes, status, created_at,
                   judge, arguments, observations, next_hearing_date, summary
            FROM matter_hearings WHERE matter_id = ?
            ORDER BY hearing_date ASC
            """,
            (matter_id,),
        ).fetchall()
        conn.close()
        return [
            {
                "hearing_id": r[0],
                "hearing_date": r[1],
                "court_name": r[2],
                "purpose": r[3],
                "notes": r[4],
                "status": r[5],
                "created_at": r[6],
                "judge": r[7],
                "arguments": r[8],
                "observations": r[9],
                "next_hearing_date": r[10],
                "summary": r[11],
            }
            for r in rows
        ]
    rows = conn.execute(
        """
        SELECT hearing_id, hearing_date, court_name, purpose, notes, status, created_at
        FROM matter_hearings WHERE matter_id = ?
        ORDER BY hearing_date ASC
        """,
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "hearing_id": r[0],
            "hearing_date": r[1],
            "court_name": r[2],
            "purpose": r[3],
            "notes": r[4],
            "status": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def add_task(
    user_id: str,
    matter_id: str,
    *,
    title: str,
    due_date: str = "",
    assignee: str = "",
    task_source: str = "manual",
) -> Dict[str, Any]:
    _require_matter(user_id, matter_id)
    ensure_practice_schema()
    tid = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    tcols = table_columns_set(conn, "matter_tasks")
    if "task_source" in tcols:
        conn.execute(
            """
            INSERT INTO matter_tasks
            (task_id, matter_id, title, due_date, status, assignee, created_at, updated_at, task_source)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?, ?)
            """,
            (tid, matter_id, title.strip(), due_date, assignee, now, now, task_source),
        )
    else:
        conn.execute(
            """
            INSERT INTO matter_tasks
            (task_id, matter_id, title, due_date, status, assignee, created_at, updated_at)
            VALUES (?, ?, ?, ?, 'open', ?, ?, ?)
            """,
            (tid, matter_id, title.strip(), due_date, assignee, now, now),
        )
    conn.commit()
    conn.close()
    return {"task_id": tid, "title": title, "due_date": due_date, "status": "open"}


def update_task(
    user_id: str,
    matter_id: str,
    task_id: str,
    **fields: Any,
) -> Optional[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return None
    allowed = {"title", "due_date", "status", "assignee"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return None
    updates["updated_at"] = _utc()
    sets = ", ".join(f"{k} = ?" for k in updates)
    conn = connect_data_db()
    conn.execute(
        f"UPDATE matter_tasks SET {sets} WHERE task_id = ? AND matter_id = ?",
        (*updates.values(), task_id, matter_id),
    )
    conn.commit()
    conn.close()
    if updates.get("status") == "done":
        add_timeline_event(
            user_id,
            matter_id,
            title=f"Task completed: {updates.get('title', 'Task')}",
            event_type="task",
        )
    return {"task_id": task_id, **updates}


def delete_task(user_id: str, matter_id: str, task_id: str) -> bool:
    if not get_matter(user_id, matter_id):
        return False
    ensure_practice_schema()
    conn = connect_data_db()
    cur = conn.execute(
        "DELETE FROM matter_tasks WHERE task_id = ? AND matter_id = ?",
        (task_id, matter_id),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_tasks(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT task_id, title, due_date, status, assignee, created_at, updated_at
        FROM matter_tasks WHERE matter_id = ?
        ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, due_date ASC
        """,
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "task_id": r[0],
            "title": r[1],
            "due_date": r[2],
            "status": r[3],
            "assignee": r[4],
            "created_at": r[5],
            "updated_at": r[6],
        }
        for r in rows
    ]


def add_deadline(
    user_id: str,
    matter_id: str,
    *,
    title: str,
    due_date: str,
    deadline_type: str = "filing",
    notes: str = "",
) -> Dict[str, Any]:
    _require_matter(user_id, matter_id)
    ensure_practice_schema()
    did = str(uuid.uuid4())
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO matter_deadlines
        (deadline_id, matter_id, title, due_date, deadline_type, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (did, matter_id, title.strip(), due_date, deadline_type, notes, now),
    )
    conn.commit()
    conn.close()
    add_timeline_event(
        user_id,
        matter_id,
        title=f"Deadline: {title}",
        description=notes,
        event_date=due_date[:10],
        event_type="deadline",
    )
    return {"deadline_id": did, "title": title, "due_date": due_date}


def list_deadlines(user_id: str, matter_id: str) -> List[Dict[str, Any]]:
    if not get_matter(user_id, matter_id):
        return []
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT deadline_id, title, due_date, deadline_type, status, notes, created_at
        FROM matter_deadlines WHERE matter_id = ?
        ORDER BY due_date ASC
        """,
        (matter_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "deadline_id": r[0],
            "title": r[1],
            "due_date": r[2],
            "deadline_type": r[3],
            "status": r[4],
            "notes": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def list_unlinked_documents(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    try:
        rows = conn.execute(
            """
            SELECT id, filename, pages, uploaded_at
            FROM documents
            WHERE uploader_id = ? AND COALESCE(matter_id, '') = ''
            ORDER BY uploaded_at DESC LIMIT ?
            """,
            (str(user_id), limit),
        ).fetchall()
    except Exception:
        rows = []
    conn.close()
    return [
        {"document_id": r[0], "filename": r[1], "pages": r[2], "uploaded_at": r[3]}
        for r in rows
    ]


def get_matter_dashboard(user_id: str, matter_id: str) -> Dict[str, Any]:
    m = get_matter(user_id, matter_id)
    if not m:
        return {}
    docs = list_matter_documents(user_id, matter_id)
    kb_health: Dict[str, Any] = {}
    try:
        from backend.app.core.kb_observability import resolve_active_index_scope

        scope = resolve_active_index_scope(str(user_id), matter_id)
        vc = int(scope.get("faiss_chunks") or 0)
        kb_health = {
            "ready": vc > 0,
            "ready_for_kb_query": vc > 0,
            "healthy": vc > 0,
            "vector_count": vc,
            "faiss_chunks": vc,
            "index_vectors": vc,
            "index_exists": bool(scope.get("index_exists")),
            "index_scope": scope.get("index_scope", "matter"),
        }
    except Exception:
        try:
            from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
            from backend.app.core.matter_index import get_matter_index_dir

            idx = get_matter_index_dir(str(user_id), matter_id)
            vc = count_index_vectors(idx) if index_exists(idx) else 0
            kb_health = {
                "ready": vc > 0,
                "ready_for_kb_query": vc > 0,
                "healthy": vc > 0,
                "vector_count": vc,
                "faiss_chunks": vc,
                "index_vectors": vc,
            }
        except Exception:
            pass
    open_tasks = sum(1 for t in list_tasks(user_id, matter_id) if t.get("status") == "open")
    pending_deadlines = sum(
        1 for d in list_deadlines(user_id, matter_id) if d.get("status") == "pending"
    )
    smoke: Dict[str, Any] = {}
    try:
        from backend.app.core.matter_intelligence import matter_dashboard_health_snapshot

        smoke = matter_dashboard_health_snapshot(str(user_id), matter_id)
    except Exception:
        pass
    timeline = list_timeline(user_id, matter_id)
    try:
        from backend.app.core.matter_hearings_intel import list_hearings as list_matter_hearings

        hearings = list_matter_hearings(user_id, matter_id)
    except Exception:
        hearings = list_hearings(user_id, matter_id)
    drafting_summary: Dict[str, Any] = {}
    try:
        from backend.app.core.platform_integrations import matter_drafting_overview

        drafting_summary = matter_drafting_overview(user_id, matter_id)
    except Exception:
        pass
    return {
        "matter": m,
        "documents": docs,
        "notes": list_matter_notes(user_id, matter_id),
        "timeline": timeline,
        "hearings": hearings,
        "tasks": list_tasks(user_id, matter_id),
        "deadlines": list_deadlines(user_id, matter_id),
        "drafting": drafting_summary,
        "stats": {
            "document_count": len(docs),
            "open_tasks": open_tasks,
            "pending_deadlines": pending_deadlines,
            "upcoming_hearings": len(hearings),
            "timeline_events": len(timeline),
            "timeline_completeness_pct": min(100, len(timeline) * 8),
            "ai_confidence": smoke.get("ai_confidence", 0),
            "kb_ready": bool(kb_health.get("ready") or kb_health.get("vector_count", 0) > 0),
            "drafts_awaiting_review": drafting_summary.get("awaiting_review", 0),
            "drafts_total": drafting_summary.get("total", 0),
        },
        "kb_health": kb_health,
        "autopilot": {},
        "smoke": smoke,
        "rag_scope": "matter_only",
        "analytics": smoke,
    }


def list_matters_summary(user_id: str) -> List[Dict[str, Any]]:
    """Lightweight list with doc counts and KB readiness for sidebar."""
    matters = list_matters(user_id)
    conn = connect_data_db()
    out: List[Dict[str, Any]] = []
    for m in matters:
        mid = m["matter_id"]
        row = conn.execute(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ? AND matter_id = ?",
            (str(user_id), mid),
        ).fetchone()
        doc_count = int(row[0]) if row else 0
        kb_ready = False
        vectors = 0
        try:
            from backend.app.core.faiss_index_stats import count_index_vectors
            from backend.app.core.matter_index import resolve_rag_index_dir
            from rag import index_exists

            idx = resolve_rag_index_dir(str(user_id), mid, require_matter_scope=True)
            vectors = count_index_vectors(idx) if index_exists(idx) else 0
            kb_ready = vectors > 0 or doc_count == 0
        except Exception:
            kb_ready = doc_count == 0
        out.append(
            {
                **m,
                "document_count": doc_count,
                "kb_ready": kb_ready,
                "vector_count": vectors,
                "next_hearing": m.get("next_hearing_date") or "",
            }
        )
    conn.close()
    return out
