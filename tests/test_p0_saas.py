"""P0 SaaS: org tenancy, Stripe billing helpers, production config."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest


def test_org_created_on_register_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "t.db"))
    from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
    from backend.app.core.org_service import create_org_for_user, get_primary_org_id, list_org_members
    from legalease_auth import create_user, ensure_db

    ensure_db()
    ensure_p0_saas_schema()
    assert create_user("firm_a", "password1")
    from legalease_auth import authenticate_user

    user = authenticate_user("firm_a", "password1")
    assert user
    org_id = create_org_for_user(user["id"], user["username"], "Free")
    assert org_id
    assert get_primary_org_id(user["id"]) == org_id
    members = list_org_members(org_id, user["id"])
    assert len(members) == 1
    assert members[0]["role"] == "owner"


def test_matter_org_scoping(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGALEASE_DB_PATH", str(tmp_path / "m.db"))
    from backend.app.core.p0_saas_schema import ensure_p0_saas_schema
    from backend.app.core.org_service import create_org_for_user
    from backend.app.core.matter_repo import create_matter, get_matter, list_matters
    from legalease_auth import create_user, ensure_db

    ensure_db()
    ensure_p0_saas_schema()
    create_user("owner1", "pass12345")
    from legalease_auth import authenticate_user

    owner = authenticate_user("owner1", "pass12345")
    org_id = create_org_for_user(owner["id"], owner["username"])
    m = create_matter(owner["id"], matter_name="Org Matter")
    assert m.get("org_id") == org_id
    listed = list_matters(owner["id"])
    assert any(x["matter_id"] == m["matter_id"] for x in listed)
    assert get_matter(owner["id"], m["matter_id"])


def test_stripe_mock_upgrade_when_disabled(monkeypatch):
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    monkeypatch.delenv("STRIPE_PRICE_PRO", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import importlib

    from backend.app.core import stripe_billing

    importlib.reload(stripe_billing)
    assert not stripe_billing.stripe_enabled()


def test_production_config_flags_weak_secret(monkeypatch):
    monkeypatch.setenv("SAAS_PRODUCTION", "1")
    monkeypatch.setenv("JWT_SECRET", "legalease-dev-change-in-production")
    monkeypatch.setenv("POSTGRES_PASSWORD", "strong_password_123")
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    from backend.app.core.production_config import validate_production_config

    errs = validate_production_config()
    assert any("JWT" in e for e in errs)


def test_stripe_webhook_checkout_completed(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "metadata": {"user_id": "u1", "plan": "Pro"},
                "client_reference_id": "u1",
                "customer": "cus_x",
                "subscription": "sub_x",
            }
        },
    }
    with patch("backend.app.core.stripe_billing.STRIPE_SECRET", "sk_test_x"), patch(
        "backend.app.core.stripe_billing.STRIPE_WEBHOOK_SECRET", "whsec_test"
    ):
        with patch("stripe.Webhook.construct_event", return_value=event):
            with patch("backend.app.core.stripe_billing.upgrade_membership") as mock_up:
                from backend.app.core.stripe_billing import handle_webhook_payload

                out = handle_webhook_payload(b"{}", "sig")
                assert out.get("handled")
                mock_up.assert_called_once_with("u1", "Pro")
