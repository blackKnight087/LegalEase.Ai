"""P0 SaaS production guards — mock billing, plan limits, org document scope."""
from __future__ import annotations

import pytest


def test_mock_billing_blocked_in_production(monkeypatch):
    monkeypatch.setenv("SAAS_PRODUCTION", "1")
    monkeypatch.delenv("ALLOW_MOCK_BILLING", raising=False)
    from backend.app.core.plan_enforcement import mock_billing_allowed

    assert mock_billing_allowed() is False


def test_mock_billing_allowed_in_dev(monkeypatch):
    monkeypatch.delenv("SAAS_PRODUCTION", raising=False)
    monkeypatch.setenv("ALLOW_MOCK_BILLING", "1")
    from backend.app.core.plan_enforcement import mock_billing_allowed

    assert mock_billing_allowed() is True


def test_production_config_requires_stripe(monkeypatch):
    monkeypatch.setenv("SAAS_PRODUCTION", "1")
    monkeypatch.setenv("JWT_SECRET", "x" * 40)
    monkeypatch.setenv("POSTGRES_PASSWORD", "secure-pass-123")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost/db")
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("ALLOW_MOCK_BILLING", raising=False)
    from backend.app.core.production_config import validate_production_config

    errs = validate_production_config()
    assert any("STRIPE_SECRET_KEY" in e for e in errs)


def test_plan_route_guard_hybrid(monkeypatch):
    from backend.app.core.plan_enforcement import apply_plan_route_guard

    monkeypatch.setenv("SAAS_ALLOW_FREE_HYBRID", "0")
    assert apply_plan_route_guard("hybrid", "Free") == "knowledge_base"
    assert apply_plan_route_guard("hybrid", "Pro") == "hybrid"

    monkeypatch.setenv("SAAS_ALLOW_FREE_HYBRID", "1")
    assert apply_plan_route_guard("hybrid", "Free") == "hybrid"


def test_document_limit_by_plan():
    from backend.app.core import plan_enforcement as pe

    assert pe.document_limit("Free") == pe.PLAN_DOCUMENT_LIMITS["Free"]
    assert pe.document_limit("Pro") == pe.PLAN_DOCUMENT_LIMITS["Pro"]


def test_can_upload_document_uses_count(monkeypatch):
    from backend.app.core.plan_enforcement import can_upload_document

    monkeypatch.setattr(
        "backend.app.core.document_db.get_org_visible_document_count",
        lambda _uid: 5,
    )
    ok, msg = can_upload_document("u1", "Free")
    assert not ok
    assert "Upgrade" in msg
