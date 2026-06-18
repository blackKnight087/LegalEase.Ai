# LegalEase SaaS — Sprint Status (Days 1–10)

## Completed

| Day | Focus | Status |
|-----|-------|--------|
| 1 | Tenant isolation, JWT | Done — `tests/test_tenant_isolation.py` |
| 2 | Stripe billing | Done — checkout, webhooks, plan gates |
| 3 | Organizations + RBAC | Done — orgs, invites, team UI |
| 4 | Postgres core | Done — `pg_core_schema`, `migrate_core_to_postgres.py` |
| 5 | Postgres rest + Docker prod | Done — `pg_rest_schema`, `migrate_sqlite_to_pg.py`, API healthcheck, non-root image |
| 6 | ML job queue | Done — Redis worker, enqueue-only when `ML_USE_QUEUE` + Redis |
| 7 | Admin + audit | Done — `/admin`, audit on login/upload/export/billing |
| 8 | Email, onboarding, GDPR | Done — reset flow, wizard, `DELETE /account`, export ZIP |
| 9 | CI/CD + monitoring | Done — `ci.yml`, `deploy.yml`, `e2e_saas_smoke.py`, `/api/v1/metrics`, `SENTRY_DSN` |
| 10 | Launch ops | Done — `scripts/backup.sh`, RUNBOOK backup section |

## Post-sprint hardening (latest)

- **SaaS readiness plan** — `docs/PILOT_LAUNCH.md`, `docs/PRODUCTION_CHECKLIST.md`, `scripts/pilot_launch.ps1`, `scripts/load_test_chat.py`
- **CI** — default pytest excludes `slow` + `legacy_kb`; required SaaS gate; optional Playwright job (`tests/e2e/`)
- **KB routing** — law-code comparisons (`CrPC vs BNSS`) no longer misclassified as case captions
- **`app_db_bridge`** — `app.run_query` uses Postgres when legacy mode is on (fixes document upload split-brain)
- **`sql_compat`** — Postgres-safe onboarding, KB status, matter members
- **Email verify** — `POST /account/verify-email/send|confirm`, `/verify-email` UI
- **Workers** — e-discovery + ML workers call `ensure_app_schemas` + DB bridges
- **Alembic** — `002_rest_schema`
- **Audit** — login IP, document delete, `invoice.paid`
- **Intake CRM 2.0** — 8-stage pipeline, structured `analysis_json`, lead scoring, document/evidence readiness, Kanban, matter conversion with tasks/deadlines/entities, firm analytics, RBAC, in-CRM assistant; public intake via `INTAKE_ORG_USER_ID`

## Quick start (Docker SaaS)

```powershell
copy .env.docker.example .env
docker compose up -d --build
```

Health: `GET /api/v1/health/public` → `core_db.backend` = `postgresql`

## Migrate existing SQLite

```powershell
$env:DATABASE_URL = "postgresql://legalease:changeme@localhost:5432/legalease"
$env:LEGALEASE_DB_PATH = "legalease.db"
py scripts/migrate_sqlite_to_pg.py
$env:SAAS_USE_POSTGRES_LEGACY = "1"
```

## Practice modules (product)

| Module | API | UI |
|--------|-----|-----|
| Matters, templates, clauses | `/api/v1/matters` | `/matters` |
| Billing, trust | `/api/v1/billing`, `/trust` | `/billing` |
| Intake CRM 2.0 | `/api/v1/crm` (dashboard, kanban, analyze, convert) | `/intake`, `/intake/board`, `/intake/[leadId]` |
| E-discovery | `/api/v1/ediscovery` | `/discovery` |
| Per-matter FAISS | chat + upload `matter_id` | `/`, `/documents` |

## Ops

- **Backup:** `sh scripts/backup.sh` or `py scripts/backup_legalease.py`
- **ML worker:** `docker compose up ml-worker` or `py scripts/ml_worker.py`
- **Admin:** superadmin usernames in `SUPERADMIN_USERNAMES` → `/admin`

## Related docs

- [SAAS_10_DAY_SPRINT.md](docs/SAAS_10_DAY_SPRINT.md)
- [DAY4_POSTGRES.md](docs/DAY4_POSTGRES.md)
- [DEPLOY.md](DEPLOY.md)
- [RUNBOOK.md](RUNBOOK.md)
