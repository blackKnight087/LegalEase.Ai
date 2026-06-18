# Stable public link (no paid domain)

Share LegalEase with a **fixed URL** that does not change when you restart `cloudflared`. Your laptop must stay on (Ollama runs locally).

## Choose your path

| Option | Stable URL | Cost | Best for |
|--------|------------|------|----------|
| **A — Cloudflare named tunnel + FreeDNS** | `https://legalease-demo.mooo.com` | $0 | Share with clients, demos |
| **B — Tailscale Funnel** | `https://your-pc.tailxxxxx.ts.net` | $0 | You + team only |
| C — Quick tunnel (`trycloudflare.com`) | Changes every restart | $0 | Temporary tests only |

**Recommended: Option A**

---

## Option A — Stable link with Cloudflare + free subdomain

### What you get

```
https://legalease-demo.mooo.com  →  Cloudflare Tunnel  →  Next.js :3000  →  API :8000  →  Ollama
```

Same URL forever (until you delete the tunnel or subdomain).

### One-time setup (~15 minutes)

**1. Start LegalEase locally**

```powershell
ollama serve          # if not running
.\run_backend.ps1
.\run_web.ps1
.\scripts\verify_local_demo.ps1
```

**2. Run the setup wizard**

```powershell
.\scripts\setup_stable_cloudflare_tunnel.ps1
```

It will:

- Log in to Cloudflare (`cloudflared tunnel login`)
- Create tunnel `legalease-demo`
- Write `%USERPROFILE%\.cloudflared\config.yml`
- Update `.env` with your stable URL

**3. Free DNS (no domain purchase)**

1. Create account at [FreeDNS — afraid.org](https://freedns.afraid.org)
2. Add a subdomain, e.g. **`legalease-demo.mooo.com`**
3. Type: **CNAME**
4. Target: **`YOUR_TUNNEL_ID.cfargotunnel.com`** (printed by the setup script)

DNS may take 5–30 minutes to propagate.

**4. Start the named tunnel (every demo session)**

```powershell
cloudflared tunnel run legalease-demo
```

Keep this terminal open with backend, web, and Ollama.

**5. Test**

```powershell
.\scripts\verify_public_demo.ps1 -PublicUrl "https://legalease-demo.mooo.com"
```

Open that URL on your phone (mobile data) → register → chat.

---

## Option B — Tailscale Funnel (alternative, no DNS setup)

If Cloudflare DNS feels heavy, use Tailscale:

```powershell
winget install Tailscale.Tailscale
# Log in via Tailscale app, then:
tailscale funnel 3000
```

Copy the stable `https://....ts.net` URL, then:

```powershell
.\scripts\configure_tunnel_env.ps1 -TunnelUrl "https://YOUR-MACHINE.ts.net"
.\run_backend.ps1
.\run_web.ps1
```

---

## Daily demo checklist

| Terminal | Command |
|----------|---------|
| 1 | `ollama serve` |
| 2 | `.\run_backend.ps1` |
| 3 | `.\run_web.ps1` |
| 4 | `cloudflared tunnel run legalease-demo` **or** quick tunnel |

**Windows:** Settings → Power → **Never sleep** while demoing.

---

## `.env` must match your stable URL

After setup, root `.env` should have (same host, no trailing slash):

```env
PUBLIC_APP_URL=https://legalease-demo.mooo.com
CORS_ORIGINS=https://legalease-demo.mooo.com
```

`web/.env.local`:

```env
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_TUNNEL_HOST=legalease-demo.mooo.com
```

Restart backend + Next.js after any URL change.

---

## Security notes (public demo)

- Use strong `JWT_SECRET` (32+ random chars)
- Do not commit `.env` to GitHub
- Rotate `GEMINI_API_KEY` / `TAVILY_API_KEY` if exposed
- Limit to 1–2 concurrent users on a laptop GPU
- This is a **demo**, not production SaaS — see [DEPLOY.md](../DEPLOY.md) for VPS

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| URL changed again | You used quick tunnel; switch to **named** tunnel (`tunnel run legalease-demo`) |
| DNS not resolving | Wait 30 min; verify CNAME → `{id}.cfargotunnel.com` |
| CORS errors | `CORS_ORIGINS` must exactly match `PUBLIC_APP_URL` |
| CRM / chat fails on tunnel | Restart Next.js after `configure_tunnel_env.ps1`; use single tunnel on port 3000 |
| Invite links show localhost | Set `PUBLIC_APP_URL` and restart backend |

---

## When you can spend later

| Budget | Upgrade |
|--------|---------|
| ~$10/year | Buy `.com` domain → point to same Cloudflare tunnel |
| ~$15/mo | Small VPS (API only; Ollama still hard without GPU) |
| ~$80+/mo | GPU VPS for 24/7 Ollama |

Related: [DEPLOY_ZERO_BUDGET.md](./DEPLOY_ZERO_BUDGET.md) (quick tunnel), [DEPLOY.md](../DEPLOY.md) (Docker/VPS).
