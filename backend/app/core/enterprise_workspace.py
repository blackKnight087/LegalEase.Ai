"""Enterprise V2 — DMS, court orders, knowledge base, client portal ops, audit."""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from backend.app.core.database import connect_data_db
from backend.app.core.sql_compat import execute_script

PRACTICE_AREAS = ("Litigation", "Corporate", "Real Estate", "Arbitration")
FOLDER_TYPES = ("Pleadings", "Orders", "Evidence", "Correspondence", "Drafts", "General")
ORDER_TYPES = (
    "judgment",
    "interim_order",
    "notice",
    "summons",
    "execution_order",
    "order",
    "other",
)
ROLES = ("partner", "senior_associate", "associate", "paralegal", "client", "admin")

_ROLE_PERMS: Dict[str, Dict[str, bool]] = {
    "partner": {k: True for k in ("read", "write", "delete", "share", "approve", "admin")},
    "admin": {k: True for k in ("read", "write", "delete", "share", "approve", "admin")},
    "senior_associate": {
        "read": True,
        "write": True,
        "delete": True,
        "share": True,
        "approve": True,
        "admin": False,
    },
    "associate": {
        "read": True,
        "write": True,
        "delete": False,
        "share": True,
        "approve": False,
        "admin": False,
    },
    "paralegal": {
        "read": True,
        "write": True,
        "delete": False,
        "share": False,
        "approve": False,
        "admin": False,
    },
    "client": {
        "read": True,
        "write": False,
        "delete": False,
        "share": False,
        "approve": True,
        "admin": False,
    },
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


def _role_key(user: Dict[str, Any]) -> str:
    role = str(user.get("role") or "associate").lower().replace(" ", "_")
    if role in ROLES:
        return role
    if role in ("superadmin", "owner"):
        return "partner"
    return "associate"


def permissions_for_user(user: Dict[str, Any]) -> Dict[str, bool]:
    return dict(_ROLE_PERMS.get(_role_key(user), _ROLE_PERMS["associate"]))


def ensure_enterprise_workspace_schema() -> None:
    conn = connect_data_db()
    execute_script(
        conn,
        """
        CREATE TABLE IF NOT EXISTS ent_dms_folders (
            folder_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            practice_area TEXT NOT NULL DEFAULT 'Litigation',
            matter_id TEXT NOT NULL DEFAULT '',
            folder_name TEXT NOT NULL,
            parent_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ent_folders_user ON ent_dms_folders(user_id);

        CREATE TABLE IF NOT EXISTS ent_dms_documents (
            doc_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            folder_id TEXT NOT NULL DEFAULT '',
            matter_id TEXT NOT NULL DEFAULT '',
            practice_area TEXT NOT NULL DEFAULT 'Litigation',
            doc_type TEXT NOT NULL DEFAULT 'General',
            title TEXT NOT NULL,
            filename TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            version_no INTEGER NOT NULL DEFAULT 1,
            content_text TEXT NOT NULL DEFAULT '',
            ocr_text TEXT NOT NULL DEFAULT '',
            ocr_confidence REAL NOT NULL DEFAULT 0,
            expiry_date TEXT NOT NULL DEFAULT '',
            file_size INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ent_docs_user ON ent_dms_documents(user_id);
        CREATE INDEX IF NOT EXISTS idx_ent_docs_matter ON ent_dms_documents(matter_id);

        CREATE TABLE IF NOT EXISTS ent_dms_versions (
            version_id TEXT PRIMARY KEY,
            doc_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            version_no INTEGER NOT NULL,
            author TEXT NOT NULL DEFAULT '',
            change_summary TEXT NOT NULL DEFAULT '',
            content_text TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ent_versions_doc ON ent_dms_versions(doc_id);

        CREATE TABLE IF NOT EXISTS ent_court_orders (
            order_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL DEFAULT '',
            client_name TEXT NOT NULL DEFAULT '',
            court TEXT NOT NULL DEFAULT '',
            judge TEXT NOT NULL DEFAULT '',
            case_number TEXT NOT NULL DEFAULT '',
            order_date TEXT NOT NULL DEFAULT '',
            order_type TEXT NOT NULL DEFAULT 'order',
            practice_area TEXT NOT NULL DEFAULT 'Litigation',
            keywords_json TEXT NOT NULL DEFAULT '[]',
            filename TEXT NOT NULL DEFAULT '',
            content_text TEXT NOT NULL DEFAULT '',
            ocr_text TEXT NOT NULL DEFAULT '',
            ocr_confidence REAL NOT NULL DEFAULT 0,
            summary TEXT NOT NULL DEFAULT '',
            directions_json TEXT NOT NULL DEFAULT '[]',
            compliance_json TEXT NOT NULL DEFAULT '[]',
            deadlines_json TEXT NOT NULL DEFAULT '[]',
            risks_json TEXT NOT NULL DEFAULT '[]',
            next_steps_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ent_orders_user ON ent_court_orders(user_id);

        CREATE TABLE IF NOT EXISTS ent_knowledge (
            entry_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            entry_type TEXT NOT NULL DEFAULT 'memo',
            title TEXT NOT NULL,
            practice_area TEXT NOT NULL DEFAULT '',
            matter_id TEXT NOT NULL DEFAULT '',
            court TEXT NOT NULL DEFAULT '',
            tags_json TEXT NOT NULL DEFAULT '[]',
            content_text TEXT NOT NULL DEFAULT '',
            linked_order_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ent_kb_user ON ent_knowledge(user_id);

        CREATE TABLE IF NOT EXISTS ent_client_requests (
            request_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            client_email TEXT NOT NULL DEFAULT '',
            request_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            fulfilled_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS ent_client_approvals (
            approval_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            matter_id TEXT NOT NULL,
            draft_id TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending_review',
            client_email TEXT NOT NULL DEFAULT '',
            client_action TEXT NOT NULL DEFAULT '',
            client_note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS ent_audit (
            audit_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            actor TEXT NOT NULL DEFAULT '',
            action TEXT NOT NULL,
            resource_type TEXT NOT NULL DEFAULT '',
            resource_id TEXT NOT NULL DEFAULT '',
            detail_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_ent_audit_user ON ent_audit(user_id, created_at);
        """
    )
    conn.commit()
    conn.close()


def _audit(
    user_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    *,
    actor: str = "",
    detail: Optional[Dict[str, Any]] = None,
) -> None:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ent_audit
        (audit_id, user_id, actor, action, resource_type, resource_id, detail_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _new_id(),
            str(user_id),
            actor or str(user_id),
            action,
            resource_type,
            resource_id,
            json.dumps(detail or {}),
            _utc(),
        ),
    )
    conn.commit()
    conn.close()


