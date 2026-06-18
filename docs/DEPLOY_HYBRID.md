# Hybrid deploy (Windows host + Docker Postgres/Redis)

## Stack

| Component | How to run |
|-----------|------------|
| Postgres + Redis | `docker compose up -d postgres redis` |
| API | `.\run_backend.ps1` |
| Web | `.\run_web_prod.ps1` (sets `LEGALEEASE_WEB_PROD=1`) |
| Public URL | `https://legalease.duckdns.org` → reverse proxy to host :3000 / :8000 |

## One-time setup

```powershell
py scripts/consolidate_env.py
docker compose up -d postgres redis
# If you have SQLite data:
py scripts/migrate_core_to_postgres.py
py scripts/verify_production_ready.py
py scripts/audit_env.py
```

## TLS / FORCE_HTTPS

- Set `FORCE_HTTPS=1` when your edge proxy sends `X-Forwarded-Proto: https`.
- Optional nginx on Docker port 8080 → host:

```powershell
docker compose -f docker-compose.yml -f deploy/hybrid/docker-compose.nginx.yml --profile hybrid-nginx up -d
```

- For HTTPS on duckdns, use Caddy/IIS/certbot on the host pointing to `localhost:3000` and `localhost:8000`, or `docker compose --profile ssl` with certs in `deploy/nginx/ssl/`.

## Pre-deploy checks

```powershell
py scripts/pre_deploy_check.ps1
```
