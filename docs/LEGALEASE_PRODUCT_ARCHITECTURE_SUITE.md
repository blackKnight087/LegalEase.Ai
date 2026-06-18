# Table of Contents

1. Executive Summary
2. Document 1 — Product Requirements Document (PRD)
3. Document 2 — System Architecture
4. Document 3 — Database Design
5. Document 4 — API Documentation
6. Document 5 — AI Architecture
7. Document 6 — Security Architecture
8. Document 7 — Deployment Architecture
9. Document 8 — Product Workflow Guide
10. Document 9 — Competitive Analysis
11. Document 10 — Technical Deep Dive
12. Product Roadmap & Appendix

---

# Executive Summary

LegalEase.AI is an AI-powered legal intelligence platform purpose-built for Indian law practice. It unifies document-grounded research (RAG), live statutory and case-law research (Open Law / Hybrid), matter-centric case management, drafting studio, CRM intake, billing, litigation operations, enterprise DMS, and an Evidence Intelligence Center (e-discovery) into a single SaaS product.

This documentation suite describes the complete product vision, technical architecture, data model, API surface (503+ HTTP routes), AI pipelines, security posture, deployment topology, user workflows, competitive positioning, and engineering rationale. It is intended for investors, enterprise buyers, technical interviewers, and engineering teams onboarding to the codebase.

**Production URL:** https://legalease.duckdns.org  
**Stack:** Next.js 15 + FastAPI + PostgreSQL/SQLite + FAISS + Redis + Docker + nginx  
**AI:** Ollama (local KB) + Gemini (web research) + adaptive learning feedback loops

---

# Document 1 — Product Requirements Document (PRD)

## 1.1 Vision & Problem Statement

Indian legal practice is fragmented across disconnected tools: generic chatbots without citations, DMS without AI, research platforms without matter context, and practice management without intelligence. Lawyers lose hours re-reading PDFs, manually mapping IPC to BNS, triaging evidence, and drafting repetitive pleadings.

LegalEase.AI solves this by anchoring every AI answer to **evidence** (uploaded documents, matter files, firm knowledge base) while providing **live research** when internal documents are insufficient. The platform learns from attorney feedback without requiring GPU fine-tuning on every interaction.

## 1.2 Target Users

| Persona | Needs | Primary Modules |
|---------|-------|-----------------|
| Solo / Small Firm Lawyer | KB chat, drafting, IPC-BNS, billing | AI Assistant, Drafting, Legal Tools, Billing |
| Litigation Associate | Hearings, cause lists, evidence, timelines | Matters, Litigation Desk, Evidence Intelligence |
| Firm Partner / Owner | Team, billing, analytics, enterprise DMS | Dashboard, Enterprise, Admin, Analytics |
| Paralegal / Intern | Intake, triage, document upload | Intake Desk, Documents, Discovery |
| Client (portal) | Status, uploads, approvals | Client Portal (token-based) |

## 1.3 Product Modules (Feature Inventory)

### Core Platform
- **AI Assistant** — Multi-mode chat: Knowledge Base, Open Law (web), Hybrid, Deep Case
- **Documents & KB** — PDF/image upload, OCR, chunking, FAISS indexing, reindex jobs
- **Matters** — Case workspace: documents, timeline, hearings, tasks, evidence, entities, contradictions
- **Memory** — Persona, facts, thread summaries, past-conversation RAG
- **Adaptive Learning** — Thumbs feedback, chunk boosts, query expansion, coach pipeline

### Practice Operations
- **Intake Desk (CRM)** — Lead pipeline, Kanban, AI classification, matter conversion
- **Billing** — Time entries, expenses, invoices, PDF export, Stripe subscriptions
- **Trust Ledger** — Client trust accounts and transactions
- **Litigation Desk** — Cause lists, court day, eCourts sync, war room, limitation calculator

### Content & Drafting
- **Drafting Studio v2/v3/v4** — Templates, versions, redline, copilot, court bundles, signatures
- **Clause Library** — Reusable clauses with feedback loop
- **Legal Tools** — IPC to BNS converter (official dataset), limitation presets

### Enterprise
- **Enterprise Workspace** — DMS folders, court orders, knowledge entries, client portal ops
- **Firm Chat** — Real-time collaboration, matter-linked rooms, SSE/WebSocket
- **Evidence Intelligence Center** — Upload PDF/DOCX/email/ZIP, OCR, classification, entity extraction, timeline, privilege detection, statute finder, contradiction detector

### Premium / Advanced
- Witness Simulator, Deal Rooms, BNS Auditor, PII Redactor, Judicial Analytics

## 1.4 User Journeys

### Journey A — New matter to grounded answer
1. Create matter (client, practice area, court)
2. Upload case PDFs to matter or global KB
3. Wait for indexing (ML worker / inline job)
4. Open AI Assistant, select matter scope
5. Ask legal question in Knowledge Base mode
6. Receive cited answer with source filename and section
7. Thumbs up/down trains retrieval for future queries

### Journey B — Evidence investigation
1. Open Evidence Intelligence Center (/discovery)
2. Link matter from dropdown
3. Drag-and-drop vendor emails, invoices, WhatsApp exports (ZIP)
4. System runs OCR, extracts entities and dates
5. Review Evidence Strength score, privilege flags, risk indicators
6. Inspect auto-built timeline across all matter evidence
7. Run contradiction check between two witness statements
8. Export findings to matter repository

### Journey C — Client intake to matter
1. Lead arrives via public intake form or manual entry
2. CRM AI classifies practice area and urgency
3. Paralegal moves lead through Kanban stages
4. Convert lead to matter with one click
5. Assign lawyer, seed folders, link documents

### Journey D — Drafting to filing
1. Create draft from template in Drafting Studio
2. AI autofill from matter variables
3. Clause intelligence and risk scan
4. Partner review workflow, track changes
5. Export PDF/DOCX court bundle
6. Optional e-sign request to client portal

## 1.5 Success Metrics (KPIs)

| Metric | Target | Measurement |
|--------|--------|-------------|
| KB answer citation rate | >85% substantive answers include source | learning analytics |
| NOT_FOUND precision | Low false negatives on indexed docs | smoke tests |
| Time to first indexed doc | <3 min for 50-page PDF | index job telemetry |
| Feedback adoption | >30% sessions with thumbs | adaptive_interactions |
| Matter conversion (CRM) | >25% qualified leads | crm_leads pipeline |
| Uptime (production) | 99.5% | health/live probes |
| Gemini daily quota compliance | Zero overage on Free tier | gemini_usage_daily |

## 1.6 Competitors (Summary)

See Document 9 for full comparison. LegalEase differentiates on Indian statute tooling (IPC-BNS), integrated matter+AI, Evidence Intelligence, and affordable SaaS pricing vs Harvey AI or Relativity.

## 1.7 Out of Scope (Current Phase)

- Native iOS/Android apps (responsive web first)
- Live eCourts API write-back (read/sync only)
- Full Relativity-scale distributed processing cluster
- E2E encrypted chat incompatible with server-side RAG

---

# Document 2 — System Architecture

## 2.1 High-Level Architecture

```text
                    +------------------+
                    |   User Browser   |
                    |  (Next.js 15 UI) |
                    +--------+---------+
                             |
                             | HTTPS
                             v
                    +------------------+
                    |  nginx (TLS)     |
                    |  Rate limit      |
                    +--------+---------+
                             |
              +--------------+--------------+
              |                             |
              v                             v
     +----------------+            +----------------+
     |  web:3000      |            |  api:8000      |
     |  Next.js SSR   |            |  FastAPI       |
     +----------------+            +--------+-------+
                                            |
                    +-----------------------+-----------------------+
                    |                       |                       |
                    v                       v                       v
           +----------------+     +----------------+     +----------------+
           | Service Layer  |     |  AI Layer      |     |  Data Layer    |
           | chat_service   |     | rag.py         |     | PostgreSQL     |
           | mode_router    |     | kb_pipeline    |     | SQLite (dev)   |
           | hybrid_orch    |     | web_intel      |     | FAISS indexes  |
           +----------------+     | ollama/gemini  |     | Redis          |
                                  +----------------+     +----------------+
```

## 2.2 Layer Responsibilities

| Layer | Location | Responsibility |
|-------|----------|----------------|
| Frontend | web/app/(app)/ | Routes, chat UI, matter workspace, settings |
| API Gateway | backend/app/main.py | Auth, middleware, CORS, health |
| Routers | backend/app/api/v1/endpoints/ | 38 endpoint modules, 503 routes |
| Services | backend/app/services/ | Chat orchestration, mode routing, open law |
| Core | backend/app/core/ | Domain logic, repos, schemas, learning |
| Legacy | legacy_saas/, rag.py, kb_pipeline.py | Auth, RAG engine, PDF extraction |

## 2.3 Product Architecture Diagram

```text
Users
  |
  v
Frontend (Next.js)
  |
  v
Backend (FastAPI)
  |
  +-- AI Layer (RAG, Open Law, Hybrid, Coach)
  +-- Legal Tools (IPC-BNS, Limitation, Court Fees)
  +-- Drafting Studio (v2/v3/v4 lifecycle)
  +-- Enterprise (DMS, Court Orders, Knowledge)
  +-- Litigation (Cause lists, War room, eCourts)
  +-- Evidence Intelligence (OCR, classification, timeline)
  +-- Analytics & Learning (feedback, tuning export)
```

## 2.4 AI Assistant Architecture

```text
User Query
    |
    v
Intent Detection (intent_engine.py, query_parser)
    |
    v
Mode Router (mode_router.py)
    |
    +-- knowledge_base --> kb_pipeline --> rag.py --> FAISS --> Ollama LLM
    |
    +-- open_law/web --> web_provider_chain --> Gemini grounded search
    |                                              --> Tavily/Serp fallback
    |                                              --> Ollama fallback
    |
    +-- hybrid/deep_case --> hybrid_orchestrator --> KB chunks + web fusion
    |
    v
Response + citations + follow-ups + interaction_id (learning)
```

**Key policy:** Gemini is blocked from synthesizing KB answers (kb_gemini_safety.py). KB mode uses Ollama + indexed PDFs only.

## 2.5 Drafting Studio Architecture

```text
Template / Smart Draft
    |
    v
Clause Engine (clause_library, drafting_v3 clause-intel)
    |
    v
AI Generate / Copilot (drafting_workspace, llm_orchestrator)
    |
    v
Risk Scanner + Document Health (drafting_v3 insights, filing-readiness)
    |
    v
Version Control (workspace_draft_versions)
    |
    v
Review Workflow (partner-review, track-changes, signatures)
    |
    v
Export (PDF/DOCX court bundle, drafting_docx_export)
```

