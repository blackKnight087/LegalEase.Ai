"""CLI — register a pilot law firm and admin user."""
from __future__ import annotations

import argparse
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ImportError:
        pass


def main() -> int:
    _load_env()
    parser = argparse.ArgumentParser(description="Onboard a pilot law firm")
    parser.add_argument("--firm", required=True, help="Firm display name")
    parser.add_argument("--email", required=True, help="Admin contact email")
    parser.add_argument("--username", default="", help="Admin username (default: email local-part)")
    parser.add_argument("--plan", default="Pro", choices=["Pro", "Legal Pro", "Enterprise"])
    parser.add_argument("--notes", default="", help="Pilot notes")
    args = parser.parse_args()

    from backend.app.core.pilot_program import register_pilot_firm
    from legalease_auth import create_user, get_user_by_username
    from backend.app.core.org_service import create_org_for_user

    username = (args.username or args.email.split("@")[0]).strip().lower()[:48]
    user = get_user_by_username(username)
    temp_password = ""
    if not user:
        temp_password = secrets.token_urlsafe(16)
        user = create_user(username, temp_password, membership=args.plan)
        if not user:
            print("[FAIL] Could not create admin user")
            return 1
        org = create_org_for_user(str(user["id"]), args.firm, plan=args.plan)
        org_id = org.get("org_id", "") if isinstance(org, dict) else ""
    else:
        org_id = ""
        print(f"[WARN] User {username} already exists — linking pilot record only")

    pilot = register_pilot_firm(
        firm_name=args.firm,
        contact_email=args.email,
        plan=args.plan,
        org_id=org_id,
        notes=args.notes,
    )
    print("[OK] Pilot firm registered")
    print(f"  pilot_id: {pilot.get('pilot_id')}")
    print(f"  firm: {args.firm}")
    print(f"  admin: {username}")
    if temp_password:
        print(f"  temp_password: {temp_password}")
        print("  (share securely — user should reset on first login)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
