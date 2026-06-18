"""SaaS subscription payments — history, plan catalog, Stripe checkout helpers."""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from backend.app.core.database import connect_data_db
from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
from backend.app.core.stripe_billing import PRICE_MAP, stripe_enabled

PLAN_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "Free",
        "name": "Free",
        "price_inr": 0,
        "interval": "year",
        "description": "Core AI assistant, limited documents and web intel.",
        "features": ["5 documents", "3 web intel queries / day", "Matter Assistant"],
    },
    {
        "id": "Pro",
        "name": "Pro",
        "price_inr": int(os.getenv("STRIPE_PRICE_PRO_INR", "999")),
        "interval": "year",
        "description": "Unlimited documents, hybrid engine, firm collaboration.",
        "features": [
            "Unlimited documents",
            "50 web intel queries / day",
            "Firm Chat included",
            "Hybrid legal engine",
        ],
        "stripe_price_id": PRICE_MAP.get("Pro", ""),
    },
    {
        "id": "Legal Pro",
        "name": "Legal Pro",
        "price_inr": int(os.getenv("STRIPE_PRICE_LEGAL_PRO_INR", "4999")),
        "interval": "year",
        "description": "Full practice suite — litigation, CRM, e-discovery, and AI tools.",
        "features": [
            "Everything in Pro",
            "Litigation Desk",
            "CRM & intake",
            "E-discovery tools",
            "200 web intel queries / day",
        ],
        "stripe_price_id": PRICE_MAP.get("Legal Pro", ""),
    },
]


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_payments_schema() -> None:
    ensure_p0_saas_schema()
    conn = connect_data_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            plan TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            payment_status TEXT NOT NULL DEFAULT 'completed',
            payment_id TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            expires_at TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id, created_at DESC)"
    )
    conn.commit()
    conn.close()


def plan_amount_inr(plan: str) -> int:
    for p in PLAN_CATALOG:
        if p["id"] == plan:
            return int(p.get("price_inr") or 0)
    return 0


def record_payment(
    user_id: str,
    plan: str,
    *,
    amount: int | None = None,
    payment_id: str = "",
    status: str = "completed",
) -> Dict[str, Any]:
    ensure_payments_schema()
    amt = amount if amount is not None else plan_amount_inr(plan)
    now = datetime.now(timezone.utc)
    expires = (now + timedelta(days=365)).isoformat()
    pid = str(uuid.uuid4())
    conn = connect_data_db()
    conn.execute(
        """
        INSERT INTO payments (id, user_id, plan, amount, payment_status, payment_id, created_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (pid, str(user_id), plan, amt, status, payment_id or pid, _utc(), expires),
    )
    conn.commit()
    conn.close()
    return {
        "id": pid,
        "plan": plan,
        "amount": amt,
        "status": status,
        "date": _utc(),
        "expires": expires,
    }


def list_payment_history(user_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    ensure_payments_schema()
    conn = connect_data_db()
    rows = conn.execute(
        """
        SELECT plan, amount, payment_status, created_at, expires_at, payment_id
        FROM payments WHERE user_id = ?
        ORDER BY created_at DESC LIMIT ?
        """,
        (str(user_id), limit),
    ).fetchall()
    sub = conn.execute(
        "SELECT plan, status, updated_at, stripe_subscription_id FROM subscriptions WHERE user_id = ? LIMIT 1",
        (str(user_id),),
    ).fetchone()
    conn.close()
    out = [
        {
            "plan": str(r[0]),
            "amount": int(r[1] or 0),
            "status": str(r[2] or "completed"),
            "date": str(r[3] or ""),
            "expires": str(r[4] or ""),
            "payment_id": str(r[5] or ""),
        }
        for r in rows
    ]
    if not out and sub and str(sub[0]) not in ("", "Free"):
        out.append(
            {
                "plan": str(sub[0]),
                "amount": plan_amount_inr(str(sub[0])),
                "status": str(sub[1] or "active"),
                "date": str(sub[2] or ""),
                "expires": "",
                "payment_id": str(sub[3] or ""),
            }
        )
    return out


def billing_public_config() -> Dict[str, Any]:
    return {
        "stripe_enabled": stripe_enabled(),
        "mock_billing": os.getenv("ALLOW_MOCK_BILLING", "1").lower() in ("1", "true", "yes"),
        "currency": "INR",
        "plans": PLAN_CATALOG,
    }