## 2.6 Legal Tools (IPC-BNS) Architecture

```text
User Query / Document Upload
    |
    v
IPC-BNS Engine v3 (ipc_bns_engine_v3.py)
    |
    v
Official Verified Dataset (BNS mappings)
    |
    v
Search + Compare + Bulk Convert
    |
    v
Mapping Validation + Report Export (PDF/DOCX)
```

## 2.7 Evidence Intelligence Architecture

```text
Evidence Upload (PDF/DOCX/EML/ZIP/Image)
    |
    v
OCR + Text Extraction (evidence_extraction.py, pdf_extraction, ocr_engine)
    |
    v
Metadata Extraction (author, dates, SHA-256 hash)
    |
    v
AI Classification (FINANCIAL, CONTRACT, COMMUNICATION, COURT_ORDER, ...)
    |
    v
Entity Extraction (people, orgs, dates, phones, IFSC, case numbers)
    |
    v
Risk + Privilege Detection
    |
    v
Timeline Builder + Statute Finder (BNS/BNSS)
    |
    v
PostgreSQL discovery_items + Matter Linkage
```

## 2.8 Enterprise Workflow

```text
Client Portal (token URL)
    |
    v
Matter
    |
    v
DMS (ent_dms_folders, ent_dms_documents)
    |
    v
Court Orders (ent_court_orders + AI analysis)
    |
    v
Knowledge Base (ent_knowledge)
    |
    v
Analytics (dashboard, saas-metrics)
```

## 2.9 Background Workers

| Worker | Script | Queue |
|--------|--------|-------|
| E-Discovery | scripts/ediscovery_worker.py | Redis legalease:ediscovery:queue |
| ML Indexing | scripts/ml_worker.py | Redis ML queue |
| Coach scheduler | backend/app/core/coach_scheduler.py | Cron-style |

---

# Document 3 — Database Design

## 3.1 Storage Strategy

| Environment | Primary DB | Vector Store | Sessions |
|-------------|------------|--------------|----------|
| Laptop dev | SQLite (legalease.db) | FAISS local dirs | In-memory / SQLite |
| Production EC2 | PostgreSQL 16 | FAISS on Docker volume | Redis 7 |

**Flag:** SAAS_USE_POSTGRES_LEGACY=1 routes all legacy tables to PostgreSQL via connect_app_db().

## 3.2 Entity Relationship Overview

```text
User (users)
  |
  +-- Organization (organizations) -- org_members
  |
  +-- Matter (matters)
  |     |
  |     +-- Documents (documents, ent_dms_documents)
  |     +-- Hearings (matter_hearings)
  |     +-- Tasks (matter_tasks)
  |     +-- Evidence (matter_evidence, discovery_items)
  |     +-- Timeline (matter_timeline)
  |     +-- Entities (matter_entities)
  |     +-- Contradictions (matter_contradictions)
  |
  +-- Chat (chat_history, adaptive_interactions)
  +-- Drafts (workspace_drafts, workspace_draft_versions)
  +-- CRM (crm_leads + v2 extensions)
  +-- Billing (financial_records, invoices, trust_accounts)
```

## 3.3 Core Tables (pg_core_schema)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| users | Authentication | id, username, password_hash, membership, role |
| organizations | Multi-tenant firms | org_id, name, plan, seat_limit |
| org_members | Team roster | org_id, user_id, role |
| matters | Case header | matter_id, user_id, matter_name, practice_area |
| chat_history | Persisted turns | id, user_id, question, answer, thread_id, matter_id |
| adaptive_interactions | Learning log | id, user_id, mode, query, chunk_keys |
| adaptive_feedback | Thumbs/events | id, interaction_id, signal, value |
| kb_answer_memory | Cached KB successes | query_norm, answer, confidence |

## 3.4 Practice / Matter Tables (practice_schema)

| Table | Purpose |
|-------|---------|
| matter_notes | Internal case notes |
| matter_timeline | Chronological events |
| matter_hearings | Court dates, cause list imports |
| matter_tasks | Task management |
| matter_deadlines | Limitation and filing deadlines |
| matter_entities | Parties, witnesses |
| matter_evidence | Matter-scoped evidence records |
| matter_contradictions | Detected conflicts |
| matter_members | RBAC on matter |
| matter_audit_log | Immutable audit trail |
| workspace_drafts | Drafting documents |
| workspace_draft_versions | Version history |

## 3.5 SaaS / Operations Tables (saas_schema)

| Table | Purpose |
|-------|---------|
| financial_records | Time billing entries |
| invoices | Invoice lifecycle |
| crm_leads | Intake pipeline |
| ediscovery_batches | Evidence batch uploads |
| discovery_items | Analyzed evidence items (+ metadata_json, entities_json, timeline_json) |
| discovery_tag_weights | Learned tag weights per matter |
| research_queries | Research session logs |
| trust_accounts / trust_transactions | Client trust ledger |
| client_portal_access | Magic-link tokens |

## 3.6 Enterprise Tables (ent_*)

| Table | Purpose |
|-------|---------|
| ent_dms_folders | Folder hierarchy |
| ent_dms_documents | Document metadata + OCR text |
| ent_dms_versions | Version control |
| ent_court_orders | Ingested orders + AI summary |
| ent_knowledge | Firm knowledge entries |
| ent_client_requests | Portal document requests |
| ent_audit | Enterprise audit log |

## 3.7 Vector Index Layout

```text
faiss_indexes/
  user_{user_id}/
    global_kb/          # Statutes, firm-wide uploads
    matter_{matter_id}/ # Matter-scoped evidence only
```

Matter AI mode queries matter index exclusively (kb_retrieval_router.py).

## 3.8 Indexing & Constraints

- Foreign keys on SQLite; UNIQUE constraints on Postgres org_members, discovery_tag_weights
- Soft delete on matters (is_archived flag)
- CASCADE delete on discovery_items when batch removed
- JWT membership refreshed from DB on each request (not trusted from token alone for plan gating)

---

# Document 4 — API Documentation

## 4.1 Base URL & Authentication

| Environment | Base URL |
|-------------|----------|
| Production | https://legalease.duckdns.org/api/v1 |
| Local dev | http://127.0.0.1:8000/api/v1 |

**Authentication:** Bearer JWT from POST /api/v1/auth/login

```http
POST /api/v1/auth/login
Content-Type: application/json

{"username": "lawyer@firm.com", "password": "..."}

Response 200:
{"token": "<jwt>", "user_id": "...", "membership": "Pro"}
```

```http
GET /api/v1/auth/me
Authorization: Bearer <jwt>
```

**Error codes:** 401 Unauthorized, 403 Forbidden (plan/suspension), 404 Not found, 422 Validation, 429 Rate limit, 500 Server error

## 4.2 Chat API

```http
POST /api/v1/chat
Authorization: Bearer <token>
Content-Type: application/json

{
  "message": "Explain IPC Section 300",
  "mode": "knowledge_base",
  "lang": "English",
  "history": [],
  "matter_id": "optional-uuid",
  "thread_id": "optional-uuid"
}
```

**Response fields:** content, similar_cases, web_sources, follow_ups, session_id, chat_id, thread_id, interaction_id

```http
POST /api/v1/chat/stream
```
Server-Sent Events stream for token-by-token rendering.

## 4.3 Matters API (Selected)

| Method | Path | Purpose |
|--------|------|---------|
| GET | /matters | List matters |
| POST | /matters | Create matter |
| GET | /matters/{id} | Matter detail |
| PATCH | /matters/{id} | Update matter |
| GET | /matters/{id}/timeline | Timeline events |
| GET | /matters/{id}/evidence | Evidence list |
| POST | /matters/{id}/documents/upload | Upload to matter |
| GET | /matters/{id}/contradictions | Contradiction report |

## 4.4 Documents & KB API

| Method | Path | Purpose |
|--------|------|---------|
| POST | /documents/upload | Upload + index PDF |
| GET | /documents/kb/health | Index health |
| POST | /documents/kb/reindex-auto | Trigger reindex |
| GET | /documents/jobs/{job_id} | Index job status |

## 4.5 Evidence Intelligence API

| Method | Path | Purpose |
|--------|------|---------|
| POST | /ediscovery/evidence/upload | Multipart file upload |
| GET | /ediscovery/evidence/repository | Matter evidence list |
| GET | /ediscovery/evidence/timeline | Merged timeline |
| POST | /ediscovery/evidence/contradictions | Compare two texts |
| POST | /ediscovery/evidence/statutes | BNS/BNSS suggestions |
| POST | /ediscovery/evidence/court-orders | Similar orders search |

## 4.6 Drafting API (Selected)

| Method | Path | Purpose |
|--------|------|---------|
| GET | /drafting/workspace/documents | List drafts |
| POST | /drafting/workspace/documents | Create draft |
| PATCH | /drafting/workspace/documents/{id}/content | Save content |
| POST | /drafting/workspace/documents/{id}/export | Export PDF/DOCX |
| POST | /drafting/workspace/v4/court-package | Court bundle |

## 4.7 Learning / Feedback API

```http
POST /api/v1/learning/feedback
Authorization: Bearer <token>

{
  "signal": "thumbs_up",
  "interaction_id": "uuid-from-chat-response",
  "chat_id": "optional"
}
```

## 4.8 IPC-BNS Legal Tools API

| Method | Path | Purpose |
|--------|------|---------|
| GET | /ipc-bns/v3/search?q=cheating | Search mappings |
| GET | /ipc-bns/v3/compare/{ipc_section} | IPC vs BNS compare |
| POST | /ipc-bns/v3/bulk | Bulk conversion |
| POST | /ipc-bns/v3/document/upload | Upload + convert |

## 4.9 Enterprise Workspace API

| Method | Path | Purpose |
|--------|------|---------|
| GET | /enterprise/workspace/dashboard | Firm dashboard |
| POST | /enterprise/workspace/court-orders | Upload order |
| GET | /enterprise/workspace/court-orders/search | Search orders |
| POST | /enterprise/workspace/knowledge | Create KB entry |

## 4.10 Complete Route Count

The API exposes **503 HTTP routes + 1 WebSocket** across 38 endpoint modules. Full catalog maintained in backend/app/api/v1/router.py and generated from endpoint files at build time.

---

# Document 5 — AI Architecture

## 5.1 Design Principles

1. **Grounded over generative** — KB answers must cite indexed documents
2. **Mode isolation** — KB uses Ollama; web uses Gemini; never cross-contaminate
3. **Feedback-driven improvement** — Thumbs adjust retrieval weights, not model weights live
4. **Graceful degradation** — web_provider_chain falls through 6 providers to local Ollama
5. **Matter isolation** — Separate FAISS indexes prevent cross-case leakage

