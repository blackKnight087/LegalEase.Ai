"""Central SaaS plan enforcement — billing, features, quotas."""
from __future__ import annotations

import os
from typing import Optional

from backend.app.core.production_config import production_mode

PAID_PLANS = frozenset({"Pro", "Legal Pro"})

PLAN_DOCUMENT_LIMITS = {
    "Free": int(os.getenv("PLAN_DOC_LIMIT_FREE", "2")),
    "Pro": int(os.getenv("PLAN_DOC_LIMIT_PRO", "500")),
    "Legal Pro": int(os.getenv("PLAN_DOC_LIMIT_LEGAL_PRO", "5000")),
}

HYBRID_MODES = frozenset({"hybrid", "deep_case"})


def free_hybrid_allowed() -> bool:
    """Self-hosted / EC2: allow Hybrid without Stripe Pro (set SAAS_ALLOW_FREE_HYBRID=0 to enforce billing)."""
    if os.getenv("SAAS_ALLOW_FREE_HYBRID", "1").strip().lower() in {"1", "true", "yes"}:
        return True
    if os.getenv("SAAS_ALL_FEATURES_FREE", "1").strip().lower() in {"1", "true", "yes"}:
        return True
    return False


def all_features_free() -> bool:
    """When true, skip paid-plan gates for documents, hybrid, enterprise tools, etc."""
    return os.getenv("SAAS_ALL_FEATURES_FREE", "1").strip().lower() in {"1", "true", "yes"}


def normalize_plan(membership: str) -> str:
    m = (membership or "Free").strip()
    if m in PLAN_DOCUMENT_LIMITS:
        return m
    if m.lower() in ("pro",):
        return "Pro"
    if "legal" in m.lower():
        return "Legal Pro"
    return "Free"


def is_paid_plan(membership: str) -> bool:
    return normalize_plan(membership) in PAID_PLANS


def mock_billing_allowed() -> bool:
    """Dev-only direct plan upgrades when Stripe is not configured."""
    if production_mode():
        return False
    return os.getenv("ALLOW_MOCK_BILLING", "1").lower() in {"1", "true", "yes"}


def document_limit(membership: str) -> int:
    return PLAN_DOCUMENT_LIMITS.get(normalize_plan(membership), PLAN_DOCUMENT_LIMITS["Free"])


def can_upload_document(user_id: str, membership: str) -> tuple[bool, str]:
    if all_features_free():
        return True, ""
    from backend.app.core.document_db import get_org_visible_document_count

    limit = document_limit(membership)
    if limit < 0:
        return True, ""
    count = get_org_visible_document_count(str(user_id))
    if count >= limit:
        plan = normalize_plan(membership)
        return (
            False,
            f"{plan} plan allows {limit} document(s). Upgrade to Pro for more storage.",
        )
    return True, ""


def apply_plan_route_guard(mode: str, membership: str) -> str:
    """Downgrade paid-only chat modes for Free users unless SAAS_ALLOW_FREE_HYBRID=1."""
    m = (mode or "").strip().lower()
    if m in HYBRID_MODES and not is_paid_plan(membership) and not free_hybrid_allowed():
        return "knowledge_base"
    return mode


def require_paid_for_mode(mode: str, membership: str) -> Optional[str]:
    m = (mode or "").strip().lower()
    if m in HYBRID_MODES and not is_paid_plan(membership) and not free_hybrid_allowed():
        return (
            "Hybrid and Deep Case modes require a Pro or Legal Pro subscription. "
            "Upgrade in Settings → billing."
        )
    return None
