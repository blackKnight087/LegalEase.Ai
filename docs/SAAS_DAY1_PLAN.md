# LegalEase → E2E SaaS · Day 1 Plan

**Timeline:** 10-day sprint to SaaS MVP (see [SAAS_10_DAY_SPRINT.md](./SAAS_10_DAY_SPRINT.md))  
**Date:** Day 1 of 10  
**Goal:** Fix the highest-risk flaws, document the sprint, establish foundations for Day 2 Stripe billing.

---

## Day 1 theme: **Secure the foundation**

> Do not add Stripe or org model until per-user ML isolation is fixed.  
> Otherwise every new feature sits on a broken multi-tenant base.

---

## Morning (Block 1) — Audit & lock the roadmap

| # | Task | Owner | Done? |
|---|------|-------|-------|
| 1.1 | Read this plan + confirm scope with team | You | ☑ |
| 1.2 | Create `docs/SAAS_ROADMAP.md` (8-phase master plan) | Agent | ☑ |
| 1.3 | Snapshot current `.env` — rotate Gemini key if repo was ever shared | You | ☐ |
| 1.4 | Verify backend + web running (`run_backend.ps1`, `run_web.ps1`) | You | ☐ |
| 1.5 | Baseline test run: `py -m pytest tests/ -q -m "not slow"` | Agent | ☑ |

**Success:** Tests pass (or failures documented). Roadmap file exists.

---

## Midday (Block 2) — P0 isolation fixes (critical)

These are **real bugs** if more than one user ever shares one server.

### Task 2.1 — Per-user Ollama model (not global)

**Problem:** `Data/ollama_exports/active_ollama_model.txt` is one file for all users.

**Files to change:**
- `backend/app/core/improvement_automation.py` — store active model per user
- `llms.py` — pass `user_id` into `get_generator()`

**Target behavior:**
```
Data/ollama_exports/{user_id}/active_model.txt   ← per user
get_generator(user_id=...) uses that user's tuned model or OLLAMA_MODEL fallback
```

| Step | Action | Done? |
|------|--------|-------|
| 2.1a | Change `get_active_tuned_model_name(user_id)` | ☑ |
| 2.1b | Change `_activate_tuned_model(user_id, model_name)` | ☑ |
| 2.1c | Thread `user_id` via request context → get_generator | ☑ |
| 2.1d | Test: two users, two different exports, no cross-over | ☑ |

---

### Task 2.2 — Per-user embedding scope (not global)

**Problem:** `maybe_auto_train()` uses `scope="global"` — all users share one embedding model.

**Files to change:**
- `backend/app/core/neural_finetuning.py` — default `scope="user"`
- `backend/app/api/v1/endpoints/learning.py` — train endpoint default scope
- `llms.py` — `get_embeddings(user_id=...)`

| Step | Action | Done? |
|------|--------|-------|
| 2.2a | Default `maybe_auto_train` to `scope="user"` | ☑ |
| 2.2b | Per-user `latest.txt` under `Data/fine_tuned_models/embeddings/{user_id}/` | ☑ |
| 2.2c | Pass `user_id` through embedding cache + request context | ☑ |
| 2.2d | Test: user A train does not change user B retrieval | ☑ |

---

### Task 2.3 — Add isolation regression tests

**New file:** `tests/test_tenant_isolation.py`

| Test | Asserts | Done? |
|------|---------|-------|
| `test_ollama_model_per_user` | User A and B get different active models | ☐ |
| `test_embedding_scope_per_user` | Global scope not default | ☐ |
| `test_improvement_pipeline_scoped` | Export paths stay under user_id | ☐ |

**Success:** All new isolation tests pass.

---

## Afternoon (Block 3) — Auth & config hardening

### Task 3.1 — JWT secret alignment (Docker prod bug)

**Problem:** Docker uses `JWT_SECRET` but code reads `LEGALEASE_API_SECRET`.

| Step | Action | Done? |
|------|--------|-------|
| 3.1a | Unify on one env var in `legacy_saas/auth_tokens.py` + `.env.docker.example` | ☑ |
| 3.1b | Document in `DEPLOY.md` | ☐ |
| 3.1c | Set strong secret in local `.env` (32+ chars) | ☐ |

---

### Task 3.2 — Server-side membership check (Hybrid gate)

**Problem:** Plan tier read from JWT only — stale for up to 7 days after upgrade/downgrade.