## 5.2 Knowledge Base RAG Pipeline

```text
Upload PDF
    |
    v
OCR Gate (150 chars/page threshold)
    |
    v
Text Extraction (PyMuPDF / pdfplumber / EasyOCR)
    |
    v
Chunking (RAG_CHUNK_SIZE, overlap)
    |
    v
Embeddings (HF sentence-transformers)
    |
    v
FAISS Index (per-user global or matter-scoped)
    |
    v
Query --> Hybrid Retrieve (dense + sparse + MMR)
    |
    v
Cross-encoder Rerank (optional)
    |
    v
kb_pipeline: Intent --> Filter --> Aggregate
    |
    v
Ollama LLM (legalease-tuned) --> Validated Answer
```

**Key files:** rag.py, kb_pipeline.py, kb_retrieval_coordinator.py, llms.py

## 5.3 Open Law Pipeline

```text
Question
    |
    v
Research Dimension Detection (web_intelligence.py)
    |
    v
Gemini Grounded Search (Google Search tool)
    |
    v (fallback)
Tavily / SerpAPI / DuckDuckGo
    |
    v (fallback)
OpenRouter / DeepSeek / Qwen
    |
    v (fallback)
Local Ollama legal_reason()
    |
    v
Formatted Answer + web_sources[]
```

## 5.4 Hybrid Mode

```text
Query
    |
    +-- KB Retrieve (top-k chunks from matter or global)
    |
    +-- Web Research (Gemini)
    |
    v
Fusion (hybrid_orchestrator.py)
    |
    v
Unified answer with KB citations + web sources
```

## 5.5 Adaptive Learning Loop

```text
Chat Turn --> record_interaction (adaptive_interactions)
    |
    v
User Thumbs Up/Down --> record_feedback
    |
    v
Update chunk boosts + query patterns (adaptive_chunk_boosts, adaptive_query_patterns)
    |
    v
Optional: Gemini-Ollama Coach (offline settings tuning)
    |
    v
Optional: Export JSONL for external LoRA fine-tuning
```

## 5.6 Evidence Intelligence AI

Rule-based + pattern classification (production-safe without GPU):
- Document category classification (regex + keyword rules)
- Entity extraction (emails, phones, IFSC, case numbers, dates, org names)
- Risk indicators (fraud, bribery, conspiracy patterns)
- Privilege markers (attorney-client, work-product)
- Statute mapping (BNS 316, 318, etc.)
- Contradiction detection (negation conflicts, date/amount mismatches)

Future: LLM enrichment layer for complex privilege review (roadmap).

## 5.7 LLM Backend Selection

| Environment | LLM_BACKEND | KB LLM | Web LLM |
|-------------|-------------|--------|---------|
| Laptop | ollama | Ollama GPU | Ollama or Gemini |
| EC2 Production | gemini | Ollama CPU fallback | Gemini primary |

---

# Document 6 — Security Architecture

## 6.1 Authentication

```text
Login --> bcrypt password verify (legalease_auth.py)
    |
    v
JWT signed with HMAC-SHA256 (JWT_SECRET / LEGALEASE_API_SECRET)
    |
    v
Token TTL: LEGALEASE_TOKEN_TTL (default 24h)
    |
    v
Each request: decode_access_token --> get_current_user
    |
    v
Live membership refresh from DB (plan changes immediate)
```

Optional: OIDC SSO via /api/v1/sso (sso_service.py)

## 6.2 Authorization Roles

| Role | Scope |
|------|-------|
| user | Standard attorney access |
| admin / superadmin | Admin panel, user suspension, metrics |
| org owner | Team invites, branding, billing |
| org lawyer | Matter write access |
| org member/viewer | Read-only matter access |
| client (portal) | Token-scoped read/upload only |

## 6.3 Data Protection

- Passwords: bcrypt (BYTEA on Postgres — fixed for EC2)
- Optional field encryption: DATA_ENCRYPTION_KEY (Fernet)
- HTTPS: nginx TLS termination, HSTS headers
- CORS: CORS_ORIGINS whitelist in production
- Rate limiting: RATE_LIMIT_PER_MINUTE, chat-specific limits
- IP firewall: FIREWALL_ENABLED optional allowlist
- PII redaction: document_services/pii_redactor.py
- Audit logs: audit_events, matter_audit_log, ent_audit

## 6.4 Multi-Tenant Isolation

- All queries scoped by user_id from JWT
- Matter access enforced by matter_policy.py
- FAISS indexes physically separated per user/matter
- Org seat limits enforced by plan_enforcement.py

## 6.5 Security Headers (Middleware Stack)

1. Memory guard
2. Rate limit
3. Request guard
4. IP firewall (optional)
5. Security headers (X-Frame-Options, CSP baseline)
6. CORS

Reference: SECURITY.md, /api/v1/health/security

---

# Document 7 — Deployment Architecture

## 7.1 Production Topology (EC2)

```text
Internet
    |
    v
DuckDNS (legalease.duckdns.org)
    |
    v
EC2 VPS (Ubuntu, ~8GB RAM)
    |
    v
Docker Compose
    |
    +-- nginx:443 (TLS, rate limit, 300s proxy timeout)
    +-- web:3000 (Next.js production build)
    +-- api:8000 (FastAPI, uvicorn workers=1 on low RAM)
    +-- postgres:16 (persistent volume)
    +-- redis:7 (sessions, queues)
    |
    +-- /data volume (FAISS indexes, uploaded files)
```

## 7.2 Laptop Development Topology

```text
run_backend.ps1 --> FastAPI :8000 (SQLite, Ollama GPU)
run_web.ps1     --> Next.js :3000 (.env.local -> 127.0.0.1:8000)
.env.local      --> SAAS_PRODUCTION=0, LLM_BACKEND=ollama
```

Laptop and EC2 run independently via .env.local (gitignored) vs production .env.

## 7.3 Deploy Commands

| Action | Command |
|--------|---------|
| Full EC2 deploy | scripts/aws_update.ps1 -PublicUrl "https://legalease.duckdns.org" |
| Local backend | run_backend.ps1 |
| Local frontend | run_web.ps1 |
| Docker local | docker compose up |

## 7.4 CI/CD

GitHub Actions (.github/workflows/ci.yml):
- Python pytest (~126 tests)
- Next.js production build
- Runs on push/PR

## 7.5 Backups & Monitoring

- Postgres: Docker volume backup (manual/script)
- Health probes: /api/v1/health/live, /health/ready, /health/llm
- Logs: Docker compose logs, structured logging in API
- Metrics: /api/v1/metrics (restricted access)

## 7.6 Environment Profiles

| Variable | Laptop | EC2 |
|----------|--------|-----|
| SAAS_PRODUCTION | 0 | 1 |
| DATABASE_URL | empty (SQLite) | postgresql://... |
| LLM_BACKEND | ollama | gemini |
| SAAS_USE_POSTGRES_LEGACY | 0 | 1 |
| OCR_ENABLED | 1 | 1 |

---

# Document 8 — Product Workflow Guide

## 8.1 Matter Lifecycle

```text
Create Matter
    |
    v
Assign Lawyer + Set Practice Area
    |
    v
Upload Documents (global KB or matter-scoped)
    |
    v
Index (FAISS) -- automatic or job queue
    |
    v
AI Research (KB / Hybrid / Open Law)
    |
    v
Draft Pleadings (Drafting Studio)
    |
    v
Track Hearings (Litigation Desk / cause list import)
    |
    v
Evidence Review (Evidence Intelligence Center)
    |
    v
Billing + Invoice
    |
    v
Close / Archive Matter
```

## 8.2 Client Portal Workflow

```text
Lawyer generates portal link (POST /portal/access)
    |
    v
Client opens magic URL (/portal/{token})
    |
    v
View matter status + timeline (read-only)
    |
    v
Upload requested documents (POST /portal/upload/{token})
    |
    v
Review / approve drafts (enterprise client portal)
    |
    v
Download court orders (when shared)
```

## 8.3 Evidence Investigation Workflow

```text
Select Matter
    |
    v
Upload evidence files (drag-and-drop)
    |
    v
Automatic: OCR + Metadata + Classification
    |
    v
Review Evidence Strength + Privilege flags
    |
    v
Inspect Entity cards + Timeline
    |
    v
Run Contradiction Check (2 documents)
    |
    v
Statute Finder (BNS sections)
    |
    v
Court Order Matcher (firm KB)
    |
    v
Evidence stored in Repository (linked to matter)
```

## 8.4 Frontend Routes Reference

| Route | Module |
|-------|--------|
| / | AI Assistant |
| /dashboard | Firm dashboard |
| /matters | Matter list |
| /matters/{id}/timeline | Case timeline |
| /matters/{id}/evidence | Matter evidence |
| /discovery | Evidence Intelligence Center |
| /drafting | Drafting Studio |
| /tools/ipc-bns | IPC-BNS converter |
| /intake | CRM Intake Desk |
| /billing | Billing |
| /litigation | Litigation Desk |
| /enterprise | Enterprise workspace |
| /collaboration | Firm Chat |
| /analytics | Analytics |
| /settings | Settings + Memory |

---

# Document 9 — Competitive Analysis

## 9.1 Market Landscape

| Competitor | Category | Strength | Gap vs LegalEase |
|------------|----------|----------|------------------|
| Harvey AI | AI legal assistant | Brand, LLM quality | No Indian IPC-BNS, no integrated DMS |
| Relativity | E-discovery | Enterprise scale | Expensive, not AI-native for Indian law |
| Everlaw | E-discovery | Review workflows | US-focused, no statute tools |
| Clio | Practice management | Market leader PM | Weak AI, no RAG |
| MyCase | PM + client portal | SMB friendly | No evidence intelligence |
| LexisNexis | Research | Authority content | Expensive, not matter-integrated AI |
| Westlaw | Research | Case law depth | Same as Lexis |
| DISCO | E-discovery | Cloud review | No Indian legal tools |
| Logikcull | E-discovery | Simple upload | No drafting/KB |

## 9.2 Feature Comparison Matrix

| Feature | LegalEase | Harvey | Relativity | Clio | LexisNexis |
|---------|-----------|--------|------------|------|------------|
| Document RAG / KB | Yes | Partial | No | No | No |
| Open Law web research | Yes | Yes | No | No | Yes |
| IPC to BNS converter | Yes | No | No | No | Partial |
| Evidence Intelligence | Yes | No | Yes | No | No |
| Drafting Studio | Yes | Yes | No | Basic | No |
| Matter workspace | Yes | Partial | Yes | Yes | No |
| CRM Intake | Yes | No | No | Yes | No |
| Billing + Trust | Yes | No | No | Yes | No |
| Indian cause lists | Yes | No | No | No | No |
| Adaptive learning | Yes | Unknown | No | No | No |
| Client portal | Yes | No | No | Yes | No |
| Price (SMB) | Low SaaS | Enterprise | Enterprise | Mid | High |

