# Key rotation checklist (before public deploy)

Rotate in provider dashboards after updating `.env`. Local secrets: `py scripts/rotate_secrets.py` then `py scripts/apply_rotation_to_env.py`.

| Secret | Action |
|--------|--------|
| `GEMINI_API_KEY` | Google AI Studio → create new key → revoke old |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe Dashboard → roll keys → update webhook URL to `https://legalease.duckdns.org/api/...` |
| `SMTP_PASSWORD` | Gmail App Password → revoke old → update `.env` |
| `ECOURTSINDIA_API_KEY` | Provider console → revoke old |
| `TAVILY_API_KEY` | Tavily dashboard if exposed |
| `JWT_SECRET` / `POSTGRES_PASSWORD` | Use `scripts/rotate_secrets.py` (invalidates sessions) |

Then: `py scripts/verify_production_ready.py` and restart API.
