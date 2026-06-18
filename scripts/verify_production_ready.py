"""Verify production readiness — run before go-live."""

from __future__ import annotations



import os

import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))



def _load_dotenv() -> None:

    try:

        from dotenv import load_dotenv



        load_dotenv(ROOT / ".env")

    except ImportError:

        env_path = ROOT / ".env"

        if not env_path.is_file():

            return

        for line in env_path.read_text(encoding="utf-8").splitlines():

            line = line.strip()

            if not line or line.startswith("#") or "=" not in line:

                continue

            key, _, val = line.partition("=")

            key = key.strip()

            val = val.strip().strip('"').strip("'")

            if key and key not in os.environ:

                os.environ[key] = val





def check(name: str, ok: bool, detail: str = "", *, warn: bool = False) -> bool:

    if warn and not ok:

        status = "WARN"

    else:

        status = "OK" if ok else "FAIL"

    line = f"[{status}] {name}"

    if detail:

        line += f" - {detail}"

    print(line)

    return ok if not warn else True





def main() -> int:
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _load_dotenv()

    print("LegalEase production readiness check\n")

    print("See docs/GO_LIVE.md for the full env to requirement mapping.\n")

    ok = True

    try:

        from backend.app.core.secret_rotation import (

            is_weak_secret,

            validate_secrets_for_production,

        )

        jwt_ok = not is_weak_secret(

            os.getenv("JWT_SECRET") or os.getenv("LEGALEASE_API_SECRET")

        )

    except Exception:

        jwt_ok = len(os.getenv("JWT_SECRET", "")) >= 32 or len(

            os.getenv("LEGALEASE_API_SECRET", "")

        ) >= 32

    ok &= check("JWT_SECRET strength", jwt_ok, "rotated, 32+ chars")

    ok &= check(

        "DATABASE_URL",

        bool(os.getenv("DATABASE_URL", "").startswith("postgresql")),

        "Postgres required",

    )

    ok &= check(

        "SAAS_USE_POSTGRES_LEGACY",

        os.getenv("SAAS_USE_POSTGRES_LEGACY", "0") == "1",

        "set to 1",

    )

    ok &= check(

        "REDIS_URL",

        bool(os.getenv("REDIS_URL", "").strip()),

        "for queues",

    )

    ok &= check(

        "STRIPE_SECRET_KEY",

        bool(os.getenv("STRIPE_SECRET_KEY", "").strip()),

        "live billing",

    )

    ok &= check(

        "STRIPE_WEBHOOK_SECRET",

        bool(os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()),

    )

    ok &= check(

        "EMAIL_PROVIDER",

        os.getenv("EMAIL_PROVIDER", "console") not in ("console", ""),

        "not console",

    )

    ok &= check(

        "SAAS_PRODUCTION",

        os.getenv("SAAS_PRODUCTION", "0") == "1",

        "optional until deploy",

    )

    ok &= check(

        "CORS_ORIGINS",

        bool(os.getenv("CORS_ORIGINS", "").strip()),

        "production origin",

    )



    posthog = bool(

        (os.getenv("POSTHOG_API_KEY") or os.getenv("NEXT_PUBLIC_POSTHOG_KEY", "")).strip()

    )

    check("POSTHOG", posthog, "optional analytics", warn=True)



    sso_on = os.getenv("SSO_ENABLED", "0").lower() in ("1", "true", "yes")

    if sso_on:

        oidc_ok = all(

            os.getenv(k, "").strip()

            for k in ("OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_REDIRECT_URI")

        )

        ok &= check("SSO OIDC vars", oidc_ok, "required when SSO_ENABLED=1")

        dev_mock = os.getenv("SSO_DEV_MOCK", "0").lower() in ("1", "true", "yes")

        if dev_mock:

            check("SSO_DEV_MOCK", False, "must be off in production", warn=True)

    else:

        check("SSO", True, "disabled")



    enc_key = bool(os.getenv("DATA_ENCRYPTION_KEY", "").strip())

    saas_prod = os.getenv("SAAS_PRODUCTION", "0") == "1"

    if saas_prod:

        ok &= check(

            "DATA_ENCRYPTION_KEY",

            enc_key,

            "required when SAAS_PRODUCTION=1",

        )

        try:

            from backend.app.core.production_config import validate_production_config

            prod_errs = validate_production_config()

            ok &= check(

                "production_config",

                not prod_errs,

                "; ".join(prod_errs[:3]) if prod_errs else "",

            )

        except Exception as exc:

            check("production_config", False, str(exc), warn=True)

    else:

        check(

            "DATA_ENCRYPTION_KEY",

            enc_key,

            "optional until SAAS_PRODUCTION=1",

            warn=not enc_key,

        )



    print()

    if ok:

        print("All critical checks passed.")

        return 0

    print("Fix FAIL items before production launch. See docs/GO_LIVE.md")

    return 1





if __name__ == "__main__":

    sys.exit(main())

