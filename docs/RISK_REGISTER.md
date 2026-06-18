# LegalEase.AI — Technical Risk Register

| ID | Risk | Severity | Mitigation | Owner |
|----|------|----------|------------|-------|
| R1 | RAG low confidence / hallucination | High | Confidence gates, citation validation, NOT_FOUND path, feedback loop | AI |
| R2 | Postgres/SQLite split-brain | High | `SAAS_USE_POSTGRES_LEGACY=1`; startup warning in API | Platform |
| R3 | FAISS index corruption | Medium | Backup `faiss_indexes/`; re-index job | Platform |
| R4 | Ollama downtime | Medium | Health checks; graceful user messaging | AI |
| R5 | Gemini API cost explosion | Medium | Per-plan daily caps (`gemini_usage.py`) | Platform |
| R6 | Cross-tenant data leak | Critical | Tenant isolation tests in CI; org-scoped queries | Security |
| R7 | Legal liability on AI drafts | High | Disclaimers; human-in-loop; citation requirements | Product |
| R8 | Stripe misconfiguration in prod | Medium | `SAAS_PRODUCTION=1` validation; checklist | Ops |
| R9 | Legacy Streamlit (`app.py`) drift | Low | Production = Next.js + FastAPI; mark Streamlit legacy | Docs |
| R10 | ML worker queue backlog | Medium | Redis queue + worker scaling; job status UI | Platform |

**Review cadence:** Monthly during pilot; quarterly after GA.

**Last updated:** 2026-06-02
