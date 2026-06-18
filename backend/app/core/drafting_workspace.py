"""Drafting Studio V2 — persisted documents, versions, dashboard, export."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.practice_schema import ensure_practice_schema

WORKFLOW_STATUSES = (
    "draft",
    "in_review",
    "partner_review",
    "needs_revision",
    "approved",
    "ready_to_file",
    "filed",
    "executed",
    "archived",
)

DOCUMENT_TYPES: List[Dict[str, str]] = [
    {"id": "contract", "label": "Contract", "category": "Commercial"},
    {"id": "agreement", "label": "Agreement", "category": "Commercial"},
    {"id": "petition", "label": "Petition", "category": "Litigation"},
    {"id": "affidavit", "label": "Affidavit", "category": "Litigation"},
    {"id": "written_submission", "label": "Written Submission", "category": "Litigation"},
    {"id": "reply", "label": "Reply", "category": "Litigation"},
    {"id": "notice", "label": "Legal Notice", "category": "Litigation"},
    {"id": "legal_opinion", "label": "Legal Opinion", "category": "Advisory"},
    {"id": "memorandum", "label": "Memorandum", "category": "Advisory"},
    {"id": "employment_contract", "label": "Employment Contract", "category": "Employment"},
    {"id": "nda", "label": "NDA", "category": "Commercial"},
    {"id": "vendor_agreement", "label": "Vendor Agreement", "category": "Commercial"},
    {"id": "property_agreement", "label": "Property Agreement", "category": "Property"},
    {"id": "bail_application", "label": "Bail Application", "category": "Criminal"},
    {"id": "writ_petition", "label": "Writ Petition", "category": "Litigation"},
    {"id": "consumer_complaint", "label": "Consumer Complaint", "category": "Litigation"},
    {"id": "arbitration", "label": "Arbitration Document", "category": "Dispute"},
    {"id": "company_document", "label": "Company Document", "category": "Corporate"},
    {"id": "court_filing", "label": "Court Filing", "category": "Litigation"},
    {"id": "custom", "label": "Custom Document", "category": "General"},
]

_DRAFT_COLS = """
    draft_id, user_id, matter_id, title, document_type, status, content,
    parties_json, jurisdiction, objectives, instructions, pinned,
    version_count, created_at, updated_at, content_format
"""


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_draft(row: Tuple) -> Dict[str, Any]:
    fmt = row[15] if len(row) > 15 else "markdown"
    return {
        "draft_id": row[0],
        "user_id": row[1],
        "matter_id": row[2] or "",
        "title": row[3],
        "document_type": row[4],
        "status": row[5],
        "content": row[6],
        "parties": json.loads(row[7] or "{}") if row[7] else {},
        "jurisdiction": row[8] or "",
        "objectives": row[9] or "",
        "instructions": row[10] or "",
        "pinned": bool(row[11]),
        "version_count": int(row[12] or 1),
        "created_at": row[13],
        "updated_at": row[14],
        "content_format": fmt or "markdown",
    }


def _summary(row: Tuple) -> Dict[str, Any]:
    return {
        "draft_id": row[0],
        "title": row[1],
        "document_type": row[2],
        "status": row[3],
        "updated_at": row[4],
        "pinned": bool(row[5]),
        "version_count": int(row[6] or 1),
    }


def dashboard(user_id: str) -> Dict[str, Any]:
    ensure_practice_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT draft_id, title, document_type, status, updated_at, pinned, version_count
        FROM workspace_drafts WHERE user_id = ?
        ORDER BY pinned DESC, updated_at DESC LIMIT 200
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    docs = [_summary(r) for r in rows]
    by_status: Dict[str, int] = {s: 0 for s in WORKFLOW_STATUSES}
    for d in docs:
        by_status[d.get("status") or "draft"] = by_status.get(d.get("status") or "draft", 0) + 1
    return {
        "recent_documents": docs[:12],
        "pinned_documents": [d for d in docs if d.get("pinned")][:8],
        "counts": {
            "total": len(docs),
            "drafts": by_status.get("draft", 0),
            "pending_review": by_status.get("in_review", 0) + by_status.get("needs_revision", 0),
            "ready_to_file": by_status.get("ready_to_file", 0),
            "executed": by_status.get("executed", 0) + by_status.get("filed", 0),
            "by_status": by_status,
        },
        "workflow_statuses": list(WORKFLOW_STATUSES),
        "document_types": DOCUMENT_TYPES,
    }


def list_documents(
    user_id: str,
    *,
    q: str = "",
    status: str = "",
    document_type: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    ensure_practice_schema()
    conn = connect_data_db()
    sql = f"SELECT {_DRAFT_COLS} FROM workspace_drafts WHERE user_id = ?"
    params: List[Any] = [str(user_id)]
    if status:
        sql += " AND status = ?"
        params.append(status)
    if document_type:
        sql += " AND document_type = ?"
        params.append(document_type)
    if q.strip():
        sql += " AND (title LIKE ? OR content LIKE ?)"
        like = f"%{q.strip()}%"
        params.extend([like, like])
    sql += " ORDER BY pinned DESC, updated_at DESC LIMIT ?"
    params.append(min(max(limit, 1), 200))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [_row_to_draft(r) for r in rows]


def get_document(user_id: str, draft_id: str) -> Optional[Dict[str, Any]]:
    ensure_practice_schema()
    try:
        from backend.app.core.drafting_v3 import ensure_workspace_v3_schema

        ensure_workspace_v3_schema()
    except Exception:
        pass
    conn = connect_data_db()
    try:
        row = conn.execute(
            f"SELECT {_DRAFT_COLS} FROM workspace_drafts WHERE draft_id = ? AND user_id = ?",
            (draft_id, str(user_id)),
        ).fetchone()
    except Exception:
        legacy_cols = _DRAFT_COLS.replace(", content_format", "")
        row = conn.execute(
            f"SELECT {legacy_cols} FROM workspace_drafts WHERE draft_id = ? AND user_id = ?",
            (draft_id, str(user_id)),
        ).fetchone()
    conn.close()
    return _row_to_draft(row) if row else None


def _insert_version(
    conn: Any,
    draft_id: str,
    user_id: str,
    version_number: int,
    content: str,
    summary: str = "",
) -> str:
    vid = str(uuid.uuid4())
    conn.execute(
        """
        INSERT INTO workspace_draft_versions
        (version_id, draft_id, user_id, version_number, content, change_summary, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (vid, draft_id, str(user_id), version_number, content, summary or "Save", _utc()),
    )
    return vid


