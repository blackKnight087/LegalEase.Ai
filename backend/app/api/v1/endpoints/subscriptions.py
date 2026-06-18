"""Stripe subscription checkout and webhooks."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ....core.auth import get_current_user
from ....core.payment_service import (
    billing_public_config,
    list_payment_history,
    record_payment,
)
from ....core.stripe_billing import (
    create_billing_portal_session,
    create_checkout_session,
    stripe_enabled,
    upgrade_membership,
)

router = APIRouter(tags=["subscriptions"])


class SubscribeRequest(BaseModel):
    plan: str


@router.get("/plans")
def billing_plans():
    return billing_public_config()


@router.get("/payments")
def billing_payments(user: Dict[str, Any] = Depends(get_current_user)):
    return {"payments": list_payment_history(str(user["id"]))}


@router.get("/status")
def subscription_status(user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "membership": user.get("membership", "Free"),
        **billing_public_config(),
    }


@router.get("/portal")
def billing_portal(user: Dict[str, Any] = Depends(get_current_user)):
    if not stripe_enabled():
        raise HTTPException(503, "Stripe not configured")
    try:
        session = create_billing_portal_session(str(user["id"]))
        return {"portal_url": session["portal_url"]}
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Billing portal failed: {exc}") from exc


@router.post("/subscribe")
def subscribe(req: SubscribeRequest, user: Dict[str, Any] = Depends(get_current_user)):
    plan = (req.plan or "").strip()
    if plan not in ("Pro", "Legal Pro"):
        raise HTTPException(400, "Invalid plan")
    if not stripe_enabled():
        from ....core.plan_enforcement import mock_billing_allowed

        if not mock_billing_allowed():
            raise HTTPException(
                503,
                "Billing is not configured. Set STRIPE_SECRET_KEY and price IDs, or enable ALLOW_MOCK_BILLING for local dev.",
            )
        if upgrade_membership(str(user["id"]), plan):
            record_payment(str(user["id"]), plan, payment_id="mock-dev")
            return {
                "mode": "mock",
                "membership": plan,
                "message": "Stripe not configured — plan updated directly (dev only)",
            }
        raise HTTPException(500, "Could not update membership")
    try:
        session = create_checkout_session(str(user["id"]), plan)
        return {"mode": "stripe", "checkout_url": session["checkout_url"]}
    except Exception as exc:
        raise HTTPException(502, f"Stripe checkout failed: {exc}") from exc
