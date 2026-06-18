# LegalEase → E2E SaaS · 10-Day Sprint

**Timeline:** 10 days to launch-ready multi-tenant SaaS MVP  
**Strategy:** Fix isolation first, add billing + orgs, migrate DB, ship admin + compliance minimum, launch.

> **MVP definition (Day 10):** Firms can register, pay (Stripe), invite team members, upload docs, chat (KB/Open Law/Hybrid), with per-user ML isolation, Postgres, and basic admin — deployable via Docker.

---

## 10-day calendar at a glance

| Day | Focus | Ship by EOD |
|-----|-------|-------------|
| **1** | Isolation + auth hardening | Per-user Ollama + embeddings; JWT fix; tests |
| **2** | Stripe billing | Checkout, webhooks, plan enforcement from DB |
| **3** | Organizations + RBAC | Firms, invites, org-scoped data |
| **4** | Postgres migration (core) | users, chat, memory, learning off SQLite |
| **5** | Postgres migration (rest) + Docker prod | CRM, billing, discovery; secrets aligned |
| **6** | ML job queue | Neural/reindex/ollama create → Redis worker |
| **7** | Admin panel + audit logs | User mgmt, usage, audit trail |
| **8** | Email + onboarding + GDPR | Welcome/reset, wizard, account delete |
| **9** | CI/CD + monitoring + E2E tests | Deploy pipeline, Sentry, Playwright smoke |
| **10** | Launch hardening + docs | Load test, security pass, runbook, go-live |

---

## Day 1 — Secure the foundation

**Theme:** Fix cross-user ML leaks before anything else.

| Task | Files | Hours |
|------|-------|-------|
| Per-user Ollama model registry | `improvement_automation.py`, `llms.py`, `chat_service.py` | 3h |
| Per-user embedding scope (`user` not `global`) | `neural_finetuning.py`, `llms.py`, `learning.py` | 3h |
| Isolation regression tests | `tests/test_tenant_isolation.py` | 2h |
| JWT secret unification | `auth_tokens.py`, `.env.docker.example`, `DEPLOY.md` | 1h |
| DB membership check for Hybrid | `chat.py`, `legalease_auth.py` | 1h |

**Done when:** User A's train/export never affects User B. All tests green.

---

## Day 2 — Stripe subscriptions

**Theme:** Real money, real plans.

| Task | Deliverable |
|------|-------------|
| Stripe SDK + env (`STRIPE_*`, price IDs for Free/Pro/Legal Pro) | `requirements.txt`, `.env.example` |
| `subscriptions` table + webhook handler | `saas_schema.py`, `billing_stripe.py` |
| `POST /billing/subscribe` → Checkout Session | API endpoint |
| Webhooks: `checkout.completed`, `invoice.paid`, `subscription.deleted` | Plan updates in DB within seconds |
| Replace mock upgrade in Settings UI | Stripe Checkout button |
| Server-side plan gates (Hybrid, doc cap, Gemini quota) | Read from DB every request |
| Tests: webhook signature + downgrade blocks Hybrid | `tests/test_stripe_billing.py` |

**Done when:** Pay → Pro → Hybrid unlocks immediately without re-login.

---

## Day 3 — Organizations + RBAC

**Theme:** Sell to firms, not just individuals.

| Task | Deliverable |
|------|-------------|
| `organizations`, `org_members` tables | Schema + migration |
| Register creates org (user = owner) | Auth flow update |
| All repos filter by `org_id` | matters, documents, chat, memory |
| Invite link flow (email stub OK — full email Day 8) | `POST /orgs/invite`, accept token |
| Roles: owner / admin / member | Permission helpers |
| Team settings UI | `/settings/team` |
| Seat limits by plan | Enforced on invite |

**Done when:** Two users in Firm A share matters; Firm B cannot see Firm A data.

---

## Day 4 — Postgres migration (core tables)

**Theme:** Scale beyond one SQLite file.

| Task | Deliverable |
|------|-------------|
| Alembic setup | `alembic/` + first migration |
| Migrate: `users`, `sessions`, `chat`, `memory`, `learning` | Scripts + dual-write or cutover |
| Fix `gemini_usage.py` hardcoded DB path | Uses `DATABASE_URL` |
| API reads/writes Postgres for core paths | No SQLite for auth/chat |
| Docker: Postgres as sole DB for new installs | `docker-compose.yml` |

**Done when:** 2 API workers share same user session state.

---

## Day 5 — Postgres (rest) + Docker production

**Theme:** Full stack prod-ready.

| Task | Deliverable |
|------|-------------|
| Migrate: CRM, billing, discovery, premium, coach | Remaining SQLite tables |
| SQLite → Postgres import script | `scripts/migrate_sqlite_to_pg.py` |
| Docker: API healthcheck, resource limits, non-root user | `docker-compose.yml`, `Dockerfile.api` |
| Align all secrets (`LEGALEASE_API_SECRET`, Stripe, Gemini) | `.env.docker.example` |
| HTTPS nginx config documented + tested locally | `deploy/nginx/` |
| Ollama strategy documented (sidecar vs host) | `DEPLOY.md` |

**Done when:** `docker compose up -d --build` runs full SaaS stack on clean machine.

---

## Day 6 — ML job queue

**Theme:** Automation off the API hot path.

