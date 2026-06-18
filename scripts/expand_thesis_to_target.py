"""Append structured expansion sections to the thesis markdown from codebase capabilities."""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THESIS = ROOT / "docs" / "LegalEase_SAAS_Thesis.md"

SECTIONS = """
## Platform expansion (auto-generated)

_Generated {ts} from Phase 1–6 implementation._

### Production guards and environment audit

- `scripts/audit_env.py` compares `.env` to `.env.example` with critical/warn severity.
- `backend/app/core/production_guards.py` blocks weak JWT, console email, non-Postgres `DATABASE_URL`, and missing `REDIS_URL` when `SAAS_PRODUCTION=1`.
- Runbook: `docs/GO_LIVE.md`.

### Feedback learning pipeline

- Thumbs-down and low-confidence answers enqueue to `feedback_learning_queue`.
- Superadmin review via `/api/v1/feedback-learning/queue`.
- Wired from `/api/v1/learning/feedback`.

### Unified chat routing

- `resolve_chat_route()` maps kb, open_law, hybrid, matter_only, research, drafting, discovery, crm.
- Prompt injection sanitization in `backend/app/core/ai_trust.py`.

### Matter intelligence

- Pipeline stages: entities, evidence, timeline, hearings, contradictions.
- Outputs include `risk_score` and `contradiction_report` JSON.

### Collaboration

- Presence heartbeats (`/api/v1/collaboration/presence`) with Redis or in-memory fallback.
- Read receipts via `last_read_at` on room members.
- Email notifications on new DMs (console provider OK in dev).

### Client portal and PWA

- Portal e-sign stub: `POST /api/v1/portal/sign/<token>`.
- PWA: `web/public/manifest.json`, `sw.js`, responsive meta in root layout.

### Enterprise preview

- OIDC token exchange via `httpx` when `SSO_DEV_MOCK=0`.
- SCIM 2.0 stub at `/api/v1/scim/v2/Users`.
- eCourts paste sync with hearing date parser; live API requires government credentials.
- Pilot onboarding: `scripts/onboard_pilot_firm.py`.

### Security CI

- `tests/test_tenant_attack_ci.py` — cross-tenant isolation scenarios (`ci_gate`).
- `docs/TECH_DEBT_REGISTER.md` — RAG, vectors, Ollama, costs, split-brain.

### External-only (not code-complete)

- Live Stripe keys and webhooks
- SOC 2 Type II certification
- Native iOS/Android apps
- Live eCourts government API credentials
"""


def main() -> int:
    if not THESIS.is_file():
        print(f"[FAIL] Thesis not found: {THESIS}")
        return 1
    marker = "## Platform expansion (auto-generated)"
    text = THESIS.read_text(encoding="utf-8")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    block = SECTIONS.format(ts=ts)
    if marker in text:
        head, _, _ = text.partition(marker)
        text = head.rstrip() + "\n\n" + block.strip() + "\n"
    else:
        text = text.rstrip() + "\n\n" + block.strip() + "\n"
    THESIS.write_text(text, encoding="utf-8")
    lines = len(text.splitlines())
    print(f"[OK] Updated {THESIS} ({lines} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
