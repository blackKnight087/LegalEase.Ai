# LegalEase Operator Runbook

**Production deploy:** see [`DEPLOY.md`](DEPLOY.md) (Docker, nginx, PostgreSQL, Redis).  
**System overview:** see [`REPORT.md`](REPORT.md).

## Start services

```powershell
# Terminal 1 — API (port 8000)
.\run_backend.ps1

# Terminal 2 — Web UI (port 3000)
.\run_web.ps1
```

Health check: http://127.0.0.1:8000/api/v1/health/live

## Backup and restore

**Backup (production):**

```bash
export DATABASE_URL=postgresql://legalease:changeme@localhost:5432/legalease
sh scripts/backup.sh
```

Or: `py scripts/backup_legalease.py --out backups/manual`

Creates `backups/<timestamp>/` with SQLite file (if present), `postgres.dump` (when `pg_dump` available), `faiss_indexes/`, and `Data/`.

**Restore:** Stop API → restore Postgres with `pg_restore` or re-run `migrate_sqlite_to_pg.py` from a SQLite copy → restore FAISS and `Data/` → start stack.

### Backup restore drill (staging)

Use before production cutover; full checklist in [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md).

1. **Backup:** `export DATABASE_URL=postgresql://...` then `sh scripts/backup.sh` (creates `backups/<timestamp>/`).
2. **Stop services:** `docker compose down` or stop uvicorn/workers.
3. **Postgres:** `dropdb legalease` (staging only) → `createdb legalease` → `pg_restore -d legalease backups/<timestamp>/postgres.dump`.
4. **Files:** Copy `backups/<timestamp>/faiss_indexes/` → project `faiss_indexes/`, and `Data/` if present.
5. **Start:** `docker compose up -d` or `.\run_backend.ps1` + `.\run_web.ps1`.
6. **Verify:** `curl http://localhost/api/v1/health/public` → `core_db.backend: postgresql`, `saas_production.errors: []`.
7. **Smoke:** `py scripts/e2e_saas_smoke.py` and login → Documents → one KB query.

## Load test

```powershell
py scripts/load_test_chat.py --url http://127.0.0.1:8000 --users 20 --rounds 3
```

Reports p50/p95 latency and error count for `/api/v1/health/live`. Pass a JWT with `--token` when testing authenticated routes.

## Index documents (required for KB)

1. Log in → **Documents**
2. Upload PDFs (IPC notes, acts, etc.)
3. Click **Index All Documents**
4. Wait until FAISS index is built under `faiss_indexes/user_<id>/`

## Knowledge Base troubleshooting

| Symptom | Fix |
|--------|-----|
| "Couldn't find clear reference" on summary | Re-index documents; query needs `Summarize all offences` style — uses full-document scan |
| Comparison shows one section only | Restart backend after update; ensures per-section retrieval for 300 vs 307 |
| Wrong law (IT Act instead of IPC) | Ask explicitly "IPC sections"; re-index if PDF mixes topics |
| Slow responses (>10s) | Set `RAG_ENABLE_CROSS_ENCODER=0`, `KB_CACHE_TTL_SEC=300` |
| Port 8000 in use | Stop old Python process, rerun `.\run_backend.ps1` |

## Debug logging

Set in `.env`:

```
KB_PIPELINE_DEBUG=1
```

Backend console shows: query type, retrieval mode, chunk scores, validation.

## Automated tests

```powershell
.\run_tests.ps1
python scripts/e2e_kb_smoke.py
```

## Chat history

- Saves to `legalease.db` table `chat_history`
- Sidebar **Saved Chats** → loads `GET /api/v1/sessions/threads/{id}`
- URL `/?thread=<uuid>` restores thread

## Rate limits (production)

```
RATE_LIMIT_ENABLED=1
RATE_LIMIT_PER_MINUTE=120
RATE_LIMIT_CHAT_PER_MINUTE=40
```

## LM Studio

Ensure LM Studio server is running at `LM_STUDIO_URL` with model loaded when using local LLM.
