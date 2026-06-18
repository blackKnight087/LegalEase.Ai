"""Drafting Studio enterprise — track changes, TOC, precedents, approvals, DOCX."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.drafting_lifecycle import (
    ensure_v4_schema,
    get_precedent,
    list_annexures,
    list_draft_timeline,
    log_draft_event,
)
from backend.app.core.drafting_v3 import html_to_plain
from backend.app.core.drafting_workspace import get_document, update_document


def ensure_enterprise_schema() -> None:
    ensure_v4_schema()
    from backend.app.core.db import connect_data_db

    conn = connect_data_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS workspace_track_changes (
            change_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            author_name TEXT NOT NULL DEFAULT '',
            change_type TEXT NOT NULL DEFAULT 'replace',
            original_text TEXT NOT NULL DEFAULT '',
            suggested_text TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_track_changes_draft ON workspace_track_changes(draft_id)"
    )
    conn.commit()
    conn.close()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_track_changes(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_enterprise_schema()
    from backend.app.core.db import connect_data_db

    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT change_id, user_id, author_name, change_type, original_text, suggested_text, status, created_at
        FROM workspace_track_changes WHERE draft_id = ?
        ORDER BY created_at ASC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "change_id": r[0],
            "user_id": r[1],
            "author_name": r[2],
            "change_type": r[3],
            "original_text": r[4],
            "suggested_text": r[5],
            "status": r[6],
            "created_at": r[7],
        }
        for r in rows
    ]


def add_track_change(
    user_id: str,
    draft_id: str,
    *,
    original_text: str,
    suggested_text: str,
    change_type: str = "replace",
    author_name: str = "",
) -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    ensure_enterprise_schema()
    cid = str(uuid.uuid4())
    from backend.app.core.db import connect_data_db

    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_track_changes
        (change_id, draft_id, user_id, author_name, change_type, original_text, suggested_text, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            cid,
            draft_id,
            str(user_id),
            author_name or "Reviewer",
            change_type,
            original_text,
            suggested_text,
            _utc(),
        ),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "track_change_proposed", detail=cid[:8])
    return {"change_id": cid, "status": "pending"}


def resolve_track_change(user_id: str, draft_id: str, change_id: str, accept: bool) -> Dict[str, Any]:
    ensure_enterprise_schema()
    from backend.app.core.db import connect_data_db

    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT original_text, suggested_text, status FROM workspace_track_changes
        WHERE change_id = ? AND draft_id = ?
        """,
        (change_id, draft_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Change not found"}
    orig, sugg, cur_status = row[0], row[1], row[2]
    status = "accepted" if accept else "rejected"
    conn.execute(
        "UPDATE workspace_track_changes SET status = ? WHERE change_id = ?",
        (status, change_id),
    )
    conn.commit()
    conn.close()

    doc_updated = None
    if accept and orig:
        doc = get_document(user_id, draft_id)
        if doc:
            body = doc.get("content") or ""
            if orig in body:
                new_body = body.replace(orig, sugg, 1)
            else:
                plain = html_to_plain(body)
                if orig in plain:
                    new_body = body + f"<p>{sugg}</p>"
                else:
                    new_body = body + f"<p><del>{orig}</del> {sugg}</p>"
            doc_updated = update_document(
                user_id,
                draft_id,
                content=new_body,
                content_format=doc.get("content_format") or "html",
                change_summary=f"Track change accepted ({change_id[:8]})",
            )
    log_draft_event(user_id, draft_id, f"track_change_{status}", detail=change_id[:8])
    return {"ok": True, "status": status, "document": doc_updated}


class _HeadingParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.headings: List[Dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: List) -> None:
        t = tag.lower()
        if t in ("h1", "h2", "h3"):
            self._tag = t
            self._buf = ""

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("h1", "h2", "h3") and getattr(self, "_buf", None) is not None:
            lvl = int(tag[1])
            self.headings.append({"level": lvl, "title": self._buf.strip()})
            self._buf = ""

    def handle_data(self, data: str) -> None:
        if hasattr(self, "_buf"):
            self._buf = getattr(self, "_buf", "") + data


def generate_toc_html(content: str, *, title: str = "Table of Contents") -> str:
    parser = _HeadingParser()
    try:
        parser.feed(content or "")
        parser.close()
    except Exception:
        pass
    if not parser.headings:
        return f'<h2>{title}</h2><p><em>No headings found — add H1, H2, or H3 sections first.</em></p>'
    parts = [f'<h2>{title}</h2>', '<div class="legal-toc">', "<ol>"]
    for i, h in enumerate(parser.headings, 1):
        indent = "  " * (h["level"] - 1)
        parts.append(
            f'<li style="margin-left:{(h["level"]-1)*12}px">'
            f'<a href="#outline-{i-1}">{indent}{h["title"]}</a></li>'
        )
    parts.extend(["</ol>", "</div>", '<hr data-page-break="true" />'])
    return "".join(parts)


def generate_annexure_index_html(annexures: List[Dict[str, Any]]) -> str:
    if not annexures:
        return "<h2>Index of Annexures</h2><p><em>No annexures attached.</em></p>"
    parts = ["<h2>Index of Annexures</h2>", "<table class='legal-signature-table'><thead><tr><th>Annexure</th><th>Description</th></tr></thead><tbody>"]
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    for i, a in enumerate(annexures):
        lab = a.get("label") or f"Annexure {labels[i] if i < len(labels) else i+1}"
        desc = (a.get("content") or "")[:120]
        parts.append(f"<tr><td><strong>{lab}</strong></td><td>{desc}</td></tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def compare_draft_to_precedent(user_id: str, draft_id: str, precedent_id: str) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    prec = get_precedent(user_id, precedent_id)
    if not prec:
        return {"error": "Precedent not found"}
    from document_services.redline_engine import generate_diff_html

    current = html_to_plain(doc.get("content") or "")
    precedent_plain = html_to_plain(prec.get("content") or "")
    diff_html = generate_diff_html(precedent_plain, current)
    words_a = set(re.findall(r"\w+", precedent_plain.lower()))
    words_b = set(re.findall(r"\w+", current.lower()))
    overlap = len(words_a & words_b) / max(len(words_a | words_b), 1)
    return {
        "precedent_id": precedent_id,
        "precedent_title": prec.get("title"),
        "similarity_score": round(overlap * 100, 1),
        "diff_html": diff_html,
        "precedent_excerpt": precedent_plain[:1500],
    }


def list_draft_assignments(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_v4_schema()
    from backend.app.core.db import connect_data_db

    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT assignment_id, assignee_user_id, assignee_name, role, due_date, status, created_at
        FROM workspace_draft_assignments WHERE draft_id = ?
        ORDER BY created_at DESC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "assignment_id": r[0],
            "assignee_user_id": r[1],
            "assignee_name": r[2],
            "role": r[3],
            "due_date": r[4],
            "status": r[5],
            "created_at": r[6],
        }
        for r in rows
    ]


def update_assignment_status(
    user_id: str, draft_id: str, assignment_id: str, status: str
) -> Dict[str, Any]:
    ensure_v4_schema()
    from backend.app.core.db import connect_data_db

    conn = connect_data_db()
    conn.execute(
        "UPDATE workspace_draft_assignments SET status = ? WHERE assignment_id = ? AND draft_id = ?",
        (status, assignment_id, draft_id),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "assignment_status", detail=f"{assignment_id[:8]}:{status}")
    return {"ok": True, "status": status}


def partner_approve(user_id: str, draft_id: str, *, note: str = "") -> Dict[str, Any]:
    from backend.app.core.drafting_v3 import transition_status

    out = transition_status(user_id, draft_id, "approved")
    if out.get("error"):
        return out
    log_draft_event(user_id, draft_id, "partner_approved", detail=note[:200])
    return out


def partner_request_revision(user_id: str, draft_id: str, *, note: str = "") -> Dict[str, Any]:
    from backend.app.core.drafting_v3 import transition_status

    out = transition_status(user_id, draft_id, "needs_revision")
    if out.get("error"):
        return out
    log_draft_event(user_id, draft_id, "partner_revision", detail=note[:200])
    return out


def send_for_partner_review(user_id: str, draft_id: str) -> Dict[str, Any]:
    from backend.app.core.drafting_v3 import transition_status

    return transition_status(user_id, draft_id, "partner_review")


def get_collaboration_hub(user_id: str, draft_id: str) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    return {
        "document": doc,
        "track_changes": list_track_changes(user_id, draft_id),
        "assignments": list_draft_assignments(user_id, draft_id),
        "annexures": list_annexures(user_id, draft_id),
        "timeline": list_draft_timeline(user_id, draft_id),
        "pending_changes": sum(
            1 for c in list_track_changes(user_id, draft_id) if c.get("status") == "pending"
        ),
    }