def create_document(
    user_id: str,
    *,
    title: str,
    document_type: str = "custom",
    content: str = "",
    matter_id: str = "",
    jurisdiction: str = "",
    objectives: str = "",
    instructions: str = "",
    parties: Optional[Dict[str, str]] = None,
    status: str = "draft",
    content_format: str = "markdown",
) -> Dict[str, Any]:
    from backend.app.core.drafting_v3 import ensure_workspace_v3_schema

    ensure_practice_schema()
    ensure_workspace_v3_schema()
    if status not in WORKFLOW_STATUSES:
        status = "draft"
    did = str(uuid.uuid4())
    now = _utc()
    body = (content or "").strip() or f"# {title.strip() or 'Untitled'}\n\n"
    conn = connect_data_db()
    fmt = content_format if content_format in ("html", "markdown") else "markdown"
    try:
        conn.execute(
            """
            INSERT INTO workspace_drafts
            (draft_id, user_id, matter_id, title, document_type, status, content,
             parties_json, jurisdiction, objectives, instructions, pinned, version_count,
             created_at, updated_at, content_format)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)
            """,
            (
                did,
                str(user_id),
                matter_id or "",
                title.strip() or "Untitled document",
                document_type or "custom",
                status,
                body,
                json.dumps(parties or {}),
                jurisdiction or "",
                objectives or "",
                instructions or "",
                now,
                now,
                fmt,
            ),
        )
    except Exception:
        conn.execute(
            """
            INSERT INTO workspace_drafts
            (draft_id, user_id, matter_id, title, document_type, status, content,
             parties_json, jurisdiction, objectives, instructions, pinned, version_count,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?)
            """,
            (
                did,
                str(user_id),
                matter_id or "",
                title.strip() or "Untitled document",
                document_type or "custom",
                status,
                body,
                json.dumps(parties or {}),
                jurisdiction or "",
                objectives or "",
                instructions or "",
                now,
                now,
            ),
        )
    _insert_version(conn, did, user_id, 1, body, "Initial version")
    conn.commit()
    conn.close()
    return get_document(user_id, did) or {}


