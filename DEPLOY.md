# LegalEase Production Deployment

> **$0 budget / Ollama on your laptop?** Start with [docs/DEPLOY_ZERO_BUDGET.md](docs/DEPLOY_ZERO_BUDGET.md) and `.\scripts\start_public_demo.ps1`.

Deploy LegalEase to the public internet using Docker Compose: **nginx** (TLS), **Next.js**, **FastAPI**, **PostgreSQL**, and **Redis**.

## Prerequisites

- Docker Desktop or Docker Engine + Compose v2
- TLS certificate files (`cert.pem`, `key.pem`) for HTTPS
- LLM endpoint reachable from the API container (LM Studio on host, or cloud API)

## Quick start

```powershell
cd "Legal_AI_Final 3"
copy .env.docker.example .env
# Edit .env: POSTGRES_PASSWORD, JWT_SECRET, NEXT_PUBLIC_API_URL, CORS_ORIGINS, LM_STUDIO_URL

# Place TLS certs (Let's Encrypt or your CA):
#   deploy/nginx/ssl/cert.pem
#   deploy/nginx/ssl/key.pem

docker compose up -d --build
```

Open: `https://your-domain.com` (or `http://localhost` if TLS certs are not yet mounted — port 80 serves HTTP).

Health: `http://localhost/api/v1/health/live`

## Architecture

| Service | Port (internal) | Role |
|---------|-----------------|------|
| nginx | 80, 443 | Reverse proxy, TLS, `/api` → FastAPI |
| web | 3000 | Next.js frontend |
| api | 8000 | FastAPI (2 workers) |
| postgres | 5432 | SQLAlchemy enterprise tables |
| redis | 6379 | Shared chat session state |

## TLS setup

1. Obtain certificates (e.g. [Let's Encrypt](https://letsencrypt.org/) certbot).
2. Copy full chain to `deploy/nginx/ssl/cert.pem` and private key to `deploy/nginx/ssl/key.pem`.
3. In `docker-compose.yml`, uncomment port `443:443` and volume mounts for `nginx-ssl.conf` and `deploy/nginx/ssl/`.
4. Set `NEXT_PUBLIC_API_URL=https://your-domain.com/api` and `CORS_ORIGINS=https://your-domain.com`.

## Ollama (local LLM)

| Setup | When to use |
|-------|-------------|
| **Host Ollama** (default dev) | Install [Ollama](https://ollama.com), run `ollama serve` on the host. In Docker set `OLLAMA_BASE_URL=http://host.docker.internal:11434` (Windows/Mac). |
| **Sidecar** (optional) | Add an `ollama` service to `docker-compose.yml` with GPU if available; point API `OLLAMA_BASE_URL=http://ollama:11434`. |
| **Cloud / LM Studio** | Set `LLM_BACKEND=lmstudio` and `LM_STUDIO_URL` — no Ollama required. |

Tuned models from the improvement pipeline are created via `ml-worker` (`ollama create`) when `OLLAMA_AUTO_CREATE=1`.

## Database strategy

| Data | Storage |
|------|---------|
| Users, chat, orgs, CRM, billing, discovery, audit, ML jobs | **PostgreSQL** when `SAAS_USE_POSTGRES_LEGACY=1` (Docker default) |
| FAISS indexes, uploaded files | Volume mounts `faiss_indexes/`, `Data/` |
| Optional SQLite fallback | `LEGALEASE_DB_PATH` if legacy mode is off |

Set `SAAS_USE_POSTGRES_LEGACY=1` and run `py scripts/migrate_sqlite_to_pg.py` once when moving from an existing SQLite install.

### PostgreSQL only (enterprise ORM)

`DATABASE_URL=postgresql://user:pass@postgres:5432/legalease` is set in `.env.docker.example`. SQLAlchemy creates tables on API startup.

### SQLite path

`LEGALEASE_DB_PATH=/data/legalease.db` is mounted on volume `app_data` alongside `Data/` and `faiss_indexes/`.

## Redis sessions

Set `REDIS_URL=redis://redis:6379/0` so multiple Uvicorn workers share conversation state. Without Redis, sessions are in-process only (single worker).

## LM Studio on Windows host

```env
LM_STUDIO_URL=http://host.docker.internal:1234
```

Ensure LM Studio listens on `0.0.0.0:1234` and a model is loaded.

## Environment variables (production checklist)

| Variable | Required | Notes |
|----------|----------|-------|
| `POSTGRES_PASSWORD` | Yes | Strong password |
| `JWT_SECRET` | Yes | Random 32+ chars |
| `NEXT_PUBLIC_API_URL` | Yes | Public URL with `/api` suffix |
| `CORS_ORIGINS` | Yes | Your frontend origin |
| `REDIS_URL` | Recommended | Multi-worker |
| `TAVILY_API_KEY` | Optional | Open Law web search |
| `LEGALEASE_DB_PATH` | Docker default | `/data/legalease.db` |

## Updates and rollback

```powershell
docker compose pull
docker compose up -d --build
docker compose logs -f api
```

Data persists in volumes: `postgres_data`, `redis_data`, `app_data`.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 502 on `/api` | `docker compose logs api` — check LM Studio URL |
| CORS errors | Match `CORS_ORIGINS` to browser URL exactly |
| KB empty | Upload PDFs → Index; check `app_data` volume has `faiss_indexes` |
| TLS handshake fail | Verify `cert.pem` / `key.pem` paths and permissions |
| Sessions lost between requests | Confirm `REDIS_URL` and Redis health |

See also [`RUNBOOK.md`](RUNBOOK.md) for KB and chat debugging.
