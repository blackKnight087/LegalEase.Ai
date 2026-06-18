# Matter KB Operations Runbook

## Scope Guardrails
- Normal KB traffic must have no `matter_id`.
- Matter KB traffic must use mode `knowledge_base`, `deep_case`, or `hybrid` with a valid `matter_id`.
- Any other mode strips matter scope at API entry.

## Upload/Index Lifecycle
- Expected status transitions: `saved` -> `processing` -> (`ready` | `queued` | `failed`).
- If status is `queued`, poll index job state and retry from matter dashboard.
- If status is `failed`, re-run upload or re-index with OCR enabled.

## Incident Checks
- Check `GET /api/v1/matters/health/indexing` for queue depth and active workers.
- Confirm matter dashboard loads under expected latency and no cross-scope retrieval.
- Verify normal KB answers with no `matter_id` are unaffected.

## Rollback
- Disable scope-enforcement feature at API edge by reverting chat request scope normalization.
- Disable archive-only delete path by using hard delete query `?hard=true`.
- Drain index queue and restart backend if jobs stall.
