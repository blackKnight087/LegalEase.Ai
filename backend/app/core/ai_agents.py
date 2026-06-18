"""AI Agents — autonomous workflows (Phase 6).

Agents run via ml_job_queue when Redis is available, else in-process.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

AGENT_TYPES = frozenset(
    {
        "drafting_agent",
        "discovery_agent",
        "crm_agent",
        "matter_agent",
        "order_analysis_agent",
        "compliance_agent",
        "knowledge_agent",
        "hearing_agent",
        "client_agent",
        "billing_agent",
    }
)


def list_agents() -> List[Dict[str, str]]:
    return [
        {
            "id": "drafting_agent",
            "name": "Drafting Agent",
            "description": "Generate draft sections from matter context and templates",
        },
        {
            "id": "discovery_agent",
            "name": "Discovery Agent",
            "description": "Triage documents and flag privilege/responsiveness",
        },
        {
            "id": "crm_agent",
            "name": "CRM Agent",
            "description": "Score leads and schedule follow-ups",
        },
        {
            "id": "matter_agent",
            "name": "Matter Agent",
            "description": "Run matter intelligence and contradiction scan",
        },
        {
            "id": "order_analysis_agent",
            "name": "Order Analysis Agent",
            "description": "Summarize court orders and extract compliance deadlines",
        },
        {
            "id": "compliance_agent",
            "name": "Compliance Agent",
            "description": "Track filing deadlines and regulatory obligations",
        },
        {
            "id": "knowledge_agent",
            "name": "Knowledge Agent",
            "description": "Search firm knowledge base and precedents",
        },
        {
            "id": "hearing_agent",
            "name": "Hearing Agent",
            "description": "Checks tomorrow's hearings and builds prep packs",
        },
        {
            "id": "client_agent",
            "name": "Client Agent",
            "description": "Sends reminders for pending client uploads and approvals",
        },
        {
            "id": "billing_agent",
            "name": "Billing Agent",
            "description": "Tracks unpaid invoices and trust account balances",
        },
    ]


def run_agent(agent_type: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    agent = (agent_type or "").strip().lower()
    if agent not in AGENT_TYPES:
        return {"ok": False, "error": f"Unknown agent: {agent_type}"}

    if agent == "drafting_agent":
        return _run_drafting_agent(user_id, payload)
    if agent == "discovery_agent":
        return _run_discovery_agent(user_id, payload)
    if agent == "crm_agent":
        return _run_crm_agent(user_id, payload)
    if agent == "matter_agent":
        return _run_matter_agent(user_id, payload)
    if agent == "order_analysis_agent":
        return _run_order_analysis_agent(user_id, payload)
    if agent == "compliance_agent":
        return _run_compliance_agent(user_id, payload)
    if agent == "knowledge_agent":
        return _run_knowledge_agent(user_id, payload)
    if agent == "hearing_agent":
        return _run_hearing_agent(user_id, payload)
    if agent == "client_agent":
        return _run_client_agent(user_id, payload)
    if agent == "billing_agent":
        return _run_billing_agent(user_id, payload)
    return {"ok": False, "error": "Unhandled agent"}


def enqueue_agent(agent_type: str, user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.core.ml_job_queue import enqueue_ml_job, should_use_ml_queue

    if should_use_ml_queue():
        return enqueue_ml_job(user_id, agent_type, payload)
    return {"ok": True, "result": run_agent(agent_type, user_id, payload), "worker": "inline"}


def _run_drafting_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    matter_id = str(payload.get("matter_id") or "")
    doc_type = str(payload.get("document_type") or "notice")
    return {
        "ok": True,
        "agent": "drafting_agent",
        "status": "manual_review",
        "message": "Use Drafting Studio to generate; agent queued context.",
        "matter_id": matter_id,
        "document_type": doc_type,
        "user_id": user_id,
    }


def _run_discovery_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    batch_id = str(payload.get("batch_id") or "")
    return {
        "ok": True,
        "agent": "discovery_agent",
        "batch_id": batch_id,
        "message": "Evidence Intelligence Center — upload files at /discovery for OCR, classification, and timeline analysis.",
    }


def _run_crm_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from backend.app.core.crm_analytics import crm_dashboard

        dash = crm_dashboard(user_id)
        return {"ok": True, "agent": "crm_agent", "analytics": dash}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _run_order_analysis_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    order_id = str(payload.get("order_id") or "")
    text = str(payload.get("text") or "")
    if order_id:
        from backend.app.core.enterprise_workspace import get_court_order

        row = get_court_order(user_id, order_id)
        if row:
            return {"ok": True, "agent": "order_analysis_agent", "order": row}
    if len(text) >= 20:
        from backend.app.core.enterprise_workspace import _ai_order_analysis

        return {"ok": True, "agent": "order_analysis_agent", "analysis": _ai_order_analysis(text)}
    return {"ok": False, "error": "order_id or text required"}


def _run_compliance_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.core.enterprise_workspace import list_court_orders

    orders = list_court_orders(user_id, limit=30)
    deadlines = []
    for o in orders:
        full = None
        try:
            from backend.app.core.enterprise_workspace import get_court_order

            full = get_court_order(user_id, o["order_id"])
        except Exception:
            pass
        if full:
            for d in full.get("deadlines") or []:
                deadlines.append({"order_id": o["order_id"], "deadline": d})
    return {
        "ok": True,
        "agent": "compliance_agent",
        "pending_deadlines": deadlines[:20],
        "orders_reviewed": len(orders),
    }


def _run_knowledge_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.core.enterprise_workspace import search_knowledge

    q = str(payload.get("query") or payload.get("q") or "bail")
    return {
        "ok": True,
        "agent": "knowledge_agent",
        "results": search_knowledge(user_id, q, limit=15),
    }


def _run_hearing_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.core.enterprise_workspace import build_action_queues

    q = build_action_queues(user_id)
    hearings = q.get("upcoming_hearings") or []
    return {
        "ok": True,
        "agent": "hearing_agent",
        "status": "completed",
        "hearings_checked": len(hearings),
        "hearings": hearings,
        "message": f"Found {len(hearings)} upcoming hearing(s). Review Court Day for prep.",
    }


def _run_client_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    from backend.app.core.enterprise_workspace import list_client_portal_ops

    ops = list_client_portal_ops(user_id)
    pending = len(ops.get("document_requests") or []) + len(
        [a for a in (ops.get("approvals") or []) if a.get("status") == "pending_review"]
    )
    return {
        "ok": True,
        "agent": "client_agent",
        "status": "completed",
        "pending_client_items": pending,
        "portals_active": len(ops.get("portals") or []),
        "message": f"{pending} client action(s) pending.",
    }


def _run_billing_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from backend.app.core.matter_repo import list_matters

        matters = list_matters(user_id) or []
        return {
            "ok": True,
            "agent": "billing_agent",
            "status": "completed",
            "matters_scanned": len(matters),
            "message": "Open Billing for invoices and trust balances.",
            "link": "/billing",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _run_matter_agent(user_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    matter_id = str(payload.get("matter_id") or "")
    if not matter_id:
        return {"ok": False, "error": "matter_id required"}
    from backend.app.core.matter_intel_pipeline import run_matter_intelligence_pipeline

    result = run_matter_intelligence_pipeline(
        user_id, matter_id, skip_if_running=True
    )
    return {"ok": True, "agent": "matter_agent", "pipeline": result}
