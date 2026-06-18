#!/usr/bin/env python3
"""
Build complete LegalEase documentation (markdown + PDF).
Merges architecture suite with auto-generated deployment, API routes, and env reference.
No placeholders — uses actual project URLs, IPs, and script names.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUITE_MD = ROOT / "docs" / "LEGALEASE_PRODUCT_ARCHITECTURE_SUITE.md"
OUTPUT_MD = ROOT / "docs" / "LEGALEASE_COMPLETE_DOCUMENTATION.md"
OUTPUT_PDF = ROOT / "docs" / "LegalEase_Product_Architecture_Suite.pdf"
ENDPOINTS_DIR = ROOT / "backend" / "app" / "api" / "v1" / "endpoints"
ROUTER_PY = ROOT / "backend" / "app" / "api" / "v1" / "router.py"

# Actual production values (from deploy/aws/DEPLOY_AWS.md and project config)
PROD_URL = "https://legalease.duckdns.org"
PROD_API = "https://legalease.duckdns.org/api"
EC2_IP = "18.61.68.82"
EC2_USER = "ubuntu"
EC2_PATH = "/opt/legalease"
SSH_KEY = r"%USERPROFILE%\.ssh\legalease-aws.pem"


def extract_routes() -> list[tuple[str, str, str]]:
    """Return (module, method, full_path) for every FastAPI route."""
    prefix_map: dict[str, str] = {}
    if ROUTER_PY.exists():
        text = ROUTER_PY.read_text(encoding="utf-8")
        for m in re.finditer(
            r'include_router\(\s*(\w+)\.router\s*,\s*prefix\s*=\s*"([^"]+)"',
            text,
        ):
            prefix_map[m.group(1)] = m.group(2)
        for m in re.finditer(
            r'include_router\(\s*(\w+)\.router\s*\)',
            text,
        ):
            mod = m.group(1)
            if mod not in prefix_map:
                prefix_map[mod] = ""

    routes: list[tuple[str, str, str]] = []
    for f in sorted(ENDPOINTS_DIR.glob("*.py")):
        mod = f.stem
        text = f.read_text(encoding="utf-8")
        local_prefix = ""
        m = re.search(r'router\s*=\s*APIRouter\([^)]*prefix\s*=\s*"([^"]*)"', text)
        if m:
            local_prefix = m.group(1)
        router_prefix = prefix_map.get(mod, "")
        for m in re.finditer(
            r'@router\.(get|post|put|patch|delete|websocket)\(\s*"([^"]*)"',
            text,
        ):
            method = m.group(1).upper()
            path = m.group(2)
            full = "/api/v1" + router_prefix + local_prefix + path
            full = re.sub(r"//+", "/", full)
            routes.append((mod, method, full))
    routes.sort(key=lambda x: (x[2], x[1]))
    return routes


def format_env_value(name: str, val: str, source: str) -> str:
    """Replace template placeholders with actual production values where known."""
    if source == "deploy/aws/.env.production.example":
        val = val.replace("YOUR.DOMAIN", "legalease.duckdns.org")
        if name == "POSTGRES_PASSWORD" and not val:
            val = "(set on server - see section 7.4.5)"
        if name in ("JWT_SECRET", "LEGALEASE_API_SECRET", "DATA_ENCRYPTION_KEY", "GEMINI_API_KEY") and not val:
            val = "(set on server - rotate_secrets.ps1)"
    return val


def parse_env_file(path: Path) -> list[tuple[str, str, str]]:
    """Parse env example into (name, value, comment) rows."""
    if not path.exists():
        return []
    rows: list[tuple[str, str, str]] = []
    comment_buf: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            comment_buf = []
            continue
        if stripped.startswith("#"):
            comment_buf.append(stripped.lstrip("#").strip())
            continue
        if "=" not in stripped:
            continue
        name, _, val = stripped.partition("=")
        name = name.strip()
        val = val.strip()
        comment = " ".join(comment_buf) if comment_buf else ""
        comment_buf = []
        rows.append((name, val, comment))
    return rows


def build_deployment_section() -> str:
    """Complete deployment guide — no placeholders for user to fill."""
    return f"""# Document 7 — Deployment Architecture (Complete Guide)

