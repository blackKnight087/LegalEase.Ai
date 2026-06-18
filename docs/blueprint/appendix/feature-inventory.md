# Feature Inventory and Code Mapping

This appendix catalogs major and small exposed features, mapped to implementation anchors.

## A) Platform Entry and Composition

- Backend API bootstrap: `backend/app/main.py`
- V1 router composition: `backend/app/api/v1/router.py`
- Frontend root shell: `web/app/layout.tsx`
- Frontend authenticated shell: `web/app/(app)/layout.tsx`
- Frontend chat page entry: `web/app/(app)/page.tsx`

## B) Chat and Session Features

- Chat submit + stream transport: `web/hooks/useChat.ts`, `web/lib/api.ts`
- Stream parser (`data:` events): `web/lib/api.ts`
- Regenerate/feedback bindings: `web/components/chat/ChatViewport.tsx`, `web/components/chat/MessageFeedback.tsx`
- Follow-up chips: `web/components/chat/SuggestionPills.tsx`
- Thread history and restore: `backend/app/api/v1/endpoints/sessions.py`, `backend/app/core/chat_persistence.py`
- Thread attachment upload/remove/read: `backend/app/api/v1/endpoints/sessions.py`, `backend/app/core/thread_attachments.py`
- Mode switch learning signal emission: `web/app/(app)/page.tsx`, `web/lib/api.ts`
- Chat export report: `backend/app/api/v1/endpoints/chat.py`, `web/lib/api.ts`

## C) KB, Upload, and Index Features

- Document upload endpoint: `backend/app/api/v1/endpoints/documents.py`
- OCR extraction routes: `backend/app/main.py`, `backend/app/api/v1/endpoints/documents.py`, `ocr_engine.py`
- Index job async runner: `backend/app/core/index_jobs.py`
- Reindex automation scheduler: `backend/app/core/reindex_scheduler.py`
- KB health snapshot endpoints: `backend/app/api/v1/endpoints/documents.py`, `backend/app/main.py`
- KB smoke tests: `backend/app/core/matter_intelligence.py`, `backend/app/api/v1/endpoints/documents.py`
- Per-scope FAISS pathing: `backend/app/core/matter_index.py`
- RAG pipeline and chunk batching: `rag.py`, `kb_pipeline.py`, `kb_preprocess.py`

Small features:
- job polling helper in frontend: `waitForIndexJob` in `web/lib/api.ts`
- fallback health contract object: `EMPTY_KB_HEALTH` in `web/lib/api.ts`
- index status transitions (`processing/ready/queued/failed`) in documents endpoint.

## D) Matter Workspace Features

- Matter CRUD + lifecycle endpoints: `backend/app/api/v1/endpoints/matters.py`
- Matter repository ops: `backend/app/core/matter_repo.py`
- Access context and role policy: `backend/app/core/matter_policy.py`
- Matter dashboard aggregation: `backend/app/core/matter_workflow.py`
- Matter dashboard UI: `web/components/matters/MatterDashboard.tsx`
- Matter settings form: `web/components/matters/MatterSettingsForm.tsx`
- Matter deletion/archive flows: `web/components/matters/MatterDeleteModal.tsx`, backend matters endpoint/repo
- Matter uploads and doc metadata flags: `web/components/matters/MatterDocumentUpload.tsx`, `backend/app/api/v1/endpoints/matters.py`
- Timeline suggestions + moderation: `web/components/matters/TimelineSuggestions.tsx`, matters endpoints
- Notifications polling: `web/hooks/useMatterNotifications.ts`

Small features:
- privileged document marker and `index_status` surface on dashboard.
- scoped “open in main chat” handoff in matter layout.
- contradiction panel and witness profile helpers in matter tabs.

## E) Auth, Security, and Platform Controls

- Auth endpoints (login/register/me): `backend/app/main.py`
- Bearer user dependency: `backend/app/core/auth.py`
- Token issuance/validation: `legacy_saas/auth_tokens.py`
- Membership source-of-truth: `legacy_saas/legalease_auth.py`
- Rate limits: `backend/app/middleware/rate_limit.py`
- Memory pressure guard headers: `backend/app/middleware/memory_guard.py`
- CORS config: `backend/app/core/config.py`

