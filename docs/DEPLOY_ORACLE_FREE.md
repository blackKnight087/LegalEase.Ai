# Oracle Cloud Always Free — LegalEase 24/7 deploy

Run LegalEase on a **free Oracle VM** so it stays online when your laptop is off.

| What you get | Tradeoff |
|--------------|----------|
| 24/7 public URL | LLM on **CPU** (slower than your GPU laptop) |
| $0/month (Always Free tier) | 1 VM, ~1–3 concurrent users |
| Ollama + Docker stack | ~1–2 hours first-time setup |
| Free DNS (no paid domain) | Oracle signup may ask for card (not charged in free tier) |

---

## Architecture

```
Internet → Oracle VM public IP :80
              ├── nginx → Next.js (web)
              ├── nginx → FastAPI (api)
              ├── PostgreSQL + Redis (Docker)
              └── Ollama on HOST :11434 ← legalease-tuned / qwen3:8b
```

---

## Part 1 — Create the VM (Oracle console)

1. Sign up: [https://cloud.oracle.com](https://cloud.oracle.com) → **Always Free** eligible account.
2. **Compute → Instances → Create instance**
   - Name: `legalease-prod`
   - **Image:** Ubuntu 22.04 **aarch64** (ARM)
   - **Shape:** Ampere A1 — pick **4 OCPU + 24 GB RAM** if available (or max free allocation)
   - **Boot volume:** 100–200 GB
   - **Networking:** assign **public IPv4**
   - **SSH keys:** paste your public key (generate below if needed)
3. **Create**
4. Note the **public IP** (e.g. `123.45.67.89`)

### Generate SSH key (Windows PowerShell, once)

```powershell
ssh-keygen -t ed25519 -C "legalease-oracle" -f $env:USERPROFILE\.ssh\legalease_oracle
Get-Content $env:USERPROFILE\.ssh\legalease_oracle.pub
# Paste into Oracle "SSH public key" box
```

### Open firewall (Oracle + Ubuntu)

**Oracle Cloud → VCN → Security List → Ingress:**

| Source | Protocol | Port |
|--------|----------|------|
| 0.0.0.0/0 | TCP | 22 |
| 0.0.0.0/0 | TCP | 80 |
| 0.0.0.0/0 | TCP | 443 |

---

## Part 2 — Bootstrap the VM

SSH in (replace IP and key path):

```powershell
ssh -i $env:USERPROFILE\.ssh\legalease_oracle ubuntu@YOUR.PUBLIC.IP
```

On the VM, run the bootstrap script from your project (after upload) **or** paste commands:

```bash
curl -fsSL https://raw.githubusercontent.com/YOUR_USER/LegalEase/main/deploy/oracle/bootstrap.sh | bash
```

If you don't have GitHub yet, copy the script manually:

```powershell
# From your laptop (project root)
scp -i $env:USERPROFILE\.ssh\legalease_oracle deploy/oracle/bootstrap.sh ubuntu@YOUR.IP:/tmp/
scp -i $env:USERPROFILE\.ssh\legalease_oracle deploy/oracle/.env.production.example ubuntu@YOUR.IP:/tmp/
```

```bash
# On VM
chmod +x /tmp/bootstrap.sh
sudo /tmp/bootstrap.sh
```

The script installs: Docker, Docker Compose, Ollama, firewall rules, and creates `/opt/legalease`.

---

## Part 3 — Upload LegalEase code

**Do not upload `Data/` (multi-GB) or `.venv/`** — upload code only; add documents later in the app.

### Option A — Git (recommended)

```bash
cd /opt/legalease
git clone https://github.com/YOUR_USER/LegalEase.git .
# Or private repo with deploy key
```

### Option B — Zip from laptop

On Windows (exclude heavy folders):

```powershell
cd "C:\Users\ASUS\Desktop\Legal_ai (1)\Legal_ai\Legal_AI_Final 3"
# Create archive without Data/node_modules/venv
tar --exclude=Data --exclude=web/node_modules --exclude=.venv_win --exclude=faiss_indexes -czf legalease-deploy.tgz .
scp -i $env:USERPROFILE\.ssh\legalease_oracle legalease-deploy.tgz ubuntu@YOUR.IP:/opt/legalease/
```

On VM:

```bash
cd /opt/legalease
tar -xzf legalease-deploy.tgz
mkdir -p Data faiss_indexes Data/hf_cache
```

---

## Part 4 — Configure environment

```bash
cd /opt/legalease
cp deploy/oracle/.env.production.example .env
nano .env   # or vim
```

**Must change:**

| Variable | Example |
|----------|---------|
| `POSTGRES_PASSWORD` | long random string |
| `JWT_SECRET` | 32+ random chars |
| `LEGALEASE_API_SECRET` | 32+ random chars |
| `PUBLIC_APP_URL` | `http://YOUR.IP` or `https://legalease.duckdns.org` |
| `CORS_ORIGINS` | same as PUBLIC_APP_URL |
| `NEXT_PUBLIC_API_URL` | `http://YOUR.IP/api` (note `/api` suffix) |
| `GEMINI_API_KEY` | your key (Open Law) |

Generate secrets:

```bash
openssl rand -hex 32
```

---

## Part 5 — Ollama models (on VM host)

```bash
sudo systemctl enable ollama
sudo systemctl start ollama

# Smaller/faster on CPU free tier (pick one):
ollama pull qwen2.5:7b

# Or your tuned model if you export Modelfile from laptop:
# On laptop: ollama show legalease-tuned --modelfile > Modelfile
# scp Modelfile ubuntu@VM:/tmp/
# ollama create legalease-tuned -f /tmp/Modelfile

ollama list
curl http://127.0.0.1:11434/api/tags
```

Set in `.env`:

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=legalease-tuned
OLLAMA_MODEL_LEGAL=legalease-tuned
LOW_RESOURCE_MODE=1
LLM_INTAKE_LEGAL_ANALYSIS=0
RAG_ENABLE_CROSS_ENCODER=0
```

---

## Part 6 — Start the stack

```bash
cd /opt/legalease
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml up -d --build
```

First build takes **15–40 minutes** on ARM.

Check status:

```bash
docker compose ps
docker compose logs -f api --tail 80
curl -s http://127.0.0.1/api/v1/health/live
curl -s http://127.0.0.1/api/v1/health/llm
```

Open in browser: `http://YOUR.PUBLIC.IP`

---

## Part 7 — Stable free hostname (optional)

### DuckDNS (free)

1. [https://www.duckdns.org](https://www.duckdns.org) → create `legalease` → `legalease.duckdns.org`
2. Point to your VM public IP
3. Update `.env`:

```env
PUBLIC_APP_URL=http://legalease.duckdns.org
CORS_ORIGINS=http://legalease.duckdns.org
NEXT_PUBLIC_API_URL=http://legalease.duckdns.org/api
```

4. Rebuild web (URL is baked at build time):

```bash
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml up -d --build web
docker compose restart api nginx
```

### HTTPS (recommended for production demo)

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d legalease.duckdns.org
# Copy certs to deploy/nginx/ssl/ and enable nginx-ssl.conf — see DEPLOY.md
```

---

## Part 8 — Copy your Modelfile from laptop (optional)

If you use `legalease-tuned` locally:

```powershell
ollama show legalease-tuned --modelfile > Modelfile
scp -i $env:USERPROFILE\.ssh\legalease_oracle Modelfile ubuntu@YOUR.IP:/tmp/
```

```bash
ollama create legalease-tuned -f /tmp/Modelfile
```

---

## Part 9 — Copy KB documents (optional)

Upload PDFs via the app UI after deploy, **or**:

```powershell
scp -i $env:USERPROFILE\.ssh\legalease_oracle -r ".\Data\documents\*" ubuntu@YOUR.IP:/opt/legalease/Data/
```

Then re-index from the Documents page in the app.

---

## Daily operations

```bash
cd /opt/legalease
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml ps
docker compose logs api --tail 50
sudo systemctl status ollama
```

**Restart everything:**

```bash
sudo systemctl restart ollama
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml restart
```

**Update code:**

```bash
git pull
docker compose -f docker-compose.yml -f deploy/oracle/docker-compose.override.yml up -d --build
```

---

## Oracle free tier limits (realistic)

| Resource | Limit |
|----------|--------|
| VM | Always Free ARM allocation (often 4 OCPU / 24 GB) |
| LLM speed | CPU only — 10–60s answers for 7B–8B |
| Concurrent users | 1–3 comfortable |
| Gemini Open Law | Free API daily caps still apply |
| Egress | Generous on Oracle; still not “unlimited CDN” |

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Site unreachable | Oracle security list ports 80/443; `sudo ufw allow 80` |
| LLM offline | `systemctl status ollama`; `ollama list`; check `OLLAMA_BASE_URL` |
| API 502 | `docker compose logs api`; wait for healthcheck (90s start) |
| CORS errors | `CORS_ORIGINS` must match browser URL exactly |
| Web calls wrong API | Rebuild `web` after changing `NEXT_PUBLIC_API_URL` |
| Out of memory | Set `LOW_RESOURCE_MODE=1`; use `qwen2.5:3b` for classify only |
| Build fails on ARM | `docker compose build --no-cache api`; ensure 24GB VM |

---

## Security checklist

- [ ] Change all default passwords in `.env`
- [ ] `SAAS_PRODUCTION=1`
- [ ] Enable HTTPS before sharing widely
- [ ] Do not commit `.env` to git
- [ ] Restrict SSH to your IP in Oracle security list if possible
- [ ] Rotate API keys if they were ever in a public repo

---

## Related docs

- [DEPLOY_FREE_24_7_REALISTIC.md](./DEPLOY_FREE_24_7_REALISTIC.md) — why free has limits
- [DEPLOY.md](../DEPLOY.md) — Docker + TLS details
- [STABLE_PUBLIC_LINK.md](./STABLE_PUBLIC_LINK.md) — laptop tunnel (not 24/7)