This section is the authoritative deployment reference for LegalEase.AI. Every command, URL, script, and environment profile below uses the actual project configuration. Follow it end-to-end without adding external notes.

## 7.1 Production Summary

| Item | Value |
|------|-------|
| Public URL | {PROD_URL} |
| API base | {PROD_API} |
| Health check | {PROD_API}/v1/health/live |
| EC2 public IP | {EC2_IP} |
| EC2 SSH user | {EC2_USER} |
| Server install path | {EC2_PATH} |
| SSH key (Windows) | {SSH_KEY} |
| Stack | Docker Compose: nginx + web + api + postgres + redis |
| LLM (production) | Gemini (CLOUD_GEMINI_KB=1, LLM_BACKEND=gemini) |
| Database (production) | PostgreSQL 16 in Docker |
| Sessions | Redis 7 |
| TLS | DuckDNS + optional Let's Encrypt certs in deploy/nginx/ssl/ |

## 7.2 Architecture Diagram (Production)

```text
Internet (HTTPS)
    |
    v
legalease.duckdns.org  (DuckDNS A record -> {EC2_IP})
    |
    v
EC2 Ubuntu (m7i-flex.large class, ~8 GB RAM)
    |
    v
Docker Compose (LEGALEASE_COMPOSE_FILES from apply-ec2-tier.sh)
    |
    +-- nginx:80/443
    |       proxy /api/* -> api:8000
    |       proxy /*     -> web:3000
    |       TLS when deploy/nginx/ssl/cert.pem present
    |
    +-- web:3000 (Next.js production build)
    |       NEXT_PUBLIC_API_URL={PROD_API} (baked at build time)
    |
    +-- api:8000 (FastAPI, UVICORN_WORKERS=1 on low RAM)
    |       Gemini for Open Law / Hybrid web leg
    |       FAISS indexes on /data/faiss_indexes volume
    |
    +-- postgres:5432 (volume postgres_data)
    +-- redis:6379 (volume redis_data, appendonly)
    |
    +-- worker / ml-worker (profile: workers — OFF by default on 8GB)
```

## 7.3 Laptop Development — Step-by-Step Setup

### Prerequisites (Windows laptop)

1. Install Python 3.10+ and Node.js 18+
2. Install Ollama from https://ollama.com and run `ollama pull legalease-tuned` (or your tuned model)
3. Install ffmpeg: `winget install Gyan.FFmpeg`
4. Optional GPU: NVIDIA drivers + CUDA for Ollama GPU and faster embeddings
5. Clone or open project folder: `Legal_AI_Final 3`

### One-time laptop configuration

```powershell
cd "C:\\Users\\ASUS\\Desktop\\Legal_ai (1)\\Legal_ai\\Legal_AI_Final 3"

# API keys (Gemini, Tavily) go in .env — copy from .env.example if missing
# Laptop-only overrides:
.\\scripts\\setup_local_env.ps1
# Creates .env.local from .env.local.example with:
#   LEGALEEASE_LOCAL_DEV=1
#   SAAS_PRODUCTION=0
#   SAAS_USE_POSTGRES_LEGACY=0  (SQLite)
#   LLM_BACKEND=ollama
#   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
#   CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Edit `.env` for Ollama settings (already in `.env.example`):

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=legalease-tuned
CLOUD_GEMINI_KB=0
GEMINI_API_KEY=your-key-for-open-law-only
```

Create Python venv (first time only):

```powershell
py -m venv .venv_win
.\\.venv_win\\Scripts\\pip install -r backend\\requirements.txt
cd web; npm install; cd ..
```

### Start laptop stack (every session)

Terminal 1 — Backend:

```powershell
.\\run_backend.ps1
```

Terminal 2 — Frontend:

```powershell
.\\run_web.ps1
```

Open browser: http://localhost:3000  
Health: http://127.0.0.1:8000/api/v1/health/live  
API docs: http://127.0.0.1:8000/docs

### What run_backend.ps1 does automatically

