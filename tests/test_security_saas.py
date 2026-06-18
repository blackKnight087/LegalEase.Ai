"""SaaS security — password policy, encryption vault, middleware headers."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient


def test_password_policy_rejects_weak():
    from backend.app.core.password_policy import validate_password

    ok, msg = validate_password("short")
    assert not ok
    assert "at least" in msg.lower()


def test_password_policy_accepts_strong():
    from backend.app.core.password_policy import validate_password

    ok, _ = validate_password("SecurePass1!")
    assert ok


def test_crypto_vault_roundtrip(monkeypatch):
    from cryptography.fernet import Fernet

    from backend.app.core.crypto_vault import decrypt_field, encrypt_field, encryption_enabled

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("DATA_ENCRYPTION_KEY", key)
    assert encryption_enabled()
    plain = "privileged client note"
    enc = encrypt_field(plain)
    assert enc.startswith("enc:v1:")
    assert decrypt_field(enc) == plain


@pytest.mark.integration
def test_security_headers_on_health(api_client):
    from backend.app.main import app

    client = TestClient(app)
    r = client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.headers.get("x-content-type-options") == "nosniff"
    assert r.headers.get("x-frame-options") == "DENY"


@pytest.mark.integration
def test_health_security_endpoint(api_client):
    from backend.app.main import app

    client = TestClient(app)
    r = client.get("/api/v1/health/security")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "encryption_at_rest" in body


@pytest.mark.integration
def test_ip_firewall_blocks_unknown(monkeypatch, api_client):
    from backend.app.main import app

    monkeypatch.setenv("FIREWALL_ENABLED", "1")
    monkeypatch.setenv("FIREWALL_ALLOWED_IPS", "203.0.113.50")
    client = TestClient(app)
    r = client.get("/api/v1/dashboard/full", headers={"X-Forwarded-For": "198.51.100.99"})
    assert r.status_code in (401, 403)


@pytest.fixture
def api_client():
    from backend.app.main import app

    return TestClient(app)