## 9.3 LegalEase Unique Value Proposition

1. **India-first** — BNS/BNSS, IPC migration, cause lists, eCourts integration path
2. **Unified stack** — One login for AI + matters + evidence + drafting + billing
3. **Evidence Intelligence Center** — Relativity-style investigation without enterprise pricing
4. **Self-improving KB** — Feedback loop without per-query GPU fine-tuning
5. **Deploy flexibility** — Laptop GPU for dev, cloud Gemini for production

---

# Document 10 — Technical Deep Dive

## 10.1 Why FastAPI?

- Native async for SSE chat streaming and concurrent uploads
- Pydantic validation on 503 endpoints
- Automatic OpenAPI docs for developer onboarding
- Python ecosystem access to PyMuPDF, FAISS, sentence-transformers, bcrypt
- Middleware stack for rate limiting and security headers

## 10.2 Why PostgreSQL (Production)?

- ACID transactions for billing, trust ledger, evidence chain-of-custody
- Concurrent writes from multiple API workers
- JSON columns for metadata_json, entities_json on discovery_items
- Mature backup/restore on EC2 Docker volumes
- SQLite retained for zero-config laptop development

## 10.3 Why RAG (Retrieval-Augmented Generation)?

- Legal answers require **citations** — pure LLM hallucinates sections
- Attorneys trust answers tied to **their** uploaded documents
- RAG allows NOT_FOUND when confidence below threshold (honest system)
- Chunk-level feedback enables targeted retrieval improvement

## 10.4 Why Vector Search (FAISS)?

- Semantic search finds relevant passages even when wording differs
- Hybrid dense+sparse+MMR reduces missed sections in long statutes
- Per-matter indexes enforce confidentiality boundaries
- CPU-FAISS sufficient for SMB firm document volumes

## 10.5 Why OCR?

- Indian courts and clients deliver scanned PDFs without text layer
- Evidence Intelligence requires text from images, WhatsApp screenshots
- 150 chars/page gate avoids unnecessary OCR on digital PDFs
- EasyOCR + Tesseract fallback chain in ocr_router.py

## 10.6 Why Role-Based Access?

- Law firms require partner/associate/paralegal separation
- Client portal must be read-only with token expiry
- Matter-level write access prevents junior staff editing senior cases
- Admin role for billing and user suspension

## 10.7 Why Audit Logs?

- Legal ethics require traceability on document access
- Enterprise sales require audit trail demonstrations
- matter_audit_log, ent_audit, collab audit support compliance story
- Feedback and learning signals auditable for model governance

## 10.8 Why Separate Laptop vs EC2 Config?

- Developers need GPU Ollama locally for fast KB iteration
- EC2 8GB RAM cannot run GPU Ollama at scale — Gemini for web
- .env.local gitignored prevents accidental production DB connection
- apply_local_env.ps1 enforces SAAS_PRODUCTION=0 on laptop

## 10.9 Testing & Quality

- ~126 pytest tests: KB, RAG, memory, auth, phase4 SaaS
- KB smoke tests via /documents/kb/smoke-test
- CI on GitHub Actions for every PR
- Health endpoints for production monitoring

## 10.10 Key File Reference

| Concern | Primary Files |
|---------|---------------|
| Chat | backend/app/services/chat_service.py |
| RAG | rag.py, kb_pipeline.py |
| Auth | legacy_saas/legalease_auth.py, backend/app/core/auth.py |
| Matters | backend/app/core/matter_repo.py |
| Evidence | backend/app/core/evidence_intelligence.py |
| Deploy | docker-compose.yml, scripts/aws_update.ps1 |
| Frontend | web/app/(app)/, web/lib/api.ts |

---

# Product Roadmap & Appendix

## Phase 1 (Complete) — Core Platform
KB chat, matters, documents, auth, billing foundation

## Phase 2 (Complete) — Practice Ops
CRM intake, billing invoices, trust ledger, collaboration

## Phase 3 (Complete) — Drafting & Tools
Drafting Studio v4, IPC-BNS engine, litigation desk

## Phase 4 (Complete) — Evidence & Research
Evidence Intelligence Center, adaptive learning, feedback loops

## Phase 5 (Complete) — Enterprise
DMS, court orders, knowledge base, client portal, analytics

## Phase 6 (Roadmap)
- Live eCourts API deep integration
- LLM-based privilege review in Evidence Intelligence
- Mobile PWA offline mode
- SOC2 Type II certification path (see docs/SOC2_READINESS.md)
- Multi-region deployment
- External LoRA fine-tuning pipeline from JSONL exports

## Appendix A — Glossary

| Term | Definition |
|------|------------|
| RAG | Retrieval-Augmented Generation |
| FAISS | Facebook AI Similarity Search (vector index) |
| BNS | Bharatiya Nyaya Sanhita (replaces IPC) |
| BNSS | Bharatiya Nagarik Suraksha Sanhita (replaces CrPC) |
| Open Law | Web-grounded legal research mode |
| Matter scope | AI limited to one case's documents |

## Appendix B — Related Documents

- docs/PRD.md — Original PRD user stories
- docs/blueprint/project-blueprint.md — Engineering blueprint
- REPORT.md — System status report
- DEPLOY.md — Deployment guide
- SECURITY.md — Security policy
- docs/SOC2_READINESS.md — Compliance roadmap

## Appendix C — Document Control

| Field | Value |
|-------|-------|
| Title | LegalEase Product Design & Technical Architecture Suite |
| Version | 1.0 |
| Author | LegalEase Engineering |
| Status | Approved for investor and client demonstrations |

---

# Appendix D — Expanded Module Specifications

## D.1 AI Assistant Module (Complete Specification)

### Purpose
The AI Assistant is the primary daily interface for attorneys. It supports four distinct reasoning modes, each with separate LLM backends, retrieval strategies, and output formats.

### Modes

| Mode | Alias | Backend | Retrieval | Output |
|------|-------|---------|-----------|--------|
| Knowledge Base | kb, knowledge_base | Ollama | FAISS user/matter index | Citations required |
| Open Law | web, web_search, open_law | Gemini + fallbacks | Live web search | web_sources[] |
| Hybrid | hybrid | Ollama + Gemini | FAISS + web | Merged citations |
| Deep Case | deep_case | Hybrid + extended | Extended retrieval | Long-form report |

### Request Lifecycle (Step by Step)

1. **Authentication** — JWT validated; suspended users rejected (403)
2. **Plan gating** — hybrid/deep_case require Pro or Legal Pro membership
3. **Matter scoping** — validate_chat_scope() ensures user owns matter
4. **Session resolution** — conversation_memory loads thread history
5. **Prompt sanitization** — ai_trust strips injection patterns
6. **Intent parsing** — query_parser extracts section numbers, act names
7. **Mode routing** — mode_router selects execution path
8. **Execution** — KB/web/hybrid pipeline runs
9. **Persistence** — chat_history + adaptive_interactions recorded
10. **Response** — JSON or SSE stream with interaction_id for feedback

### Streaming Protocol (SSE)

The frontend (useChat.ts) opens POST /api/v1/chat/stream and parses events:
- meta: thread_id, chat_id, interaction_id
- token: incremental text chunks
- done: final metadata

Timeout: 180 seconds aligned with nginx proxy_timeout.

### Follow-Up Suggestions

Generated from content analysis when answer is substantive. Examples: "Explain in simple language", "Summarize key points", "Show official sources".

### Similar Cases

Retrieved from KB chunk metadata when statute/case references detected in indexed documents.

---

## D.2 Matter Workspace Module

### Matter Data Model (Full Fields)

| Field | Type | Description |
|-------|------|-------------|
| matter_id | UUID | Primary key |
| user_id | TEXT | Owner |
| org_id | TEXT | Optional firm org |
| matter_name | TEXT | Display name |
| case_number | TEXT | Court case number |
| practice_area | TEXT | Criminal, Civil, Corporate, etc. |
| status_tier | TEXT | ACTIVE, CLOSED, ARCHIVED |
| client_name | TEXT | Client display name |
| opposing_party | TEXT | Opposing side |
| venue | TEXT | Court / jurisdiction |
| police_station | TEXT | FIR context |
| fir_number | TEXT | First Information Report |
| filing_date | TEXT | ISO date |
| next_hearing_date | TEXT | ISO date |
| priority | TEXT | High, Medium, Low |
| description | TEXT | Free text summary |

### Sub-Modules per Matter

Each matter exposes a workspace navigation (MatterWorkspaceNav.tsx):

1. **Overview** — Dashboard cards, recent activity
2. **Documents** — Linked uploads, matter-scoped indexing
3. **Timeline** — Manual + AI-generated events
4. **Hearings** — Cause list imports, voice entry
5. **Tasks** — Assignable to team members
6. **Evidence** — Matter evidence records
7. **Entities** — Parties, witnesses, organizations
8. **Contradictions** — AI-detected conflicts
9. **Knowledge** — Matter-scoped KB entries
10. **AI** — Matter-scoped chat shortcut
11. **Discussion** — Matter-linked Firm Chat room
12. **History** — Chat thread history filter
13. **Settings** — Matter members, archive

### Matter Intelligence Pipeline

POST /matters/{id}/intelligence/run triggers:
- Entity extraction across linked documents
- Timeline suggestion generation
- Contradiction scanning
- Status tracked in matter_intel_status table

---

## D.3 Drafting Studio Module (v2/v3/v4)

### Document Lifecycle States

```text
draft --> in_review --> partner_review --> approved --> filed --> archived
```

Transitions enforced by POST /drafting/workspace/documents/{id}/status and v4 transition endpoint.

### Version Control

Every content save creates workspace_draft_versions row:
- version_number (monotonic)
- content_html snapshot
- author user_id
- created_at timestamp
- Compare via /compare and /compare-v3 endpoints

### AI Copilot Commands (v3)

POST /drafting/workspace/documents/{id}/copilot accepts natural language commands:
- "Add limitation period paragraph"
- "Insert standard indemnity clause"
- "Convert to formal court format"

### Court Bundle (v4)

POST /workspace/v4/court-package assembles:
- Main pleading PDF
- Annexures with auto-index
- Cover page with matter metadata
- Table of contents insertion

### Filing Readiness Score

GET /workspace/documents/{id}/filing-readiness returns checklist:
- Required fields populated
- Signature blocks present
- Annexure references valid
- Court-specific formatting warnings

