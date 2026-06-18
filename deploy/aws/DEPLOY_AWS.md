# LegalEase on AWS EC2

## Live app (public)

**DuckDNS (after port 80 is open):** http://legalease.duckdns.org

**Cloudflare quick tunnel (works without port 80):** check `/tmp/cloudflared.log` on EC2 for `trycloudflare.com` URL.

```powershell
.\scripts\connect_duckdns_ec2.ps1
```

See [OPEN_PORT_80.md](./OPEN_PORT_80.md) if DuckDNS times out from your browser.

## Permanent URL on the EC2 IP

1. Open **inbound HTTP port 80** — see [OPEN_PORT_80.md](./OPEN_PORT_80.md).
2. On EC2: `bash deploy/aws/ec2-go-live.sh http://YOUR.PUBLIC.IP`

## Re-deploy from Windows (after code changes)

**Full update** (uploads entire project, rebuilds api + web):

```powershell
.\scripts\aws_update.ps1 -VmIp 18.61.68.82 -PublicUrl "https://legalease.duckdns.org"
```

**Hotfix only** (5 deploy files + go-live, no full codebase):

```powershell
.\scripts\aws_go_live.ps1 -VmIp 18.61.68.82 -PublicUrl "https://legalease.duckdns.org"
```

## What runs on AWS

| Service | Notes |
|---------|--------|
| api | Slim image, Gemini LLM, 1 worker |
| web | Next.js, `NEXT_PUBLIC_API_URL` baked at build |
| postgres / redis | Full SaaS data |
| nginx | Port 80 → api + web |
| worker / ml-worker | Off by default (`profiles: workers`) — enable if you scale RAM |

## Env

Copy `deploy/aws/.env.production.example` → `.env` on the server. Required: `GEMINI_API_KEY`, Postgres passwords, JWT secrets.

**Never upload your laptop `.env`** — `aws_update.ps1` excludes it. Server `.env` must use Docker hostnames (`postgres`, `redis`), not `localhost`. After deploy, add real `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` before setting `SAAS_PRODUCTION_STRICT=1`.

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| API unhealthy, `password authentication failed` | `bash deploy/aws/fix-postgres-password.sh` |
| API unhealthy, `STRIPE_SECRET_KEY` placeholder | Edit `/opt/legalease/.env` with live Stripe keys, or `SAAS_PRODUCTION_STRICT=0` temporarily |
| Web build fails on `premium/page.tsx` | Stale route on server — removed automatically by `aws_update.ps1` |
