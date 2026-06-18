"""Brevo email provider."""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_brevo_provider_enabled():
    from backend.app.core import email_service

    with patch.object(email_service, "EMAIL_PROVIDER", "brevo"):
        with patch.object(email_service, "BREVO_API_KEY", "test-key"):
            assert email_service.email_enabled() is True


def test_brevo_send_payload():
    from backend.app.core.email_service import _send_brevo

    captured = {}

    class FakeResp:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=30):
        captured["url"] = req.full_url
        captured["headers"] = dict(req.header_items())
        captured["body"] = req.data.decode("utf-8")
        return FakeResp()

    with patch("urllib.request.urlopen", fake_urlopen):
        with patch("backend.app.core.email_service.BREVO_API_KEY", "test-key"):
            ok = _send_brevo("user@example.com", "Test", "<p>Hi</p>", "Hi")
    assert ok is True
    assert captured["url"] == "https://api.brevo.com/v3/smtp/email"
    assert any(k.lower() == "api-key" for k in captured["headers"])
    assert "user@example.com" in captured["body"]
