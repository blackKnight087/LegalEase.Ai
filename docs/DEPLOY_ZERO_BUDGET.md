# Zero-budget public demo (laptop + Ollama + free tunnel)

Share LegalEase on the internet for **$0** while Ollama runs on your laptop. Your PC must stay on; this is a **demo**, not 24/7 SaaS hosting.

## Architecture

```
Internet user → Cloudflare Tunnel (HTTPS) → Next.js :3000 → FastAPI :8000 → Ollama :11434
                                              ↓
                                         SQLite + FAISS on your disk
```

- **Gemini/GPT**: cloud APIs (optional backup via `GEMINI_API_KEY`).
- **Ollama**: must run on the same machine as the API (or a URL you configure).

## Prerequisites

| Item | Check |
|------|--------|
| Ollama installed | `ollama --version` |
| Model pulled | `ollama list` matches `OLLAMA_MODEL` in `.env` |
| Python + Node | `py --version`, `node --version` |
| Project `.env` | `LLM_BACKEND=ollama`, `OLLAMA_BASE_URL=http://127.0.0.1:11434` |

## Quick start (automated)

From the project root in PowerShell:

```powershell
.\scripts\start_public_demo.ps1
```

This checks health, reminds you to run `cloudflared`, and can apply tunnel URLs to `.env`.

## Step 1 — Local health (must be green)

Start (if not already running):

```powershell
# Terminal 1 — Ollama (if not a background service)
ollama serve

# Terminal 2
.\run_backend.ps1

# Terminal 3
.\run_web.ps1
```

Verify:

| URL | Expected |
|-----|----------|
| http://127.0.0.1:8000/api/v1/health/live | HTTP 200 |
| http://127.0.0.1:8000/api/v1/health/llm | HTTP 200, LLM online |
| http://127.0.0.1:11434/api/tags | HTTP 200 |
| http://127.0.0.1:3000 | Login page loads |

Or run:

```powershell
.\scripts\verify_local_demo.ps1
```

## Step 2 — Cloudflare Tunnel (free)

1. Download **cloudflared**: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
2. With backend + web running, expose the frontend:

```powershell
cloudflared tunnel --url http://127.0.0.1:3000
```

3. Copy the `https://....trycloudflare.com` URL from the output.

**How API routing works:** Next.js rewrites `/api/*` to `NEXT_PUBLIC_API_URL` (see `web/next.config.js`). For the quick tunnel, set that URL to the **same** tunnel hostname so browser calls stay same-origin:

```env
NEXT_PUBLIC_API_URL=https://YOUR-TUNNEL.trycloudflare.com
```

The rewrite targets your backend on port 8000 only when `NEXT_PUBLIC_API_URL` points to `http://127.0.0.1:8000` at **build/dev server start**. For tunnel demos, use the helper script below.

### If chat fails through the tunnel

**Option A (recommended):** Point `NEXT_PUBLIC_API_URL` at localhost and rely on Next rewrites (default dev):

- Keep `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` in `web/.env.local`
- Tunnel only port **3000** — API goes through Next proxy.

**Option B:** Second tunnel to the API:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

Set `NEXT_PUBLIC_API_URL` to that URL and restart `run_web.ps1`.

## Step 3 — Update `.env` for public URL

```powershell
.\scripts\configure_tunnel_env.ps1 -TunnelUrl "https://YOUR-TUNNEL.trycloudflare.com"
```

Then **restart the backend** (`.\run_backend.ps1`) so `CORS_ORIGINS` and `PUBLIC_APP_URL` apply.

Manual edits in project root `.env`:

```env
PUBLIC_APP_URL=https://YOUR-TUNNEL.trycloudflare.com
CORS_ORIGINS=https://YOUR-TUNNEL.trycloudflare.com
```

For `web/.env.local` when using Option A (single tunnel on 3000):

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

## Step 4 — Share and test

1. Open the tunnel URL on your **phone using mobile data** (not the same Wi‑Fi).
2. Register → upload a PDF → index → ask a KB question.
3. Share the link (WhatsApp, email). **Google search** will not list a free tunnel URL; this is link-sharing only.

```powershell
.\scripts\verify_public_demo.ps1 -PublicUrl "https://YOUR-TUNNEL.trycloudflare.com"
```

## Keep the demo running

- Disable Windows sleep while demoing (Settings → Power).
- Keep terminals open: Ollama, backend, web, cloudflared.
- One or two concurrent users max on a 6GB GPU laptop.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Public page loads, chat fails | Use Option A (tunnel :3000 only) or Option B (second tunnel :8000) |
| CORS error | `CORS_ORIGINS` must match tunnel URL exactly (no trailing `/`) |
| LLM offline | `ollama serve`, `ollama list`, check `OLLAMA_MODEL` |
| Tunnel URL changed | Re-run `configure_tunnel_env.ps1` and restart backend |
| Invite links show localhost | Update `PUBLIC_APP_URL` and restart backend |

## When you have a budget

| Budget | Next step |
|--------|-----------|
| ~$10/year | Custom domain |
| ~$15/mo | Small VPS — see [DEPLOY.md](../DEPLOY.md) |
| ~$80+/mo | GPU VPS for 24/7 Ollama |

## Related docs

- [DEPLOY.md](../DEPLOY.md) — Docker + VPS production
- [RUNBOOK.md](../RUNBOOK.md) — KB and chat debugging