def update_document(
    user_id: str,
    draft_id: str,
    *,
    title: Optional[str] = None,
    content: Optional[str] = None,
    status: Optional[str] = None,
    matter_id: Optional[str] = None,
    pinned: Optional[bool] = None,
    jurisdiction: Optional[str] = None,
    objectives: Optional[str] = None,
    instructions: Optional[str] = None,
    parties: Optional[Dict[str, str]] = None,
    content_format: Optional[str] = None,
    change_summary: str = "Edited",
) -> Optional[Dict[str, Any]]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return None
    new_title = title if title is not None else doc["title"]
    new_content = content if content is not None else doc["content"]
    new_status = status if status is not None else doc["status"]
    if new_status not in WORKFLOW_STATUSES:
        new_status = doc["status"]
    new_matter = matter_id if matter_id is not None else doc["matter_id"]
    new_pin = int(pinned) if pinned is not None else int(doc["pinned"])
    new_jur = jurisdiction if jurisdiction is not None else doc["jurisdiction"]
    new_obj = objectives if objectives is not None else doc["objectives"]
    new_inst = instructions if instructions is not None else doc["instructions"]
    new_parties = parties if parties is not None else doc["parties"]
    new_fmt = content_format if content_format is not None else doc.get("content_format", "markdown")
    ver = int(doc["version_count"]) + 1
    now = _utc()
    ensure_practice_schema()
    conn = connect_data_db()
    try:
        conn.execute(
            """
            UPDATE workspace_drafts SET
                title = ?, content = ?, status = ?, matter_id = ?, pinned = ?,
                jurisdiction = ?, objectives = ?, instructions = ?, parties_json = ?,
                version_count = ?, updated_at = ?, content_format = ?
            WHERE draft_id = ? AND user_id = ?
            """,
            (
                new_title,
                new_content,
                new_status,
                new_matter,
                new_pin,
                new_jur,
                new_obj,
                new_inst,
                json.dumps(new_parties),
                ver,
                now,
                new_fmt,
                draft_id,
                str(user_id),
            ),
        )
    except Exception:
        conn.execute(
            """
            UPDATE workspace_drafts SET
                title = ?, content = ?, status = ?, matter_id = ?, pinned = ?,
                jurisdiction = ?, objectives = ?, instructions = ?, parties_json = ?,
                version_count = ?, updated_at = ?
            WHERE draft_id = ? AND user_id = ?
            """,
            (
                new_title,
                new_content,
                new_status,
                new_matter,
                new_pin,
                new_jur,
                new_obj,
                new_inst,
                json.dumps(new_parties),
                ver,
                now,
                draft_id,
                str(user_id),
            ),
        )
    _insert_version(conn, draft_id, user_id, ver, new_content, change_summary)
    conn.commit()
    conn.close()
    return get_document(user_id, draft_id)


def delete_document(user_id: str, draft_id: str) -> bool:
    ensure_practice_schema()
    conn = connect_data_db()
    conn.execute(
        "DELETE FROM workspace_draft_versions WHERE draft_id = ?",
        (draft_id,),
    )
    conn.execute(
        "DELETE FROM workspace_draft_comments WHERE draft_id = ?",
        (draft_id,),
    )
    cur = conn.execute(
        "DELETE FROM workspace_drafts WHERE draft_id = ? AND user_id = ?",
        (draft_id, str(user_id)),
    )
    conn.commit()
    conn.close()
    return cur.rowcount > 0


