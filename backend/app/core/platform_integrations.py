"""CRM → Matter → Drafting → Litigation → Billing platform bridges."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.drafting_lifecycle import ensure_v4_schema, log_draft_event, matter_drafting_hub
from backend.app.core.drafting_workspace import get_document, list_documents
from backend.app.core.practice_schema import ensure_practice_schema

REVIEW_STATUSES = frozenset({"in_review", "partner_review", "needs_revision"})
FILED_STATUSES = frozenset({"filed", "executed", "ready_to_file"})

_DRAFT_TAG_RE = re.compile(r"draft:([a-f0-9-]{36})", re.I)


def ensure_integration_schema() -> None:
    ensure_v4_schema()
    conn = connect_data_db()
    for stmt in (
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_links (
            link_id TEXT PRIMARY KEY,
            draft_id TEXT NOT NULL,
            link_type TEXT NOT NULL,
            target_id TEXT NOT NULL,
            meta_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_draft_links_draft ON workspace_draft_links(draft_id)",
        """
        CREATE TABLE IF NOT EXISTS workspace_draft_billing_sessions (
            draft_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            last_billed_at TEXT NOT NULL,
            total_units REAL NOT NULL DEFAULT 0,
            PRIMARY KEY (draft_id, user_id)
        )
        """,
    ):
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def matter_drafting_overview(user_id: str, matter_id: str) -> Dict[str, Any]:
    """Summary for matter overview card."""
    hub = matter_drafting_hub(user_id, matter_id)
    if hub.get("error"):
        return hub
    docs = hub.get("documents") or []
    awaiting = [d for d in docs if d.get("status") in REVIEW_STATUSES]
    filed = [d for d in docs if d.get("status") in FILED_STATUSES]
    drafts = [d for d in docs if d.get("status") == "draft"]
    return {
        "matter_id": matter_id,
        "total": len(docs),
        "drafts": len(drafts),
        "awaiting_review": len(awaiting),
        "filed_or_ready": len(filed),
        "awaiting_documents": awaiting[:8],
        "control_center_url": f"/drafting?matter={matter_id}",
        "recent_timeline": (hub.get("timeline") or [])[:5],
    }


def control_center_for_matter(user_id: str, matter_id: str = "") -> Dict[str, Any]:
    from backend.app.core.drafting_lifecycle import control_center

    base = control_center(user_id)
    if not matter_id:
        return base
    docs = [d for d in list_documents(user_id, limit=200) if d.get("matter_id") == matter_id]
    by_status: Dict[str, List[Dict[str, Any]]] = {s: [] for s in base.get("columns", {})}
    for d in docs:
        st = d.get("status") or "draft"
        card = {
            "draft_id": d.get("draft_id"),
            "title": d.get("title"),
            "status": st,
            "health_score": d.get("health_score", 0),
            "filing_readiness_score": d.get("filing_readiness_score", 0),
        }
        if st in by_status:
            by_status[st].append(card)
    base["matter_id"] = matter_id
    base["columns"] = by_status
    base["counts"] = {s: len(by_status.get(s, [])) for s in by_status}
    return base


def add_draft_link(
    user_id: str,
    draft_id: str,
    link_type: str,
    target_id: str,
    *,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    ensure_integration_schema()
    lid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO workspace_draft_links (link_id, draft_id, link_type, target_id, meta_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (lid, draft_id, link_type, target_id, json.dumps(meta or {}), _utc()),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, f"linked_{link_type}", detail=target_id)
    return {"link_id": lid, "link_type": link_type, "target_id": target_id}


def list_draft_links(user_id: str, draft_id: str) -> List[Dict[str, Any]]:
    if not get_document(user_id, draft_id):
        return []
    ensure_integration_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT link_id, link_type, target_id, meta_json, created_at
        FROM workspace_draft_links WHERE draft_id = ?
        ORDER BY created_at DESC
        """,
        (draft_id,),
    ).fetchall()
    conn.close()
    return [
        {
            "link_id": r[0],
            "link_type": r[1],
            "target_id": r[2],
            "meta": json.loads(r[3] or "{}"),
            "created_at": r[4],
        }
        for r in rows
    ]


def link_draft_to_hearing(
    user_id: str,
    draft_id: str,
    hearing_id: str,
) -> Dict[str, Any]:
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    matter_id = doc.get("matter_id") or ""
    if not matter_id:
        return {"error": "Link document to a matter first"}
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT hearing_id, matter_id, notes FROM matter_hearings WHERE hearing_id = ? AND matter_id = ?",
        (hearing_id, matter_id),
    ).fetchone()
    if not row:
        conn.close()
        return {"error": "Hearing not found on this matter"}
    note = (row[2] or "").strip()
    marker = f"[Draft:{draft_id}] {doc.get('title', '')}"
    if marker not in note:
        note = f"{note}\n{marker}".strip()
    conn.execute("UPDATE matter_hearings SET notes = ? WHERE hearing_id = ?", (note, hearing_id))
    conn.commit()
    conn.close()
    add_draft_link(user_id, draft_id, "hearing", hearing_id, meta={"title": doc.get("title")})
    try:
        from backend.app.core.matter_workflow import add_timeline_event

        add_timeline_event(
            user_id,
            matter_id,
            title="Draft linked to hearing",
            description=doc.get("title", ""),
            event_type="drafting",
        )
    except Exception:
        pass
    return {"ok": True, "hearing_id": hearing_id, "draft_id": draft_id}