- Calls `scripts\\apply_local_env.ps1` to merge `.env.local` overrides
- Sets `LEGALEASE_DB_PATH` to project `legalease.db` (SQLite)
- Sets `SAAS_PRODUCTION=0`, skips blocking RAG warmup for fast boot
- Auto-starts Ollama on GPU when `OLLAMA_AUTO_START=1`
- Runs uvicorn on 127.0.0.1:8000 with 300s keep-alive

### Laptop vs EC2 separation (critical)

| File | Used on | Must NOT contain |
|------|---------|------------------|
| .env | Both (API keys) | SAAS_PRODUCTION=1 on laptop |
| .env.local | Laptop only (gitignored) | postgres/redis Docker hostnames |
| {EC2_PATH}/.env | EC2 only | localhost database URLs |

`aws_update.ps1` explicitly excludes `.env` and `.env.local` from upload. Server `.env` is never overwritten by deploy.

## 7.4 EC2 — Initial Server Setup (First Time)

### 7.4.1 AWS resources

1. Launch Ubuntu 22.04+ EC2 instance (recommended: m7i-flex.large, 8 GB RAM)
2. Security group inbound rules:
   - SSH 22 from your IP
   - HTTP 80 from 0.0.0.0/0 (required for DuckDNS)
   - HTTPS 443 from 0.0.0.0/0 (when TLS certs mounted)
3. Elastic IP optional; current production IP: {EC2_IP}
4. DuckDNS: point `legalease.duckdns.org` A record to {EC2_IP}

See `deploy/aws/OPEN_PORT_80.md` if DuckDNS times out (port 80 blocked).

### 7.4.2 SSH access from Windows

```powershell
ssh -i $env:USERPROFILE\\.ssh\\legalease-aws.pem {EC2_USER}@{EC2_IP}
```

### 7.4.3 Install Docker on EC2 (if fresh server)

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
# Log out and back in
```

### 7.4.4 First deploy from Windows

From project root on your laptop:

```powershell
.\\scripts\\aws_update.ps1 -VmIp {EC2_IP} -PublicUrl "{PROD_URL}"
```

This script:
1. Creates `legalease-deploy.tgz` (excludes Data, node_modules, .next, venv, .env)
2. SCP upload to `{EC2_PATH}/legalease-deploy.tgz`
3. SSH runs remote script that:
   - Extracts tarball to `{EC2_PATH}`
   - Runs `deploy/aws/fix-ec2-env.sh '{PROD_URL}'`
   - Runs `deploy/aws/fix-postgres-password.sh`
   - Runs `deploy/aws/ec2-go-live.sh '{PROD_URL}'`
4. Rebuilds api + web Docker images with correct `NEXT_PUBLIC_API_URL`
5. Starts nginx, api, web, postgres, redis

Expected duration: 5–15 minutes.

### 7.4.5 Create production .env on server (first time only)

SSH to EC2 and create `{EC2_PATH}/.env` from template:

```bash
cd {EC2_PATH}
cp deploy/aws/.env.production.example .env
nano .env
```

Required values to set (generate secrets with `pwsh scripts/rotate_secrets.ps1` on laptop):

```env
POSTGRES_PASSWORD=<strong-random-password>
JWT_SECRET=<32+-char-random>
LEGALEASE_API_SECRET=<32+-char-random>
DATA_ENCRYPTION_KEY=<32+-char-random>
GEMINI_API_KEY=<your-google-ai-key>
PUBLIC_APP_URL={PROD_URL}
CORS_ORIGINS={PROD_URL}
NEXT_PUBLIC_API_URL={PROD_API}
DATABASE_URL=postgresql://legalease:<POSTGRES_PASSWORD>@postgres:5432/legalease
REDIS_URL=redis://redis:6379/0
SAAS_USE_POSTGRES_LEGACY=1
SAAS_PRODUCTION=1
LLM_BACKEND=gemini
CLOUD_GEMINI_KB=1
```

Stripe (before SAAS_PRODUCTION_STRICT=1):

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_LEGAL_PRO=price_...
```

Then re-run go-live:

```bash
bash deploy/aws/ec2-go-live.sh {PROD_URL}
```

## 7.5 EC2 — Re-Deploy After Code Changes

### Full update (recommended)

