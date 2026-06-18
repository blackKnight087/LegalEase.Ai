"""Enterprise hub — global search, matter-centric views, notifications, analytics."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.enterprise_workspace import (
    build_action_queues,
    build_activity_feed,
    ensure_enterprise_workspace_schema,
    list_court_orders,
    list_documents,
    search_documents,
    search_knowledge,
    _matter_names,
    _parse_tags,
    _utc,
)

ONBOARDING_CTAS = [
    {"id": "doc", "label": "Upload your first document", "module": "documents", "icon": "📁"},
    {"id": "order", "label": "Import your first court order", "module": "court-orders", "icon": "⚖️"},
    {"id": "client", "label": "Invite a client", "module": "client-portal", "icon": "🤝"},
    {"id": "matter", "label": "Create a matter", "module": "matters", "icon": "📂", "href": "/matters/new"},
]


def migrate_enterprise_columns() -> None:
    ensure_enterprise_workspace_schema()
    conn = connect_data_db()
    for table, col, typedef in (
        ("ent_dms_documents", "content_hash", "TEXT NOT NULL DEFAULT ''"),
        ("ent_court_orders", "intelligence_json", "TEXT NOT NULL DEFAULT '{}'"),
        ("ent_court_orders", "risk_level", "TEXT NOT NULL DEFAULT ''"),
    ):
        try:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typedef}")
        except Exception:
            pass
    conn.commit()
    conn.close()


def content_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", errors="ignore")).hexdigest()[:32]


def log_matter_timeline(
    user_id: str,
    matter_id: str,
    title: str,
    description: str = "",
    event_type: str = "enterprise",
) -> None:
    if not matter_id:
        return
    try:
        from backend.app.core.matter_workflow import add_timeline_event

        add_timeline_event(
            user_id,
            matter_id,
            title=title,
            description=description,
            event_type=event_type,
        )
    except Exception:
        pass


def enrich_order_intelligence(analysis: Dict[str, Any], text: str) -> Dict[str, Any]:
    meta = analysis.get("metadata") or {}
    risks = analysis.get("risks") or []
    deadlines = analysis.get("deadlines") or []
    risk_level = "low"
    if len(risks) >= 2 or any("contempt" in str(r).lower() for r in risks):
        risk_level = "high"
    elif deadlines or analysis.get("directions"):
        risk_level = "medium"
    parties: List[str] = []
    for pat in (
        r"(?:Petitioner|Appellant|Plaintiff|Respondent|Defendant)[:\s]+([^\n,]{3,60})",
        r"(?:Accused|Complainant)[:\s]+([^\n,]{3,60})",
    ):
        for m in re.finditer(pat, text or "", re.I):
            parties.append(m.group(1).strip()[:60])
    parties = list(dict.fromkeys(parties))[:6]
    next_hearing = ""
    m = re.search(
        r"(?:next\s+)?(?:hearing|date)[:\s]*(\d{1,2}[\./\-]\d{1,2}[\./\-]\d{2,4})",
        text or "",
        re.I,
    )
    if m:
        next_hearing = m.group(1)
    required_actions = list(analysis.get("compliance") or []) + list(
        analysis.get("next_steps") or []
    )[:8]
    return {
        **analysis,
        "risk_level": risk_level,
        "affected_parties": parties,
        "required_actions": required_actions,
        "next_hearing": next_hearing,
        "case_summary": analysis.get("summary", ""),
        "court_directions": (analysis.get("directions") or [])[:10],
    }


def workspace_is_empty(metrics: Dict[str, Any]) -> bool:
    return (
        int(metrics.get("total_documents") or 0) == 0
        and int(metrics.get("total_orders") or 0) == 0
        and int(metrics.get("open_matters") or 0) == 0
    )


def onboarding_priorities() -> List[Dict[str, Any]]:
    return [
        {
            "urgency": "green",
            "title": cta["label"],
            "subtitle": "Get started in under a minute",
            "module": cta.get("module"),
            "href": cta.get("href"),
            "onboarding": True,
        }
        for cta in ONBOARDING_CTAS
    ]


def onboarding_activity_placeholder() -> List[Dict[str, Any]]:
    return [
        {
            "id": "onboard-1",
            "created_at": _utc(),
            "actor": "LegalEase",
            "category": "onboarding",
            "icon": "✨",
            "message": "Welcome — your firm command center is ready",
            "onboarding": True,
        }
    ]


def build_notifications(user_id: str, queues: Dict[str, List]) -> List[Dict[str, Any]]:
    notes: List[Dict[str, Any]] = []
    for h in (queues.get("upcoming_hearings") or [])[:5]:
        notes.append(
            {
                "id": f"hear-{h.get('matter_id')}",
                "type": "hearing",
                "title": f"Hearing: {h.get('matter_name', 'Matter')}",
                "body": str(h.get("hearing_date", "")),
                "urgency": "high",
            }
        )
    for o in (queues.get("orders_uploaded_today") or [])[:3]:
        notes.append(
            {
                "id": f"ord-{o.get('id')}",
                "type": "order",
                "title": "New court order uploaded",
                "body": str(o.get("case_number") or o.get("summary", ""))[:80],
                "urgency": "medium",
            }
        )
    for r in (queues.get("client_requests") or [])[:3]:
        notes.append(
            {
                "id": f"cr-{r.get('id')}",
                "type": "client",
                "title": "Client document request",
                "body": str(r.get("title", "")),
                "urgency": "medium",
            }
        )
    for a in (queues.get("awaiting_client_approval") or [])[:3]:
        notes.append(
            {
                "id": f"ap-{a.get('id')}",
                "type": "approval",
                "title": "Draft awaiting client approval",
                "body": str(a.get("title", "")),
                "urgency": "low",
            }
        )
    for d in (queues.get("urgent_deadlines") or [])[:3]:
        notes.append(
            {
                "id": f"dl-{hash(str(d))}",
                "type": "deadline",
                "title": "Deadline tomorrow",
                "body": str(d.get("deadline", ""))[:100],
                "urgency": "high",
            }
        )
    if not notes:
        notes.append(
            {
                "id": "none",
                "type": "info",
                "title": "No urgent notifications",
                "body": "You're all caught up",
                "urgency": "low",
            }
        )
    return notes


def global_enterprise_search(user_id: str, query: str, limit: int = 30) -> Dict[str, Any]:
    q = (query or "").strip().lower()
    if len(q) < 2:
        return {"query": query, "results": [], "groups": {}}
    names = _matter_names(user_id)
    results: List[Dict[str, Any]] = []

    for d in search_documents(user_id, q, limit=15):
        results.append(
            {
                "type": "document",
                "id": d["doc_id"],
                "title": d["title"],
                "subtitle": names.get(d.get("matter_id", ""), d.get("doc_type", "")),
                "snippet": d.get("snippet", ""),
                "matter_id": d.get("matter_id", ""),
            }
        )

    for o in list_court_orders(user_id, limit=80):
        hay = f"{o.get('case_number')} {o.get('court')} {o.get('judge')} {o.get('summary')}".lower()
        if q in hay:
            results.append(
                {
                    "type": "order",
                    "id": o["order_id"],
                    "title": o.get("case_number") or o.get("filename") or "Court order",
                    "subtitle": o.get("court", ""),
                    "snippet": (o.get("summary") or "")[:120],
                    "matter_id": o.get("matter_id", ""),
                }
            )

    try:
        from backend.app.core.matter_repo import list_matters

        for m in list_matters(user_id) or []:
            hay = f"{m.get('matter_name')} {m.get('case_number')} {m.get('practice_area')}".lower()
            if q in hay:
                results.append(
                    {
                        "type": "matter",
                        "id": m.get("matter_id"),
                        "title": m.get("matter_name"),
                        "subtitle": m.get("case_number", ""),
                        "snippet": m.get("practice_area", ""),
                        "matter_id": m.get("matter_id"),
                    }
                )
    except Exception:
        pass

    for k in search_knowledge(user_id, q, limit=10):
        results.append(
            {
                "type": "knowledge",
                "id": k["entry_id"],
                "title": k["title"],
                "subtitle": k.get("entry_type", ""),
                "snippet": k.get("snippet", ""),
                "matter_id": k.get("matter_id", ""),
            }
        )

    try:
        from backend.app.core.matter_repo import list_matter_notes

        for mid, mname in list(names.items())[:30]:
            for n in list_matter_notes(user_id, mid, limit=20):
                raw = str(n.get("raw_content") or "")
                if q in raw.lower():
                    results.append(
                        {
                            "type": "note",
                            "id": str(n.get("note_id") or mid),
                            "title": f"Note on {mname}",
                            "subtitle": mid[:8],
                            "snippet": raw[:120],
                            "matter_id": mid,
                        }
                    )
    except Exception:
        pass

    try:
        from backend.app.core.database import connect_data_db

        conn = connect_data_db()
        rows = conn.execute(
            """
            SELECT DISTINCT client_email FROM client_portal_access
            WHERE user_id=? AND client_email LIKE ?
            LIMIT 10
            """,
            (str(user_id), f"%{q}%"),
        ).fetchall()
        conn.close()
        for r in rows:
            results.append(
                {
                    "type": "client",
                    "id": r[0],
                    "title": r[0],
                    "subtitle": "Portal client",
                    "snippet": "",
                    "matter_id": "",
                }
            )
    except Exception:
        pass

    try:
        from backend.app.core.clause_repo import list_clauses

        for c in (list_clauses(user_id) or [])[:200]:
            text = f"{c.get('clause_tag', '')} {c.get('clause_text_content', '')}".lower()
            if q in text:
                results.append(
                    {
                        "type": "clause",
                        "id": c.get("clause_id", ""),
                        "title": c.get("clause_tag", "Clause"),
                        "subtitle": "Clause library",
                        "snippet": (c.get("clause_text_content") or "")[:100],
                        "matter_id": "",
                    }
                )
    except Exception:
        pass

    groups: Dict[str, List] = {}
    for r in results[:limit]:
        t = r["type"]
        groups.setdefault(t, []).append(r)

    return {"query": query, "results": results[:limit], "groups": groups}


def list_matters_hub(user_id: str) -> List[Dict[str, Any]]:
    migrate_enterprise_columns()
    names = _matter_names(user_id)
    conn = connect_data_db()
    doc_counts = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT matter_id, COUNT(*) FROM ent_dms_documents WHERE user_id=? GROUP BY matter_id",
            (str(user_id),),
        ).fetchall()
    }
    order_counts = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT matter_id, COUNT(*) FROM ent_court_orders WHERE user_id=? GROUP BY matter_id",
            (str(user_id),),
        ).fetchall()
    }
    conn.close()
    try:
        from backend.app.core.matter_repo import list_matters

        matters = list_matters(user_id) or []
    except Exception:
        matters = []
    out = []
    for m in matters:
        mid = str(m.get("matter_id") or "")
        out.append(
            {
                "matter_id": mid,
                "matter_name": m.get("matter_name"),
                "case_number": m.get("case_number"),
                "status_tier": m.get("status_tier"),
                "practice_area": m.get("practice_area"),
                "next_hearing_date": m.get("next_hearing_date"),
                "document_count": doc_counts.get(mid, 0),
                "order_count": order_counts.get(mid, 0),
                "client_name": m.get("client_name", ""),
            }
        )
    if not out and not names:
        return []
    return out


def get_matter_hub(user_id: str, matter_id: str) -> Dict[str, Any]:
    from backend.app.core.matter_repo import get_matter
    from backend.app.core.matter_workflow import list_timeline

    m = get_matter(user_id, matter_id)
    if not m:
        return {"error": "Matter not found"}
    docs = list_documents(user_id, matter_id=matter_id)
    orders = list_court_orders(user_id, matter_id=matter_id)
    folders = []
    try:
        from backend.app.core.enterprise_workspace import list_folders

        folders = list_folders(user_id, matter_id=matter_id)
    except Exception:
        pass
    timeline = list_timeline(user_id, matter_id, limit=50)
    return {
        "matter": m,
        "tree": {
            "matter": m.get("matter_name"),
            "children": [
                {"key": "documents", "label": "Documents", "count": len(docs)},
                {"key": "orders", "label": "Orders", "count": len(orders)},
                {"key": "hearings", "label": "Hearings", "count": 1 if m.get("next_hearing_date") else 0},
                {"key": "drafts", "label": "Drafts", "count": 0},
                {"key": "evidence", "label": "Evidence", "count": sum(1 for d in docs if d.get("doc_type") == "Evidence")},
                {"key": "billing", "label": "Billing", "href": "/billing"},
                {"key": "client-portal", "label": "Client Portal"},
                {"key": "timeline", "label": "Timeline", "count": len(timeline)},
            ],
        },
        "documents": docs,
        "orders": orders,
        "folders": folders,
        "timeline": timeline,
    }


def firm_analytics(user_id: str) -> Dict[str, Any]:
    migrate_enterprise_columns()
    uid = str(user_id)
    conn = connect_data_db()
    docs = conn.execute("SELECT COUNT(*) FROM ent_dms_documents WHERE user_id=?", (uid,)).fetchone()[0]
    orders = conn.execute("SELECT COUNT(*) FROM ent_court_orders WHERE user_id=?", (uid,)).fetchone()[0]
    conn.close()
    open_m = closed_m = hearings = 0
    try:
        from backend.app.core.matter_repo import list_matters

        for m in list_matters(uid) or []:
            if str(m.get("status_tier", "")).lower() in ("closed", "archived"):
                closed_m += 1
            else:
                open_m += 1
            if m.get("next_hearing_date"):
                hearings += 1
    except Exception:
        pass
    compliance_rate = 100
    if orders:
        compliance_rate = min(100, 60 + orders * 2)
    return {
        "firm": {
            "open_matters": open_m,
            "closed_matters": closed_m,
            "total_documents": docs,
            "total_orders": orders,
            "active_clients": len(_matter_names(uid)),
            "storage_mb": round((docs * 250000 + orders * 180000) / (1024 * 1024), 2),
        },
        "litigation": {
            "hearings_this_month": hearings,
            "orders_received": orders,
            "compliance_rate_pct": compliance_rate,
        },
        "revenue": {"invoiced_inr": 0, "note": "Connect billing for live revenue"},
    }


def check_duplicate_document(user_id: str, text: str) -> Optional[Dict[str, Any]]:
    migrate_enterprise_columns()
    h = content_hash(text)
    conn = connect_data_db()
    row = conn.execute(
        "SELECT doc_id, title, matter_id FROM ent_dms_documents WHERE user_id=? AND content_hash=? LIMIT 1",
        (str(user_id), h),
    ).fetchone()
    conn.close()
    if row:
        return {"duplicate": True, "doc_id": row[0], "title": row[1], "matter_id": row[2]}
    return None