---

## D.4 Intake Desk (CRM) Module

### Pipeline Stages

Default stages: new_lead, contacted, qualified, proposal, converted, rejected, archived

Kanban board at /intake/board with drag-and-drop stage updates via PATCH /crm/{id}/stage.

### Lead Scoring

AI analysis (POST /crm/{id}/analyze) produces:
- lead_score (0-100)
- lead_score_band (hot/warm/cold)
- case_strength assessment
- practice_area classification
- suggested next actions

### Conversion to Matter

POST /crm/{id}/convert creates matter with pre-filled:
- client_name from lead
- practice_area from classification
- linked documents from crm_lead_documents
- initial timeline event "Lead converted"

### Public Intake

POST /practice/public-intake (optional X-Intake-Key header) captures website leads into crm_leads with org_id scoping.

---

## D.5 Billing Module

### Time Entry Flow

1. POST /billing/entries — log hours with matter_id, narrative, rate
2. AI narrative preview — POST /billing/narrative/preview polishes description
3. Entries appear in billing workspace
4. Select entries for invoice — GET /billing/invoices/prefill
5. POST /billing/invoices/draft — save draft
6. POST /billing/invoices/{id}/finalize — lock invoice
7. GET /billing/invoices/{id}/pdf — download PDF

### Trust Accounting

Separate from operating billing:
- GET /trust/account?matter_id= — trust balance
- POST /trust/transactions — deposit/disbursement with narrative
- Trust ledger complies with client fund separation principle

### Stripe Integration

- GET /subscriptions/plans — public plan list
- POST /subscriptions/subscribe — checkout session
- POST /billing/stripe/webhook — plan sync
- Plans: Free, Pro, Legal Pro with feature gates in plan_enforcement.py

---

## D.6 Litigation Desk Module

### Court Day Mission Control

GET /practice/court-day/mission-control aggregates:
- Today's hearings across all matters
- Cause list matches
- Prep pack links
- Limitation warnings

### Cause List Import

POST /practice/court-day/import parses pasted cause list text or uploaded file:
- Extracts case numbers, item numbers, bench, dates
- Matches to existing matters by case_number fuzzy match
- Creates matter_hearings records

### eCourts Integration

GET /practice/ecourts/search — search by CNR or party name
GET /practice/ecourts/case/{cnr} — case preview
POST /practice/ecourts/case/{cnr}/sync — sync to matter

### War Room

GET /practice/litigation/war-room/{matter_id} — consolidated view:
- Upcoming hearings
- Recent orders
- Open tasks
- Key evidence items
- AI litigation assist (POST /practice/litigation/ai)

---

## D.7 Enterprise Workspace Module

### DMS (Document Management)

Folder hierarchy: ent_dms_folders with parent_id tree
Documents: ent_dms_documents with OCR text, tags, matter_id link
Versions: ent_dms_versions for check-in/check-out pattern
Search: GET /enterprise/workspace/documents/search full-text

### Court Orders Repository

Upload: POST /enterprise/workspace/court-orders (multipart)
Fields: case_number, court, judge, order_date, summary, content_text
AI analysis: intelligence_json with extracted ratio, directions, next dates
Search: GET /enterprise/workspace/court-orders/search

### Knowledge Base

Entry types: precedent, template, memo, statute_note, court_order
Linked to matters and court orders
Powers Evidence Intelligence court-order matcher

### Client Portal Operations

POST /enterprise/workspace/client-portal/document-request — ask client for doc
POST /enterprise/workspace/client-portal/request-review — draft approval workflow
Tracked in ent_client_requests, ent_client_approvals

---

## D.8 Firm Chat (Collaboration) Module

### Room Types

- **Channel** — firm-wide or practice-area
- **DM** — direct message between two users
- **Matter room** — auto-linked to matter_id

### Real-Time Transport

- SSE: GET /collaboration/rooms/{id}/stream for message stream
- WebSocket: /collaboration/ws for typing, presence (access_token query param)
- Fallback polling if SSE unavailable

### Permissions (collab_rbac.py)

All authenticated org members can view/post by default.
DM requires accepted collab_chat_request.

### Message Attachments

POST /collaboration/rooms/{id}/messages/{id}/attachments
Stored with download via GET /collaboration/attachments/{id}/download

### AI Summarize

POST /collaboration/rooms/{id}/summarize — LLM summary of recent messages for catch-up

---

## D.9 Evidence Intelligence Center (Full Specification)

### Supported File Formats

PDF, DOCX, DOC, PNG, JPG, JPEG, WEBP, GIF, TIFF, XLSX, XLS, CSV, TXT, EML, MSG, ZIP

### Processing Pipeline (evidence_extraction.py + evidence_intelligence.py)

**Stage 1 — Extraction**
- PDF: PyMuPDF native + sparse OCR via pdf_extraction.py
- Images: EasyOCR via ocr_engine.py
- DOCX: python-docx paragraphs
- EML: email.parser headers + body
- MSG: extract_msg if installed, else fallback
- XLSX: openpyxl or XML fallback
- ZIP: recursive extraction (depth limit 2)

**Stage 2 — Metadata**
- SHA-256 hash (chain of custody)
- Author, created/modified dates
- File type, page count
- Extraction method tag

**Stage 3 — Classification Categories**
FINANCIAL, CONTRACT, COMMUNICATION, INVOICE, COURT_ORDER, MEDICAL, IDENTITY, EVIDENCE, GENERAL

**Stage 4 — Risk Detection**
FRAUD, BRIBERY, MONEY_TRAIL, CONSPIRACY, HARASSMENT, THREAT, CONTRACT_BREACH

**Stage 5 — Privilege Detection**
ATTORNEY_CLIENT, WORK_PRODUCT, CONFIDENTIAL markers

**Stage 6 — Entity Extraction**
People (Mr./Dr./Shri patterns), Organizations (Pvt Ltd, LLP), Locations (Indian cities), Emails, Phones, IFSC, Bank accounts, Case numbers (WP, CRL, etc.), Dates

**Stage 7 — Timeline**
Date regex extraction from sentences, sorted chronologically

**Stage 8 — Statute Mapping**
Pattern rules mapping content to BNS 316, 318, 336, 61, ICA s.73, BNSS bail provisions

**Stage 9 — Storage**
discovery_items extended columns: metadata_json, entities_json, timeline_json, statutes_json, privilege_json, risks_json, category, file_hash

**Stage 10 — Court Order Match**
search_court_orders() + search_knowledge() from enterprise_workspace

### Evidence Strength Score

Combines triage_document() relevance with risk boost:
- 80%+ = Highly Relevant
- 60-79% = Moderately Relevant
- 40-59% = Low Relevance
- Below 40% = Minimal Relevance

### Contradiction Detector Algorithm

Compares two documents for:
- Awareness conflicts (denial vs affirmation)
- Date conflicts across documents
- Amount conflicts (INR values)
- Witness statement conflicts (same person, different claims)

### API Endpoints (Complete)

| Method | Path | Body | Response |
|--------|------|------|----------|
| GET | /ediscovery/evidence/formats | — | {formats:[]} |
| POST | /ediscovery/evidence/upload | multipart file+matter_id | {analysis, batch_id, items} |
| POST | /ediscovery/evidence/analyze | {text, matter_id} | {analysis, court_orders} |
| GET | /ediscovery/evidence/repository | ?matter_id= | {items, timeline, count} |
| GET | /ediscovery/evidence/timeline | ?matter_id= | {timeline:[]} |
| POST | /ediscovery/evidence/contradictions | {document_a, document_b} | {contradictions, summary} |
| POST | /ediscovery/evidence/statutes | {text} | {statutes, count} |
| POST | /ediscovery/evidence/court-orders | {text, matter_id} | {results, count} |

---

## D.10 Adaptive Learning System

### Tables

- adaptive_interactions — every chat turn
- adaptive_feedback — explicit signals (thumbs, export, copy)
- adaptive_chunk_boosts — per-chunk score adjustments
- adaptive_query_patterns — successful query expansions
- adaptive_mode_stats — per-mode hit rates
- learning_signal_events — unified signal log
- human_labels — RLAIF training labels
- preference_pairs — DPO training pairs

### Signal Types

Positive: thumbs_up, helpful, verbal_positive, copy, export_docx, export_pdf, save_to_matter
Negative: thumbs_down, verbal_negative, regenerate

### Background Processing

FEEDBACK_FAST=1 — instant SQLite/Postgres write, heavy enrichment in daemon threads
FEEDBACK_SKIP_RLAIF=1 — skip Gemini RLAIF on fast path

Coach pipeline (gemini_ollama_coach.py) runs offline — never at inference time.

### Export for Fine-Tuning

POST /learning/tuning/export — JSONL pairs
POST /learning/training/export-sft — SFT dataset
POST /learning/training/export-dpo — DPO preference dataset

---

# Appendix E — Complete API Route Index by Module

## E.1 Authentication & Account (main.py + account.py)

POST /auth/login, POST /auth/register, GET /auth/me
POST /account/forgot-password, POST /account/reset-password/{token}
GET /account/export (GDPR ZIP), DELETE /account
GET /account/onboarding, POST /account/onboarding/dismiss
PATCH /account/preferences/learner-mode

## E.2 Health & Diagnostics

GET /health/live, /health/ready, /health/llm, /health/embeddings, /health/public
GET /health (user-scoped), GET /health/diagnostics, GET /health/security
GET /health/schema (superadmin), GET /metrics (metrics access)

## E.3 Chat & Sessions

POST /chat, POST /chat/stream, POST /chat/export-report
GET /sessions/history, DELETE /sessions/history
GET /sessions/threads/{id}, DELETE /sessions/threads/{id}
POST /sessions/threads/{id}/attachment

## E.4 Documents & KB

POST /documents/upload, GET /documents, DELETE /documents/{id}
POST /documents/kb/reindex-auto, GET /documents/kb/health
GET /documents/jobs/{id}, GET /kb/debug-query

## E.5 Matters (53 routes)

Full CRUD plus timeline, hearings, tasks, deadlines, evidence, entities, contradictions, intelligence pipeline, export, audit, members, hearing prep pack, client status letter, cause list import, voice hearing entry.

## E.6 Drafting (80+ routes across v2/v3/v4)

Workspace CRUD, versions, export, review, comments, AI generate/assist, autofill, insights, clause-intel, copilot, redline, precedents, court bundle, signatures, track changes, partner review, filing readiness.

## E.7 CRM (29 routes)

Dashboard, kanban, analytics, lead CRUD, stage updates, analyze, convert, documents, interactions, follow-up templates, intent correction.

