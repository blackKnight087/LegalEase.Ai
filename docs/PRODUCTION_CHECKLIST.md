# Production launch checklist

Use after pilot validation ([PILOT_LAUNCH.md](PILOT_LAUNCH.md)) when moving to **paid private beta** or public launch.

## 1. Infrastructure

- [ ] Domain + TLS (nginx or cloud load balancer)
- [ ] `SAAS_PRODUCTION=1` with no `saas_production.errors` on `GET /api/v1/health/public`
- [ ] PostgreSQL (`DATABASE_URL`) + `SAAS_USE_POSTGRES_LEGACY=1`
- [ ] Redis (`REDIS_URL`) for sessions and ML/e-discovery queues
- [ ] Secrets: `JWT_SECRET`, `LEGALEASE_API_SECRET` (32+ chars), `POSTGRES_PASSWORD`
- [ ] `CORS_ORIGINS` set to production web origin only

## 2. Billing

- [ ] Stripe **live** keys (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`)
- [ ] Price IDs: `STRIPE_PRICE_PRO`, `STRIPE_PRICE_LEGAL_PRO`
- [ ] Webhook endpoint registered and verified
- [ ] Test checkout → plan reflected in Settings

## 3. Email

- [ ] `EMAIL_PROVIDER=sendgrid` or `ses` (not `console`)
- [ ] `EMAIL_FROM` verified domain
- [ ] Password reset + optional `REQUIRE_EMAIL_VERIFICATION=1` tested

## 4. Observability

- [ ] `SENTRY_DSN` on API (optional but recommended)
- [ ] `GET /api/v1/metrics` scraped or reviewed manually
- [ ] Log retention and disk alerts on Postgres volume

## 5. Backup and restore drill

See [RUNBOOK.md](../RUNBOOK.md#backup-restore-drill).

1. Run `sh scripts/backup.sh` (or `py scripts/backup_legalease.py --out backups/drill`)
2. Stop API/workers
3. Restore Postgres: `pg_restore -d legalease backups/<ts>/postgres.dump`
4. Restore `faiss_indexes/` and `Data/` from the same backup folder
5. Start stack → register/login smoke → upload + KB query

## 6. Load test (20 concurrent users)

```powershell
# Health-only (no auth):
py scripts/load_test_chat.py --url https://your-api.example.com --users 20 --rounds 3

# Authenticated (JWT from Settings or login API):
py scripts/load_test_chat.py --url https://your-api.example.com --token YOUR_JWT --users 20 --rounds 3
```

Target: p95 &lt; 2s on `/api/v1/health/live`, zero errors. Document results in your ops log.

## 7. Automated checks

```powershell
py -m pytest tests/test_document_schema_fresh_db.py tests/test_tenant_isolation.py tests/test_saas_days5_10.py tests/test_p0_saas.py -q
py scripts/e2e_saas_smoke.py
.\scripts\run_e2e_playwright.ps1
```

## 8. Go / no-go

- [ ] SaaS pytest gate green in CI
- [ ] Backup restore drill completed once on staging
- [ ] Stripe test or live payment verified
- [ ] On-call runbook and rollback owner assigned

Post-MVP (enterprise): SSO, SOC2, legal hold — see [SAAS_10_DAY_SPRINT.md](SAAS_10_DAY_SPRINT.md).
