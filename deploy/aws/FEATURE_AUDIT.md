# AWS deployment — feature audit

Last checked against EC2 stack (api, web, nginx, postgres, redis).

## Infrastructure

| Item | Status | Notes |
|------|--------|--------|
| API live | OK | `/api/v1/health/live` |
| Postgres + legacy SaaS | OK | `SAAS_USE_POSTGRES_LEGACY=1` |
| Redis sessions | OK | Configured |
| Public URL | OK | Cloudflare tunnel or DuckDNS after port 80 |
| Port 80 from internet | Often blocked | Open security group for DuckDNS |
| ml-worker / ediscovery worker | Off | `ML_USE_QUEUE=0`, workers profile disabled — queue jobs run inline or skip |

## AI / search

| Feature | AWS status | Fix applied |
|---------|------------|-------------|
| Open Law / web (Gemini) | OK | `GEMINI_API_KEY`, grounded search |
| Knowledge Base chat | Was broken | **CLOUD_GEMINI_KB** — Gemini answers from chunks when Ollama absent |
| Embeddings / indexing | Was broken | **LEGALEEASE_HF_CACHE=/data/hf_cache** (permission fix) |
| FAISS | OK | faiss-cpu in image |
| Ollama / legalease-tuned | N/A on 8GB EC2 | Use laptop for tuned model |
| LM Studio | N/A | Health UI now shows Gemini when configured |
| DuckDuckGo fallback | Off in slim image | Gemini covers web search |

## Product modules (API routes present)

| Module | Expected on AWS |
|--------|-----------------|
| Auth / account / sessions | OK |
| Chat (KB, open law, hybrid) | OK after cloud KB + embeddings fix |
| Documents / KB upload | OK after embeddings fix |
| Practice / litigation / CRM | OK (Postgres) |
| Billing / Stripe | OK if keys in `.env` |
| eDiscovery queue | Limited without ml-worker |
| Speech | OK if ffmpeg in image |
| SSO / enterprise | OK if configured in `.env` |
| Email SMTP | Depends on `.env` |

## After code deploy

```powershell
.\scripts\aws_go_live.ps1 -VmIp 18.61.68.82 -PublicUrl "https://YOUR-TUNNEL-OR-DOMAIN"
```

On EC2 once:

```bash
sudo chown -R 10001:10001 /opt/legalease/Data /data 2>/dev/null || true
```

Verify:

```bash
curl -s http://127.0.0.1/api/v1/health/ready
curl -s http://127.0.0.1/api/v1/health/llm
curl -s http://127.0.0.1/api/v1/health/public
```

`ready: true` and `llm_ready: true` (Gemini) = good.
