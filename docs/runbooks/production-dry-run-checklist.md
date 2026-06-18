# Production Dry Run Checklist

## 1) Backup And Restore Drill
- Take a full DB snapshot before deploy.
- Restore snapshot into staging and run smoke tests.
- Verify matter rows, documents, and adaptive learning tables restore cleanly.

## 2) Migration Replay
- Run migrations on staging snapshot.
- Confirm new columns/tables:
  - `matters.is_archived`, `matters.archived_at`
  - `adaptive_interactions.scope_key`
  - `adaptive_feedback.scope_key`
  - `adaptive_scope_promotions`
- Validate no migration step fails when optional tables are missing.

## 3) Matter Security Verification
- Owner can read/write/delete/restore own matter.
- Viewer/client can read but receives `403` on write routes.
- Cross-tenant matter access returns `404`.
- Chat with unauthorized `matter_id` returns `404` when strict scope is enabled.

## 4) Feature-Flag Rollout Plan
- `MATTER_STRICT_SCOPE_ENFORCEMENT=1` for canary tenants first.
- `MATTER_STRICT_ROLE_WRITE=1` for canary tenants first.
- `LEARNING_SCOPE_PROMOTION_ENABLED=1` only for admin-operated environments.
- Keep flags reversible; document current values per environment.

## 5) Observability Gates
- Confirm events are visible in logs:
  - `chat_scope_decision`
  - `matter_access_denied`
  - `index_status_transition`
  - `scope_promotion_completed`
- Alert thresholds:
  - `matter_access_denied` surge > baseline
  - `index_status_transition` to `failed` > 2% in 15 min

## 6) Rollback Rehearsal
- Disable strict flags if user-impacting auth regressions appear.
- Disable scope promotion endpoint (`LEARNING_SCOPE_PROMOTION_ENABLED=0`).
- Redeploy previous stable build.
- Re-run smoke tests for chat, uploads, and matter dashboard.

## 7) Final Go/No-Go
- All targeted hardening tests green.
- Canary tenant run has no critical errors for 24 hours.
- On-call handoff includes rollback owner and command steps.
