"""Unified practice SaaS metrics for dashboard."""
from __future__ import annotations

from typing import Any, Dict

from backend.app.core.billing_service import billing_summary
from backend.app.core.crm_service import list_leads
from backend.app.core.ediscovery_service import list_batches
from backend.app.core.matter_repo import list_matters
from backend.app.core.saas_schema import ensure_saas_schema


def practice_overview(user_id: str) -> Dict[str, Any]:
    ensure_saas_schema()
    matters = list_matters(user_id, limit=200)
    billing = billing_summary(user_id)
    leads = list_leads(user_id, limit=500)
    batches = list_batches(user_id)
    stages: Dict[str, int] = {}
    for lead in leads:
        st = lead.get("pipeline_stage") or "NEW_INTAKE"
        stages[st] = stages.get(st, 0) + 1
    active_matters = sum(1 for m in matters if m.get("status_tier") == "ACTIVE")
    return {
        "matters_total": len(matters),
        "matters_active": active_matters,
        "billing": billing,
        "crm": {
            "leads_total": len(leads),
            "pipeline_stages": stages,
        },
        "ediscovery": {
            "batches_total": len(batches),
        },
        "modules_ready": {
            "phase1_matters": True,
            "phase2_billing": True,
            "phase3_crm": True,
            "phase4_ediscovery": True,
        },
    }