| Step | Action | Done? |
|------|--------|-------|
| 3.2a | Add `get_membership_from_db(user_id)` in auth layer | ☑ |
| 3.2b | Hybrid mode checks DB via `get_current_user` | ☑ |
| 3.2c | Test: Free tier blocked from Hybrid auto-upgrade | ☑ |

---

## Late afternoon (Block 4) — SaaS scaffolding (no Stripe yet)

### Task 4.1 — Create SaaS schema stubs (Day 2+ ready)

**New tables (SQLite/Postgres migration stub):**
```sql
organizations (id, name, plan, stripe_customer_id, created_at)
org_members (org_id, user_id, role)  -- owner | admin | member
subscriptions (org_id, stripe_sub_id, status, current_period_end)
audit_events (id, org_id, user_id, action, detail, created_at)
```

| Step | Action | Done? |
|------|--------|-------|
| 4.1a | Add schema to `backend/app/core/saas_schema.py` | ☐ |
| 4.1b | Migration script stub `scripts/migrate_saas_v1.py` | ☐ |
| 4.1c | No UI yet — schema only | ☐ |

---

### Task 4.2 — Admin route skeleton

| Step | Action | Done? |
|------|--------|-------|
| 4.2a | `GET /api/v1/admin/health` — superadmin only | ☐ |
| 4.2b | `users.role = 'superadmin'` check helper | ☐ |
| 4.2c | Placeholder `web/app/(app)/admin/page.tsx` (403 if not admin) | ☐ |

---

## End of Day 1 — Definition of done

| Criteria | Required |
|----------|----------|
| Per-user Ollama model routing works | ✅ Must |
| Per-user embedding scope default | ✅ Must |
| Isolation tests added and passing | ✅ Must |
| JWT secret unified | ✅ Must |
| Hybrid checks DB membership | ✅ Should |
| SaaS schema stubs created | ✅ Should |
| Full test suite green (or failures logged) | ✅ Must |
| `docs/SAAS_ROADMAP.md` 8-phase plan written | ✅ Must |

---

## What we are NOT doing on Day 1

| Deferred to | Item |
|-------------|------|
| **Day 2** | Stripe Checkout + webhooks |
| **Day 3** | Org model + invite flow |
| **Day 4–5** | Postgres migration |
| **Day 6** | ML job queue (Redis worker) |
| **Day 7** | Admin UI + audit |
| **Day 8** | Email + GDPR + onboarding |
| **Day 9–10** | CI/CD + monitoring + launch |

Full calendar: [SAAS_10_DAY_SPRINT.md](./SAAS_10_DAY_SPRINT.md)

---

## Day 1 schedule (suggested)

```
09:00 – 10:00   Block 1: Roadmap + baseline tests + env check
10:00 – 12:30   Block 2: Per-user Ollama + embedding isolation
12:30 – 13:30   Lunch
13:30 – 15:00   Block 2 cont: Isolation tests + fix regressions
15:00 – 16:30   Block 3: JWT secret + DB membership check
16:30 – 18:00   Block 4: SaaS schema stubs + admin skeleton
18:00 – 18:30   End-of-day: run full pytest, update SAAS_STATUS.md
```

---

## Commands reference

```powershell
# Start stack
cd "c:\Users\ASUS\Desktop\Legal_ai (1)\Legal_ai\Legal_AI_Final 3"
.\run_backend.ps1
.\run_web.ps1

# Run tests
py -m pytest tests/test_tenant_isolation.py tests/test_improvement_automation.py -q
py -m pytest tests/ -q -m "not slow"

# Regenerate blueprint after changes
.\.venv_win\Scripts\python.exe scripts/generate_legalease_blueprint.py
```

---

## 10-day sprint preview (full doc: SAAS_10_DAY_SPRINT.md)

| Day | Focus |
|-----|-------|
| **1** | Isolation + auth ← **TODAY** |
| **2** | Stripe billing |
| **3** | Organizations + RBAC |
| **4–5** | Postgres + Docker prod |
| **6** | ML job queue |
| **7** | Admin + audit |
| **8** | Email + GDPR + onboarding |
| **9** | CI/CD + E2E tests |
| **10** | Launch hardening |

---

## Risk register (Day 1)

| Risk | Mitigation |
|------|------------|
| `get_embeddings()` LRU cache hard to make per-user | Use keyed cache or model pool |
| Chat service doesn't pass user_id to llms today | Trace all get_generator() call sites |
| Breaking solo-user setup | Keep fallback when user_id empty |
| Tests slow on Windows | Run isolation tests first, full suite at EOD |

---

*Day 1 · LegalEase SaaS Transformation · Start here, ship isolation fixes before billing.*
