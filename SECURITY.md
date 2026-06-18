# LegalEase Security Model

## Encryption layers

| Layer | What it protects | How to enable |
|-------|------------------|---------------|
| **In transit** | Browser ↔ nginx ↔ API | TLS 1.2+ via `deploy/nginx/nginx-ssl.conf`; set `FORCE_HTTPS=1` and `SAAS_PRODUCTION=1` |
| **At rest (passwords)** | User credentials | bcrypt hashes (always on) |
| **At rest (tokens)** | Email verify tokens | SHA-256 hashes (always on) |
| **At rest (optional fields)** | Sensitive DB text | `DATA_ENCRYPTION_KEY` (Fernet) — see `backend/app/core/crypto_vault.py` |
| **Auth sessions** | API access | JWT signed with `JWT_SECRET` / `LEGALEASE_API_SECRET` (min 32 chars in production) |

## End-to-end encryption (E2E) and AI

True **client-side E2E** (where only the user can decrypt data) is **not compatible** with server-side features in this product:

- Knowledge-base RAG and document indexing
- Matter-scoped AI chat and contradiction extraction
- Hearing prep packs and litigation desk scans

Those features require the server to read document content. LegalEase uses **SaaS-grade encryption in transit + at rest + tenant isolation + audit**, not messenger-style E2E.

For maximum confidentiality, host on your own VPC, enable Postgres TDE/disk encryption, and restrict network access with `FIREWALL_ALLOWED_IPS`.

## Application security controls

Enabled via environment variables (see `.env.example`):

- **Rate limiting** — `RATE_LIMIT_ENABLED`, per-IP and per-token buckets
- **Security headers** — HSTS (HTTPS), `X-Frame-Options`, CSP (optional `CONTENT_SECURITY_POLICY`)
- **IP firewall** — `FIREWALL_ENABLED=1` + `FIREWALL_ALLOWED_IPS=1.2.3.4,...`
- **Password policy** — length + complexity; stricter when `SAAS_PRODUCTION=1`
- **Production guards** — `SAAS_PRODUCTION=1` validates secrets, CORS, Stripe, Postgres
- **CORS** — `CORS_ORIGINS` allowlist only
- **Audit** — login success/failure via `audit_service`

Check posture: `GET /api/v1/health/security` (no secrets returned).

## Generate encryption key

```bash
py -c "from backend.app.core.crypto_vault import generate_encryption_key; print(generate_encryption_key())"
```

Add to `.env`:

```
DATA_ENCRYPTION_KEY=<paste key>
```

## Deploy checklist

1. Set `SAAS_PRODUCTION=1`, `SAAS_PRODUCTION_STRICT=1`, strong `JWT_SECRET`, `DATA_ENCRYPTION_KEY`
2. Use Postgres (`DATABASE_URL`) and `REDIS_URL` for multi-worker
3. Terminate TLS at nginx; mount `deploy/nginx/nginx-ssl.conf` + `nginx-security.conf`
4. Set `CORS_ORIGINS` to your HTTPS app URL only (`CORS_ALLOW_LOCALHOST_REGEX=0`)
5. Optional: `FIREWALL_ENABLED=1` + non-empty `FIREWALL_ALLOWED_IPS` for pilot IP lockdown
6. Never commit `.env` or API keys to git
7. Run `py scripts/verify_production_ready.py` before go-live

## Rotate all keys (go-live)

**Local secrets** (generated on your machine — invalidates existing JWT sessions):

```powershell
pwsh scripts/rotate_secrets.ps1
# merges into server .env from scripts/.env.rotation.generated
```

Rotates: `JWT_SECRET`, `LEGALEASE_API_SECRET`, `POSTGRES_PASSWORD`, `DATA_ENCRYPTION_KEY`, `INTERNAL_CRON_SECRET`.

**Provider dashboards** (revoke old keys after updating `.env`):

| Service | Variables | Where to rotate |
|---------|-----------|-----------------|
| Google AI | `GEMINI_API_KEY` | [Google AI Studio](https://aistudio.google.com/apikey) |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` | Stripe Dashboard → Developers |
| Email | `BREVO_API_KEY`, `SENDGRID_API_KEY`, `SMTP_PASSWORD` | Provider console |
| SSO | `OIDC_CLIENT_SECRET` | IdP app registration |
| Observability | `SENTRY_DSN`, `POSTHOG_API_KEY` | Project settings |

After rotation: restart API + web containers, confirm `/api/v1/health/security` shows no `production.errors`, and test login + billing webhook.

**PowerShell** (API must be running on port 8000):

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/v1/health/security | ConvertTo-Json -Depth 5
```

Template: `deploy/env.production.hardened.example`

## Network firewall (infrastructure)

Application middleware is not a substitute for cloud firewalls. In production also use:

- Security groups / NSG allowing only 443 (and 80 → redirect)
- WAF (Cloudflare, AWS WAF) in front of nginx
- Private subnets for API and database
