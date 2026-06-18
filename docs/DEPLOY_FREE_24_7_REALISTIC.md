# Free 24/7 hosting — what is actually possible

You asked for: **always on**, **laptop off**, **$0**, **no limits**.

With LegalEase today (local **Ollama `legalease-tuned`**, FAISS on disk, ~16GB laptop), that **exact combo does not exist**. Someone must run the server 24/7, and free cloud always has caps.

This doc explains the tradeoffs and the **best free path** that gets closest.

---

## Why your laptop tunnel cannot be 24/7

| Piece | On your laptop | When laptop is off |
|-------|----------------|---------------------|
| Ollama + `legalease-tuned` | Runs locally | **Stops** |
| FAISS / uploaded PDFs | On your disk | **Unavailable** |
| Cloudflare quick tunnel | Points to your PC | **Dead** |

Tunnels (Cloudflare, ngrok) only forward traffic **to a machine that is running**. They are not hosting.

---

## The honest matrix

| Goal | Free? | 24/7? | Keeps Ollama / tuned model? | No limits? |
|------|-------|-------|----------------------------|------------|
| Cloudflare tunnel → laptop | Yes | No | Yes | No (PC must stay on) |
| Render / Railway free tier | Yes | **Partial** (sleeps when idle) | No GPU | No (hours/credits cap) |
| Vercel (frontend only) | Yes | Yes | N/A | No (serverless limits) |
| **Oracle Cloud Always Free VM** | Yes | **Yes** | Yes (CPU, slow) | No (1 VM, RAM/CPU caps) |
| Gemini-only cloud mode | Yes tier | Yes if API hosted | **No** (cloud LLM) | No (15–200 calls/day) |

**There is no free tier that is 24/7 + unlimited LLM + unlimited users + your custom Ollama model with zero caps.**

You choose what to sacrifice.

---

## Recommended: Oracle Cloud Always Free (closest to your goal)

**What you get (free forever tier, if account approved):**

- 1–4 ARM VMs (e.g. **Ampere A1**: up to 4 OCPU, **24 GB RAM** on the free allocation)
- Public IP + optional free subdomain or later a cheap domain
- Can run **Docker Compose** (nginx, API, web, Postgres, Redis)
- Can run **Ollama on CPU** with `qwen3:8b` or `legalease-tuned` (if you copy the Modelfile) — **slower** than your RTX 4050, but **always on**

**What you give up:**

- Setup time (1–2 hours first time)
- No GPU on free tier → LLM answers slower (10–30s+)
- Single VM → **1–3 concurrent users** realistically
- You manage updates, backups, security
- Oracle signup can require card verification (not charged if you stay in Always Free)

**Stable URL options without buying a domain:**

- Use the VM’s **public IP**: `http://YOUR.IP.ADDRESS` (HTTPS needs cert — Let’s Encrypt works with a free DuckDNS/FreeDNS name)
- Free DNS: `legalease.duckdns.org` or `legalease.mooo.com` → point A record to VM IP

---

## Alternative: “Always on UI, LLM when you’re online” (hybrid)

If you refuse Oracle setup:

1. **Frontend + API shell** on Render free / Fly.io → URL always resolves but **API sleeps** after ~15 min idle (cold start 30–60s).
2. **LLM**: Gemini free when configured; **no `legalease-tuned`** unless your laptop is on and you expose Ollama (back to tunnel problem).

This is **not** true 24/7 quality for chat.

---

## Alternative: Cloud LLM only (no Ollama)

Set on a free VM or Render:

```env
LLM_BACKEND=ollama   # off
GEMINI_KB_SYNTHESIS=0
# Use Gemini / OpenRouter for answers — not legalease-tuned
```

- Works 24/7 on a small free host
- **Hard daily limits** on Gemini free
- Different answer quality vs your tuned model

---

## What we recommend for LegalEase demo → small public beta

### Path A — Serious free 24/7 (best match)

1. Create **Oracle Cloud Always Free** account  
2. Ubuntu 22.04 ARM VM (24 GB RAM if available)  
3. Install Docker + Ollama  
4. `git clone` LegalEase (exclude `Data/` from git; upload KB separately or empty)  
5. `docker compose up -d --build`  
6. Free DNS → VM IP  
7. Pull `legalease-tuned` or `qwen3:8b` on the VM  

**Guide to add next:** `docs/DEPLOY_ORACLE_FREE.md` (step-by-step).

### Path B — Keep laptop for LLM, cloud for “brochure site” only

Not what you asked for — UI loads 24/7 but **chat dies** when laptop off.

---

## Minimum viable `.env` on a cloud VM (CPU Ollama)

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=legalease-tuned
PUBLIC_APP_URL=https://legalease.duckdns.org
CORS_ORIGINS=https://legalease.duckdns.org
SAAS_PRODUCTION=1
JWT_SECRET=<long-random-secret>
DATABASE_URL=postgresql://...
REDIS_URL=redis://redis:6379/0
LOW_RESOURCE_MODE=1
LLM_INTAKE_LEGAL_ANALYSIS=0
```

Use **Postgres + Redis** in Docker (included in `docker-compose.yml`).

---

## Summary

| Your requirement | Reality |
|------------------|---------|
| Laptop off | Need a **cloud VM** or PaaS |
| Free | **Oracle Always Free VM** is the strongest option |
| No limitations | **Not possible** on any free tier — expect slower LLM, user caps, API quotas |
| Keep `legalease-tuned` | Possible on Oracle VM **CPU only**, not on Render/Vercel alone |

**Next step:** If you accept Oracle setup (~1–2 hours) and slower CPU inference, follow **[DEPLOY_ORACLE_FREE.md](./DEPLOY_ORACLE_FREE.md)** for copy-paste VM setup.

If you need **true** unlimited 24/7 with GPU-speed LLM, the minimum realistic budget is roughly **$20–80/month** (GPU VPS or paid inference API).