```powershell
cd "C:\\Users\\ASUS\\Desktop\\Legal_ai (1)\\Legal_ai\\Legal_AI_Final 3"
.\\scripts\\aws_update.ps1 -VmIp {EC2_IP} -PublicUrl "{PROD_URL}"
```

### Hotfix only (5 deploy files, no full tarball)

```powershell
.\\scripts\\aws_go_live.ps1 -VmIp {EC2_IP} -PublicUrl "{PROD_URL}"
```

### Post-deploy verification checklist

1. `curl {PROD_API}/v1/health/live` returns 200
2. `curl {PROD_API}/v1/health/public` shows `core_db.backend: postgresql`
3. Open {PROD_URL} in browser — hard refresh (Ctrl+Shift+R)
4. Login as admin user
5. Test chat (KB mode) and thumbs feedback
6. Test Evidence Intelligence upload on /discovery

## 7.6 Docker Compose Services Reference

| Service | Image/Build | Ports | Memory limit (EC2 low) | Role |
|---------|-------------|-------|------------------------|------|
| postgres | postgres:16-alpine | 5432 internal | default | All SaaS tables when SAAS_USE_POSTGRES_LEGACY=1 |
| redis | redis:7-alpine | 6379 internal | default | Chat sessions, ML job queues |
| api | deploy/Dockerfile.api.aws | 8000 internal | 4G | FastAPI REST + SSE |
| web | deploy/Dockerfile.web | 3000 internal | 1536M | Next.js UI |
| nginx | nginx:alpine | 80, 443 | default | Reverse proxy |
| worker | same as api | — | profile workers | E-discovery job processor |
| ml-worker | same as api | — | profile workers | ML tuning / reindex jobs |

Compose file stack (from `deploy/aws/apply-ec2-tier.sh`):

```bash
-f docker-compose.yml
-f deploy/aws/docker-compose.override.yml
# + deploy/aws/docker-compose.highmem.yml when RAM tier != low
# + deploy/aws/docker-compose.https.yml when SSL certs exist
```

Environment exported to `/tmp/legalease-compose.env`:

```bash
LEGALEASE_COMPOSE_FILES="-f docker-compose.yml -f deploy/aws/docker-compose.override.yml ..."
eval "$(cat /tmp/legalease-compose.env)"
docker compose ${{LEGALEASE_COMPOSE_FILES}} ps
```

## 7.7 EC2 Memory Tiers (apply-ec2-tier.sh)

| Tier | Detection | ML_USE_QUEUE | LOW_RESOURCE_MODE | STT model | Workers |
|------|-----------|--------------|-------------------|-----------|---------|
| low | <=8 GB | 0 | 1 | tiny | disabled |
| medium | 8–16 GB | 1 | 0 | small | optional |
| high | >16 GB | 1 | 0 | small | can enable |

On low tier (current 8GB production):
- `UVICORN_WORKERS=1`
- `RAG_ENABLE_CROSS_ENCODER=0`
- `HF_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`
- Ollama disabled; Gemini required for web modes

Enable workers on high-memory instance:

```bash
docker compose $LEGALEASE_COMPOSE_FILES --profile workers up -d worker ml-worker
```

## 7.8 nginx Configuration

Production nginx config: `deploy/nginx/nginx.conf` (HTTP) and `deploy/nginx/nginx-ssl.conf` (HTTPS).

Key settings:
- `/api/` proxied to `http://api:8000/api/`
- `/` proxied to `http://web:3000/`
- `proxy_read_timeout 300s` for long chat streams
- Rate limiting zones for auth and chat endpoints

TLS certificates path:
- `deploy/nginx/ssl/cert.pem` (full chain)
- `deploy/nginx/ssl/key.pem` (private key)

When both exist, `apply-ec2-tier.sh` adds `-f deploy/aws/docker-compose.https.yml`.

## 7.9 DuckDNS and TLS Setup

### DuckDNS

1. Register subdomain at duckdns.org
2. Set A record to {EC2_IP}
3. Ensure AWS security group allows inbound TCP 80
4. Set in server `.env`:
   - `PUBLIC_APP_URL={PROD_URL}`
   - `CORS_ORIGINS={PROD_URL}`
   - `NEXT_PUBLIC_API_URL={PROD_API}`

