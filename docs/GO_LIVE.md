# LegalEase.AI — Go-Live Checklist

Run these checks before every production deploy (do not edit `.env` in CI — use your secrets manager).

## Step-by-step runbook

1. **Environment audit** — compare local or deploy secrets against the template:
   ```bash
   py scripts/audit_env.py
   ```
   Fix all `[CRITICAL]` items; resolve `[WARN]` before accepting traffic.

2. **Production readiness script**:
   ```bash
   py scripts/verify_production_ready.py
   ```

3. **Set production flag** — on the host only (not in repo):
   - `SAAS_PRODUCTION=1`
   - `SAAS_PRODUCTION_STRICT=1` (API refuses boot if guards fail)
   - `SAAS_USE_POSTGRES_LEGACY=1`
   - Strong `JWT_SECRET` (≥32 chars), `DATABASE_URL=postgresql://…`, `REDIS_URL`

4. **Start API** — confirm startup logs show no production guard errors:
   ```bash
   py -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
   ```

5. **CI gate tests** (from dev machine or pipeline):
   ```bash
   py -3 -m pytest tests/test_kb_trust_ci.py tests/test_enterprise_api_ci.py tests/test_tenant_attack_ci.py -q --tb=short -m ci_gate
   ```

6. **Smoke** — `py scripts/e2e_saas_smoke.py` against staging URL.

7. **PostHog / analytics** (optional) — set `POSTHOG_API_KEY` or `NEXT_PUBLIC_POSTHOG_KEY`.

8. **External checklist** (cannot be coded here):
   - Live Stripe keys + webhook endpoint
   - Transactional email provider (not `console`)
   - SOC 2 / pen-test engagement
   - SSO IdP client registration (or keep `SSO_DEV_MOCK=0` with real OIDC vars)

Map each requirement to environment variables in `.env.example` at the project root.

## Core platform

| Requirement | Env vars | Notes |
|-------------|----------|--------|
| Postgres tenancy | `DATABASE_URL`, `SAAS_USE_POSTGRES_LEGACY=1` | `postgresql://...` required |
| JWT / API auth | `JWT_SECRET` or `LEGALEASE_API_SECRET` | Min 32 characters |
| Production flag | `SAAS_PRODUCTION=1` | Enables stricter defaults |
| Redis (queues) | `REDIS_URL` | e.g. `redis://host:6379/0` |
| CORS | `CORS_ORIGINS` | Comma-separated production app URLs |

## Billing (Stripe)

| Requirement | Env vars |
|-------------|----------|
| Live charges | `STRIPE_SECRET_KEY` |
| Webhooks | `STRIPE_WEBHOOK_SECRET` |
| Price IDs | `STRIPE_PRICE_PRO`, `STRIPE_PRICE_ENTERPRISE` (as configured in app) |

## Email

| Requirement | Env vars |
|-------------|----------|
| Transactional mail | `EMAIL_PROVIDER` (not `console`), `RESEND_API_KEY` or SMTP vars per provider docs |

## SSO (enterprise)

When `SSO_ENABLED=1`:

| Requirement | Env vars |
|-------------|----------|
| OIDC | `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_REDIRECT_URI` |
| Public app URL | `PUBLIC_APP_URL` or `NEXT_PUBLIC_APP_URL` |
| Pilot dev only | `SSO_DEV_MOCK=1` (never in production) |

## Security & observability

| Requirement | Env vars | Notes |
|-------------|----------|--------|
| Field encryption | `DATA_ENCRYPTION_KEY` | Fernet key; required if encrypting CRM/sensitive fields |
| Analytics (optional) | `POSTHOG_API_KEY`, `POSTHOG_HOST` | Warn-only if missing |
| Superadmin | `SUPERADMIN_USERNAMES` | Comma-separated usernames |

## Frontend

| Requirement | Env vars |
|-------------|----------|
| API base | `NEXT_PUBLIC_API_URL` | HTTPS backend URL |
| App URL | `NEXT_PUBLIC_APP_URL` | Used for SSO redirects |

## CI gates (pre-release)

```bash
python -m pytest tests/test_kb_trust_ci.py tests/test_enterprise_api_ci.py -q --tb=short -m ci_gate
python scripts/verify_production_ready.py
```

See also `docs/PRODUCTION_CHECKLIST.md` and `docs/PHASE6_ENTERPRISE.md`.
