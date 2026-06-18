#!/usr/bin/env python3
"""Test Gmail SMTP from .env — run: py scripts/test_smtp_email.py you@gmail.com"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def main() -> int:
    to = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    if not to or "@" not in to:
        print("Usage: py scripts/test_smtp_email.py your@gmail.com")
        return 1

    from backend.app.core.email_service import send_email, smtp_configured

    if not smtp_configured():
        print("FAIL: SMTP not configured.")
        print("  Set SMTP_USER and EMAIL_FROM to your real Gmail (not your.email@gmail.com)")
        print("  Set SMTP_PASSWORD to your Google App Password (16 chars, no spaces)")
        return 1

    ok = send_email(
        to,
        "LegalEase SMTP test",
        "<p>If you received this, Gmail SMTP works.</p>",
    )
    if ok:
        print(f"OK: test email sent to {to}")
        return 0
    print(f"FAIL: could not send to {to} — check backend logs / Gmail App Password")
    return 1


if __name__ == "__main__":
    sys.exit(main())