### Let's Encrypt (optional HTTPS)

On EC2 with port 443 open:

```bash
sudo apt install certbot
sudo certbot certonly --standalone -d legalease.duckdns.org
sudo cp /etc/letsencrypt/live/legalease.duckdns.org/fullchain.pem deploy/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/legalease.duckdns.org/privkey.pem deploy/nginx/ssl/key.pem
bash deploy/aws/apply-ec2-tier.sh
bash deploy/aws/ec2-go-live.sh {PROD_URL}
```

### Cloudflare quick tunnel (fallback when port 80 blocked)

`ec2-go-live.sh` auto-starts cloudflared if direct HTTP fails:

```bash
cloudflared tunnel --url http://127.0.0.1:80
# URL logged to /tmp/cloudflared.log
# systemd unit: cloudflared-legalease.service
```

Use tunnel URL as `-PublicUrl` until port 80 is opened.

## 7.10 Environment Variable Profiles (Laptop vs EC2)

| Variable | Laptop (.env.local) | EC2 ({EC2_PATH}/.env) |
|----------|---------------------|------------------------|
| LEGALEEASE_LOCAL_DEV | 1 | unset |
| SAAS_PRODUCTION | 0 | 1 |
| SAAS_PRODUCTION_STRICT | 0 | 1 (after Stripe keys set) |
| SAAS_USE_POSTGRES_LEGACY | 0 | 1 |
| DATABASE_URL | empty (SQLite) | postgresql://legalease:PASS@postgres:5432/legalease |
| LEGALEASE_DB_PATH | legalease.db | /data/legalease.db |
| REDIS_URL | optional | redis://redis:6379/0 |
| LLM_BACKEND | ollama | gemini |
| CLOUD_GEMINI_KB | 0 | 1 |
| OLLAMA_AUTO_START | 1 | 0 |
| NEXT_PUBLIC_API_URL | http://127.0.0.1:8000 | {PROD_API} |
| CORS_ORIGINS | http://localhost:3000 | {PROD_URL} |
| PUBLIC_APP_URL | http://localhost:3000 | {PROD_URL} |
| ALLOW_MOCK_BILLING | 1 | 0 |
| SAAS_ALL_FEATURES_FREE | 1 | 1 (demo) |
| RATE_LIMIT_ENABLED | 0 or 1 | 1 |
| STT_ENABLED | 1 | 1 |
| STT_DEVICE | cuda if GPU | cpu |
| STT_MODEL | base/small | tiny (low RAM) |
| IMPROVEMENT_AUTO | 1 | 0 |
| COACH_AUTO_SCHEDULE | 1 | 0 |

## 7.11 Stripe Billing Setup (Production)

1. Create Stripe account and products (Pro, Legal Pro)
2. Copy price IDs to `.env`: `STRIPE_PRICE_PRO`, `STRIPE_PRICE_LEGAL_PRO`
3. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`
4. Configure Stripe webhook endpoint: `{PROD_API}/v1/subscriptions/webhook`
5. Set `SAAS_PRODUCTION_STRICT=1` only after keys are live
6. If API unhealthy due to placeholder Stripe key, temporarily set `SAAS_PRODUCTION_STRICT=0`

## 7.12 Database Backup and Restore

### Backup (production)

```bash
ssh -i ~/.ssh/legalease-aws.pem ubuntu@{EC2_IP}
cd {EC2_PATH}
export DATABASE_URL=postgresql://legalease:YOUR_PASS@postgres:5432/legalease
docker compose $LEGALEASE_COMPOSE_FILES exec -T postgres pg_dump -U legalease legalease > backups/postgres_$(date +%Y%m%d).dump
```

Or from laptop:

```powershell
py scripts\\backup_legalease.py --out backups/manual
```

Backup includes: postgres dump, SQLite (if present), faiss_indexes/, Data/

### Restore procedure

1. Stop API: `docker compose $LEGALEASE_COMPOSE_FILES stop api web`
2. Restore Postgres: `pg_restore -d legalease backups/postgres_YYYYMMDD.dump`
3. Restore files: copy faiss_indexes/ and Data/ from backup
4. Start stack: `bash deploy/aws/ec2-go-live.sh {PROD_URL}`
5. Verify: `curl {PROD_API}/v1/health/public`

### SQLite to Postgres migration (one-time)

```powershell
py scripts\\migrate_sqlite_to_pg.py
```

Run when moving from laptop SQLite to Docker Postgres.

## 7.13 Rollback Procedure

If deploy breaks production:

```bash
ssh ubuntu@{EC2_IP}
cd {EC2_PATH}
# View previous images
docker images | grep legalease
# Roll back to previous git state if tagged
git log --oneline -5
# Or restore from backup (section 7.12)
docker compose $LEGALEASE_COMPOSE_FILES logs api --tail 100
```

From Windows, redeploy last known good commit:

```powershell
git checkout <last-good-commit>
.\\scripts\\aws_update.ps1 -PublicUrl "{PROD_URL}"
```

## 7.14 Monitoring and Logs

```bash
# All services
docker compose $LEGALEASE_COMPOSE_FILES ps
docker compose $LEGALEASE_COMPOSE_FILES logs -f api
docker compose $LEGALEASE_COMPOSE_FILES logs -f web
docker compose $LEGALEASE_COMPOSE_FILES logs -f nginx