def _parse_tags(raw: Any) -> List[str]:
    if isinstance(raw, list):
        return [str(x) for x in raw[:20]]
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed[:20]]
        except json.JSONDecodeError:
            return [t.strip() for t in raw.split(",") if t.strip()][:20]
    return []


def _extract_order_metadata(text: str) -> Dict[str, Any]:
    t = text or ""
    court = ""
    for pat in (
        r"(?:IN THE|Before the)\s+(.{10,80}?)(?:\n|COURT)",
        r"(Supreme Court|High Court|District Court|Sessions Court|Tribunal)[^\n]{0,60}",
    ):
        m = re.search(pat, t, re.I)
        if m:
            court = m.group(1).strip()[:120]
            break
    judge = ""
    m = re.search(
        r"(?:Hon['']?ble\s+)?(?:Mr\.?|Ms\.?|Dr\.?)?\s*Justice\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
        t,
    )
    if m:
        judge = f"Justice {m.group(1).strip()}"
    case_no = ""
    m = re.search(
        r"(?:Case\s+No\.?|CNR|FIR|Diary\s+No\.?|W\.?P\.?\s*\(?Civil\)?)\s*[:\s]*([A-Z0-9/\-]+)",
        t,
        re.I,
    )
    if m:
        case_no = m.group(1).strip()[:80]
    order_date = ""
    m = re.search(
        r"(?:Dated|Date)\s*[:\s]*(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4})",
        t,
        re.I,
    )
    if m:
        order_date = m.group(1)
    keywords: List[str] = []
    for kw in ("bail", "interim", "stay", "execution", "summons", "notice", "302", "437"):
        if re.search(rf"\b{kw}\b", t, re.I):
            keywords.append(kw)
    return {
        "court": court,
        "judge": judge,
        "case_number": case_no,
        "order_date": order_date,
        "keywords": keywords,
    }


def _ai_order_analysis(text: str) -> Dict[str, Any]:
    snippet = (text or "")[:8000]
    meta = _extract_order_metadata(snippet)
    court_part = f" in {meta['court']}" if meta.get("court") else ""
    case_part = f" — {meta['case_number']}" if meta.get("case_number") else ""
    fallback = {
        "summary": (
            f"Court order{court_part}{case_part}. "
            "Review extracted directions and deadlines below."
        ),
        "directions": [],
        "compliance": [],
        "deadlines": [],
        "risks": [],
        "next_steps": ["File compliance affidavit if directed", "Update matter timeline"],
    }
    for line in snippet.splitlines():
        low = line.lower().strip()
        if any(
            w in low
            for w in ("directed", "ordered", "shall", "hereby", "directs the")
        ):
            if 20 < len(line) < 400:
                fallback["directions"].append(line.strip()[:300])
        if "within" in low and ("day" in low or "week" in low):
            fallback["deadlines"].append(line.strip()[:200])
    fallback["directions"] = fallback["directions"][:8]
    fallback["deadlines"] = fallback["deadlines"][:6]
    try:
        from llms import generate_text

        prompt = (
            "Analyze this Indian court order excerpt. Return JSON only with keys: "
            "summary (2 sentences), directions (array), compliance (array), "
            "deadlines (array), risks (array), next_steps (array).\n\n"
            + snippet[:6000]
        )
        raw = generate_text(prompt, max_tokens=1200, temperature=0.2)
        if raw and "{" in raw:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            parsed = json.loads(raw[start:end])
            for k in fallback:
                if parsed.get(k):
                    fallback[k] = parsed[k]
    except Exception:
        pass
    return {**fallback, "metadata": meta}


def _today_prefix() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _matter_names(user_id: str) -> Dict[str, str]:
    try:
        from backend.app.core.matter_repo import list_matters

        return {
            str(m.get("matter_id") or ""): str(m.get("matter_name") or "Matter")
            for m in list_matters(user_id) or []
        }
    except Exception:
        return {}


def _audit_message(action: str, resource_type: str, detail: Dict[str, Any]) -> str:
    title = detail.get("title") or detail.get("filename") or detail.get("name") or ""
    if action == "upload" and resource_type == "document":
        return f"uploaded {title or 'a document'}"
    if action == "upload" and resource_type == "court_order":
        return f"uploaded court order {title or detail.get('filename') or ''}".strip()
    if action == "approval_request":
        return f"requested client review on {title or 'draft'}"
    if action == "request_create":
        return f"requested {detail.get('type', 'documents')} from client"
    if action == "folder_create":
        return f"created folder {title or detail.get('name', '')}"
    if action == "create" and resource_type == "knowledge":
        return f"added knowledge entry {title}"
    if action == "court_sync":
        return "synced hearings from eCourts cause list"
    return f"{action.replace('_', ' ')} {resource_type}".strip()


