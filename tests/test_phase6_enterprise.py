"""Phase 6 enterprise module tests."""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.ci_gate

from backend.app.core.ai_agents import list_agents, run_agent
from backend.app.core.ecourts_adapter import integration_status, sync_cause_list
from backend.app.core.sso_service import sso_status


def test_sso_status_defaults():
    st = sso_status()
    assert "enabled" in st
    assert "oidc_configured" in st


def test_ecourts_paste_requires_text():
    out = sync_cause_list("user-1", source="paste", text="")
    assert out.get("ok") is False


def test_ecourts_api_stub_when_disabled():
    out = sync_cause_list("user-1", source="ecourts_api")
    assert out.get("stub") is True


def test_ecourtsindia_requires_key():
    out = sync_cause_list("user-1", source="ecourtsindia", api_date="2025-03-15", api_state="DL")
    assert out.get("ok") is False
    assert "API key" in str(out.get("error", ""))


def test_agents_catalog():
    agents = list_agents()
    assert len(agents) >= 4
    ids = {a["id"] for a in agents}
    assert "matter_agent" in ids


def test_matter_agent_requires_matter_id():
    out = run_agent("matter_agent", "user-1", {})
    assert out.get("ok") is False


def test_oidc_token_exchange_mock(monkeypatch):
    monkeypatch.setenv("SSO_ENABLED", "1")
    monkeypatch.setenv("SSO_DEV_MOCK", "0")
    from backend.app.core import sso_service

    monkeypatch.setattr(sso_service, "SSO_ENABLED", True)
    monkeypatch.setattr(sso_service, "SSO_DEV_MOCK", False)
    monkeypatch.setattr(sso_service, "OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setattr(sso_service, "OIDC_CLIENT_ID", "client")
    monkeypatch.setattr(sso_service, "OIDC_CLIENT_SECRET", "secret")
    monkeypatch.setattr(sso_service, "OIDC_REDIRECT_URI", "https://app/callback")

    class _Resp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            pass

        def json(self):
            return self._data

    class _Client:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def post(self, url, data=None):
            return _Resp({"access_token": "tok"})

        def get(self, url, headers=None):
            return _Resp({"email": "oidc@firm.com", "sub": "sub-1", "name": "OIDC User"})

    with patch("httpx.Client", _Client), patch(
        "backend.app.core.sso_service.provision_sso_user"
    ) as mock_prov:
        mock_prov.return_value = {"token": "t", "user": {"id": "1"}}
        out = sso_service.handle_oidc_callback(code="auth-code")
        assert out["token"] == "t"
        mock_prov.assert_called_once()


def test_ecourts_parse_hearing_dates():
    from backend.app.core.ecourts_adapter import parse_hearing_dates_from_text

    dates = parse_hearing_dates_from_text("Hearing on 15-03-2026 for WP 123/2025")
    assert len(dates) >= 1
    assert dates[0].get("iso_date")


def test_sso_dev_mock_provision(monkeypatch):
    monkeypatch.setenv("SSO_ENABLED", "1")
    monkeypatch.setenv("SSO_DEV_MOCK", "1")
    from backend.app.core import sso_service

    monkeypatch.setattr(
        sso_service,
        "SSO_ENABLED",
        True,
    )
    monkeypatch.setattr(
        sso_service,
        "SSO_DEV_MOCK",
        True,
    )
    with patch("backend.app.core.sso_service.provision_sso_user") as mock_prov:
        mock_prov.return_value = {"token": "t", "user": {"id": "1", "username": "a"}}
        from backend.app.core.sso_service import handle_oidc_callback

        out = handle_oidc_callback(email="pilot@firm.com", name="Pilot Firm")
        assert out["token"] == "t"
        mock_prov.assert_called_once()