## E.8 Billing & Subscriptions

Time entries, expenses, invoices, PDF, Stripe checkout, portal, plans, trust ledger.

## E.9 Collaboration (32 HTTP + WS)

Rooms, messages, reactions, attachments, DM requests, presence, typing, search, notifications, summarize.

## E.10 Enterprise (23 + 12 routes)

Branding, court sync, agents, pilot program, workspace dashboard, DMS, court orders, knowledge, client portal, audit, storage.

## E.11 Practice / Litigation (48 routes)

Court day, cause lists, eCourts, evidence desk, limitation, litigation dashboard, calendar, war room, watchlist, public intake.

## E.12 Learning (42 routes)

Feedback, signals, corrections, tuning export, neural training, coach, automation, quality gate, preferences, training pipelines.

## E.13 Ediscovery (18 routes)

Evidence upload/analyze/repository/timeline/contradictions/statutes/court-orders, batches, PII tools.

## E.14 IPC-BNS v3 (12 routes)

Search, compare, convert, bulk, document upload, report export, categories, matter migration.

## E.15 Speech

GET /speech/status, POST /speech/transcribe, POST /speech/polish

## E.16 Admin (superadmin)

Users list, suspend/unsuspend, plan override, audit, usage, health.

---

# Appendix F — Database Column Reference (Key Tables)

## F.1 users

id TEXT PK, username UNIQUE, password_hash BYTEA/TEXT, membership TEXT, role TEXT, email, display_name, suspended INTEGER, accepted_terms_at, created_at, last_login_at

## F.2 matters

matter_id TEXT PK, user_id TEXT, org_id TEXT, matter_name TEXT, case_number TEXT, practice_area TEXT, status_tier TEXT, client_name TEXT, opposing_party TEXT, venue TEXT, created_at TEXT, updated_at TEXT, plus criminal/civil extended fields (fir_number, police_station, next_hearing_date, priority, description, is_archived)

## F.3 documents

doc_id TEXT PK, user_id TEXT, title TEXT, filename TEXT, doc_type TEXT, matter_id TEXT, content_hash TEXT, indexed INTEGER, chunk_count INTEGER, created_at TEXT

## F.4 discovery_items (Evidence Intelligence)

item_id TEXT PK, batch_id TEXT FK, source_identifier TEXT, content_payload TEXT, assigned_tags TEXT, relevance_score REAL, classification TEXT, rationale TEXT, reviewed_status INTEGER, created_at TEXT, file_type TEXT, file_hash TEXT, metadata_json TEXT, entities_json TEXT, timeline_json TEXT, statutes_json TEXT, privilege_json TEXT, risks_json TEXT, category TEXT, extraction_method TEXT

## F.5 workspace_drafts

draft_id TEXT PK, user_id TEXT, matter_id TEXT, title TEXT, document_type TEXT, status TEXT, content_html TEXT, created_at TEXT, updated_at TEXT

## F.6 crm_leads

lead_id TEXT PK, user_id TEXT, org_id TEXT, client_name TEXT, email TEXT, phone TEXT, practice_area TEXT, pipeline_stage TEXT, lead_score INTEGER, analysis_json TEXT, matter_id TEXT (after conversion), created_at TEXT

## F.7 chat_history

id TEXT PK, user_id TEXT, question TEXT, answer TEXT, language TEXT, mode TEXT, thread_id TEXT, matter_id TEXT, created_at TEXT

## F.8 adaptive_interactions

id TEXT PK, user_id TEXT, mode TEXT, query TEXT, query_norm TEXT, answer_preview TEXT, found_in_kb INTEGER, chunk_keys TEXT, chat_id TEXT, thread_id TEXT, scope_key TEXT, created_at TEXT

---

# Appendix G — User Interface Map

## G.1 Navigation Structure (Sidebar)

| Label | Route | Learner Hidden |
|-------|-------|----------------|
| AI Assistant | / | No |
| Dashboard | /dashboard | No |
| Documents | /documents | No |
| Matters | /matters | No |
| Litigation | /litigation | Yes |
| Intake Desk | /intake | Yes |
| Firm Chat | /collaboration | Yes |
| Billing | /billing | Yes |
| Evidence | /discovery | Yes |
| Drafting | /drafting | Yes |
| Legal Tools | /tools | No |
| Enterprise | /enterprise | Yes |
| Analytics | /analytics | Yes |
| Settings | /settings | No |
| Admin | /admin | Yes (role gated) |

## G.2 Settings Sub-Pages

- Profile and preferences
- Memory management (MemoryPanel.tsx) — persona, facts, pruning
- Subscription (/settings/subscription) — Stripe plans
- Team (/settings/team) — org invites

## G.3 Design System