| Task | Deliverable |
|------|-------------|
| Job types: `neural_train`, `kb_reindex`, `ollama_create`, `coach_cycle` | `job_queue.py` |
| `scripts/ml_worker.py` | Like `ediscovery_worker.py` |
| Docker `ml-worker` service | `docker-compose.yml` |
| Replace daemon threads in `improvement_automation.py` | Enqueue only |
| Job status API + Settings UI progress | `/learning/automation/jobs` |
| Redis-backed dedup (not in-memory `_running_users`) | Cross-replica safe |

**Done when:** Thumbs-up → job queued → API returns instantly → worker completes pipeline.

---

## Day 7 — Admin panel + audit

**Theme:** Operate without DB access.

| Task | Deliverable |
|------|-------------|
| `audit_events` table + logger helper | All critical actions logged |
| `GET /admin/users`, suspend, plan override | Superadmin API |
| `GET /admin/audit`, `GET /admin/usage` | Dashboard data |
| `/admin` UI (superadmin only) | User list, usage, audit viewer |
| Log: login, upload, delete, export, plan change, payment | Compliance minimum |

**Done when:** Superadmin can suspend user and see why from audit log.

---

## Day 8 — Email + onboarding + GDPR

**Theme:** Conversion + compliance minimum.

| Task | Deliverable |
|------|-------------|
| SendGrid/SES integration | `email_service.py` |
| Templates: welcome, verify email, password reset, invite | HTML templates |
| Password reset flow (API + UI) | `/forgot-password` |
| 5-step onboarding wizard | upload → index → matter → plan → first chat |
| `DELETE /account` — purge user + FAISS + files | GDPR minimum |
| `GET /account/export` — ZIP all data | Portability |
| Privacy policy + ToS checkbox on register | Static pages |

**Done when:** New user completes wizard; delete account removes all traces.

---

## Day 9 — CI/CD + monitoring + E2E

**Theme:** Ship with confidence.

| Task | Deliverable |
|------|-------------|
| GitHub Actions: test + Docker build | `.github/workflows/deploy.yml` |
| Staging deploy workflow | Push to registry |
| Playwright E2E: register → upload → KB → upgrade | `tests/e2e/` |
| Sentry (frontend + backend) | Error tracking |
| Health + basic metrics endpoint | `/metrics` or Sentry breadcrumbs |
| Run isolation + Stripe + org tests in CI | Required pass |

**Done when:** Push to main → tests green → staging deploy succeeds.

---

## Day 10 — Launch hardening

**Theme:** Go live.

| Task | Deliverable |
|------|-------------|
| Security pass: secrets scan, dependency audit | No keys in repo |
| Load test: 20 concurrent chat users | p95 < 30s documented |
| Backup script + restore runbook | `scripts/backup.sh`, `RUNBOOK.md` |
| Update blueprint + SAAS_STATUS | Regenerate docs |
| Production env checklist | Stripe live keys, domain, TLS |
| Smoke test on staging | Full user journey |
| **Go / no-go decision** | Launch or 2-day buffer |

**Done when:** Production URL live, first paying customer can sign up end-to-end.

---

## What we cut (post-launch backlog)

| Deferred | Why |
|----------|-----|
| Full browser E2E suite (50+ tests) | Smoke only on Day 9 |
| Prometheus/Grafana dashboards | Sentry sufficient for MVP |
| DocuSign live (not mock) | Env stub OK |
| Advanced admin (impersonate, bulk ops) | Basic suspend/plan override enough |
| Multi-region / read replicas | Single region MVP |
| SOC2 audit prep | Post-revenue |
| Mobile app | Web responsive enough |

---

## Daily rhythm (every day)

```
09:00  Standup — yesterday / today / blockers (15 min)
09:15  Build block 1 (deep work)
12:30  Lunch
13:30  Build block 2
17:00  Tests + commit
17:30  Update checklist in this doc (mark Done)
18:00  End — note tomorrow's first task
```

---

## Risk buffer

If behind by Day 5:
- **Cut:** Full Postgres migration of premium/enterprise tables → stay SQLite for non-core
- **Keep:** Isolation, Stripe, orgs, admin

If behind by Day 8:
- **Cut:** Onboarding wizard polish → checklist in dashboard instead
- **Keep:** Email reset, account delete, Stripe

**Hard deadline:** Day 10 = launch MVP. Polish continues post-launch.

---

## Success metrics (Day 10)

| Metric | Target |
|--------|--------|
| Signup → paid Pro | < 5 minutes |
| Signup → first KB answer | < 15 minutes |
| Cross-tenant data leak | 0 (tested) |
| Stripe webhook success | > 99% |
| API uptime (staging 48h) | > 99% |
| Isolation tests | 100% pass |

---

## Related docs

- [SAAS_DAY1_PLAN.md](./SAAS_DAY1_PLAN.md) — Day 1 detailed checklist (start here today)
- [SAAS_ROADMAP.md](./SAAS_ROADMAP.md) — Original 20-day plan (reference)
- [LEGALEASE_COMPLETE_GUIDE.md](./LEGALEASE_COMPLETE_GUIDE.md) — Product features
- [exports/LEGALEASE_BLUEPRINT.docx](./exports/LEGALEASE_BLUEPRINT.docx) — Architecture

---

*10-Day Sprint · LegalEase E2E SaaS · Day 1 starts now*
