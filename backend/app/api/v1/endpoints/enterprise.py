"""Enterprise API — branding, court sync, AI agents, pilot program."""
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ....core.admin_auth import require_superadmin
from ....core.ai_agents import enqueue_agent, list_agents, run_agent
from ....core.auth import get_current_user
from ....core.ecourts_adapter import integration_status, sync_cause_list
from ....core.org_branding import branding_for_user, get_org_branding, update_org_branding
from ....core.org_service import is_org_owner
from ....core.pilot_program import (
    list_pilot_firms,
    pilot_summary,
    register_pilot_firm,
    update_pilot_status,
)

router = APIRouter(tags=["enterprise"])


class BrandingUpdate(BaseModel):
    custom_domain: Optional[str] = None
    logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    support_email: Optional[str] = None


class CauseListSync(BaseModel):
    source: str = "paste"
    text: str = ""
    court_code: str = ""
    bench_id: str = ""
    hearing_date: str = ""
    auto_schedule: bool = False


class AgentRunRequest(BaseModel):
    agent_type: str = Field(..., min_length=3)
    payload: Dict[str, Any] = Field(default_factory=dict)
    async_queue: bool = True


class PilotRegister(BaseModel):
    firm_name: str = Field(..., min_length=2)
    contact_email: str = Field(..., min_length=5)
    plan: str = "Pro"
    org_id: str = ""
    notes: str = ""


class PilotStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(active|paused|completed|churned)$")
    notes: str = ""


@router.get("/branding")
def my_branding(user: Dict[str, Any] = Depends(get_current_user)):
    return {"branding": branding_for_user(str(user["id"]))}


@router.get("/orgs/{org_id}/branding")
def org_branding(org_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    if not is_org_owner(str(user["id"]), org_id):
        raise HTTPException(403, "Owner only")
    return {"branding": get_org_branding(org_id)}


@router.patch("/orgs/{org_id}/branding")
def patch_org_branding(
    org_id: str,
    body: BrandingUpdate,
    user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        brand = update_org_branding(
            str(user["id"]),
            org_id,
            custom_domain=body.custom_domain,
            logo_url=body.logo_url,
            primary_color=body.primary_color,
            support_email=body.support_email,
        )
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    return {"branding": brand}


@router.get("/court/status")
def court_integration_status(user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    return integration_status()


@router.post("/court/sync")
def court_sync(body: CauseListSync, user: Dict[str, Any] = Depends(get_current_user)):
    out = sync_cause_list(
        str(user["id"]),
        source=body.source,
        text=body.text,
        court_code=body.court_code,
        bench_id=body.bench_id,
        hearing_date=body.hearing_date,
        auto_schedule=body.auto_schedule,
    )
    if not out.get("ok"):
        raise HTTPException(400, out.get("error", "Sync failed"))
    try:
        from ....core.enterprise_workspace import log_court_sync_activity

        log_court_sync_activity(
            str(user["id"]),
            matched=int(out.get("matched") or out.get("scheduled") or 0),
        )
    except Exception:
        pass
    return out


@router.get("/agents")
def agents_catalog(user: Dict[str, Any] = Depends(get_current_user)):
    _ = user
    return {"agents": list_agents()}


@router.post("/agents/run")
def agents_run(body: AgentRunRequest, user: Dict[str, Any] = Depends(get_current_user)):
    uid = str(user["id"])
    if body.async_queue:
        return enqueue_agent(body.agent_type, uid, body.payload)
    return run_agent(body.agent_type, uid, body.payload)


@router.get("/pilot/summary")
def pilot_summary_admin(_admin: Dict[str, Any] = Depends(require_superadmin)):
    return pilot_summary()


@router.get("/pilot/firms")
def pilot_firms_list(_admin: Dict[str, Any] = Depends(require_superadmin)):
    return {"firms": list_pilot_firms()}


@router.post("/pilot/firms")
def pilot_firms_register(
    body: PilotRegister,
    _admin: Dict[str, Any] = Depends(require_superadmin),
):
    return register_pilot_firm(
        firm_name=body.firm_name,
        contact_email=body.contact_email,
        plan=body.plan,
        org_id=body.org_id,
        notes=body.notes,
    )


@router.patch("/pilot/firms/{pilot_id}")
def pilot_firms_update(
    pilot_id: str,
    body: PilotStatusUpdate,
    _admin: Dict[str, Any] = Depends(require_superadmin),
):
    ok = update_pilot_status(pilot_id, body.status, body.notes)
    if not ok:
        raise HTTPException(404, "Pilot firm not found")
    return {"ok": True, "pilot_id": pilot_id, "status": body.status}