# Health endpoints
curl {PROD_API}/v1/health/live
curl {PROD_API}/v1/health/ready
curl {PROD_API}/v1/health/public
curl {PROD_API}/v1/health/llm
```

Structured logs in API include request ID, user ID, and pipeline stage when `KB_PIPELINE_DEBUG=1`.

## 7.15 CI/CD (GitHub Actions)

File: `.github/workflows/ci.yml`

On every push/PR:
- Python pytest (~126 tests)
- Next.js production build verification
- Lint checks

CI does not auto-deploy to EC2. Production deploy is manual via `aws_update.ps1`.

## 7.16 Troubleshooting Matrix (Complete)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 502 Bad Gateway on /api | API container down or starting | `docker compose logs api`; wait 90s start_period |
| CORS error in browser | CORS_ORIGINS mismatch | Set CORS_ORIGINS exactly to {PROD_URL} (no trailing slash) |
| Web shows wrong API | Stale NEXT_PUBLIC_API_URL | Rebuild web: `ec2-go-live.sh {PROD_URL}` |
| password authentication failed for postgres | POSTGRES_PASSWORD drift | `bash deploy/aws/fix-postgres-password.sh` |
| STRIPE_SECRET_KEY placeholder error | SAAS_PRODUCTION_STRICT=1 without keys | Add Stripe keys or set STRICT=0 temporarily |
| Thumbs feedback not saving | adaptive_mode_stats schema | Deploy latest code (pg_core_schema migration) |
| KB returns NOT_FOUND | Documents not indexed | Upload PDFs, click Index All, check faiss_indexes volume |
| Open Law quota exceeded | Gemini daily limit | Wait for reset or upgrade plan; Tavily fallback |
| Ollama connection refused on EC2 | Expected — EC2 uses Gemini | Set LLM_BACKEND=gemini, CLOUD_GEMINI_KB=1 |
| Port 8000 in use on laptop | Stale Python process | `.\\stop_backend.ps1` then `run_backend.ps1` |
| DuckDNS timeout | Port 80 blocked | Open AWS SG port 80 or use Cloudflare tunnel |
| Web build fails premium/page | Stale route | aws_update.ps1 removes web/app/(app)/premium |
| Sessions lost between requests | Redis not configured | Set REDIS_URL=redis://redis:6379/0 |
| OCR fails on scans | EasyOCR not in container | Rebuild api image; check OCR_ENABLED=1 |
| STT fails in browser | ffmpeg missing on laptop | winget install Gyan.FFmpeg |
| Feedback 500 on Postgres | Transaction rollback on stats | Latest adaptive_learning.py commits interaction first |
| Index job stuck | ML_USE_QUEUE=0 on low RAM | Run index from UI; or enable worker profile |
| High API memory | FAISS + embeddings | LOW_RESOURCE_MODE=1, RAG_ENABLE_CROSS_ENCODER=0 |
| TLS handshake error | Cert path wrong | Verify deploy/nginx/ssl/cert.pem and key.pem |
| Login works locally not EC2 | Wrong DATABASE_URL | Must use @postgres:5432 not @localhost |
| Deploy tarball huge | Data included | aws_update excludes Data, faiss_indexes, node_modules |

## 7.17 fix-ec2-env.sh — Line-by-Line Behavior

Script: `deploy/aws/fix-ec2-env.sh`

1. Sets working directory to `{EC2_PATH}`
2. Accepts public URL argument (defaults to http://{EC2_IP})
3. Forces SAAS_USE_POSTGRES_LEGACY=1
4. Runs apply-ec2-tier.sh for memory tier compose files
5. Rewrites DATABASE_URL localhost to postgres hostname
6. Rewrites REDIS_URL 127.0.0.1 to redis hostname
7. Sets CLOUD_GEMINI_KB=1 if missing
8. Sets CORS_ORIGINS, PUBLIC_APP_URL, NEXT_PUBLIC_API_URL from public URL
9. Configures CPU speech-to-text (STT_MODEL=tiny, STT_DEVICE=cpu)
10. Rebuilds api + web containers
11. Restarts api, web, nginx

## 7.18 ec2-go-live.sh — Line-by-Line Behavior

Script: `deploy/aws/ec2-go-live.sh`

1. Detects EC2 public IP via checkip.amazonaws.com
2. Sets SAAS_USE_POSTGRES_LEGACY=1, SAAS_PRODUCTION=1
3. Configures STT for CPU
4. Runs apply-ec2-tier.sh
5. `docker compose up -d --build` full stack
6. If no PUBLIC_BASE arg and port 80 unreachable: starts Cloudflare tunnel
7. Writes systemd unit for cloudflared persistence
8. Updates CORS, PUBLIC_APP_URL, NEXT_PUBLIC_API_URL
9. Rebuilds api + web with exported NEXT_PUBLIC_API_URL
10. Health check loop (60 attempts, 2s interval)
11. Prints live URL and health response

## 7.19 Docker Local Production (Non-EC2)

For self-hosted Docker on any server:

```powershell
copy .env.docker.example .env
# Edit POSTGRES_PASSWORD, JWT_SECRET, NEXT_PUBLIC_API_URL, CORS_ORIGINS
# Place TLS certs in deploy/nginx/ssl/
docker compose up -d --build
```

Health: http://localhost/api/v1/health/live

See DEPLOY.md for LM Studio on Windows host (`LM_STUDIO_URL=http://host.docker.internal:1234`).

