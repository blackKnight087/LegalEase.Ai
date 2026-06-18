"""Stripe Checkout + webhooks for SaaS plan enforcement."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.app.core.database import connect_data_db
from backend.app.core.org_service import get_primary_org_id, sync_org_plan_from_membership
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema

logger = logging.getLogger(__name__)

STRIPE_SECRET = os.getenv("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
PUBLIC_APP_URL = (os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL") or "http://localhost:3000").rstrip("/")
BILLING_SUCCESS_PATH = os.getenv("STRIPE_SUCCESS_PATH", "/settings/subscription?checkout=success")
BILLING_CANCEL_PATH = os.getenv("STRIPE_CANCEL_PATH", "/settings/subscription?checkout=cancel")

PRICE_MAP = {
    "Pro": os.getenv("STRIPE_PRICE_PRO", "").strip(),
    "Legal Pro": os.getenv("STRIPE_PRICE_LEGAL_PRO", "").strip(),
}


def stripe_enabled() -> bool:
    return bool(STRIPE_SECRET and any(PRICE_MAP.values()))


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stripe():
    if not STRIPE_SECRET:
        raise RuntimeError("STRIPE_SECRET_KEY is not configured")
    import stripe

    stripe.api_key = STRIPE_SECRET
    return stripe


def upgrade_membership(user_id: str, plan: str) -> bool:
    from legalease_auth import upgrade_user_membership

    ok = upgrade_user_membership(str(user_id), plan)
    org_id = get_primary_org_id(str(user_id))
    if org_id:
        sync_org_plan_from_membership(org_id, plan)
    _upsert_subscription_row(str(user_id), plan=plan, status="active")
    return ok


def _upsert_subscription_row(
    user_id: str,
    *,
    plan: str,
    status: str,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
) -> None:
    ensure_p0_saas_schema()
    now = _utc()
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO subscriptions (user_id, stripe_customer_id, stripe_subscription_id, plan, status, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            stripe_customer_id=excluded.stripe_customer_id,
            stripe_subscription_id=excluded.stripe_subscription_id,
            plan=excluded.plan,
            status=excluded.status,
            updated_at=excluded.updated_at
        """,
        (
            str(user_id),
            stripe_customer_id,
            stripe_subscription_id,
            plan,
            status,
            now,
        ),
    )
    conn.commit()
    conn.close()


def create_billing_portal_session(user_id: str) -> Dict[str, Any]:
    """Stripe Customer Portal for self-service billing management."""
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT stripe_customer_id FROM subscriptions WHERE user_id = ? LIMIT 1",
        (str(user_id),),
    ).fetchone()
    conn.close()
    customer_id = str(row[0] or "") if row else ""
    if not customer_id:
        raise ValueError("No Stripe customer on file — subscribe to a paid plan first")
    stripe = _stripe()
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{PUBLIC_APP_URL}/settings/subscription",
    )
    return {"portal_url": session.url}


def create_checkout_session(user_id: str, plan: str) -> Dict[str, Any]:
    price_id = PRICE_MAP.get(plan)
    if not price_id:
        raise ValueError(f"No Stripe price configured for plan: {plan}")
    stripe = _stripe()
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{PUBLIC_APP_URL}{BILLING_SUCCESS_PATH}",
        cancel_url=f"{PUBLIC_APP_URL}{BILLING_CANCEL_PATH}",
        client_reference_id=str(user_id),
        metadata={"user_id": str(user_id), "plan": plan},
    )
    return {"checkout_url": session.url, "session_id": session.id}


def handle_webhook_payload(payload: bytes, sig_header: str) -> Dict[str, Any]:
    stripe = _stripe()
    if STRIPE_WEBHOOK_SECRET:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    else:
        import json

        event = stripe.Event.construct_from(json.loads(payload.decode()), stripe.api_key)

    if hasattr(event, "to_dict"):
        ev = event.to_dict()
    elif isinstance(event, dict):
        ev = event
    else:
        ev = {"type": getattr(event, "type", ""), "data": getattr(event, "data", {})}
    etype = ev.get("type", "")
    data = (ev.get("data") or {}).get("object", {}) if isinstance(ev.get("data"), dict) else {}
    if not data and hasattr(ev.get("data"), "object"):
        obj = ev["data"].object
        data = obj.to_dict() if hasattr(obj, "to_dict") else dict(obj)

    if etype == "checkout.session.completed":
        uid = (data.get("metadata") or {}).get("user_id") or data.get("client_reference_id")
        plan = (data.get("metadata") or {}).get("plan") or "Pro"
        if uid:
            upgrade_membership(str(uid), plan)
            _upsert_subscription_row(
                str(uid),
                plan=plan,
                status="active",
                stripe_customer_id=str(data.get("customer") or ""),
                stripe_subscription_id=str(data.get("subscription") or ""),
            )
            try:
                from backend.app.core.payment_service import record_payment

                record_payment(
                    str(uid),
                    plan,
                    payment_id=str(data.get("payment_intent") or data.get("id") or ""),
                    status="completed",
                )
            except Exception:
                pass
            try:
                from backend.app.core.audit_service import log_audit

                log_audit("billing.checkout_completed", user_id=str(uid), detail=f"plan={plan}")
            except Exception:
                pass
        return {"handled": True, "type": etype, "user_id": uid, "plan": plan}

    if etype == "invoice.paid":
        sub = data.get("subscription") or ""
        uid = ""
        if sub:
            uid = _user_id_from_subscription({"id": sub})
        if uid:
            plan = _plan_from_price(data) or "Pro"
            try:
                from backend.app.core.audit_service import log_audit

                log_audit(
                    "billing.invoice_paid",
                    user_id=str(uid),
                    detail=f"subscription={sub} plan={plan}",
                )
            except Exception:
                pass
        return {"handled": True, "type": etype, "user_id": uid}

    if etype in ("customer.subscription.deleted", "customer.subscription.updated"):
        uid = _user_id_from_subscription(data)
        status = str(data.get("status") or "")
        if etype.endswith("deleted") or status in ("canceled", "unpaid", "incomplete_expired"):
            if uid:
                upgrade_membership(str(uid), "Free")
                _upsert_subscription_row(str(uid), plan="Free", status="canceled")
                try:
                    from backend.app.core.audit_service import log_audit

                    log_audit("billing.subscription_canceled", user_id=str(uid))
                except Exception:
                    pass
        elif status == "active" and uid:
            plan = _plan_from_price(data)
            if plan:
                upgrade_membership(str(uid), plan)
                try:
                    from backend.app.core.audit_service import log_audit

                    log_audit("billing.subscription_active", user_id=str(uid), detail=f"plan={plan}")
                except Exception:
                    pass
        return {"handled": True, "type": etype, "user_id": uid}

    return {"handled": False, "type": etype}


def _user_id_from_subscription(sub_obj: Dict[str, Any]) -> str:
    sub_id = str(sub_obj.get("id") or "")
    if not sub_id:
        return ""
    ensure_p0_saas_schema()
    conn = connect_data_db()
    row = conn.execute(
        "SELECT user_id FROM subscriptions WHERE stripe_subscription_id = ? LIMIT 1",
        (sub_id,),
    ).fetchone()
    conn.close()
    return str(row[0]) if row else ""


def _plan_from_price(sub_obj: Dict[str, Any]) -> str:
    try:
        items = sub_obj.get("items", {}).get("data", [])
        price_id = items[0]["price"]["id"] if items else ""
    except (KeyError, IndexError, TypeError):
        price_id = ""
    for plan, pid in PRICE_MAP.items():
        if pid and pid == price_id:
            return plan
    return ""
