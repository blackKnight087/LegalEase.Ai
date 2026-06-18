# Phase 6 — Enterprise & Moat (2027+)

LegalEase Phase 6 adds enterprise sales readiness, court integrations, AI agents, and pilot GTM.

## Implemented in codebase

| Module | API | Status |
|--------|-----|--------|
| SSO / OIDC | `GET /api/v1/sso/status`, `/login`, `POST /callback` | Dev mock + OIDC URL builder |
| Org branding | `GET/PATCH /api/v1/enterprise/orgs/{id}/branding` | White-label fields |
| eCourts adapter | `POST /api/v1/enterprise/court/sync` | Paste import live; API stub |
| AI agents | `GET /api/v1/enterprise/agents`, `POST .../run` | 4 agents via ML queue |
| Pilot program | `GET/POST /api/v1/enterprise/pilot/*` | Superadmin only |

## Environment variables

```env
# SSO (Enterprise login)
SSO_ENABLED=0
SSO_DEV_MOCK=0          # Pilot: provision user from email on callback
OIDC_ISSUER=
OIDC_CLIENT_ID=
OIDC_CLIENT_SECRET=
OIDC_REDIRECT_URI=
SAML_IDP_METADATA_URL=

# Court integrations
ECOURTS_API_ENABLED=0
ECOURTS_API_BASE=https://hcservices.ecourts.gov.in
```

## SSO pilot flow (dev)

1. Set `SSO_ENABLED=1` and `SSO_DEV_MOCK=1`
2. `POST /api/v1/sso/callback` with `{"email":"lawyer@firm.com","name":"Firm Name"}`
3. Receive JWT — same as password login

## AI agents

| Agent | Purpose |
|-------|---------|
| `drafting_agent` | Routes to Drafting Studio context |
| `discovery_agent` | E-discovery batch triage |
| `crm_agent` | CRM analytics + follow-up |
| `matter_agent` | Full matter intelligence pipeline |

Enqueue: `POST /api/v1/enterprise/agents/run` with `{"agent_type":"matter_agent","payload":{"matter_id":"..."}}`

## Pilot launch checklist

1. Register firms: `POST /api/v1/enterprise/pilot/firms` (superadmin)
2. Target: 5 active pilots on Pro/Legal Pro
3. Weekly: KB accuracy review + feedback export
4. Document case studies for [INVESTOR_BRIEF.md](INVESTOR_BRIEF.md)

## Still external / partnership required

- SAML IdP federation (Azure AD, Okta)
- SCIM user provisioning
- Live eCourts API credentials
- SOC2 Type II certification
- Dedicated VPC / Helm charts for institutional hosting

See [SOC2_READINESS.md](SOC2_READINESS.md) and [RISK_REGISTER.md](RISK_REGISTER.md).