## 7.20 Post-Deploy Smoke Tests

```powershell
# From laptop
curl {PROD_API}/v1/health/live
py scripts\\e2e_saas_smoke.py --url {PROD_API}
py scripts\\e2e_kb_smoke.py --url {PROD_API}
```

Manual UI tests:
1. Register / login
2. Upload PDF to Documents, Index All
3. KB chat with citation
4. Create matter, link document
5. Evidence Intelligence upload on /discovery
6. Thumbs up on chat response — verify POST /api/v1/learning/feedback returns ok:true
7. Billing invoice PDF export (if Stripe configured)

## 7.21 Security Hardening Checklist

- [ ] JWT_SECRET and LEGALEASE_API_SECRET are unique 32+ char random strings
- [ ] POSTGRES_PASSWORD is strong and not committed to git
- [ ] GEMINI_API_KEY only on server .env
- [ ] SAAS_PRODUCTION_STRICT=1 after Stripe configured
- [ ] FORCE_HTTPS=1 and SECURITY_HEADERS_ENABLED=1 on production
- [ ] FIREWALL_ENABLED=0 or restrict FIREWALL_ALLOWED_IPS for admin
- [ ] SUPERADMIN_USERNAMES lists only trusted admins
- [ ] Regular Postgres backups scheduled
- [ ] SSH key-only access (disable password auth)
- [ ] AWS security group limits SSH to your IP

## 7.22 Volume and Data Persistence

