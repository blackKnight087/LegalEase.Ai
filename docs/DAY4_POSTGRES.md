# Day 4 — Postgres core migration

Core app data (auth, chat, memory, learning, orgs) can run on PostgreSQL instead of `legalease.db` when `DATABASE_URL` points at Postgres and legacy mode is enabled.

## Quick start (Docker)

`docker-compose.yml` already sets:

- `DATABASE_URL=postgresql://legalease:changeme@postgres:5432/legalease`
- `SAAS_USE_POSTGRES_LEGACY=1`

On API startup, `ensure_core_schemas()` creates tables via `pg_core_schema.py` and patches `legalease_auth` to use the same connection.

Check health: `GET /api/v1/health/public` → `core_db.backend` should be `postgresql`.

## Existing SQLite → Postgres

1. Start Postgres and set `DATABASE_URL`.
2. Run migration (copies rows, idempotent `ON CONFLICT DO NOTHING`):

```powershell
$env:DATABASE_URL = "postgresql://legalease:changeme@localhost:5432/legalease"
$env:LEGALEASE_DB_PATH = "legalease.db"
py scripts/migrate_core_to_postgres.py
```

3. Enable reads/writes on Postgres:

```powershell
$env:SAAS_USE_POSTGRES_LEGACY = "1"
```

4. Restart API. Two workers (or processes) now share chat threads and user rows from the same database.

## Environment

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | `postgresql://...` for core + SQLAlchemy enterprise tables |
| `SAAS_USE_POSTGRES_LEGACY` | `1` = auth/chat/memory/learning use Postgres |
| `SAAS_AUTO_POSTGRES_LEGACY` | `1` + `SAAS_PRODUCTION=1` auto-enables legacy Postgres |
| `LEGALEASE_DB_PATH` | Still used for CRM, billing, ML jobs until Day 5 |

## Schema source of truth

- **Runtime DDL:** `backend/app/core/pg_core_schema.py` (`ensure_pg_core_schema()`)
- **Alembic (optional):** `alembic upgrade head` runs the same DDL via revision `001_core_legacy`

Tables: `users`, `organizations`, `org_members`, `org_invites`, `subscriptions`, `chat_history`, `matters`, `user_profiles`, `user_facts`, `thread_summaries`, `adaptive_*`, `kb_answer_memory`, `kb_rescue_events`, `gemini_usage_daily`, `logs`.

## Sessions (not in Postgres)

JWT sessions use Redis when `REDIS_URL` is set (`session_store.py`). Day 4 exit criteria for “shared session state” means **shared chat/auth data across API replicas**, not JWT storage in Postgres.

## Day 5 — full app on Postgres

With `SAAS_USE_POSTGRES_LEGACY=1`, CRM, billing, discovery, documents, ML jobs, and audit tables use the same Postgres database via `connect_data_db()`.

**Migrate everything:**

```powershell
py scripts/migrate_sqlite_to_pg.py
```

See also `docs/SAAS_10_DAY_SPRINT.md` Days 5–10 checklist in `SAAS_STATUS.md`.
