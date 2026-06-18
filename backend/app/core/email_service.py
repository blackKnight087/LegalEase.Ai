"""Transactional email — Brevo, SendGrid, SMTP, or console fallback."""
from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger("legalease.email")

EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@legalease.local").strip()
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "console").strip().lower()
SMTP_HOST = os.getenv("SMTP_HOST", "").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "").strip()
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "").strip()
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "").strip()
BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
EMAIL_FROM_NAME = os.getenv("EMAIL_FROM_NAME", "LegalEase").strip()
PUBLIC_APP_URL = (
    os.getenv("PUBLIC_APP_URL") or os.getenv("NEXT_PUBLIC_APP_URL") or "http://localhost:3000"
).rstrip("/")


def email_enabled() -> bool:
    if EMAIL_PROVIDER in ("brevo", "sendinblue") and BREVO_API_KEY:
        return True
    if EMAIL_PROVIDER == "sendgrid" and SENDGRID_API_KEY:
        return True
    if EMAIL_PROVIDER == "smtp" and SMTP_HOST:
        return True
    return EMAIL_PROVIDER not in ("", "none", "off", "console")


def _resolve_to(email: str) -> str:
    addr = (email or "").strip()
    if "@" in addr and not addr.endswith("@users.legalease.local"):
        return addr
    return f"{addr.split('@')[0] if '@' in addr else addr}@users.legalease.local"


def is_valid_email(addr: str) -> bool:
    a = (addr or "").strip()
    if "@" not in a or a.endswith("@users.legalease.local"):
        return False
    local, _, domain = a.partition("@")
    return bool(local) and "." in domain and len(domain) > 3


def resolve_delivery_email(username: str, email: str = "") -> Optional[str]:
    """Real inbox for transactional mail — not fake @users.legalease.local."""
    em = (email or "").strip()
    if is_valid_email(em):
        return em
    un = (username or "").strip()
    if is_valid_email(un):
        return un
    return None


def smtp_configured() -> bool:
    if EMAIL_PROVIDER != "smtp" or not SMTP_HOST:
        return False
    if not SMTP_USER or "your.email" in SMTP_USER.lower() or "@" not in SMTP_USER:
        return False
    if not SMTP_PASSWORD or "app-password" in SMTP_PASSWORD.lower():
        return False
    return is_valid_email(EMAIL_FROM) or is_valid_email(SMTP_USER)


def send_email(
    to: str,
    subject: str,
    html_body: str,
    *,
    text_body: Optional[str] = None,
) -> bool:
    recipient = _resolve_to(to)
    text = text_body or _html_to_text(html_body)
    provider = EMAIL_PROVIDER
    if provider in ("brevo", "sendinblue") and BREVO_API_KEY:
        return _send_brevo(recipient, subject, html_body, text)
    if provider == "sendgrid" and SENDGRID_API_KEY:
        return _send_sendgrid(recipient, subject, html_body, text)
    if provider == "smtp" and SMTP_HOST:
        if not smtp_configured():
            logger.error(
                "SMTP misconfigured: set SMTP_USER and EMAIL_FROM to your real Gmail "
                "(same account as the Google App Password)."
            )
            return False
        to_addr = resolve_delivery_email("", to) or to
        if not is_valid_email(to_addr):
            logger.error(
                "Cannot send email to %r — account has no email. "
                "Register with your Gmail or add email in Settings.",
                to,
            )
            return False
        return _send_smtp(to_addr, subject, html_body, text)
    logger.info(
        "[EMAIL console] to=%s subject=%s\n%s",
        recipient,
        subject,
        text[:2000],
    )
    return True


def _html_to_text(html: str) -> str:
    import re

    t = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    return t.strip()


def _send_smtp(to: str, subject: str, html: str, text: str) -> bool:
    from_addr = EMAIL_FROM if is_valid_email(EMAIL_FROM) else SMTP_USER
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{EMAIL_FROM_NAME} <{from_addr}>" if EMAIL_FROM_NAME else from_addr
    msg["To"] = to
    msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(from_addr, [to], msg.as_string())
        logger.info("SMTP sent to %s subject=%s", to, subject)
        return True
    except Exception:
        logger.exception("SMTP send failed to %s (check Gmail App Password and EMAIL_FROM)", to)
        return False


def _send_brevo(to: str, subject: str, html: str, text: str) -> bool:
    try:
        import json
        import urllib.error
        import urllib.request

        payload = {
            "sender": {"name": EMAIL_FROM_NAME, "email": EMAIL_FROM},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
            "textContent": text,
        }
        req = urllib.request.Request(
            "https://api.brevo.com/v3/smtp/email",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": BREVO_API_KEY,
                "Content-Type": "application/json",
                "accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        logger.error("Brevo send failed to %s: HTTP %s %s", to, exc.code, body)
        return False
    except Exception:
        logger.exception("Brevo send failed to %s", to)
        return False


def _send_sendgrid(to: str, subject: str, html: str, text: str) -> bool:
    try:
        import json
        import urllib.request

        payload = {
            "personalizations": [{"to": [{"email": to}]}],
            "from": {"email": EMAIL_FROM},
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text},
                {"type": "text/html", "value": html},
            ],
        }
        req = urllib.request.Request(
            "https://api.sendgrid.com/v3/mail/send",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return 200 <= resp.status < 300
    except Exception:
        logger.exception("SendGrid send failed to %s", to)
        return False


def send_welcome_email(username: str) -> bool:
    html = f"""
    <p>Welcome to LegalEase, <b>{username}</b>!</p>
    <p>Your workspace is ready. <a href="{PUBLIC_APP_URL}/onboarding">Complete setup</a> to upload documents and start researching.</p>
  """
    return send_email(username, "Welcome to LegalEase", html)


def send_password_reset_email(username: str, reset_url: str) -> bool:
    html = f"""
    <p>Reset your LegalEase password for <b>{username}</b>.</p>
    <p><a href="{reset_url}">Reset password</a> (expires in 1 hour)</p>
    <p>If you did not request this, ignore this email.</p>
  """
    return send_email(username, "Reset your LegalEase password", html)


def send_verify_email(email: str, *, verify_url: str = "", confirmed: bool = False) -> bool:
    if confirmed:
        html = "<p>Your email address has been verified on LegalEase. You can close this message.</p>"
        return send_email(email, "Email verified — LegalEase", html)
    html = f"""
    <p>Verify your email for LegalEase.</p>
    <p><a href="{verify_url}">Confirm email address</a> (expires in 48 hours)</p>
  """
    return send_email(email, "Verify your LegalEase email", html)


def send_org_invite_email(invite_email: str, org_name: str, invite_url: str) -> bool:
    html = f"""
    <p>You are invited to join <b>{org_name}</b> on LegalEase.</p>
    <p><a href="{invite_url}">Accept invitation</a></p>
  """
    return send_email(invite_email, f"Join {org_name} on LegalEase", html)
