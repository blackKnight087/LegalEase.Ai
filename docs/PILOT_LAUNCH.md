# Pilot launch checklist

Use this for **1–5 law firms** on Docker with Postgres, Redis, and Stripe test mode.

## 1. Environment

```powershell
copy .env.docker.example .env
# Edit .env:
#   POSTGRES_PASSWORD, JWT_SECRET, LEGALEASE_API_SECRET (32+ chars each)
#   SAAS_PRODUCTION=1
#   SAAS_USE_POSTGRES_LEGACY=1
#   DATABASE_URL=postgresql://legalease:YOUR_PASS@postgres:5432/legalease
#   STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET (test mode)
#   STRIPE_PRICE_PRO, STRIPE_PRICE_LEGAL_PRO
#   PUBLIC_APP_URL, NEXT_PUBLIC_API_URL, CORS_ORIGINS
```

Or copy [.env.pilot.example](../.env.pilot.example) as a starting point.

## 2. Migrate existing data (optional)

If you have `legalease.db`:

```powershell
$env:DATABASE_URL = "postgresql://legalease:YOUR_PASS@localhost:5432/legalease"
$env:LEGALEASE_DB_PATH = "legalease.db"
py scripts/migrate_sqlite_to_pg.py
```

## 3. Start stack

```powershell
.\scripts\pilot_launch.ps1
# or: docker compose up -d --build
```

## 4. Verify

| Check | Command |
|-------|---------|
| Health | `curl http://localhost/api/v1/health/public` |
| Core DB | `core_db.backend` = `postgresql` |
| Production | `saas_production.errors` = `[]` |
| Metrics | `curl http://localhost/api/v1/metrics` |

## 5. Smoke test

```powershell
py scripts/e2e_saas_smoke.py
py scripts/system_diagnostic.py
```

## 6. Stripe test mode

1. Create products/prices in Stripe Dashboard (test mode).
2. Set `STRIPE_PRICE_PRO` / `STRIPE_PRICE_LEGAL_PRO` price IDs in `.env`.
3. Forward webhooks: `stripe listen --forward-to localhost/api/v1/billing/stripe/webhook`
4. Register → Settings → Upgrade → complete Checkout with test card `4242…`.

## 7. Superadmin

Set `SUPERADMIN_USERNAMES=your_admin_username` in `.env`, restart API, open `/admin`.