def build_activity_feed(user_id: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Unified timeline — audits, uploads, approvals, client activity."""
    ensure_enterprise_workspace_schema()
    uid = str(user_id)
    names = _matter_names(uid)
    events: List[Dict[str, Any]] = []

    for row in list_audit(uid, limit=40):
        detail = row.get("detail") or {}
        events.append(
            {
                "id": row["audit_id"],
                "created_at": row["created_at"],
                "actor": row.get("actor") or "Firm",
                "category": row.get("resource_type") or "system",
                "icon": "📄"
                if row.get("resource_type") == "document"
                else "⚖️"
                if row.get("resource_type") == "court_order"
                else "🤝"
                if "client" in str(row.get("action"))
                else "⚡",
                "message": _audit_message(
                    str(row.get("action")),
                    str(row.get("resource_type")),
                    detail,
                ),
            }
        )

    conn = connect_data_db()
    for r in conn.execute(
        """
        SELECT doc_id, title, filename, matter_id, created_at
        FROM ent_dms_documents WHERE user_id=? ORDER BY created_at DESC LIMIT 12
        """,
        (uid,),
    ).fetchall():
        label = r[2] or r[1]
        events.append(
            {
                "id": f"doc-{r[0]}",
                "created_at": r[4],
                "actor": "You",
                "category": "document",
                "icon": "📁",
                "message": f"uploaded {label}"
                + (f" → {names.get(r[3], '')}" if r[3] else ""),
            }
        )
    for r in conn.execute(
        """
        SELECT order_id, case_number, filename, matter_id, created_at
        FROM ent_court_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 12
        """,
        (uid,),
    ).fetchall():
        label = r[2] or r[1] or "Court order"
        events.append(
            {
                "id": f"ord-{r[0]}",
                "created_at": r[4],
                "actor": "You",
                "category": "order",
                "icon": "⚖️",
                "message": f"uploaded {label}"
                + (f" → {names.get(r[3], '')}" if r[3] else ""),
            }
        )
    for r in conn.execute(
        """
        SELECT approval_id, title, status, client_action, updated_at
        FROM ent_client_approvals WHERE user_id=? ORDER BY updated_at DESC LIMIT 10
        """,
        (uid,),
    ).fetchall():
        if r[2] == "approved" or r[3] == "approved":
            events.append(
                {
                    "id": f"ap-{r[0]}",
                    "created_at": r[4],
                    "actor": "Client",
                    "category": "approval",
                    "icon": "✅",
                    "message": f"{r[1]} approved",
                }
            )
        elif r[2] == "pending_review":
            events.append(
                {
                    "id": f"ap-p-{r[0]}",
                    "created_at": r[4],
                    "actor": "Firm",
                    "category": "approval",
                    "icon": "📝",
                    "message": f"Awaiting client approval: {r[1]}",
                }
            )
    conn.close()

    try:
        from backend.app.core.matter_repo import list_matter_notes, list_matters

        for m in (list_matters(uid) or [])[:15]:
            mid = str(m.get("matter_id") or "")
            for n in list_matter_notes(uid, mid, limit=3):
                raw = str(n.get("raw_content") or "")
                if "[Client portal upload]" in raw:
                    fname = raw.replace("[Client portal upload]", "").strip()
                    events.append(
                        {
                            "id": f"cli-{mid}-{n.get('timestamp', '')}",
                            "created_at": str(n.get("timestamp") or _utc()),
                            "actor": "Client",
                            "category": "client",
                            "icon": "📤",
                            "message": f"uploaded {fname or 'document'}"
                            + (f" on {m.get('matter_name', 'matter')}" if m.get("matter_name") else ""),
                        }
                    )
    except Exception:
        pass

    events.sort(key=lambda e: str(e.get("created_at") or ""), reverse=True)
    seen = set()
    out: List[Dict[str, Any]] = []
    for e in events:
        key = (e.get("message"), e.get("created_at"))
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
        if len(out) >= limit:
            break
    return out


def build_action_queues(user_id: str) -> Dict[str, List[Dict[str, Any]]]:
    ensure_enterprise_workspace_schema()
    uid = str(user_id)
    names = _matter_names(uid)
    today = _today_prefix()
    conn = connect_data_db()

    pending_review: List[Dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT doc_id, title, filename, matter_id, ocr_confidence, updated_at
        FROM ent_dms_documents
        WHERE user_id=? AND (ocr_confidence < 0.5 OR doc_type IN ('Draft', 'Pleading'))
        ORDER BY updated_at DESC LIMIT 15
        """,
        (uid,),
    ).fetchall():
        pending_review.append(
            {
                "id": r[0],
                "title": r[1] or r[2],
                "matter_name": names.get(r[3], ""),
                "reason": "OCR / review required" if r[4] < 0.5 else "Draft review",
                "updated_at": r[5],
            }
        )

    awaiting_client: List[Dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT approval_id, title, matter_id, client_email, updated_at
        FROM ent_client_approvals WHERE user_id=? AND status='pending_review'
        ORDER BY updated_at DESC
        """,
        (uid,),
    ).fetchall():
        awaiting_client.append(
            {
                "id": r[0],
                "title": r[1],
                "matter_name": names.get(r[2], ""),
                "client_email": r[3],
                "updated_at": r[4],
            }
        )

    client_requests: List[Dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT request_id, request_type, matter_id, client_email, created_at
        FROM ent_client_requests WHERE user_id=? AND status='pending'
        ORDER BY created_at DESC
        """,
        (uid,),
    ).fetchall():
        client_requests.append(
            {
                "id": r[0],
                "title": r[1],
                "matter_name": names.get(r[2], ""),
                "client_email": r[3],
                "created_at": r[4],
            }
        )

    orders_today: List[Dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT order_id, case_number, court, summary, created_at
        FROM ent_court_orders WHERE user_id=? AND created_at >= ?
        ORDER BY created_at DESC LIMIT 20
        """,
        (uid, today),
    ).fetchall():
        orders_today.append(
            {
                "id": r[0],
                "case_number": r[1],
                "court": r[2],
                "summary": (r[3] or "")[:120],
                "created_at": r[4],
            }
        )

    orders_to_comply: List[Dict[str, Any]] = []
    for r in conn.execute(
        """
        SELECT order_id, case_number, deadlines_json, next_steps_json, created_at
        FROM ent_court_orders WHERE user_id=? ORDER BY created_at DESC LIMIT 25
        """,
        (uid,),
    ).fetchall():
        deadlines = _parse_tags(r[2])
        if deadlines or _parse_tags(r[3]):
            orders_to_comply.append(
                {
                    "id": r[0],
                    "case_number": r[1],
                    "deadlines": deadlines[:3],
                    "next_steps": _parse_tags(r[3])[:2],
                    "created_at": r[4],
                }
            )

    conn.close()

    upcoming_hearings: List[Dict[str, Any]] = []
    try:
        from backend.app.core.matter_repo import list_matters

        for m in list_matters(uid) or []:
            hd = m.get("next_hearing_date")
            if hd:
                upcoming_hearings.append(
                    {
                        "matter_id": m.get("matter_id"),
                        "matter_name": m.get("matter_name"),
                        "hearing_date": hd,
                        "venue": m.get("venue", ""),
                        "case_number": m.get("case_number", ""),
                    }
                )
    except Exception:
        pass

    urgent_deadlines: List[Dict[str, Any]] = []
    for o in orders_to_comply[:8]:
        for d in o.get("deadlines") or []:
            urgent_deadlines.append(
                {
                    "order_id": o["id"],
                    "case_number": o.get("case_number"),
                    "deadline": d,
                    "source": "court_order",
                }
            )

    drafts_ready: List[Dict[str, Any]] = []
    conn2 = connect_data_db()
    for r in conn2.execute(
        """
        SELECT approval_id, title, matter_id, updated_at
        FROM ent_client_approvals
        WHERE user_id=? AND (status='approved' OR client_action='approved')
        ORDER BY updated_at DESC LIMIT 10
        """,
        (uid,),
    ).fetchall():
        drafts_ready.append(
            {
                "id": r[0],
                "title": r[1],
                "matter_name": names.get(r[2], ""),
                "updated_at": r[3],
            }
        )
    conn2.close()

    return {
        "documents_awaiting_review": pending_review,
        "awaiting_client_approval": awaiting_client,
        "client_requests": client_requests,
        "orders_uploaded_today": orders_today,
        "orders_to_comply": orders_to_comply[:12],
        "upcoming_hearings": upcoming_hearings[:12],
        "urgent_deadlines": urgent_deadlines[:10],
        "drafts_ready_to_file": drafts_ready,
    }


def build_priorities_today(user_id: str, queues: Dict[str, List]) -> List[Dict[str, Any]]:
    priorities: List[Dict[str, Any]] = []
    for d in (queues.get("urgent_deadlines") or [])[:3]:
        priorities.append(
            {
                "urgency": "red",
                "title": f"Comply: {str(d.get('deadline', ''))[:80]}",
                "subtitle": f"Case {d.get('case_number', '')}",
                "module": "court-orders",
            }
        )
    for o in (queues.get("orders_uploaded_today") or [])[:2]:
        priorities.append(
            {
                "urgency": "yellow",
                "title": f"Review order uploaded today",
                "subtitle": o.get("case_number") or o.get("court", ""),
                "module": "court-orders",
            }
        )
    for a in (queues.get("awaiting_client_approval") or [])[:2]:
        priorities.append(
            {
                "urgency": "yellow",
                "title": f"Awaiting client: {a.get('title', 'Draft')}",
                "subtitle": a.get("matter_name", ""),
                "module": "client-portal",
            }
        )
    for h in (queues.get("upcoming_hearings") or [])[:2]:
        priorities.append(
            {
                "urgency": "yellow",
                "title": f"Hearing — {h.get('matter_name', 'Matter')}",
                "subtitle": str(h.get("hearing_date", "")),
                "module": "automation",
            }
        )
    for d in (queues.get("drafts_ready_to_file") or [])[:2]:
        priorities.append(
            {
                "urgency": "green",
                "title": f"Ready to file: {d.get('title', 'Draft')}",
                "subtitle": d.get("matter_name", ""),
                "module": "drafting",
            }
        )
    if not priorities:
        priorities.append(
            {
                "urgency": "green",
                "title": "All caught up — upload a court order or document",
                "subtitle": "Command center updates in real time",
                "module": "documents",
            }
        )
    return priorities[:8]


def agent_runtime_status(user_id: str) -> List[Dict[str, Any]]:
    from backend.app.core.ai_agents import list_agents

    running_types: set = set()
    try:
        from backend.app.core.ml_job_queue import list_user_ml_jobs

        for j in list_user_ml_jobs(user_id, limit=20):
            if str(j.get("status", "")).upper() in ("QUEUED", "RUNNING", "PROCESSING"):
                running_types.add(str(j.get("job_type", "")))
    except Exception:
        pass

    catalog = {
        "drafting_agent": ("Drafting Agent", "Drafts documents from matter context", "On matter update"),
        "hearing_agent": ("Hearing Agent", "Checks tomorrow's hearings and prep packs", "Daily 6 AM"),
        "compliance_agent": ("Compliance Agent", "Monitors filing deadlines from orders", "Hourly"),
        "order_analysis_agent": ("Order Agent", "Reads new court orders automatically", "On upload"),
        "client_agent": ("Client Agent", "Sends reminders for pending uploads", "Daily"),
        "billing_agent": ("Billing Agent", "Tracks unpaid invoices and trust balances", "Daily"),
        "discovery_agent": ("Discovery Agent", "Triage and privilege review", "On batch upload"),
        "matter_agent": ("Matter Agent", "Matter intelligence and contradictions", "On demand"),
        "knowledge_agent": ("Knowledge Agent", "Indexes precedents and memos", "On new entry"),
        "crm_agent": ("CRM Agent", "Lead scoring and follow-ups", "Hourly"),
    }
    out = []
    for a in list_agents():
        aid = a["id"]
        extra = catalog.get(aid, (a["name"], a["description"], "On demand"))
        out.append(
            {
                **a,
                "name": extra[0],
                "description": extra[1],
                "schedule": extra[2],
                "mode": "autonomous",
                "status": "running" if aid in running_types else "idle",
            }
        )
    for aid, extra in catalog.items():
        if aid not in {x["id"] for x in out}:
            out.append(
                {
                    "id": aid,
                    "name": extra[0],
                    "description": extra[1],
                    "schedule": extra[2],
                    "mode": "autonomous",
                    "status": "running" if aid in running_types else "idle",
                }
            )
    return out


def log_court_sync_activity(user_id: str, matched: int = 0) -> None:
    _audit(
        user_id,
        "court_sync",
        "hearing",
        _new_id(),
        detail={"matched": matched},
    )


def workspace_dashboard(user_id: str, user: Dict[str, Any]) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    uid = str(user_id)
    docs = conn.execute(
        "SELECT COUNT(*) FROM ent_dms_documents WHERE user_id=?", (uid,)
    ).fetchone()[0]
    orders = conn.execute(
        "SELECT COUNT(*) FROM ent_court_orders WHERE user_id=?", (uid,)
    ).fetchone()[0]
    pending_reviews = conn.execute(
        "SELECT COUNT(*) FROM ent_client_approvals WHERE user_id=? AND status='pending_review'",
        (uid,),
    ).fetchone()[0]
    client_requests = conn.execute(
        "SELECT COUNT(*) FROM ent_client_requests WHERE user_id=? AND status='pending'",
        (uid,),
    ).fetchone()[0]
    kb_size = conn.execute(
        "SELECT COUNT(*) FROM ent_knowledge WHERE user_id=?", (uid,)
    ).fetchone()[0]
    ocr_queue = conn.execute(
        "SELECT COUNT(*) FROM ent_dms_documents WHERE user_id=? AND ocr_confidence < 0.5 AND ocr_text=''",
        (uid,),
    ).fetchone()[0]
    conn.close()

    matters_open = 0
    matters_closed = 0
    upcoming_hearings = 0
    try:
        from backend.app.core.matter_repo import list_matters

        for m in list_matters(uid) or []:
            tier = str(m.get("status_tier") or "").lower()
            if tier in ("closed", "archived"):
                matters_closed += 1
            else:
                matters_open += 1
            if m.get("next_hearing_date"):
                upcoming_hearings += 1
    except Exception:
        pass

    storage_bytes = docs * 250_000 + orders * 180_000
    today = _today_prefix()
    conn = connect_data_db()
    orders_today_count = conn.execute(
        "SELECT COUNT(*) FROM ent_court_orders WHERE user_id=? AND created_at >= ?",
        (uid, today),
    ).fetchone()[0]
    client_count = conn.execute(
        "SELECT COUNT(DISTINCT client_email) FROM client_portal_access WHERE user_id=?",
        (uid,),
    ).fetchone()[0]
    conn.close()

    ai_running = 0
    try:
        from backend.app.core.ml_job_queue import list_user_ml_jobs

        ai_running = sum(
            1
            for j in list_user_ml_jobs(uid, limit=30)
            if str(j.get("status", "")).upper() in ("QUEUED", "RUNNING", "PROCESSING")
        )
    except Exception:
        pass

    queues = build_action_queues(uid)
    activity = build_activity_feed(uid, limit=30)
    priorities = build_priorities_today(uid, queues)

    from backend.app.core.enterprise_hub import (
        build_notifications,
        firm_analytics,
        onboarding_activity_placeholder,
        onboarding_priorities,
        workspace_is_empty,
    )

    metrics_dict = {
        "total_documents": docs,
        "total_orders": orders,
        "open_matters": matters_open,
    }
    is_empty = workspace_is_empty(metrics_dict) and not activity
    if is_empty:
        activity = onboarding_activity_placeholder() + activity
        priorities = onboarding_priorities()
    notifications = build_notifications(uid, queues)

    return {
        "metrics": {
            "total_documents": docs,
            "total_orders": orders,
            "pending_reviews": pending_reviews,
            "upcoming_deadlines": upcoming_hearings,
            "client_requests": client_requests,
            "storage_mb": round(storage_bytes / (1024 * 1024), 2),
            "ocr_queue": ocr_queue,
            "ai_processing_queue": ai_running,
            "knowledge_base_size": kb_size,
            "open_matters": matters_open,
            "closed_matters": matters_closed,
            "orders_today": orders_today_count,
            "documents_awaiting_review": len(queues.get("documents_awaiting_review") or []),
            "pending_approvals": len(queues.get("awaiting_client_approval") or []),
            "active_clients": client_count,
        },
        "kpi_strip": {
            "documents": docs,
            "court_orders": orders,
            "matters": matters_open,
            "clients": client_count,
            "storage_mb": round(storage_bytes / (1024 * 1024), 2),
            "ai_tasks": ai_running,
        },
        "snapshot": {
            "documents_awaiting_review": len(queues.get("documents_awaiting_review") or []),
            "orders_today": orders_today_count,
            "client_requests": client_requests,
            "pending_approvals": pending_reviews,
            "ai_tasks_running": ai_running,
            "upcoming_hearings": len(queues.get("upcoming_hearings") or []),
        },
        "action_queues": queues,
        "activity_feed": activity,
        "priorities_today": priorities,
        "agents": agent_runtime_status(uid),
        "permissions": permissions_for_user(user),
        "permission_roles": _permission_roles_summary(),
        "practice_areas": list(PRACTICE_AREAS),
        "notifications": notifications,
        "is_empty": is_empty,
        "analytics": firm_analytics(uid),
    }


def _permission_roles_summary() -> List[Dict[str, Any]]:
    return [
        {"role": "partner", "label": "Partner", "access": "Full firm control"},
        {"role": "senior_associate", "label": "Senior Associate", "access": "Matters, DMS, orders, billing"},
        {"role": "associate", "label": "Associate", "access": "Matters, drafts, upload"},
        {"role": "paralegal", "label": "Clerk / Paralegal", "access": "Documents, calendar"},
        {"role": "client", "label": "Client", "access": "Portal only"},
        {"role": "admin", "label": "Admin", "access": "Settings & users"},
    ]


def list_folders(user_id: str, *, matter_id: str = "", practice_area: str = "") -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    q = "SELECT folder_id, practice_area, matter_id, folder_name, parent_id, created_at FROM ent_dms_folders WHERE user_id=?"
    params: List[Any] = [str(user_id)]
    if practice_area:
        q += " AND practice_area=?"
        params.append(practice_area)
    if matter_id:
        q += " AND matter_id=?"
        params.append(matter_id)
    rows = conn.execute(q + " ORDER BY practice_area, folder_name", params).fetchall()
    conn.close()
    return [
        {
            "folder_id": r[0],
            "practice_area": r[1],
            "matter_id": r[2],
            "folder_name": r[3],
            "parent_id": r[4],
            "created_at": r[5],
        }
        for r in rows
    ]


def ensure_matter_folders(user_id: str, matter_id: str, matter_name: str, practice_area: str) -> None:
    pa = practice_area if practice_area in PRACTICE_AREAS else "Litigation"
    existing = {f["folder_name"] for f in list_folders(user_id, matter_id=matter_id)}
    for fname in FOLDER_TYPES:
        if fname in existing:
            continue
        create_folder(
            user_id,
            practice_area=pa,
            matter_id=matter_id,
            folder_name=fname,
            parent_id="",
        )


def create_folder(
    user_id: str,
    *,
    practice_area: str,
    matter_id: str = "",
    folder_name: str,
    parent_id: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    fid = _new_id()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ent_dms_folders
        (folder_id, user_id, practice_area, matter_id, folder_name, parent_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (fid, str(user_id), practice_area, matter_id, folder_name, parent_id, now, now),
    )
    conn.commit()
    conn.close()
    _audit(user_id, "folder_create", "folder", fid, detail={"name": folder_name})
    return {"folder_id": fid, "folder_name": folder_name}


def list_documents(
    user_id: str,
    *,
    matter_id: str = "",
    folder_id: str = "",
    practice_area: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    q = (
        "SELECT doc_id, folder_id, matter_id, practice_area, doc_type, title, filename, "
        "tags_json, version_no, ocr_confidence, expiry_date, updated_at FROM ent_dms_documents WHERE user_id=?"
    )
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND matter_id=?"
        params.append(matter_id)
    if folder_id:
        q += " AND folder_id=?"
        params.append(folder_id)
    if practice_area:
        q += " AND practice_area=?"
        params.append(practice_area)
    rows = conn.execute(q + " ORDER BY updated_at DESC LIMIT ?", params + [limit]).fetchall()
    conn.close()
    return [_doc_row(r) for r in rows]


def _doc_row(r: Tuple[Any, ...]) -> Dict[str, Any]:
    return {
        "doc_id": r[0],
        "folder_id": r[1],
        "matter_id": r[2],
        "practice_area": r[3],
        "doc_type": r[4],
        "title": r[5],
        "filename": r[6],
        "tags": _parse_tags(r[7]),
        "version_no": r[8],
        "ocr_confidence": r[9],
        "expiry_date": r[10],
        "updated_at": r[11],
    }


def get_document(user_id: str, doc_id: str) -> Optional[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    row = conn.execute(
        """
        SELECT doc_id, folder_id, matter_id, practice_area, doc_type, title, filename,
               tags_json, version_no, content_text, ocr_text, ocr_confidence, expiry_date,
               created_at, updated_at
        FROM ent_dms_documents WHERE user_id=? AND doc_id=?
        """,
        (str(user_id), doc_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    return {
        "doc_id": row[0],
        "folder_id": row[1],
        "matter_id": row[2],
        "practice_area": row[3],
        "doc_type": row[4],
        "title": row[5],
        "filename": row[6],
        "tags": _parse_tags(row[7]),
        "version_no": row[8],
        "content_text": row[9],
        "ocr_text": row[10],
        "ocr_confidence": row[11],
        "expiry_date": row[12],
        "created_at": row[13],
        "updated_at": row[14],
        "versions": list_document_versions(user_id, doc_id),
    }


def list_document_versions(user_id: str, doc_id: str) -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT version_id, version_no, author, change_summary, created_at
        FROM ent_dms_versions WHERE user_id=? AND doc_id=? ORDER BY version_no DESC
        """,
        (str(user_id), doc_id),
    ).fetchall()
    conn.close()
    return [
        {
            "version_id": r[0],
            "version_no": r[1],
            "author": r[2],
            "change_summary": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]


def upload_document(
    user_id: str,
    *,
    title: str,
    filename: str = "",
    content_text: str = "",
    matter_id: str = "",
    folder_id: str = "",
    practice_area: str = "Litigation",
    doc_type: str = "General",
    tags: Optional[List[str]] = None,
    run_ocr: bool = True,
    author: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    from backend.app.core.enterprise_hub import (
        check_duplicate_document,
        content_hash,
        log_matter_timeline,
        migrate_enterprise_columns,
    )

    migrate_enterprise_columns()
    text = (content_text or "").strip()
    dup = check_duplicate_document(user_id, text) if text else None
    ocr_text = text
    ocr_conf = 0.95 if len(text) > 200 else 0.0
    if run_ocr and len(text) < 200:
        ocr_conf = 0.35
    doc_id = _new_id()
    now = _utc()
    tags_json = json.dumps(tags or [])
    chash = content_hash(text)
    conn = connect_data_db()
    try:
        conn.execute(
            """
            INSERT INTO ent_dms_documents
            (doc_id, user_id, folder_id, matter_id, practice_area, doc_type, title, filename,
             tags_json, version_no, content_text, ocr_text, ocr_confidence, expiry_date,
             file_size, content_hash, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, '', ?, ?, ?, ?)
            """,
        (
            doc_id,
            str(user_id),
            folder_id,
            matter_id,
            practice_area,
            doc_type,
            title or filename or "Document",
            filename,
            tags_json,
            text,
            ocr_text,
            ocr_conf,
            len(text.encode("utf-8")),
            chash,
            now,
            now,
        ),
        )
    except Exception:
        conn.execute(
            """
            INSERT INTO ent_dms_documents
            (doc_id, user_id, folder_id, matter_id, practice_area, doc_type, title, filename,
             tags_json, version_no, content_text, ocr_text, ocr_confidence, expiry_date,
             file_size, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, '', ?, ?, ?)
            """,
            (
                doc_id,
                str(user_id),
                folder_id,
                matter_id,
                practice_area,
                doc_type,
                title or filename or "Document",
                filename,
                tags_json,
                text,
                ocr_text,
                ocr_conf,
                len(text.encode("utf-8")),
                now,
                now,
            ),
        )
    vid = _new_id()
    conn.execute(
        """
        INSERT INTO ent_dms_versions
        (version_id, doc_id, user_id, version_no, author, change_summary, content_text, created_at)
        VALUES (?, ?, ?, 1, ?, 'Initial upload', ?, ?)
        """,
        (vid, doc_id, str(user_id), author or str(user_id), text, now),
    )
    conn.commit()
    conn.close()
    _audit(user_id, "upload", "document", doc_id, actor=author, detail={"title": title, "filename": filename})
    log_matter_timeline(
        user_id,
        matter_id,
        f"Document uploaded: {title or filename}",
        description="Added to firm DMS",
        event_type="document",
    )
    out = get_document(user_id, doc_id) or {"doc_id": doc_id}
    if dup:
        out["duplicate_warning"] = dup
    return out


def search_documents(
    user_id: str,
    query: str,
    *,
    matter_id: str = "",
    doc_type: str = "",
    tag: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    q = (query or "").strip().lower()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT doc_id, title, matter_id, practice_area, doc_type, tags_json, updated_at,
               content_text, ocr_text
        FROM ent_dms_documents WHERE user_id=?
        ORDER BY updated_at DESC LIMIT 200
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        if matter_id and r[2] != matter_id:
            continue
        if doc_type and r[4] != doc_type:
            continue
        tags = _parse_tags(r[5])
        if tag and tag not in tags:
            continue
        hay = f"{r[1]} {r[4]} {' '.join(tags)} {r[7]} {r[8]}".lower()
        if q and q not in hay:
            continue
        out.append(
            {
                "doc_id": r[0],
                "title": r[1],
                "matter_id": r[2],
                "practice_area": r[3],
                "doc_type": r[4],
                "tags": tags,
                "updated_at": r[6],
                "snippet": (r[7] or r[8] or "")[:240],
            }
        )
        if len(out) >= limit:
            break
    return out


def list_court_orders(
    user_id: str,
    *,
    matter_id: str = "",
    limit: int = 100,
) -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    q = (
        "SELECT order_id, matter_id, client_name, court, judge, case_number, order_date, "
        "order_type, practice_area, filename, summary, created_at FROM ent_court_orders WHERE user_id=?"
    )
    params: List[Any] = [str(user_id)]
    if matter_id:
        q += " AND matter_id=?"
        params.append(matter_id)
    rows = conn.execute(q + " ORDER BY order_date DESC, created_at DESC LIMIT ?", params + [limit]).fetchall()
    conn.close()
    return [_order_list_row(r) for r in rows]


def _order_list_row(r: Tuple[Any, ...]) -> Dict[str, Any]:
    return {
        "order_id": r[0],
        "matter_id": r[1],
        "client_name": r[2],
        "court": r[3],
        "judge": r[4],
        "case_number": r[5],
        "order_date": r[6],
        "order_type": r[7],
        "practice_area": r[8],
        "filename": r[9],
        "summary": r[10],
        "created_at": r[11],
    }


def get_court_order(user_id: str, order_id: str) -> Optional[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT * FROM ent_court_orders WHERE user_id=? AND order_id=?",
        (str(user_id), order_id),
    ).fetchone()
    conn.close()
    if not row:
        return None
    cols = [
        "order_id",
        "user_id",
        "matter_id",
        "client_name",
        "court",
        "judge",
        "case_number",
        "order_date",
        "order_type",
        "practice_area",
        "keywords_json",
        "filename",
        "content_text",
        "ocr_text",
        "ocr_confidence",
        "summary",
        "directions_json",
        "compliance_json",
        "deadlines_json",
        "risks_json",
        "next_steps_json",
        "created_at",
        "updated_at",
    ]
    d = dict(zip(cols, row))
    for k in ("keywords", "directions", "compliance", "deadlines", "risks", "next_steps"):
        jk = f"{k}_json" if k != "keywords" else "keywords_json"
        if jk in d:
            d[k] = _parse_tags(d.pop(jk, "[]"))
    try:
        intel = json.loads(d.pop("intelligence_json", "{}") or "{}")
        if isinstance(intel, dict):
            d["intelligence"] = intel
            d["affected_parties"] = intel.get("affected_parties", [])
            d["required_actions"] = intel.get("required_actions", [])
            d["next_hearing"] = intel.get("next_hearing", "")
            d["court_directions"] = intel.get("court_directions", d.get("directions", []))
    except Exception:
        pass
    if "risk_level" in d:
        d["risk_level"] = d.get("risk_level") or ""
    return d


def upload_court_order(
    user_id: str,
    *,
    content_text: str,
    filename: str = "",
    matter_id: str = "",
    client_name: str = "",
    order_type: str = "order",
    practice_area: str = "Litigation",
    run_analysis: bool = True,
) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    from backend.app.core.enterprise_hub import enrich_order_intelligence, log_matter_timeline, migrate_enterprise_columns

    migrate_enterprise_columns()
    text = (content_text or "").strip()
    raw_analysis = _ai_order_analysis(text) if run_analysis else {}
    analysis = enrich_order_intelligence(raw_analysis, text) if run_analysis else {}
    meta = analysis.get("metadata") or _extract_order_metadata(text)
    oid = _new_id()
    now = _utc()
    otype = order_type if order_type in ORDER_TYPES else "order"
    intel_json = json.dumps(
        {
            "case_summary": analysis.get("case_summary"),
            "court_directions": analysis.get("court_directions"),
            "required_actions": analysis.get("required_actions"),
            "affected_parties": analysis.get("affected_parties"),
            "next_hearing": analysis.get("next_hearing"),
        }
    )
    conn = connect_data_db()
    try:
        conn.execute(
            """
            INSERT INTO ent_court_orders
            (order_id, user_id, matter_id, client_name, court, judge, case_number, order_date,
             order_type, practice_area, keywords_json, filename, content_text, ocr_text,
             ocr_confidence, summary, directions_json, compliance_json, deadlines_json,
             risks_json, next_steps_json, intelligence_json, risk_level, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                oid,
                str(user_id),
                matter_id,
                client_name,
                meta.get("court", ""),
                meta.get("judge", ""),
                meta.get("case_number", ""),
                meta.get("order_date", ""),
                otype,
                practice_area,
                json.dumps(meta.get("keywords", [])),
                filename,
                text,
                text,
                0.9 if len(text) > 100 else 0.4,
                str(analysis.get("case_summary") or analysis.get("summary", "")),
                json.dumps(analysis.get("court_directions") or analysis.get("directions", [])),
                json.dumps(analysis.get("required_actions") or analysis.get("compliance", [])),
                json.dumps(analysis.get("deadlines", [])),
                json.dumps(analysis.get("risks", [])),
                json.dumps(analysis.get("next_steps", [])),
                intel_json,
                str(analysis.get("risk_level", "")),
                now,
                now,
            ),
        )
    except Exception:
        conn.execute(
            """
            INSERT INTO ent_court_orders
            (order_id, user_id, matter_id, client_name, court, judge, case_number, order_date,
             order_type, practice_area, keywords_json, filename, content_text, ocr_text,
             ocr_confidence, summary, directions_json, compliance_json, deadlines_json,
             risks_json, next_steps_json, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                oid,
                str(user_id),
                matter_id,
                client_name,
                meta.get("court", ""),
                meta.get("judge", ""),
                meta.get("case_number", ""),
                meta.get("order_date", ""),
                otype,
                practice_area,
                json.dumps(meta.get("keywords", [])),
                filename,
                text,
                text,
                0.9 if len(text) > 100 else 0.4,
                str(analysis.get("summary", "")),
                json.dumps(analysis.get("directions", [])),
                json.dumps(analysis.get("compliance", [])),
                json.dumps(analysis.get("deadlines", [])),
                json.dumps(analysis.get("risks", [])),
                json.dumps(analysis.get("next_steps", [])),
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()
    _audit(user_id, "upload", "court_order", oid, detail={"filename": filename})
    log_matter_timeline(
        user_id,
        matter_id,
        f"Court order uploaded: {filename or meta.get('case_number') or 'Order'}",
        description=analysis.get("case_summary", "")[:500],
        event_type="court_order",
    )
    add_knowledge_entry(
        user_id,
        entry_type="order",
        title=filename or f"Order {meta.get('case_number') or oid[:8]}",
        content_text=text[:12000],
        matter_id=matter_id,
        court=meta.get("court", ""),
        tags=meta.get("keywords", []),
        linked_order_id=oid,
    )
    return get_court_order(user_id, oid) or {"order_id": oid}


def search_court_orders(
    user_id: str,
    query: str,
    *,
    judge: str = "",
    court: str = "",
    matter_id: str = "",
    order_type: str = "",
    limit: int = 50,
) -> List[Dict[str, Any]]:
    items = list_court_orders(user_id, matter_id=matter_id, limit=200)
    q = (query or "").strip().lower()
    out = []
    for o in items:
        if judge and judge.lower() not in (o.get("judge") or "").lower():
            continue
        if court and court.lower() not in (o.get("court") or "").lower():
            continue
        if order_type and o.get("order_type") != order_type:
            continue
        hay = " ".join(
            str(o.get(k) or "")
            for k in ("summary", "court", "judge", "case_number", "client_name")
        ).lower()
        if q and q not in hay:
            full = get_court_order(user_id, o["order_id"])
            if full and q not in (full.get("content_text") or "").lower():
                continue
        out.append(o)
        if len(out) >= limit:
            break
    return out


def add_knowledge_entry(
    user_id: str,
    *,
    entry_type: str,
    title: str,
    content_text: str = "",
    practice_area: str = "",
    matter_id: str = "",
    court: str = "",
    tags: Optional[List[str]] = None,
    linked_order_id: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    eid = _new_id()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ent_knowledge
        (entry_id, user_id, entry_type, title, practice_area, matter_id, court,
         tags_json, content_text, linked_order_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eid,
            str(user_id),
            entry_type,
            title,
            practice_area,
            matter_id,
            court,
            json.dumps(tags or []),
            content_text[:50000],
            linked_order_id,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()
    _audit(user_id, "create", "knowledge", eid, detail={"title": title})
    return {"entry_id": eid, "title": title}


def search_knowledge(user_id: str, query: str, limit: int = 40) -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    q = (query or "").strip().lower()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT entry_id, entry_type, title, practice_area, matter_id, court, tags_json,
               content_text, linked_order_id, updated_at
        FROM ent_knowledge WHERE user_id=? ORDER BY updated_at DESC LIMIT 150
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        tags = _parse_tags(r[6])
        hay = f"{r[2]} {r[3]} {r[4]} {r[5]} {' '.join(tags)} {r[7]}".lower()
        if q and q not in hay:
            continue
        out.append(
            {
                "entry_id": r[0],
                "entry_type": r[1],
                "title": r[2],
                "practice_area": r[3],
                "matter_id": r[4],
                "court": r[5],
                "tags": tags,
                "snippet": (r[7] or "")[:280],
                "linked_order_id": r[8],
                "updated_at": r[9],
            }
        )
        if len(out) >= limit:
            break
    return out


def list_client_portal_ops(user_id: str) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    from backend.app.core.saas_schema import ensure_saas_schema

    ensure_saas_schema()
    conn = connect_data_db()
    portals = conn.execute(
        """
        SELECT access_id, matter_id, client_email, expires_at, created_at
        FROM client_portal_access WHERE user_id=? ORDER BY created_at DESC LIMIT 50
        """,
        (str(user_id),),
    ).fetchall()
    requests = conn.execute(
        """
        SELECT request_id, matter_id, client_email, request_type, status, notes, created_at
        FROM ent_client_requests WHERE user_id=? ORDER BY created_at DESC LIMIT 50
        """,
        (str(user_id),),
    ).fetchall()
    approvals = conn.execute(
        """
        SELECT approval_id, matter_id, title, status, client_email, client_action, updated_at
        FROM ent_client_approvals WHERE user_id=? ORDER BY updated_at DESC LIMIT 50
        """,
        (str(user_id),),
    ).fetchall()
    conn.close()
    return {
        "portals": [
            {
                "access_id": r[0],
                "matter_id": r[1],
                "client_email": r[2],
                "expires_at": r[3],
                "created_at": r[4],
            }
            for r in portals
        ],
        "document_requests": [
            {
                "request_id": r[0],
                "matter_id": r[1],
                "client_email": r[2],
                "request_type": r[3],
                "status": r[4],
                "notes": r[5],
                "created_at": r[6],
            }
            for r in requests
        ],
        "approvals": [
            {
                "approval_id": r[0],
                "matter_id": r[1],
                "title": r[2],
                "status": r[3],
                "client_email": r[4],
                "client_action": r[5],
                "updated_at": r[6],
            }
            for r in approvals
        ],
    }


def create_document_request(
    user_id: str,
    *,
    matter_id: str,
    request_type: str,
    client_email: str = "",
    notes: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    rid = _new_id()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ent_client_requests
        (request_id, user_id, matter_id, client_email, request_type, status, notes, created_at)
        VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (rid, str(user_id), matter_id, client_email, request_type, notes, now),
    )
    conn.commit()
    conn.close()
    _audit(user_id, "request_create", "client_request", rid, detail={"type": request_type})
    return {"request_id": rid, "status": "pending"}


def request_client_review(
    user_id: str,
    *,
    matter_id: str,
    title: str,
    draft_id: str = "",
    client_email: str = "",
) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    aid = _new_id()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO ent_client_approvals
        (approval_id, user_id, matter_id, draft_id, title, status, client_email,
         client_action, client_note, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'pending_review', ?, '', '', ?, ?)
        """,
        (aid, str(user_id), matter_id, draft_id, title, client_email, now, now),
    )
    conn.commit()
    conn.close()
    _audit(user_id, "approval_request", "approval", aid, detail={"title": title})
    return {"approval_id": aid, "status": "pending_review"}


def list_audit(user_id: str, *, query: str = "", limit: int = 80) -> List[Dict[str, Any]]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT audit_id, actor, action, resource_type, resource_id, detail_json, created_at
        FROM ent_audit WHERE user_id=? ORDER BY created_at DESC LIMIT ?
        """,
        (str(user_id), limit * 2),
    ).fetchall()
    conn.close()
    q = (query or "").strip().lower()
    out = []
    for r in rows:
        detail = r[5]
        hay = f"{r[2]} {r[3]} {r[4]} {detail}".lower()
        if q and q not in hay:
            continue
        out.append(
            {
                "audit_id": r[0],
                "actor": r[1],
                "action": r[2],
                "resource_type": r[3],
                "resource_id": r[4],
                "detail": json.loads(detail) if detail else {},
                "created_at": r[6],
            }
        )
        if len(out) >= limit:
            break
    return out


def storage_summary(user_id: str) -> Dict[str, Any]:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    doc_rows = conn.execute(
        "SELECT file_size FROM ent_dms_documents WHERE user_id=?", (str(user_id),)
    ).fetchall()
    order_rows = conn.execute(
        "SELECT LENGTH(content_text) FROM ent_court_orders WHERE user_id=?", (str(user_id),)
    ).fetchall()
    conn.close()
    bytes_used = sum(r[0] or 0 for r in doc_rows) + sum(r[0] or 0 for r in order_rows)
    quota_gb = 50
    return {
        "bytes_used": bytes_used,
        "mb_used": round(bytes_used / (1024 * 1024), 2),
        "quota_gb": quota_gb,
        "percent_used": min(100, round(100 * bytes_used / (quota_gb * 1024**3), 2)),
        "document_count": len(doc_rows),
        "order_count": len(order_rows),
    }
