# LegalEase.AI — Technical Debt Register

| ID | Area | Risk | Mitigation | Owner |
|----|------|------|------------|-------|
| TD-01 | RAG retrieval failure | Wrong or empty KB answers | Confidence gates, `test_kb_trust_ci`, FAISS recovery | Eng |
| TD-02 | Vector index corruption | Stale or missing chunks | `faiss_recovery.py`, re-index jobs, health endpoints | Ops |
| TD-03 | Ollama downtime | Chat/drafting unavailable | `ollama_manager` auto-start, GPU profile docs, fallback messaging | Ops |
| TD-04 | Gemini / API cost overrun | Bill shock | Daily caps, usage meters, plan enforcement | Product |
| TD-05 | Split-brain DB | Auth in Postgres, data in SQLite | `check_legacy_db_split_brain` at startup, `SAAS_USE_POSTGRES_LEGACY=1` | Eng |
| TD-06 | Legacy chat path | Inconsistent modes | `resolve_chat_route()` unified routing | Eng |
| TD-07 | SCIM / live SSO | Enterprise blockers | OIDC with httpx; SCIM stub documented | Partnerships |
| TD-08 | eCourts live API | Manual cause lists | Paste parser + hearing date extraction | Partnerships |
| TD-09 | Portal e-sign | Non-binding client ack | DocuSign when `ESIGN_PROVIDER` configured | Product |
| TD-10 | Mobile native app | PWA-only today | `manifest.json` + service worker; native app external | Product |

Review quarterly or before each production deploy.