Reference: docs/DESIGN_SYSTEM.md
Primary brand: navy (#1e3a5f)
Typography: system fonts, monospace for legal citations
Components: PageHeader, VoiceTextarea, ThumbsFeedback, MatterWorkspaceNav

---

# Appendix H — Interview Preparation (System Design Q&A)

## H.1 "Walk me through what happens when a user asks a legal question"

The user submits a POST to /api/v1/chat with mode=knowledge_base. FastAPI validates JWT, checks plan, resolves matter scope. chat_service loads thread history from conversation_memory. mode_router confirms KB mode. kb_pipeline runs intent detection (section lookup vs comparison vs summary). kb_retrieval_coordinator retrieves top-k chunks from FAISS using hybrid dense+sparse+MMR. Chunks are reranked, filtered by confidence threshold. Ollama generates answer with citation instructions. Response validated for substantive content. Turn saved to chat_history and adaptive_interactions. interaction_id returned for thumbs feedback.

## H.2 "How do you prevent hallucination in legal answers?"

Four layers: (1) RAG grounding — LLM only sees retrieved chunks, (2) NOT_FOUND path when confidence below threshold, (3) kb_gemini_safety blocks cloud LLM from KB synthesis, (4) export quality gate and citation requirements in prompts.

## H.3 "How does multi-tenancy work?"

Every database query includes user_id from JWT. Matters, documents, FAISS indexes are namespaced by user_id. Org membership adds org_id scoping for firm features. Matter policy enforces write access by org role. No cross-user vector index access.

## H.4 "Why not fine-tune the LLM on every feedback click?"

Latency and cost. Real-time GPU fine-tuning is impractical for SaaS. Instead, chunk boosts and query expansions adjust retrieval immediately. Optional offline JSONL export enables batch LoRA training without affecting production inference.

## H.5 "How would you scale to 10,000 users?"

Horizontal API workers behind nginx load balancer, PostgreSQL read replicas, Redis cluster for sessions, dedicated ML worker pool for indexing, S3 for document storage, separate FAISS service or migrate to Pinecone/Weaviate, CDN for frontend static assets.

## H.6 "Explain the Evidence Intelligence vs Relativity difference"

Relativity processes terabytes with distributed OCR clusters. LegalEase targets SMB Indian firms with integrated matter+AI context. Our pipeline runs on single EC2 with rule-based+OCR classification, entity extraction, BNS statute mapping, and matter linkage — not just review tags but legal intelligence specific to Indian practice.

---

# Appendix I — Operational Runbooks (Summary)

## I.1 Production Deploy

1. Run scripts/aws_update.ps1 -PublicUrl "https://legalease.duckdns.org"
2. Wait for Docker rebuild (5-15 min)
3. Verify GET /api/v1/health/live
4. Hard refresh browser

## I.2 Laptop Setup

1. Copy .env.local.example to .env.local
2. Run scripts/setup_local_env.ps1
3. run_backend.ps1 + run_web.ps1
4. Open http://localhost:3000

## I.3 KB Reindex

POST /documents/kb/reindex-auto or trigger via Documents UI. Monitor GET /documents/jobs/{id}.

## I.4 Feedback Not Working (Postgres)

Ensure adaptive_mode_stats has not_found_count and threshold_delta columns. Ensure adaptive_interactions insert commits before stats bump. Check SAAS_USE_POSTGRES_LEGACY=1.

## I.5 OCR Failures

Verify OCR_ENABLED=1, EasyOCR installed, ffmpeg present in Docker image. Check GET /health/gpu for STT/OCR status.

Reference: docs/runbooks/production-dry-run-checklist.md, RUNBOOK.md, docs/SUPPORT_RUNBOOK.md

---

# Appendix J — Compliance & Risk

## J.1 SOC2 Readiness

See docs/SOC2_READINESS.md for control mapping:
- Access control (JWT, RBAC, admin suspension)
- Audit logging (matter_audit_log, ent_audit, audit_events)
- Encryption in transit (HTTPS/TLS)
- Data export (GDPR GET /account/export)
- Incident response (RUNBOOK.md)

## J.2 Risk Register Summary

See docs/RISK_REGISTER.md for:
- LLM hallucination risk — mitigated by RAG + NOT_FOUND
- Data breach — mitigated by tenant isolation + HTTPS
- Dependency on Gemini API — mitigated by provider chain fallbacks
- Single EC2 point of failure — mitigated by backup/runbook

## J.3 Data Retention

User-controlled via account deletion (DELETE /account).
Matters support archive (is_archived flag).
Chat history deletable per thread.

---

# Appendix K — Future Roadmap (Detailed)

## K.1 Q3 2026 — Enterprise Hardening
- SSO mandatory for enterprise tier
- SCIM user provisioning (stub exists at /scim/v2)
- Dedicated VPC deployment option
- Automated Postgres backups to S3

## K.2 Q4 2026 — AI Advancement
- LLM privilege review in Evidence Intelligence
- Multi-document cross-reference graph
- Voice-first mobile PWA
- Hindi/regional language STT and answers

## K.3 2027 — Platform Expansion
- API marketplace for third-party integrations
- White-label firm branding (partial — org branding exists)
- Court e-filing connector (where APIs available)
- External expert network marketplace

---

# Appendix L — Glossary (Extended)

| Term | Definition |
|------|------------|
| Cause list | Daily court schedule listing cases to be heard |
| CNR | Case Number Record (eCourts identifier) |
| FIR | First Information Report (criminal) |
| RAG | Retrieval-Augmented Generation — LLM + document search |
| FAISS | Vector similarity index library |
| SSE | Server-Sent Events for streaming |
| RLAIF | Reinforcement Learning from AI Feedback |
| DPO | Direct Preference Optimization (training method) |
| SFT | Supervised Fine-Tuning |
| DMS | Document Management System |
| BNSS | Bharatiya Nagarik Suraksha Sanhita |
| BNS | Bharatiya Nyaya Sanhita |
| IPC | Indian Penal Code (legacy) |
| CrPC | Code of Criminal Procedure (legacy) |
| JWT | JSON Web Token authentication |
| OCR | Optical Character Recognition |
| MMR | Maximal Marginal Relevance (diversity in retrieval) |
| KB | Knowledge Base mode in chat |
| Open Law | Web research mode using live search |
| Matter scope | Restricting AI to one case's documents |
| Evidence Strength | Relevance score 0-100% in Evidence Intelligence |
| Privilege review | Checking if document is attorney-client protected |
| War room | Litigation command center view for a matter |
| Pilot program | Enterprise onboarding program (superadmin managed) |

---

# Appendix M — Environment Variables Reference

## M.1 Core Application

| Variable | Default | Purpose |
|----------|---------|---------|
| DATABASE_URL | sqlite | PostgreSQL connection string |
| LEGALEASE_DB_PATH | legalease.db | SQLite file path |
| SAAS_USE_POSTGRES_LEGACY | auto | Route legacy tables to Postgres |
| SAAS_PRODUCTION | 0 | Production mode guards |
| LEGALEEASE_LOCAL_DEV | 1 | Laptop dev bypass |
| REDIS_URL | — | Session store + job queues |
| JWT_SECRET | — | JWT signing key (min 32 chars prod) |
| LEGALEASE_TOKEN_TTL | 86400 | Token lifetime seconds |
| CORS_ORIGINS | localhost | Allowed frontend origins |
| PUBLIC_APP_URL | — | Public frontend URL |
| NEXT_PUBLIC_API_URL | — | Frontend API base |

## M.2 LLM & AI

| Variable | Laptop | EC2 |
|----------|--------|-----|
| LLM_BACKEND | ollama | gemini |
| OLLAMA_BASE_URL | http://127.0.0.1:11434 | — |
| OLLAMA_MODEL | legalease-tuned | — |
| OLLAMA_AUTO_START | 1 | 0 |
| OLLAMA_NUM_GPU | -1 (all) | 0 |
| GEMINI_API_KEY | optional | required |
| GEMINI_FREE_MODEL | gemini-2.0-flash | same |
| CLOUD_GEMINI_KB | 0 | 1 |
| GEMINI_KB_SYNTHESIS | 0 | 0 |
| TAVILY_API_KEY | optional | optional |
| OPENROUTER_API_KEY | optional | optional |

## M.3 RAG & Retrieval

| Variable | Default | Purpose |
|----------|---------|---------|
| HF_EMBEDDING_MODEL | all-MiniLM-L6-v2 | Embedding model |
| RAG_CHUNK_SIZE | 800 | Chunk size chars |
| RAG_CHUNK_OVERLAP | 120 | Overlap chars |
| RAG_RETRIEVAL_K | 12 | Initial retrieval count |
| RAG_FINAL_TOP_K | 6 | Final chunks to LLM |
| RAG_SCORE_THRESHOLD | 0.35 | Min similarity score |
| RAG_ENABLE_CROSS_ENCODER | 0 | Reranker (slow on CPU) |
| KB_CACHE_TTL_SEC | 300 | Query cache TTL |
| OCR_ENABLED | 1 | Enable OCR pipeline |

## M.4 Security & Rate Limits

| Variable | Default | Purpose |
|----------|---------|---------|
| RATE_LIMIT_ENABLED | 1 | Global rate limit |
| RATE_LIMIT_PER_MINUTE | 120 | General API limit |
| RATE_LIMIT_CHAT_PER_MINUTE | 30 | Chat-specific limit |
| SECURITY_HEADERS_ENABLED | 1 | Security headers |
| FORCE_HTTPS | 0 | HSTS in dev |
| FIREWALL_ENABLED | 0 | IP allowlist |
| SUPERADMIN_USERNAMES | — | Admin allowlist |
| SAAS_ALL_FEATURES_FREE | 0 | Bypass plan gates (EC2 demo) |

## M.5 Billing & Email

| Variable | Purpose |
|----------|---------|
| STRIPE_SECRET_KEY | Stripe API |
| STRIPE_WEBHOOK_SECRET | Webhook verification |
| STRIPE_PRICE_PRO | Pro plan price ID |
| STRIPE_PRICE_LEGAL_PRO | Legal Pro price ID |
| ALLOW_MOCK_BILLING | Dev mock billing |
| BREVO_API_KEY | Transactional email |
| SMTP_HOST | Email fallback |

---

# Appendix N — Sample API Request/Response Library

## N.1 Register User

Request:
POST /api/v1/auth/register
{"username":"advocate1","password":"SecurePass123!","confirm_password":"SecurePass123!","accept_terms":true,"email":"advocate1@firm.com"}

Response 200:
{"ok":true,"user_id":"uuid","token":"eyJ..."}

## N.2 Create Matter

Request:
POST /api/v1/matters
{"matter_name":"State v. Sharma","practice_area":"Criminal","client_name":"Rajesh Sharma","venue":"Sessions Court Delhi"}

Response 200:
{"matter_id":"uuid","matter_name":"State v. Sharma",...}

## N.3 Upload Document

Request:
POST /api/v1/documents/upload (multipart)
file: contract.pdf
matter_id: uuid (optional)

Response 200:
{"doc_id":"uuid","indexed":true,"chunk_count":42,"job_id":"optional"}

## N.4 Knowledge Base Chat

Request:
POST /api/v1/chat
{"message":"What does Section 302 IPC say?","mode":"knowledge_base","lang":"English","history":[]}

Response 200:
{"content":"Section 302 IPC deals with...","similar_cases":[],"follow_ups":["Explain in simple language"],"interaction_id":"uuid","thread_id":"uuid"}

## N.5 Open Law Chat

Request:
POST /api/v1/chat
{"message":"Latest Supreme Court judgment on bail in economic offences","mode":"web_search","lang":"English"}

Response 200:
{"content":"...","web_sources":[{"title":"...","url":"..."}],"interaction_id":"uuid"}

## N.6 Thumbs Feedback

Request:
POST /api/v1/learning/feedback
{"signal":"thumbs_up","interaction_id":"uuid-from-chat"}

Response 200:
{"ok":true,"feedback_id":"uuid","queued":true}

## N.7 Evidence Upload

Request:
POST /api/v1/ediscovery/evidence/upload (multipart)
file: vendor_invoice.pdf
matter_id: uuid

Response 200:
{"batch_id":"uuid","analysis":{"evidence_strength":{"percent":92,"label":"Highly Relevant"},"entities":{"people":["Rajesh Sharma"],"dates":["17 Jan 2025"]},"privilege":{"privileged":false}},"items":[...]}

## N.8 IPC-BNS Search

Request:
GET /api/v1/ipc-bns/v3/search?q=cheating

Response 200:
{"results":[{"ipc_section":"420","bns_section":"318","offence":"Cheating"}]}

## N.9 CRM Create Lead

Request:
POST /api/v1/crm
{"client_name":"Priya Verma","phone":"9876543210","practice_area":"Family","referral_source":"Website"}

Response 200:
{"lead_id":"uuid","pipeline_stage":"new_lead"}

## N.10 Billing Time Entry

Request:
POST /api/v1/billing/entries
{"matter_id":"uuid","hours":2.5,"narrative":"Drafted bail application","rate":5000}

Response 200:
{"record_id":"uuid","amount_inr":12500}

## N.11 Drafting Create Document

Request:
POST /api/v1/drafting/workspace/documents
{"title":"Bail Application","document_type":"bail_application","matter_id":"uuid"}

Response 200:
{"draft_id":"uuid","status":"draft"}

## N.12 Enterprise Court Order Upload

Request:
POST /api/v1/enterprise/workspace/court-orders (multipart)
file: order.pdf
case_number: WP(C) 1234/2024
court: Delhi High Court

Response 200:
{"order_id":"uuid","summary":"Court directed..."}

## N.13 Collaboration Create Channel

Request:
POST /api/v1/collaboration/rooms/channel
{"name":"Criminal Team","description":"Criminal practice discussions"}

Response 200:
{"room_id":"uuid"}

## N.14 Portal Access Link

Request:
POST /api/v1/portal/access
{"matter_id":"uuid","client_email":"client@email.com","expires_days":30}

Response 200:
{"token":"secure-token","url":"https://app/portal/token"}

## N.15 Speech Transcription

Request:
POST /api/v1/speech/transcribe (multipart)
audio: recording.webm
language: English

Response 200:
{"text":"transcribed text","method":"whisper"}

---

# Appendix O — Test Coverage Summary

## O.1 Test Files (tests/)

Approximately 29 test files covering:
- test_phase4_saas_rigorous.py — E-discovery, CRM, billing
- test_saas_extensions.py — SaaS feature extensions
- KB retrieval and RAG golden tests
- Memory and user facts tests
- Auth and bcrypt Postgres tests
- IPC-BNS engine tests
- OCR and PDF extraction tests

## O.2 CI Pipeline

GitHub Actions on push/PR:
- Python pytest suite
- Next.js production build (npm run build)
- Validates TypeScript compilation

## O.3 Manual Smoke Tests

- POST /documents/kb/smoke-test — KB retrieval regression
- POST /matters/{id}/smoke — Matter pipeline smoke
- GET /health/ready — Embeddings + FAISS + LLM readiness

---

# Appendix P — Product Development History

## P.1 Phase A — Core KB & Chat (Complete)
Fixed chat persistence, refactored kb_pipeline, hybrid retrieval, sidebar saved chats, 126+ tests, CI pipeline.

## P.2 Phase B — Premium Suite (Complete)
Witness simulator, precedent tree, BNS auditor, deal rooms, redline engine, PII redactor.

## P.3 Phase C — Adaptive Learning (Complete)
Thumbs feedback, chunk boosts, query patterns, JSONL export, MessageFeedback UI.

## P.4 Phase D — Enterprise Persistence (Complete)
SQLAlchemy ORM, OCR router, analytics page, deal room SQL backing.

## P.5 Phase E — Memory & Hardening (Complete)
User profiles, facts, thread summaries, past-conversation RAG, prompt budgets, Memory Panel UI.

## P.6 Phase F — Frontend Security (Complete)
Next.js 15.5.18, React 19, zero npm audit vulnerabilities, security headers.

## P.7 Phase G — Deploy Infrastructure (Complete)
Docker Compose, Redis sessions, PostgreSQL path, nginx TLS, aws_update.ps1.

## P.8 Phase H — Practice Operations (Complete)
CRM intake v2, billing invoices, trust ledger, litigation desk, cause lists, eCourts.

## P.9 Phase I — Drafting Studio v4 (Complete)
Court bundles, signatures, track changes, partner review, filing readiness, precedents.

## P.10 Phase J — Evidence Intelligence Center (Complete)
Replaced text-box e-discovery with professional evidence workspace: OCR upload, classification, entities, timeline, privilege, statutes, contradictions, matter linkage. Deployed EC2 + laptop.

## P.11 Current Production State

URL: https://legalease.duckdns.org
Stack: Docker (api, web, nginx, postgres, redis) on EC2
Features: All modules free tier enabled (SAAS_ALL_FEATURES_FREE=1)
Feedback: Postgres adaptive_interactions fix deployed

---

# Appendix Q — Investor FAQ

**Q: What is the moat?**
India-specific statute tools + integrated matter-AI-evidence stack + adaptive learning from attorney feedback.

**Q: Who pays?**
Solo lawyers and SMB firms at Pro/Legal Pro SaaS pricing. Enterprise custom for DMS + SSO.

**Q: What is the TAM?**
600,000+ registered advocates in India, majority underserved by Harvey/Relativity pricing.

**Q: GPU costs?**
KB runs on local Ollama (laptop) or CPU; cloud uses Gemini API pay-per-query with daily caps.

**Q: Regulatory risk?**
Positioned as legal information/research tool, not legal advice. Disclaimers on all outputs.

**Q: Data privacy?**
Tenant isolation, HTTPS, GDPR export, optional field encryption, audit logs.

---

# Appendix R — Document Generation Instructions

To regenerate this PDF after editing the markdown source:

```powershell
cd "Legal_AI_Final 3"
py scripts/generate_architecture_pdf.py
```

Output: docs/LegalEase_Product_Architecture_Suite.pdf
Source: docs/LEGALEASE_PRODUCT_ARCHITECTURE_SUITE.md

To customize output path:
py scripts/generate_architecture_pdf.py --output "C:\path\to\LegalEase_Documentation.pdf"

---

# Appendix S — Screen-by-Screen Product Guide

## S.1 Login & Registration (/login)

The login page provides username/password authentication with links to registration and forgot-password flows. Registration requires accept_terms checkbox for compliance. On success, JWT stored in localStorage (legalease_token) and user redirected to /dashboard. Cinematic background optional from legacy Streamlit migration. Error states: invalid credentials (401), suspended account (403), network unreachable (connection banner from ApiConnectionProvider).

## S.2 Dashboard (/dashboard)

Central firm overview showing: active matters count, unbilled work amount, CRM pipeline stage distribution, Evidence Intelligence batch count, recent activity feed, quick links to all modules. PracticeModuleCards component renders stat cards with deep links. Mobile-responsive grid layout.

## S.3 AI Assistant (/)

Primary chat interface with: mode selector (Knowledge Base, Open Law, Hybrid, Deep Case), language selector (English, Hindi, etc.), matter scope dropdown, voice input via VoiceTextarea, streaming markdown rendering, source citations panel, similar cases chips, follow-up suggestion buttons, thumbs feedback (MessageFeedback component), thread history in sidebar, export report button. SSE streaming via useChat hook. Session restored from URL ?thread=uuid parameter.

## S.4 Documents (/documents)

Global document library: upload PDF/image, view indexing status, KB health indicator, reindex button, document list with filename/size/date, delete document, view extracted timeline and entities per document. Links to matter assignment. Shows chunk count after indexing completes.

## S.5 Matters List (/matters)

Table/cards of all matters with: matter name, client, practice area, status, next hearing date, priority badge. Create new matter button links to /matters/new. Filter and search. Archive indicator for closed matters.

## S.6 Matter Workspace (/matters/[id])

Tabbed navigation (MatterWorkspaceNav): Overview shows dashboard cards, recent documents, upcoming hearings, open tasks. Each sub-route loads matter-scoped data from /api/v1/matters/{id}/... endpoints.

## S.7 Matter Documents (/matters/[id]/documents)

Matter-scoped document list, upload to matter, link unlinked documents, reindex matter KB, document metadata edit. Matter FAISS index separate from global KB.

## S.8 Matter Timeline (/matters/[id]/timeline)

Chronological event list with manual add form. AI generate timeline button. Suggestion approval workflow for AI-proposed events. Export capability.

## S.9 Matter Hearings (/matters/[id]/hearings)

Hearing list with date, court, item number, bench. Import cause list. Voice entry for hearing details. Link to hearing prep pack PDF.

## S.10 Matter Tasks (/matters/[id]/tasks)

Task kanban or list with assignee, due date, status. Create from Firm Chat message action.

## S.11 Matter Evidence (/matters/[id]/evidence)

Matter evidence records distinct from Evidence Intelligence Center repository but linked. Add evidence, extract from documents.

## S.12 Matter Entities (/matters/[id]/entities)

Extracted and manual entities: parties, witnesses, organizations. Entity profiles with relationship map.

## S.13 Matter Contradictions (/matters/[id]/contradictions)

AI-detected contradictions across matter documents. Extract button runs analysis pipeline.

## S.14 Matter Knowledge (/matters/[id]/knowledge)

Matter-scoped knowledge entries linked to enterprise knowledge base.

## S.15 Matter AI (/matters/[id]/ai)

Shortcut to AI Assistant pre-scoped to matter_id.

## S.16 Matter Discussion (/matters/[id]/discussion)

Matter-linked Firm Chat room for team collaboration on case.

## S.17 Evidence Intelligence Center (/discovery)

Five tabs: Upload Evidence (drag-drop), Evidence Repository, Timeline, Contradiction Check, Statute & Orders. Matter dropdown links all evidence. Analysis panel shows strength score, entities, risks, privilege, statutes, metadata hash.

## S.18 Intake Desk (/intake)

Lead list with pipeline stage filters. Quick stats. Link to new lead, board view, analytics, public intake portal config.

## S.19 Intake Board (/intake/board)

Kanban columns per pipeline stage. Drag card to update stage via API.

## S.20 Intake Lead Detail (/intake/[leadId])

Lead profile, documents, interactions timeline, AI analysis panel, convert to matter button, follow-up templates, reject/archive actions.

## S.21 Billing (/billing)

Tabs: time entries, expenses, invoices, collections, matter financials. Log time form with AI narrative polish. Invoice builder with PDF preview. Trust account tab for client funds.

## S.22 Litigation Desk (/litigation)

Mission control for hearings, cause list import, calendar view, war room access, limitation deadlines, litigation AI assist, watchlist dashboard.

## S.23 Drafting List (/drafting)

All drafts with status badges, matter links, create new draft, filter by document type.

## S.24 Draft Editor (/drafting/[draftId])

Rich text/HTML editor, version history sidebar, AI copilot panel, clause intelligence, comments, track changes, export buttons, filing readiness score, collaboration presence indicators.

## S.25 Legal Tools Hub (/tools)

Cards linking to IPC-BNS converter, court fee calculator, contract review, case prediction, citation builder, ODR tools.

## S.26 IPC-BNS Tool (/tools/ipc-bns)

Search IPC/BNS sections, compare migration, bulk convert list, upload document for auto-conversion, export PDF/DOCX report.

## S.27 Enterprise (/enterprise)

Dashboard, global search, matters hub, DMS folders/documents, court orders repository, knowledge base, client portal ops, analytics, storage usage, audit log viewer.

## S.28 Firm Chat (/collaboration)

Room list (channels + DMs), message thread, attachments, reactions, typing indicators, user presence, AI summarize, create channel/DM, matter-linked rooms.

## S.29 Analytics (/analytics)

Learning stats, retrieval metrics, similar case clusters, judicial analytics from judgments table, tuning export triggers.

## S.30 Settings (/settings)

Profile edit, memory panel (persona, facts, prune), LLM test button, API connection status, learner mode toggle.

## S.31 Subscription (/settings/subscription)

Current plan, upgrade buttons (Stripe checkout), billing portal link, payment history.

## S.32 Team (/settings/team)

Org members list, invite form, pending invites, role management.

## S.33 Admin (/admin)

Superadmin: user search, suspend/unsuspend, plan override, system audit, usage metrics, health dashboard.

## S.34 Client Portal (/portal/[token])

Public-facing (no login): matter status, timeline, document upload area, e-sign stub, branded header from org branding.

## S.35 Onboarding (/onboarding)

First-run checklist: upload first document, create first matter, try AI chat, explore modules. Dismissible.

---

# Appendix T — Error Code Reference

| HTTP Code | Meaning | Common Causes |
|-----------|---------|---------------|
| 400 | Bad Request | Validation failure, missing matter_id, empty file |
| 401 | Unauthorized | Missing/expired JWT |
| 403 | Forbidden | Suspended account, plan gate, matter access denied |
| 404 | Not Found | Matter/document/batch not found |
| 422 | Unprocessable | Pydantic validation error |
| 429 | Too Many Requests | Rate limit exceeded |
| 500 | Server Error | Unhandled exception, DB error |
| 503 | Service Unavailable | LLM unavailable, not ready |

## Common Error Messages

- "Backend not reachable" — Frontend cannot connect to API (check NEXT_PUBLIC_API_URL)
- "interaction not found" — Feedback before interaction persisted (Postgres transaction fix applied)
- "Matter not found" — Invalid matter_id or wrong user scope
- "Plan required" — Hybrid/deep_case on Free tier
- "NOT_FOUND in knowledge base" — No relevant chunks above threshold (expected behavior)
- "Gemini daily limit reached" — GEMINI_DAILY_* quota exhausted

---

# Appendix U — Architecture Decision Records (ADR)

## ADR-001: Ollama for KB, Gemini for Web
Decision: Separate LLM backends by mode to prevent cloud hallucination in document-grounded answers.
Status: Accepted. Enforced by kb_gemini_safety.py.

## ADR-002: FAISS over Pinecone for v1
Decision: Local FAISS indexes for zero vendor dependency and laptop offline dev.
Status: Accepted. Migration to managed vector DB in roadmap.

## ADR-003: SQLite default, Postgres production
Decision: Zero-config laptop dev; Postgres when SAAS_USE_POSTGRES_LEGACY=1.
Status: Accepted. EC2 runs full Postgres.

## ADR-004: Feedback via retrieval tuning not live fine-tune
Decision: Chunk boosts and query patterns instead of GPU training per click.
Status: Accepted. JSONL export for optional batch training.

## ADR-005: Evidence Intelligence rule-based classification
Decision: Regex/pattern classification for predictable legal tags without GPU on EC2.
Status: Accepted. LLM enrichment planned for v2.

## ADR-006: JWT stateless auth with DB membership refresh
Decision: Stateless JWT for horizontal scaling; membership from DB not token for plan changes.
Status: Accepted.

## ADR-007: Next.js over Streamlit for production UI
Decision: Streamlit retained for legacy; Next.js 15 is primary product surface.
Status: Accepted.

---

*End of Documentation Suite*