| Volume | Mount | Contents |
|--------|-------|----------|
| postgres_data | postgres | All PostgreSQL data |
| redis_data | redis | Session/cache AOF |
| app_data | api | /data/legalease.db fallback, uploads |
| ./faiss_indexes | api | Per-user FAISS vector indexes |
| ./Data | api | Uploaded PDFs and HF cache |

Never delete postgres_data without backup. faiss_indexes can be rebuilt via reindex but takes time.

---

"""


def build_api_index(routes: list[tuple[str, str, str]]) -> str:
    lines = [
        "# Appendix V — Complete API Route Index (Auto-Generated)",
        "",
        f"Total routes: **{len(routes)}** (includes WebSocket endpoints).",
        "Base prefix: `/api/v1`. Authentication: JWT Bearer unless noted public.",
        "",
        "| Module | Method | Path |",
        "|--------|--------|------|",
    ]
    for mod, method, path in routes:
        lines.append(f"| {mod} | {method} | `{path}` |")
    lines.append("")
    return "\n".join(lines)


def build_env_appendix() -> str:
    env_files = [
        (".env.example", "Root application (.env)"),
        (".env.local.example", "Laptop overrides (.env.local)"),
        (".env.docker.example", "Docker Compose local production"),
        ("deploy/aws/.env.production.example", "EC2 production template"),
    ]
    sections = [
        "# Appendix W — Complete Environment Variables Catalog",
        "",
        "Every variable from project env templates. Set secrets on server only; never commit real keys.",
        "",
    ]
    for rel, title in env_files:
        path = ROOT / rel
        rows = parse_env_file(path)
        if not rows:
            continue
        sections.append(f"## W.{rel}")
        sections.append(f"**Source file:** `{rel}` — {title}")
        sections.append("")
        sections.append("| Variable | Example value | Notes |")
        sections.append("|----------|---------------|-------|")
        for name, val, comment in rows:
            val = format_env_value(name, val, rel)
            display_val = val if len(val) <= 40 else val[:37] + "..."
            comment = comment.replace("|", "/")[:80]
            sections.append(f"| `{name}` | `{display_val}` | {comment} |")
        sections.append("")
    return "\n".join(sections)


def merge_markdown(deployment: str, api_index: str, env_appendix: str) -> str:
    base = SUITE_MD.read_text(encoding="utf-8")
    pattern = r"(# Document 7 — Deployment Architecture\n)(.*?)(\n# Document 8 — Product Workflow Guide)"

    def _replace_doc7(m: re.Match[str]) -> str:
        return deployment.rstrip() + m.group(3)

    merged, n = re.subn(pattern, _replace_doc7, base, count=1, flags=re.DOTALL)
    if n == 0:
        merged = base + "\n\n" + deployment
    merged += "\n\n---\n\n" + api_index + "\n\n---\n\n" + env_appendix
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    merged += f"\n\n---\n\n*Complete documentation built {ts}. Production URL: {PROD_URL}*\n"
    return merged


def generate_pdf(md_path: Path, pdf_path: Path) -> int:
    script = ROOT / "scripts" / "generate_architecture_pdf.py"
    result = subprocess.run(
        [sys.executable, str(script), "--input", str(md_path), "--output", str(pdf_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    m = re.search(r"Pages:\s*(\d+)", result.stdout)
    return int(m.group(1)) if m else 0


def main() -> None:
    if not SUITE_MD.exists():
        raise SystemExit(f"Missing {SUITE_MD}")

    print("Extracting API routes...")
    routes = extract_routes()
    print(f"  Found {len(routes)} routes")

    print("Building deployment section...")
    deployment = build_deployment_section()

    print("Building appendices...")
    api_index = build_api_index(routes)
    env_appendix = build_env_appendix()

    print("Merging markdown...")
    merged = merge_markdown(deployment, api_index, env_appendix)
    OUTPUT_MD.write_text(merged, encoding="utf-8")
    print(f"  Written: {OUTPUT_MD} ({len(merged.splitlines())} lines)")

    print("Generating PDF...")
    pages = generate_pdf(OUTPUT_MD, OUTPUT_PDF)
    print(f"Done. PDF: {OUTPUT_PDF} ({pages} pages)")


if __name__ == "__main__":
    main()