def list_versions(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_practice_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT version_id, version_number, user_id, change_summary, created_at
        FROM workspace_draft_versions
        WHERE draft_id = ?
        ORDER BY version_number DESC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "version_id": r[0],
            "version_number": r[1],
            "user_id": r[2],
            "change_summary": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def get_version_content(user_id: str, draft_id: str, version_number: int) -> Optional[str]:
    if not get_document(user_id, draft_id):
        return None
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT content FROM workspace_draft_versions
        WHERE draft_id = ? AND version_number = ?
        """,
        (draft_id, version_number),
    ).fetchone()
    conn.close()
    return row[0] if row else None


def compare_versions(
    user_id: str,
    draft_id: str,
    version_a: int,
    version_b: int,
) -> Dict[str, Any]:
    from document_services.redline_engine import generate_diff_html, generate_diff_markdown

    a = get_version_content(user_id, draft_id, version_a)
    b = get_version_content(user_id, draft_id, version_b)
    if a is None or b is None:
        return {"error": "Version not found"}
    return {
        "version_a": version_a,
        "version_b": version_b,
        "diff_markdown": generate_diff_markdown(a, b),
        "diff_html": generate_diff_html(a, b),
    }


def restore_version(user_id: str, draft_id: str, version_number: int) -> Optional[Dict[str, Any]]:
    content = get_version_content(user_id, draft_id, version_number)
    if content is None:
        return None
    return update_document(
        user_id,
        draft_id,
        content=content,
        change_summary=f"Restored v{version_number}",
    )


def export_document(
    user_id: str,
    draft_id: str,
    fmt: str = "pdf",
    *,
    watermark: str = "",
    signature_blocks: bool = False,
) -> Tuple[bytes, str, str]:
    from backend.app.core.drafting_v3 import export_document_v3

    return export_document_v3(
        user_id,
        draft_id,
        fmt,
        watermark=watermark,
        signature_blocks=signature_blocks,
    )


def add_comment(
    user_id: str,
    draft_id: str,
    body: str,
    *,
    author_name: str = "",
) -> Dict[str, Any]:
    if not get_document(user_id, draft_id):
        return {"error": "Document not found"}
    cid = str(uuid.uuid4())
    now = _utc()
    ensure_practice_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_draft_comments
        (comment_id, draft_id, user_id, author_name, body, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (cid, draft_id, str(user_id), author_name or "Reviewer", body.strip(), now),
    )
    conn.commit()
    conn.close()
    return {"comment_id": cid, "created_at": now}


def list_comments(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_practice_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT comment_id, user_id, author_name, body, created_at
        FROM workspace_draft_comments WHERE draft_id = ?
        ORDER BY created_at ASC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "comment_id": r[0],
            "user_id": r[1],
            "author_name": r[2],
            "body": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def generate_ai_draft(
    user_id: str,
    *,
    document_type: str,
    parties: Dict[str, str],
    facts: str,
    jurisdiction: str,
    objectives: str,
    instructions: str = "",
    use_polish: bool = True,
) -> Dict[str, Any]:
    """AI document generation — template + optional LLM polish; KB clauses cited when available."""
    from backend.app.core.drafting_studio import SMART_DRAFT_SPECS, generate_smart_draft

    dtype = (document_type or "custom").strip()
    label = next((t["label"] for t in DOCUMENT_TYPES if t["id"] == dtype), dtype)
    answers = {
        "facts": facts,
        "jurisdiction": jurisdiction,
        "objectives": objectives,
        "instructions": instructions,
        **(parties or {}),
    }
    smart_key = dtype if dtype in SMART_DRAFT_SPECS else None
    rendered = ""
    sources: List[str] = []

    if smart_key:
        out = generate_smart_draft(user_id, smart_key, answers, use_ai_polish=use_polish)
        if not out.get("error"):
            rendered = out.get("rendered") or ""
            sources.append(f"template:{smart_key}")

    if not rendered.strip():
        rendered = _fallback_markdown(label, parties, facts, jurisdiction, objectives, instructions)

    try:
        from backend.app.core.drafting_clause_intel import enrich_with_clause_refs

        rendered, clause_sources = enrich_with_clause_refs(user_id, rendered, jurisdiction)
        sources.extend(clause_sources)
    except Exception:
        pass

    if use_polish and rendered.strip():
        rendered = _polish_draft(user_id, rendered, label, instructions) or rendered

    title = f"{label} — {parties.get('client_name') or parties.get('party_a') or 'Draft'}"
    doc = create_document(
        user_id,
        title=title[:120],
        document_type=dtype,
        content=rendered,
        jurisdiction=jurisdiction,
        objectives=objectives,
        instructions=instructions,
        parties=parties,
        status="draft",
    )
    return {"document": doc, "sources": sources, "rendered": rendered}


def _fallback_markdown(
    label: str,
    parties: Dict[str, str],
    facts: str,
    jurisdiction: str,
    objectives: str,
    instructions: str,
) -> str:
    party_lines = "\n".join(f"- **{k.replace('_', ' ').title()}:** {v}" for k, v in parties.items() if v)
    return f"""# {label}

## Jurisdiction
{jurisdiction or 'To be specified'}

## Parties
{party_lines or '- (specify parties)'}

## Facts
{facts or '(summarize facts)'}

## Objectives
{objectives or '(state relief or commercial objectives)'}

## Instructions
{instructions or 'None'}

## Draft body
(To be expanded — use AI polish or insert clauses from the clause library.)

## Definitions
"Agreement" means this document and all schedules.

## Execution
IN WITNESS WHEREOF the parties execute this document at {jurisdiction or '________'} on ________.
"""


def _polish_draft(user_id: str, text: str, doc_label: str, instructions: str) -> str:
    import os

    backend = (os.getenv("LLM_BACKEND") or "ollama").strip().lower()
    prompt = (
        f"Draft a professional Indian legal document: {doc_label}. "
        f"Use formal legal language. Structure with headings. "
        f"Additional instructions: {instructions or 'None'}. "
        f"Base content:\n\n{text[:12000]}"
    )
    if backend == "gemini":
        try:
            from google.genai import types
            from backend.app.core.web_intelligence import GEMINI_FREE_MODEL, _get_client

            client = _get_client()
            resp = client.models.generate_content(
                model=GEMINI_FREE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.25, max_output_tokens=4096),
            )
            return (getattr(resp, "text", None) or "").strip() or text
        except Exception:
            pass
    try:
        from llms import get_generator

        gen = get_generator(user_id=user_id)
        if gen and getattr(gen, "available", False):
            return (gen.generate(prompt, max_tokens=4096) or text).strip()
    except Exception:
        pass
    return text