Small features:
- endpoint-specific promotion limit rule in rate-limit middleware.
- compatibility aliases for legacy `/api/*` routes in `backend/app/main.py`.

## F) Learning, Tuning, and Automation

- Learning endpoints: `backend/app/api/v1/endpoints/learning.py`
- Adaptive interaction/feedback stores: `backend/app/core/adaptive_learning.py`
- Learning signal handling: `backend/app/core/learning_signals.py`
- Learning engine status and memory: `backend/app/core/learning_engine.py`
- Neural train orchestration: `backend/app/core/neural_finetuning.py`
- LLM fine-tuning support: `backend/app/core/llm_finetuning.py`
- Coach directives/scheduler: `backend/app/core/gemini_ollama_coach.py`, `backend/app/core/coach_scheduler.py`
- Improvement automation pipeline: `backend/app/core/improvement_automation.py`

Small features:
- scope-keyed feedback separation (`global` vs `matter:<id>`).
- admin-only scope promotion endpoint with feature gate.
- run-now and status APIs for tuning pipeline observability.

## G) Speech Features

- Speech transcribe API surface: `backend/app/api/v1/endpoints/speech.py`
- Speech service implementation: `backend/app/services/speech_service.py`
- UI speech panel and recorder control: `web/components/speech/SpeechPanel.tsx`
- Voice-aware text input: `web/components/ui/VoiceTextarea.tsx`
- speech hook state machine: `web/hooks/useSpeechToText.ts`
- language code mapping: `web/lib/speechLang.ts`
- speech UI status derivation helper: `web/lib/speech/uiFlags.ts`

Small features:
- explicit browser fallback error class and handling path.
- mic device persistence and diagnostics logs.

## H) Business Domains (SaaS Modules)

- Billing: `backend/app/api/v1/endpoints/billing.py`, `web/app/(app)/billing/page.tsx`
- CRM/Intake: `backend/app/api/v1/endpoints/crm.py`, `web/app/(app)/intake/page.tsx`
- Trust ledger: `backend/app/api/v1/endpoints/trust.py`
- E-discovery: `backend/app/api/v1/endpoints/ediscovery.py`, `backend/app/core/job_queue.py`, `run_ediscovery_worker.ps1`
- Research log: `backend/app/api/v1/endpoints/research_log.py`
- Templates/clauses/drafting: corresponding endpoints and `web/app/(app)/drafting/page.tsx`
- Portal and e-sign: `backend/app/api/v1/endpoints/portal.py`, `backend/app/api/v1/endpoints/esign.py`
- Premium tools: `backend/app/api/v1/endpoints/premium.py`, `web/app/(app)/premium/page.tsx`

## I) Frontend UX Helpers and Utility Features

- API connection quality polling: `web/components/providers/ApiConnectionProvider.tsx`
- Chat cache persistence helpers: `web/lib/chatStorage.ts`
- Display label normalization: `web/lib/displayLabels.ts`
- Mode pills membership gating: `web/components/chat/ModePills.tsx`
- Engine and scope health strips: `web/components/chat/EngineStatusBar.tsx`, `web/components/chat/KbScopeHealth.tsx`

Small features:
- `localhost` to `127.0.0.1` normalization resilience in API layer.
- default retry/backoff logic shared by all client API calls.

## J) Observability, Runbooks, and Ops

- Structured event emitter: `backend/app/core/observability.py`
- Startup snapshot status: `backend/app/core/startup_state.py`
- Production runbooks:
  - `docs/runbooks/matter-kb-ops.md`
  - `docs/runbooks/production-dry-run-checklist.md`
  - `RUNBOOK.md`

## K) Test Mapping

- Matter hardening regressions: `tests/test_matter_hardening_regression.py`
- Matter lifecycle E2E: `tests/test_api_matter_e2e_flow.py`
- Matter policy feature flags: `tests/test_matter_policy_flags.py`
- Chat/session/API suites: `tests/test_api_*.py`, `tests/test_chat_*.py`
- KB/RAG suites: `tests/test_kb_*.py`, `tests/test_rag.py`
- Learning/tuning suites: `tests/test_learning_*.py`, `tests/test_neural_finetuning.py`
- SaaS phase suites: `tests/test_phase*_*.py`