def sync_draft_filed_to_litigation(user_id: str, draft_id: str) -> Dict[str, Any]:
    """On filed/ready_to_file — create court order record and link next hearing if any."""
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found"}
    matter_id = doc.get("matter_id") or ""
    if not matter_id:
        return {"error": "No matter linked"}
    from backend.app.core.drafting_v3 import matter_variables
    from backend.app.core.litigation_os import list_court_orders, save_court_order

    vars_ = matter_variables(user_id, matter_id)
    title = doc.get("title") or "Filed document"
    existing = [
        o
        for o in list_court_orders(user_id, matter_id=matter_id, limit=50)
        if f"draft:{draft_id}" in (o.get("tags") or "")
    ]
    if existing:
        order_id = existing[0]["order_id"]
    else:
        out = save_court_order(
            user_id,
            {
                "matter_id": matter_id,
                "order_type": "application",
                "title": title,
                "order_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "court_name": vars_.get("CourtName", ""),
                "judge": "",
                "summary": f"Filed from Drafting Studio. Document type: {doc.get('document_type', '')}.",
                "document_id": draft_id,
                "tags": f"draft:{draft_id},source:drafting_studio",
            },
        )
        if out.get("error"):
            return out
        order_id = out.get("order_id", "")
    add_draft_link(user_id, draft_id, "court_order", order_id, meta={"auto": True})
    hearing_id = _next_hearing_for_matter(matter_id)
    if hearing_id:
        link_draft_to_hearing(user_id, draft_id, hearing_id)
    log_draft_event(user_id, draft_id, "filed_litigation_sync", detail=order_id)
    return {"ok": True, "order_id": order_id, "hearing_id": hearing_id}


def _next_hearing_for_matter(matter_id: str) -> str:
    ensure_practice_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT hearing_id FROM matter_hearings
        WHERE matter_id = ? AND hearing_date >= date('now')
        ORDER BY hearing_date ASC LIMIT 1
        """,
        (matter_id,),
    ).fetchone()
    conn.close()
    return row[0] if row else ""


def log_drafting_billing_session(
    user_id: str,
    draft_id: str,
    *,
    change_summary: str = "Editor save",
    force: bool = False,
) -> Dict[str, Any]:
    """Bill drafting time to matter — at most once per 15 minutes per draft (0.25 hr default)."""
    doc = get_document(user_id, draft_id)
    if not doc:
        return {"error": "Document not found", "skipped": True}
    matter_id = doc.get("matter_id") or ""
    if not matter_id:
        return {"skipped": True, "reason": "no_matter"}
    if change_summary == "Autosave" and not force:
        return {"skipped": True, "reason": "autosave"}
    ensure_integration_schema()
    now = datetime.now(timezone.utc)
    conn = connect_data_db()
    row = conn.execute(
        "SELECT last_billed_at, total_units FROM workspace_draft_billing_sessions WHERE draft_id = ? AND user_id = ?",
        (draft_id, str(user_id)),
    ).fetchone()
    if row and not force:
        try:
            last = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if now - last < timedelta(minutes=15):
                conn.close()
                return {"skipped": True, "reason": "cooldown"}
        except Exception:
            pass
    units = 0.25
    rate = _default_hourly_rate(user_id, matter_id)
    from backend.app.core.billing_service import log_time_entry

    activity = f"Drafting: {doc.get('title', 'Document')} — {change_summary}"
    out = log_time_entry(
        user_id,
        matter_id=matter_id,
        raw_activity=activity,
        units_logged=units,
        rate_per_unit=rate,
        billing_type="HOURLY",
    )
    if out.get("error"):
        conn.close()
        return out
    ts = _utc()
    conn.execute(
        """
        INSERT INTO workspace_draft_billing_sessions (draft_id, user_id, last_billed_at, total_units)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(draft_id, user_id) DO UPDATE SET
            last_billed_at = excluded.last_billed_at,
            total_units = workspace_draft_billing_sessions.total_units + excluded.total_units
        """,
        (draft_id, str(user_id), ts, units),
    )
    conn.commit()
    conn.close()
    log_draft_event(user_id, draft_id, "billing_logged", detail=out.get("record_id", ""))
    return {
        "billed": True,
        "record_id": out.get("record_id"),
        "units_logged": units,
        "amount": out.get("amount"),
        "narrative_description": out.get("narrative_description"),
    }


def _default_hourly_rate(user_id: str, matter_id: str) -> float:
    try:
        from backend.app.core.practice_billing_service import matter_billing_profile

        prof = matter_billing_profile(user_id, matter_id)
        if prof and float(prof.get("default_rate") or 0) > 0:
            return float(prof["default_rate"])
    except Exception:
        pass
    return 5000.0


def enrich_orders_with_drafts(orders: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    for o in orders:
        tags = o.get("tags") or ""
        m = _DRAFT_TAG_RE.search(tags)
        doc_id = o.get("document_id") or ""
        if m:
            o["linked_draft_id"] = m.group(1)
        elif doc_id and len(doc_id) == 36:
            o["linked_draft_id"] = doc_id
        else:
            o["linked_draft_id"] = ""
        if o.get("linked_draft_id"):
            o["draft_editor_url"] = f"/drafting/{o['linked_draft_id']}"
    return orders


def parse_draft_id_from_tags(tags: str) -> str:
    m = _DRAFT_TAG_RE.search(tags or "")
    return m.group(1) if m else ""
