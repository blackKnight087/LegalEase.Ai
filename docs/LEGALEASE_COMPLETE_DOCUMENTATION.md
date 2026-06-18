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

# Document 7 — Deployment Architecture (Complete Guide)

This section is the authoritative deployment reference for LegalEase.AI. Every command, URL, script, and environment profile below uses the actual project configuration. Follow it end-to-end without adding external notes.

## 7.1 Production Summary

| Item | Value |
|------|-------|
| Public URL | https://legalease.duckdns.org |
| API base | https://legalease.duckdns.org/api |
| Health check | https://legalease.duckdns.org/api/v1/health/live |
| EC2 public IP | 18.61.68.82 |
| EC2 SSH user | ubuntu |
| Server install path | /opt/legalease |
| SSH key (Windows) | %USERPROFILE%\.ssh\legalease-aws.pem |
| Stack | Docker Compose: nginx + web + api + postgres + redis |
| LLM (production) | Gemini (CLOUD_GEMINI_KB=1, LLM_BACKEND=gemini) |
| Database (production) | PostgreSQL 16 in Docker |
| Sessions | Redis 7 |
| TLS | DuckDNS + optional Let's Encrypt certs in deploy/nginx/ssl/ |

## 7.2 Architecture Diagram (Production)

```text
Internet (HTTPS)
    |
    v
legalease.duckdns.org  (DuckDNS A record -> 18.61.68.82)
    |
    v
EC2 Ubuntu (m7i-flex.large class, ~8 GB RAM)
    |
    v
Docker Compose (LEGALEASE_COMPOSE_FILES from apply-ec2-tier.sh)
    |
    +-- nginx:80/443
    |       proxy /api/* -> api:8000
    |       proxy /*     -> web:3000
    |       TLS when deploy/nginx/ssl/cert.pem present
    |
    +-- web:3000 (Next.js production build)
    |       NEXT_PUBLIC_API_URL=https://legalease.duckdns.org/api (baked at build time)
    |
    +-- api:8000 (FastAPI, UVICORN_WORKERS=1 on low RAM)
    |       Gemini for Open Law / Hybrid web leg
    |       FAISS indexes on /data/faiss_indexes volume
    |
    +-- postgres:5432 (volume postgres_data)
    +-- redis:6379 (volume redis_data, appendonly)
    |
    +-- worker / ml-worker (profile: workers — OFF by default on 8GB)
```

## 7.3 Laptop Development — Step-by-Step Setup

### Prerequisites (Windows laptop)

1. Install Python 3.10+ and Node.js 18+
2. Install Ollama from https://ollama.com and run `ollama pull legalease-tuned` (or your tuned model)
3. Install ffmpeg: `winget install Gyan.FFmpeg`
4. Optional GPU: NVIDIA drivers + CUDA for Ollama GPU and faster embeddings
5. Clone or open project folder: `Legal_AI_Final 3`

### One-time laptop configuration

```powershell
cd "C:\Users\ASUS\Desktop\Legal_ai (1)\Legal_ai\Legal_AI_Final 3"

# API keys (Gemini, Tavily) go in .env — copy from .env.example if missing
# Laptop-only overrides:
.\scripts\setup_local_env.ps1
# Creates .env.local from .env.local.example with:
#   LEGALEEASE_LOCAL_DEV=1
#   SAAS_PRODUCTION=0
#   SAAS_USE_POSTGRES_LEGACY=0  (SQLite)
#   LLM_BACKEND=ollama
#   NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
#   CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

Edit `.env` for Ollama settings (already in `.env.example`):

```env
LLM_BACKEND=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=legalease-tuned
CLOUD_GEMINI_KB=0
GEMINI_API_KEY=your-key-for-open-law-only
```

Create Python venv (first time only):

```powershell
py -m venv .venv_win
.\.venv_win\Scripts\pip install -r backend\requirements.txt
cd web; npm install; cd ..
```

### Start laptop stack (every session)

Terminal 1 — Backend:

```powershell
.\run_backend.ps1
```

Terminal 2 — Frontend:

```powershell
.\run_web.ps1
```

Open browser: http://localhost:3000  
Health: http://127.0.0.1:8000/api/v1/health/live  
API docs: http://127.0.0.1:8000/docs

### What run_backend.ps1 does automatically

- Calls `scripts\apply_local_env.ps1` to merge `.env.local` overrides
- Sets `LEGALEASE_DB_PATH` to project `legalease.db` (SQLite)
- Sets `SAAS_PRODUCTION=0`, skips blocking RAG warmup for fast boot
- Auto-starts Ollama on GPU when `OLLAMA_AUTO_START=1`
- Runs uvicorn on 127.0.0.1:8000 with 300s keep-alive

### Laptop vs EC2 separation (critical)

| File | Used on | Must NOT contain |
|------|---------|------------------|
| .env | Both (API keys) | SAAS_PRODUCTION=1 on laptop |
| .env.local | Laptop only (gitignored) | postgres/redis Docker hostnames |
| /opt/legalease/.env | EC2 only | localhost database URLs |

`aws_update.ps1` explicitly excludes `.env` and `.env.local` from upload. Server `.env` is never overwritten by deploy.

## 7.4 EC2 — Initial Server Setup (First Time)

### 7.4.1 AWS resources

1. Launch Ubuntu 22.04+ EC2 instance (recommended: m7i-flex.large, 8 GB RAM)
2. Security group inbound rules:
   - SSH 22 from your IP
   - HTTP 80 from 0.0.0.0/0 (required for DuckDNS)
   - HTTPS 443 from 0.0.0.0/0 (when TLS certs mounted)
3. Elastic IP optional; current production IP: 18.61.68.82
4. DuckDNS: point `legalease.duckdns.org` A record to 18.61.68.82

See `deploy/aws/OPEN_PORT_80.md` if DuckDNS times out (port 80 blocked).

### 7.4.2 SSH access from Windows

```powershell
ssh -i $env:USERPROFILE\.ssh\legalease-aws.pem ubuntu@18.61.68.82
```

### 7.4.3 Install Docker on EC2 (if fresh server)

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo usermod -aG docker ubuntu
# Log out and back in
```

### 7.4.4 First deploy from Windows

From project root on your laptop:

```powershell
.\scripts\aws_update.ps1 -VmIp 18.61.68.82 -PublicUrl "https://legalease.duckdns.org"
```

This script:
1. Creates `legalease-deploy.tgz` (excludes Data, node_modules, .next, venv, .env)
2. SCP upload to `/opt/legalease/legalease-deploy.tgz`
3. SSH runs remote script that:
   - Extracts tarball to `/opt/legalease`
   - Runs `deploy/aws/fix-ec2-env.sh 'https://legalease.duckdns.org'`
   - Runs `deploy/aws/fix-postgres-password.sh`
   - Runs `deploy/aws/ec2-go-live.sh 'https://legalease.duckdns.org'`
4. Rebuilds api + web Docker images with correct `NEXT_PUBLIC_API_URL`
5. Starts nginx, api, web, postgres, redis

Expected duration: 5–15 minutes.

### 7.4.5 Create production .env on server (first time only)

SSH to EC2 and create `/opt/legalease/.env` from template:

```bash
cd /opt/legalease
cp deploy/aws/.env.production.example .env
nano .env
```

Required values to set (generate secrets with `pwsh scripts/rotate_secrets.ps1` on laptop):

```env
POSTGRES_PASSWORD=<strong-random-password>
JWT_SECRET=<32+-char-random>
LEGALEASE_API_SECRET=<32+-char-random>
DATA_ENCRYPTION_KEY=<32+-char-random>
GEMINI_API_KEY=<your-google-ai-key>
PUBLIC_APP_URL=https://legalease.duckdns.org
CORS_ORIGINS=https://legalease.duckdns.org
NEXT_PUBLIC_API_URL=https://legalease.duckdns.org/api
DATABASE_URL=postgresql://legalease:<POSTGRES_PASSWORD>@postgres:5432/legalease
REDIS_URL=redis://redis:6379/0
SAAS_USE_POSTGRES_LEGACY=1
SAAS_PRODUCTION=1
LLM_BACKEND=gemini
CLOUD_GEMINI_KB=1
```

Stripe (before SAAS_PRODUCTION_STRICT=1):

```env
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO=price_...
STRIPE_PRICE_LEGAL_PRO=price_...
```

Then re-run go-live:

```bash
bash deploy/aws/ec2-go-live.sh https://legalease.duckdns.org
```

## 7.5 EC2 — Re-Deploy After Code Changes

### Full update (recommended)

```powershell
cd "C:\Users\ASUS\Desktop\Legal_ai (1)\Legal_ai\Legal_AI_Final 3"
.\scripts\aws_update.ps1 -VmIp 18.61.68.82 -PublicUrl "https://legalease.duckdns.org"
```

### Hotfix only (5 deploy files, no full tarball)

```powershell
.\scripts\aws_go_live.ps1 -VmIp 18.61.68.82 -PublicUrl "https://legalease.duckdns.org"
```

### Post-deploy verification checklist

1. `curl https://legalease.duckdns.org/api/v1/health/live` returns 200
2. `curl https://legalease.duckdns.org/api/v1/health/public` shows `core_db.backend: postgresql`
3. Open https://legalease.duckdns.org in browser — hard refresh (Ctrl+Shift+R)
4. Login as admin user
5. Test chat (KB mode) and thumbs feedback
6. Test Evidence Intelligence upload on /discovery

## 7.6 Docker Compose Services Reference

| Service | Image/Build | Ports | Memory limit (EC2 low) | Role |
|---------|-------------|-------|------------------------|------|
| postgres | postgres:16-alpine | 5432 internal | default | All SaaS tables when SAAS_USE_POSTGRES_LEGACY=1 |
| redis | redis:7-alpine | 6379 internal | default | Chat sessions, ML job queues |
| api | deploy/Dockerfile.api.aws | 8000 internal | 4G | FastAPI REST + SSE |
| web | deploy/Dockerfile.web | 3000 internal | 1536M | Next.js UI |
| nginx | nginx:alpine | 80, 443 | default | Reverse proxy |
| worker | same as api | — | profile workers | E-discovery job processor |
| ml-worker | same as api | — | profile workers | ML tuning / reindex jobs |

Compose file stack (from `deploy/aws/apply-ec2-tier.sh`):

```bash
-f docker-compose.yml
-f deploy/aws/docker-compose.override.yml
# + deploy/aws/docker-compose.highmem.yml when RAM tier != low
# + deploy/aws/docker-compose.https.yml when SSL certs exist
```

Environment exported to `/tmp/legalease-compose.env`:

```bash
LEGALEASE_COMPOSE_FILES="-f docker-compose.yml -f deploy/aws/docker-compose.override.yml ..."
eval "$(cat /tmp/legalease-compose.env)"
docker compose ${LEGALEASE_COMPOSE_FILES} ps
```

## 7.7 EC2 Memory Tiers (apply-ec2-tier.sh)

| Tier | Detection | ML_USE_QUEUE | LOW_RESOURCE_MODE | STT model | Workers |
|------|-----------|--------------|-------------------|-----------|---------|
| low | <=8 GB | 0 | 1 | tiny | disabled |
| medium | 8–16 GB | 1 | 0 | small | optional |
| high | >16 GB | 1 | 0 | small | can enable |

On low tier (current 8GB production):
- `UVICORN_WORKERS=1`
- `RAG_ENABLE_CROSS_ENCODER=0`
- `HF_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5`
- Ollama disabled; Gemini required for web modes

Enable workers on high-memory instance:

```bash
docker compose $LEGALEASE_COMPOSE_FILES --profile workers up -d worker ml-worker
```

## 7.8 nginx Configuration

Production nginx config: `deploy/nginx/nginx.conf` (HTTP) and `deploy/nginx/nginx-ssl.conf` (HTTPS).

Key settings:
- `/api/` proxied to `http://api:8000/api/`
- `/` proxied to `http://web:3000/`
- `proxy_read_timeout 300s` for long chat streams
- Rate limiting zones for auth and chat endpoints

TLS certificates path:
- `deploy/nginx/ssl/cert.pem` (full chain)
- `deploy/nginx/ssl/key.pem` (private key)

When both exist, `apply-ec2-tier.sh` adds `-f deploy/aws/docker-compose.https.yml`.

## 7.9 DuckDNS and TLS Setup

### DuckDNS

1. Register subdomain at duckdns.org
2. Set A record to 18.61.68.82
3. Ensure AWS security group allows inbound TCP 80
4. Set in server `.env`:
   - `PUBLIC_APP_URL=https://legalease.duckdns.org`
   - `CORS_ORIGINS=https://legalease.duckdns.org`
   - `NEXT_PUBLIC_API_URL=https://legalease.duckdns.org/api`

### Let's Encrypt (optional HTTPS)

On EC2 with port 443 open:

```bash
sudo apt install certbot
sudo certbot certonly --standalone -d legalease.duckdns.org
sudo cp /etc/letsencrypt/live/legalease.duckdns.org/fullchain.pem deploy/nginx/ssl/cert.pem
sudo cp /etc/letsencrypt/live/legalease.duckdns.org/privkey.pem deploy/nginx/ssl/key.pem
bash deploy/aws/apply-ec2-tier.sh
bash deploy/aws/ec2-go-live.sh https://legalease.duckdns.org
```

### Cloudflare quick tunnel (fallback when port 80 blocked)

`ec2-go-live.sh` auto-starts cloudflared if direct HTTP fails:

```bash
cloudflared tunnel --url http://127.0.0.1:80
# URL logged to /tmp/cloudflared.log
# systemd unit: cloudflared-legalease.service
```

Use tunnel URL as `-PublicUrl` until port 80 is opened.

## 7.10 Environment Variable Profiles (Laptop vs EC2)

| Variable | Laptop (.env.local) | EC2 (/opt/legalease/.env) |
|----------|---------------------|------------------------|
| LEGALEEASE_LOCAL_DEV | 1 | unset |
| SAAS_PRODUCTION | 0 | 1 |
| SAAS_PRODUCTION_STRICT | 0 | 1 (after Stripe keys set) |
| SAAS_USE_POSTGRES_LEGACY | 0 | 1 |
| DATABASE_URL | empty (SQLite) | postgresql://legalease:PASS@postgres:5432/legalease |
| LEGALEASE_DB_PATH | legalease.db | /data/legalease.db |
| REDIS_URL | optional | redis://redis:6379/0 |
| LLM_BACKEND | ollama | gemini |
| CLOUD_GEMINI_KB | 0 | 1 |
| OLLAMA_AUTO_START | 1 | 0 |
| NEXT_PUBLIC_API_URL | http://127.0.0.1:8000 | https://legalease.duckdns.org/api |
| CORS_ORIGINS | http://localhost:3000 | https://legalease.duckdns.org |
| PUBLIC_APP_URL | http://localhost:3000 | https://legalease.duckdns.org |
| ALLOW_MOCK_BILLING | 1 | 0 |
| SAAS_ALL_FEATURES_FREE | 1 | 1 (demo) |
| RATE_LIMIT_ENABLED | 0 or 1 | 1 |
| STT_ENABLED | 1 | 1 |
| STT_DEVICE | cuda if GPU | cpu |
| STT_MODEL | base/small | tiny (low RAM) |
| IMPROVEMENT_AUTO | 1 | 0 |
| COACH_AUTO_SCHEDULE | 1 | 0 |

## 7.11 Stripe Billing Setup (Production)

1. Create Stripe account and products (Pro, Legal Pro)
2. Copy price IDs to `.env`: `STRIPE_PRICE_PRO`, `STRIPE_PRICE_LEGAL_PRO`
3. Set `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET`
4. Configure Stripe webhook endpoint: `https://legalease.duckdns.org/api/v1/subscriptions/webhook`
5. Set `SAAS_PRODUCTION_STRICT=1` only after keys are live
6. If API unhealthy due to placeholder Stripe key, temporarily set `SAAS_PRODUCTION_STRICT=0`

## 7.12 Database Backup and Restore

### Backup (production)

```bash
ssh -i ~/.ssh/legalease-aws.pem ubuntu@18.61.68.82
cd /opt/legalease
export DATABASE_URL=postgresql://legalease:YOUR_PASS@postgres:5432/legalease
docker compose $LEGALEASE_COMPOSE_FILES exec -T postgres pg_dump -U legalease legalease > backups/postgres_$(date +%Y%m%d).dump
```

Or from laptop:

```powershell
py scripts\backup_legalease.py --out backups/manual
```

Backup includes: postgres dump, SQLite (if present), faiss_indexes/, Data/

### Restore procedure

1. Stop API: `docker compose $LEGALEASE_COMPOSE_FILES stop api web`
2. Restore Postgres: `pg_restore -d legalease backups/postgres_YYYYMMDD.dump`
3. Restore files: copy faiss_indexes/ and Data/ from backup
4. Start stack: `bash deploy/aws/ec2-go-live.sh https://legalease.duckdns.org`
5. Verify: `curl https://legalease.duckdns.org/api/v1/health/public`

### SQLite to Postgres migration (one-time)

```powershell
py scripts\migrate_sqlite_to_pg.py
```

Run when moving from laptop SQLite to Docker Postgres.

## 7.13 Rollback Procedure

If deploy breaks production:

```bash
ssh ubuntu@18.61.68.82
cd /opt/legalease
# View previous images
docker images | grep legalease
# Roll back to previous git state if tagged
git log --oneline -5
# Or restore from backup (section 7.12)
docker compose $LEGALEASE_COMPOSE_FILES logs api --tail 100
```

From Windows, redeploy last known good commit:

```powershell
git checkout <last-good-commit>
.\scripts\aws_update.ps1 -PublicUrl "https://legalease.duckdns.org"
```

## 7.14 Monitoring and Logs

```bash
# All services
docker compose $LEGALEASE_COMPOSE_FILES ps
docker compose $LEGALEASE_COMPOSE_FILES logs -f api
docker compose $LEGALEASE_COMPOSE_FILES logs -f web
docker compose $LEGALEASE_COMPOSE_FILES logs -f nginx

# Health endpoints
curl https://legalease.duckdns.org/api/v1/health/live
curl https://legalease.duckdns.org/api/v1/health/ready
curl https://legalease.duckdns.org/api/v1/health/public
curl https://legalease.duckdns.org/api/v1/health/llm
```

Structured logs in API include request ID, user ID, and pipeline stage when `KB_PIPELINE_DEBUG=1`.

## 7.15 CI/CD (GitHub Actions)

File: `.github/workflows/ci.yml`

On every push/PR:
- Python pytest (~126 tests)
- Next.js production build verification
- Lint checks

CI does not auto-deploy to EC2. Production deploy is manual via `aws_update.ps1`.

## 7.16 Troubleshooting Matrix (Complete)

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| 502 Bad Gateway on /api | API container down or starting | `docker compose logs api`; wait 90s start_period |
| CORS error in browser | CORS_ORIGINS mismatch | Set CORS_ORIGINS exactly to https://legalease.duckdns.org (no trailing slash) |
| Web shows wrong API | Stale NEXT_PUBLIC_API_URL | Rebuild web: `ec2-go-live.sh https://legalease.duckdns.org` |
| password authentication failed for postgres | POSTGRES_PASSWORD drift | `bash deploy/aws/fix-postgres-password.sh` |
| STRIPE_SECRET_KEY placeholder error | SAAS_PRODUCTION_STRICT=1 without keys | Add Stripe keys or set STRICT=0 temporarily |
| Thumbs feedback not saving | adaptive_mode_stats schema | Deploy latest code (pg_core_schema migration) |
| KB returns NOT_FOUND | Documents not indexed | Upload PDFs, click Index All, check faiss_indexes volume |
| Open Law quota exceeded | Gemini daily limit | Wait for reset or upgrade plan; Tavily fallback |
| Ollama connection refused on EC2 | Expected — EC2 uses Gemini | Set LLM_BACKEND=gemini, CLOUD_GEMINI_KB=1 |
| Port 8000 in use on laptop | Stale Python process | `.\stop_backend.ps1` then `run_backend.ps1` |
| DuckDNS timeout | Port 80 blocked | Open AWS SG port 80 or use Cloudflare tunnel |
| Web build fails premium/page | Stale route | aws_update.ps1 removes web/app/(app)/premium |
| Sessions lost between requests | Redis not configured | Set REDIS_URL=redis://redis:6379/0 |
| OCR fails on scans | EasyOCR not in container | Rebuild api image; check OCR_ENABLED=1 |
| STT fails in browser | ffmpeg missing on laptop | winget install Gyan.FFmpeg |
| Feedback 500 on Postgres | Transaction rollback on stats | Latest adaptive_learning.py commits interaction first |
| Index job stuck | ML_USE_QUEUE=0 on low RAM | Run index from UI; or enable worker profile |
| High API memory | FAISS + embeddings | LOW_RESOURCE_MODE=1, RAG_ENABLE_CROSS_ENCODER=0 |
| TLS handshake error | Cert path wrong | Verify deploy/nginx/ssl/cert.pem and key.pem |
| Login works locally not EC2 | Wrong DATABASE_URL | Must use @postgres:5432 not @localhost |
| Deploy tarball huge | Data included | aws_update excludes Data, faiss_indexes, node_modules |

## 7.17 fix-ec2-env.sh — Line-by-Line Behavior

Script: `deploy/aws/fix-ec2-env.sh`

1. Sets working directory to `/opt/legalease`
2. Accepts public URL argument (defaults to http://18.61.68.82)
3. Forces SAAS_USE_POSTGRES_LEGACY=1
4. Runs apply-ec2-tier.sh for memory tier compose files
5. Rewrites DATABASE_URL localhost to postgres hostname
6. Rewrites REDIS_URL 127.0.0.1 to redis hostname
7. Sets CLOUD_GEMINI_KB=1 if missing
8. Sets CORS_ORIGINS, PUBLIC_APP_URL, NEXT_PUBLIC_API_URL from public URL
9. Configures CPU speech-to-text (STT_MODEL=tiny, STT_DEVICE=cpu)
10. Rebuilds api + web containers
11. Restarts api, web, nginx

## 7.18 ec2-go-live.sh — Line-by-Line Behavior

Script: `deploy/aws/ec2-go-live.sh`

1. Detects EC2 public IP via checkip.amazonaws.com
2. Sets SAAS_USE_POSTGRES_LEGACY=1, SAAS_PRODUCTION=1
3. Configures STT for CPU
4. Runs apply-ec2-tier.sh
5. `docker compose up -d --build` full stack
6. If no PUBLIC_BASE arg and port 80 unreachable: starts Cloudflare tunnel
7. Writes systemd unit for cloudflared persistence
8. Updates CORS, PUBLIC_APP_URL, NEXT_PUBLIC_API_URL
9. Rebuilds api + web with exported NEXT_PUBLIC_API_URL
10. Health check loop (60 attempts, 2s interval)
11. Prints live URL and health response

## 7.19 Docker Local Production (Non-EC2)

For self-hosted Docker on any server:

```powershell
copy .env.docker.example .env
# Edit POSTGRES_PASSWORD, JWT_SECRET, NEXT_PUBLIC_API_URL, CORS_ORIGINS
# Place TLS certs in deploy/nginx/ssl/
docker compose up -d --build
```

Health: http://localhost/api/v1/health/live

See DEPLOY.md for LM Studio on Windows host (`LM_STUDIO_URL=http://host.docker.internal:1234`).

## 7.20 Post-Deploy Smoke Tests

```powershell
# From laptop
curl https://legalease.duckdns.org/api/v1/health/live
py scripts\e2e_saas_smoke.py --url https://legalease.duckdns.org/api
py scripts\e2e_kb_smoke.py --url https://legalease.duckdns.org/api
```

Manual UI tests:
1. Register / login
2. Upload PDF to Documents, Index All
3. KB chat with citation
4. Create matter, link document
5. Evidence Intelligence upload on /discovery
6. Thumbs up on chat response — verify POST /api/v1/learning/feedback returns ok:true
7. Billing invoice PDF export (if Stripe configured)

## 7.21 Security Hardening Checklist

- [ ] JWT_SECRET and LEGALEASE_API_SECRET are unique 32+ char random strings
- [ ] POSTGRES_PASSWORD is strong and not committed to git
- [ ] GEMINI_API_KEY only on server .env
- [ ] SAAS_PRODUCTION_STRICT=1 after Stripe configured
- [ ] FORCE_HTTPS=1 and SECURITY_HEADERS_ENABLED=1 on production
- [ ] FIREWALL_ENABLED=0 or restrict FIREWALL_ALLOWED_IPS for admin
- [ ] SUPERADMIN_USERNAMES lists only trusted admins
- [ ] Regular Postgres backups scheduled
- [ ] SSH key-only access (disable password auth)
- [ ] AWS security group limits SSH to your IP

## 7.22 Volume and Data Persistence

| Volume | Mount | Contents |
|--------|-------|----------|
| postgres_data | postgres | All PostgreSQL data |
| redis_data | redis | Session/cache AOF |
| app_data | api | /data/legalease.db fallback, uploads |
| ./faiss_indexes | api | Per-user FAISS vector indexes |
| ./Data | api | Uploaded PDFs and HF cache |

Never delete postgres_data without backup. faiss_indexes can be rebuilt via reindex but takes time.

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





---

# Appendix V — Complete API Route Index (Auto-Generated)

Total routes: **493** (includes WebSocket endpoints).
Base prefix: `/api/v1`. Authentication: JWT Bearer unless noted public.

| Module | Method | Path |
|--------|--------|------|
| account | DELETE | `/api/v1/account` |
| account | GET | `/api/v1/account/export` |
| account | POST | `/api/v1/account/forgot-password` |
| account | GET | `/api/v1/account/onboarding` |
| account | POST | `/api/v1/account/onboarding/dismiss` |
| account | GET | `/api/v1/account/preferences` |
| account | PATCH | `/api/v1/account/preferences/learner-mode` |
| account | POST | `/api/v1/account/reset-password/{token}` |
| account | POST | `/api/v1/account/verify-email/confirm` |
| account | POST | `/api/v1/account/verify-email/send` |
| admin | GET | `/api/v1/admin/audit` |
| admin | GET | `/api/v1/admin/health` |
| admin | GET | `/api/v1/admin/usage` |
| admin | GET | `/api/v1/admin/users` |
| admin | POST | `/api/v1/admin/users/{user_id}/plan` |
| admin | POST | `/api/v1/admin/users/{user_id}/suspend` |
| admin | POST | `/api/v1/admin/users/{user_id}/unsuspend` |
| billing | GET | `/api/v1/billing/collections` |
| billing | GET | `/api/v1/billing/entries` |
| billing | POST | `/api/v1/billing/entries` |
| billing | POST | `/api/v1/billing/entries/bulk` |
| billing | DELETE | `/api/v1/billing/entries/{record_id}` |
| billing | PUT | `/api/v1/billing/entries/{record_id}` |
| billing | POST | `/api/v1/billing/entries/{record_id}/duplicate` |
| billing | GET | `/api/v1/billing/expenses` |
| billing | POST | `/api/v1/billing/expenses` |
| billing | DELETE | `/api/v1/billing/expenses/{expense_id}` |
| billing | GET | `/api/v1/billing/invoices` |
| billing | POST | `/api/v1/billing/invoices` |
| billing | POST | `/api/v1/billing/invoices/compute-totals` |
| billing | POST | `/api/v1/billing/invoices/draft` |
| billing | GET | `/api/v1/billing/invoices/prefill` |
| billing | GET | `/api/v1/billing/invoices/{invoice_id}` |
| billing | PUT | `/api/v1/billing/invoices/{invoice_id}` |
| billing | POST | `/api/v1/billing/invoices/{invoice_id}/finalize` |
| billing | GET | `/api/v1/billing/invoices/{invoice_id}/pdf` |
| billing | PATCH | `/api/v1/billing/invoices/{invoice_id}/status` |
| billing | GET | `/api/v1/billing/matter/{matter_id}/financials` |
| billing | GET | `/api/v1/billing/matter/{matter_id}/profile` |
| billing | PUT | `/api/v1/billing/matter/{matter_id}/profile` |
| billing | POST | `/api/v1/billing/narrative/correct` |
| billing | POST | `/api/v1/billing/narrative/preview` |
| billing | GET | `/api/v1/billing/payments` |
| billing | GET | `/api/v1/billing/plans` |
| billing | GET | `/api/v1/billing/reports/{report_type}` |
| billing | GET | `/api/v1/billing/status` |
| billing | GET | `/api/v1/billing/summary` |
| billing | GET | `/api/v1/billing/workspace` |
| chat | POST | `/api/v1/chat` |
| chat | POST | `/api/v1/chat/export-report` |
| chat | POST | `/api/v1/chat/stream` |
| clauses | GET | `/api/v1/clauses` |
| clauses | POST | `/api/v1/clauses` |
| clauses | POST | `/api/v1/clauses/feedback` |
| collab | GET | `/api/v1/collaboration/attachments/{attachment_id}/download` |
| collab | GET | `/api/v1/collaboration/debug/realtime` |
| collab | GET | `/api/v1/collaboration/members` |
| collab | POST | `/api/v1/collaboration/messages/{message_id}/create-deadline` |
| collab | POST | `/api/v1/collaboration/messages/{message_id}/create-task` |
| collab | GET | `/api/v1/collaboration/notifications` |
| collab | POST | `/api/v1/collaboration/notifications/{notification_id}/read` |
| collab | GET | `/api/v1/collaboration/permissions` |
| collab | GET | `/api/v1/collaboration/presence` |
| collab | POST | `/api/v1/collaboration/presence` |
| collab | GET | `/api/v1/collaboration/requests` |
| collab | POST | `/api/v1/collaboration/requests` |
| collab | POST | `/api/v1/collaboration/requests/{request_id}/accept` |
| collab | POST | `/api/v1/collaboration/requests/{request_id}/reject` |
| collab | GET | `/api/v1/collaboration/rooms` |
| collab | POST | `/api/v1/collaboration/rooms/channel` |
| collab | POST | `/api/v1/collaboration/rooms/dm` |
| collab | GET | `/api/v1/collaboration/rooms/matter/{matter_id}` |
| collab | GET | `/api/v1/collaboration/rooms/{room_id}` |
| collab | GET | `/api/v1/collaboration/rooms/{room_id}/context` |
| collab | GET | `/api/v1/collaboration/rooms/{room_id}/messages` |
| collab | POST | `/api/v1/collaboration/rooms/{room_id}/messages` |
| collab | POST | `/api/v1/collaboration/rooms/{room_id}/messages/{message_id}/attachments` |
| collab | POST | `/api/v1/collaboration/rooms/{room_id}/messages/{message_id}/reactions` |
| collab | POST | `/api/v1/collaboration/rooms/{room_id}/read` |
| collab | GET | `/api/v1/collaboration/rooms/{room_id}/stats` |
| collab | GET | `/api/v1/collaboration/rooms/{room_id}/stream` |
| collab | POST | `/api/v1/collaboration/rooms/{room_id}/summarize` |
| collab | GET | `/api/v1/collaboration/rooms/{room_id}/typing` |
| collab | GET | `/api/v1/collaboration/search` |
| collab | POST | `/api/v1/collaboration/typing` |
| collab | GET | `/api/v1/collaboration/users/search` |
| collab | WEBSOCKET | `/api/v1/collaboration/ws` |
| crm | GET | `/api/v1/crm` |
| crm | POST | `/api/v1/crm` |
| crm | GET | `/api/v1/crm/analytics` |
| crm | POST | `/api/v1/crm/assistant` |
| crm | POST | `/api/v1/crm/classify` |
| crm | GET | `/api/v1/crm/command-center` |
| crm | GET | `/api/v1/crm/dashboard` |
| crm | POST | `/api/v1/crm/intent/correct` |
| crm | GET | `/api/v1/crm/kanban` |
| crm | GET | `/api/v1/crm/permissions` |
| crm | GET | `/api/v1/crm/pipeline-stages` |
| crm | GET | `/api/v1/crm/{lead_id}` |
| crm | PATCH | `/api/v1/crm/{lead_id}` |
| crm | POST | `/api/v1/crm/{lead_id}/analyze` |
| crm | POST | `/api/v1/crm/{lead_id}/archive` |
| crm | GET | `/api/v1/crm/{lead_id}/audit` |
| crm | POST | `/api/v1/crm/{lead_id}/convert` |
| crm | POST | `/api/v1/crm/{lead_id}/convert-to-matter` |
| crm | POST | `/api/v1/crm/{lead_id}/convert/preview` |
| crm | GET | `/api/v1/crm/{lead_id}/documents` |
| crm | POST | `/api/v1/crm/{lead_id}/documents` |
| crm | POST | `/api/v1/crm/{lead_id}/follow-up/apply` |
| crm | POST | `/api/v1/crm/{lead_id}/follow-up/preview` |
| crm | POST | `/api/v1/crm/{lead_id}/follow-up/send` |
| crm | GET | `/api/v1/crm/{lead_id}/follow-up/templates` |
| crm | GET | `/api/v1/crm/{lead_id}/interactions` |
| crm | POST | `/api/v1/crm/{lead_id}/interactions` |
| crm | POST | `/api/v1/crm/{lead_id}/reject` |
| crm | PATCH | `/api/v1/crm/{lead_id}/stage` |
| dashboard | GET | `/api/v1/dashboard/full` |
| documents | GET | `/api/v1/documents` |
| documents | POST | `/api/v1/documents/index` |
| documents | GET | `/api/v1/documents/jobs` |
| documents | GET | `/api/v1/documents/jobs/{job_id}` |
| documents | GET | `/api/v1/documents/kb/health` |
| documents | POST | `/api/v1/documents/kb/reindex-auto` |
| documents | POST | `/api/v1/documents/kb/smoke-test` |
| documents | POST | `/api/v1/documents/kb/sync-status` |
| documents | POST | `/api/v1/documents/upload` |
| documents | DELETE | `/api/v1/documents/{doc_id}` |
| documents | GET | `/api/v1/documents/{doc_id}/entities` |
| documents | GET | `/api/v1/documents/{doc_id}/timeline` |
| drafting_v3 | POST | `/api/v1/drafting/redline` |
| drafting_v3 | POST | `/api/v1/drafting/redline/feedback` |
| drafting_studio | POST | `/api/v1/drafting/smart-draft/generate` |
| drafting_studio | GET | `/api/v1/drafting/smart-draft/types` |
| drafting_studio | GET | `/api/v1/drafting/smart-draft/{draft_type}/questions` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/ai/generate` |
| drafting_workspace | GET | `/api/v1/drafting/workspace/dashboard` |
| drafting_workspace | GET | `/api/v1/drafting/workspace/document-types` |
| drafting_workspace | GET | `/api/v1/drafting/workspace/documents` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/documents` |
| drafting_workspace | DELETE | `/api/v1/drafting/workspace/documents/{draft_id}` |
| drafting_workspace | GET | `/api/v1/drafting/workspace/documents/{draft_id}` |
| drafting_workspace | PATCH | `/api/v1/drafting/workspace/documents/{draft_id}` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/documents/{draft_id}/ai/assist` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/annexures` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/annexures` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/assign` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/assignments` |
| drafting_v4 | PATCH | `/api/v1/drafting/workspace/documents/{draft_id}/assignments/{assignment_id}` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/audit` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/autofill` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/billing-session` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/clause-intel` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/collaboration-hub` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/documents/{draft_id}/comments` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/comments/{comment_id}/resolve` |
| drafting_workspace | GET | `/api/v1/drafting/workspace/documents/{draft_id}/compare` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/compare-precedent` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/compare-v3` |
| drafting_v3 | PATCH | `/api/v1/drafting/workspace/documents/{draft_id}/content` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/copilot` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/documents/{draft_id}/export` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/export-v3` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/filing-readiness` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/insert-annexure-index` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/insert-toc` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/insights` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/link-hearing` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/links` |
| drafting_v4 | DELETE | `/api/v1/drafting/workspace/documents/{draft_id}/lock` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/lock` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/partner-approve` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/partner-review` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/partner-revision` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/presence` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/presence/heartbeat` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/promote-precedent` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/documents/{draft_id}/restore/{version_number}` |
| drafting_workspace | POST | `/api/v1/drafting/workspace/documents/{draft_id}/review` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/review-workspace` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/signatures` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/signatures` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/signatures/{signature_id}/signed` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/status` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/suggestions` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/suggestions/{suggestion_id}/resolve` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/sync-litigation` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/timeline` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/documents/{draft_id}/track-changes` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/track-changes` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/track-changes/{change_id}/resolve` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/documents/{draft_id}/transition` |
| drafting_workspace | GET | `/api/v1/drafting/workspace/documents/{draft_id}/versions` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/v3/matters/{matter_id}/variables` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/v3/pack` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/v3/search` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/v3/templates` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/v3/templates/create-document` |
| drafting_v3 | POST | `/api/v1/drafting/workspace/v3/templates/render` |
| drafting_v3 | GET | `/api/v1/drafting/workspace/v3/workflow` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/v4/control-center` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/v4/court-package` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/v4/matters/{matter_id}/court-bundle` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/v4/matters/{matter_id}/drafting` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/v4/matters/{matter_id}/drafting-overview` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/v4/matters/{matter_id}/drafts` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/v4/precedents` |
| drafting_v4 | POST | `/api/v1/drafting/workspace/v4/precedents` |
| drafting_v4 | GET | `/api/v1/drafting/workspace/v4/precedents/search` |
| ediscovery | GET | `/api/v1/ediscovery/batches` |
| ediscovery | POST | `/api/v1/ediscovery/batches` |
| ediscovery | GET | `/api/v1/ediscovery/batches/{batch_id}` |
| ediscovery | GET | `/api/v1/ediscovery/batches/{batch_id}/search` |
| ediscovery | POST | `/api/v1/ediscovery/evidence/analyze` |
| ediscovery | POST | `/api/v1/ediscovery/evidence/contradictions` |
| ediscovery | POST | `/api/v1/ediscovery/evidence/court-orders` |
| ediscovery | GET | `/api/v1/ediscovery/evidence/formats` |
| ediscovery | GET | `/api/v1/ediscovery/evidence/repository` |
| ediscovery | POST | `/api/v1/ediscovery/evidence/statutes` |
| ediscovery | GET | `/api/v1/ediscovery/evidence/timeline` |
| ediscovery | POST | `/api/v1/ediscovery/evidence/upload` |
| ediscovery | POST | `/api/v1/ediscovery/items/{item_id}/review` |
| ediscovery | GET | `/api/v1/ediscovery/jobs/{job_id}` |
| ediscovery | POST | `/api/v1/ediscovery/pii/detect` |
| ediscovery | POST | `/api/v1/ediscovery/pii/redact` |
| ediscovery | POST | `/api/v1/ediscovery/pii/whitelist` |
| ediscovery | POST | `/api/v1/ediscovery/triage` |
| engines | GET | `/api/v1/engines/matters/{matter_id}/autopilot` |
| engines | GET | `/api/v1/engines/status` |
| engines | GET | `/api/v1/engines/watchlist` |
| engines | POST | `/api/v1/engines/watchlist` |
| engines | DELETE | `/api/v1/engines/watchlist/{watch_id}` |
| engines | POST | `/api/v1/engines/watchlist/{watch_id}/check` |
| enterprise | GET | `/api/v1/enterprise/agents` |
| enterprise | POST | `/api/v1/enterprise/agents/run` |
| enterprise | GET | `/api/v1/enterprise/branding` |
| enterprise | GET | `/api/v1/enterprise/court/status` |
| enterprise | POST | `/api/v1/enterprise/court/sync` |
| enterprise | GET | `/api/v1/enterprise/orgs/{org_id}/branding` |
| enterprise | PATCH | `/api/v1/enterprise/orgs/{org_id}/branding` |
| enterprise | GET | `/api/v1/enterprise/pilot/firms` |
| enterprise | POST | `/api/v1/enterprise/pilot/firms` |
| enterprise | PATCH | `/api/v1/enterprise/pilot/firms/{pilot_id}` |
| enterprise | GET | `/api/v1/enterprise/pilot/summary` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/analytics` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/audit` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/client-portal` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/client-portal/document-request` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/client-portal/request-review` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/court-orders` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/court-orders` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/court-orders/search` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/court-orders/{order_id}` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/dashboard` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/documents` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/documents` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/documents/search` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/documents/{doc_id}` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/folders` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/folders` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/folders/seed-matter` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/knowledge` |
| enterprise_workspace | POST | `/api/v1/enterprise/workspace/knowledge` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/matters` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/matters/{matter_id}/hub` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/search` |
| enterprise_workspace | GET | `/api/v1/enterprise/workspace/storage` |
| esign | POST | `/api/v1/esign/mock/{request_id}/complete` |
| esign | POST | `/api/v1/esign/requests` |
| esign | GET | `/api/v1/esign/requests/{request_id}` |
| feedback | GET | `/api/v1/feedback-learning/queue` |
| feedback | GET | `/api/v1/feedback-learning/queue/mine` |
| feedback | POST | `/api/v1/feedback-learning/queue/{queue_id}/review` |
| health | GET | `/api/v1/health` |
| health | GET | `/api/v1/health/embeddings` |
| health | GET | `/api/v1/health/gpu` |
| health | GET | `/api/v1/health/live` |
| health | GET | `/api/v1/health/llm` |
| health | GET | `/api/v1/health/public` |
| health | GET | `/api/v1/health/ready` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/bns/{section}` |
| ipc_bns_v3 | POST | `/api/v1/ipc-bns/v3/bulk` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/categories` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/categories/{category}` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/compare/{ipc_section}` |
| ipc_bns_v3 | POST | `/api/v1/ipc-bns/v3/convert` |
| ipc_bns_v3 | POST | `/api/v1/ipc-bns/v3/document/convert` |
| ipc_bns_v3 | POST | `/api/v1/ipc-bns/v3/document/upload` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/ipc/{section}` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/matters/{matter_id}/migration` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/meta` |
| ipc_bns_v3 | POST | `/api/v1/ipc-bns/v3/report/export` |
| ipc_bns_v3 | GET | `/api/v1/ipc-bns/v3/search` |
| kb_debug | GET | `/api/v1/kb/debug-batch` |
| kb_debug | GET | `/api/v1/kb/debug-query` |
| learning | GET | `/api/v1/learning/analytics/full` |
| learning | GET | `/api/v1/learning/automation/jobs` |
| learning | GET | `/api/v1/learning/automation/jobs/{job_id}` |
| learning | POST | `/api/v1/learning/automation/run-now` |
| learning | GET | `/api/v1/learning/automation/status` |
| learning | POST | `/api/v1/learning/correction` |
| learning | POST | `/api/v1/learning/engine/auto-improve` |
| learning | POST | `/api/v1/learning/engine/rescue-test` |
| learning | GET | `/api/v1/learning/engine/status` |
| learning | POST | `/api/v1/learning/eval/holdout` |
| learning | POST | `/api/v1/learning/feedback` |
| learning | GET | `/api/v1/learning/preferences` |
| learning | GET | `/api/v1/learning/progress` |
| learning | GET | `/api/v1/learning/quality-gate` |
| learning | POST | `/api/v1/learning/signals` |
| learning | GET | `/api/v1/learning/signals/stats` |
| learning | GET | `/api/v1/learning/signals/tags` |
| learning | GET | `/api/v1/learning/stats` |
| learning | POST | `/api/v1/learning/training/export-dpo` |
| learning | POST | `/api/v1/learning/training/export-sft` |
| learning | GET | `/api/v1/learning/training/llm-status` |
| learning | GET | `/api/v1/learning/training/status` |
| learning | POST | `/api/v1/learning/training/train-dpo` |
| learning | POST | `/api/v1/learning/training/train-sft` |
| learning | POST | `/api/v1/learning/tuning/coach/analyze` |
| learning | POST | `/api/v1/learning/tuning/coach/apply` |
| learning | GET | `/api/v1/learning/tuning/coach/directives` |
| learning | POST | `/api/v1/learning/tuning/coach/directives` |
| learning | POST | `/api/v1/learning/tuning/coach/run` |
| learning | POST | `/api/v1/learning/tuning/coach/schedule/run-now` |
| learning | GET | `/api/v1/learning/tuning/coach/schedule/status` |
| learning | POST | `/api/v1/learning/tuning/coach/schedule/toggle` |
| learning | GET | `/api/v1/learning/tuning/coach/status` |
| learning | POST | `/api/v1/learning/tuning/coach/toggle` |
| learning | POST | `/api/v1/learning/tuning/export` |
| learning | POST | `/api/v1/learning/tuning/export-saas` |
| learning | POST | `/api/v1/learning/tuning/neural/collect` |
| learning | GET | `/api/v1/learning/tuning/neural/status` |
| learning | POST | `/api/v1/learning/tuning/neural/train` |
| learning | POST | `/api/v1/learning/tuning/ollama/export-modelfile` |
| learning | GET | `/api/v1/learning/tuning/ollama/export-status` |
| learning | POST | `/api/v1/learning/tuning/scope/promote` |
| legal_conversion | GET | `/api/v1/legal-conversion/convert` |
| legal_conversion | POST | `/api/v1/legal-conversion/convert` |
| legal_conversion | GET | `/api/v1/legal-conversion/meta` |
| legal_conversion | GET | `/api/v1/legal-conversion/search` |
| matters | GET | `/api/v1/matters` |
| matters | POST | `/api/v1/matters` |
| matters | GET | `/api/v1/matters/documents/unlinked` |
| matters | GET | `/api/v1/matters/evidence-desk` |
| matters | POST | `/api/v1/matters/evidence-desk/scan` |
| matters | GET | `/api/v1/matters/health/indexing` |
| matters | GET | `/api/v1/matters/hearings/digest` |
| matters | GET | `/api/v1/matters/meta/types` |
| matters | GET | `/api/v1/matters/notifications/all` |
| matters | DELETE | `/api/v1/matters/{matter_id}` |
| matters | GET | `/api/v1/matters/{matter_id}` |
| matters | PATCH | `/api/v1/matters/{matter_id}` |
| matters | GET | `/api/v1/matters/{matter_id}/audit` |
| matters | GET | `/api/v1/matters/{matter_id}/autopilot` |
| matters | GET | `/api/v1/matters/{matter_id}/client-status-letter` |
| matters | GET | `/api/v1/matters/{matter_id}/contradictions` |
| matters | POST | `/api/v1/matters/{matter_id}/contradictions/extract` |
| matters | GET | `/api/v1/matters/{matter_id}/dashboard` |
| matters | GET | `/api/v1/matters/{matter_id}/deadlines` |
| matters | POST | `/api/v1/matters/{matter_id}/deadlines` |
| matters | POST | `/api/v1/matters/{matter_id}/documents/link` |
| matters | POST | `/api/v1/matters/{matter_id}/documents/upload` |
| matters | PATCH | `/api/v1/matters/{matter_id}/documents/{document_id}` |
| matters | GET | `/api/v1/matters/{matter_id}/entities` |
| matters | POST | `/api/v1/matters/{matter_id}/entities/extract` |
| matters | GET | `/api/v1/matters/{matter_id}/entities/profiles` |
| matters | GET | `/api/v1/matters/{matter_id}/evidence` |
| matters | POST | `/api/v1/matters/{matter_id}/evidence` |
| matters | POST | `/api/v1/matters/{matter_id}/evidence/extract` |
| matters | GET | `/api/v1/matters/{matter_id}/export` |
| matters | GET | `/api/v1/matters/{matter_id}/hearing-prep-pack` |
| matters | GET | `/api/v1/matters/{matter_id}/hearings` |
| matters | POST | `/api/v1/matters/{matter_id}/hearings` |
| matters | POST | `/api/v1/matters/{matter_id}/hearings/extract` |
| matters | POST | `/api/v1/matters/{matter_id}/hearings/from-voice` |
| matters | POST | `/api/v1/matters/{matter_id}/hearings/import-cause-list` |
| matters | POST | `/api/v1/matters/{matter_id}/intelligence/run` |
| matters | GET | `/api/v1/matters/{matter_id}/intelligence/status` |
| matters | GET | `/api/v1/matters/{matter_id}/members` |
| matters | POST | `/api/v1/matters/{matter_id}/members` |
| matters | POST | `/api/v1/matters/{matter_id}/notes` |
| matters | POST | `/api/v1/matters/{matter_id}/restore` |
| matters | GET | `/api/v1/matters/{matter_id}/search` |
| matters | POST | `/api/v1/matters/{matter_id}/smoke` |
| matters | GET | `/api/v1/matters/{matter_id}/tasks` |
| matters | POST | `/api/v1/matters/{matter_id}/tasks` |
| matters | PATCH | `/api/v1/matters/{matter_id}/tasks/{task_id}` |
| matters | GET | `/api/v1/matters/{matter_id}/timeline` |
| matters | POST | `/api/v1/matters/{matter_id}/timeline` |
| matters | POST | `/api/v1/matters/{matter_id}/timeline/generate` |
| matters | GET | `/api/v1/matters/{matter_id}/timeline/suggestions` |
| matters | POST | `/api/v1/matters/{matter_id}/timeline/suggestions/{suggestion_id}/approve` |
| matters | POST | `/api/v1/matters/{matter_id}/timeline/suggestions/{suggestion_id}/reject` |
| memory | GET | `/api/v1/memory/context` |
| memory | POST | `/api/v1/memory/facts` |
| memory | POST | `/api/v1/memory/facts/reindex-chats` |
| memory | DELETE | `/api/v1/memory/facts/{fact_id}` |
| memory | PATCH | `/api/v1/memory/facts/{fact_id}` |
| memory | GET | `/api/v1/memory/profile` |
| memory | PATCH | `/api/v1/memory/profile` |
| health | GET | `/api/v1/metrics` |
| orgs | POST | `/api/v1/orgs/invite` |
| orgs | GET | `/api/v1/orgs/invites` |
| orgs | DELETE | `/api/v1/orgs/invites/{invite_id}` |
| orgs | GET | `/api/v1/orgs/invites/{token}` |
| orgs | POST | `/api/v1/orgs/invites/{token}/accept` |
| orgs | GET | `/api/v1/orgs/me` |
| health | GET | `/api/v1/ping` |
| portal | POST | `/api/v1/portal/access` |
| portal | POST | `/api/v1/portal/sign/{token}` |
| portal | POST | `/api/v1/portal/upload/{token}` |
| portal | GET | `/api/v1/portal/view/{token}` |
| practice | GET | `/api/v1/practice/court-day/calendar.ics` |
| practice | POST | `/api/v1/practice/court-day/import` |
| practice | GET | `/api/v1/practice/court-day/mission-control` |
| practice | POST | `/api/v1/practice/court-day/parse` |
| practice | POST | `/api/v1/practice/court-day/parse-file` |
| practice | GET | `/api/v1/practice/court-day/prep/{matter_id}` |
| practice | GET | `/api/v1/practice/court-day/prep/{matter_id}/pdf` |
| practice | GET | `/api/v1/practice/court-day/today` |
| practice | POST | `/api/v1/practice/court-sync` |
| practice | GET | `/api/v1/practice/court-sync/history` |
| practice | GET | `/api/v1/practice/court-sync/settings` |
| practice | PUT | `/api/v1/practice/court-sync/settings` |
| practice | GET | `/api/v1/practice/court-sync/status` |
| practice | GET | `/api/v1/practice/ecourts/case/{cnr}` |
| practice | POST | `/api/v1/practice/ecourts/case/{cnr}/sync` |
| practice | GET | `/api/v1/practice/ecourts/causelist/available-dates` |
| practice | GET | `/api/v1/practice/ecourts/court-structure/states` |
| practice | GET | `/api/v1/practice/ecourts/court-structure/states/{state}/districts` |
| practice | GET | `/api/v1/practice/ecourts/search` |
| practice | GET | `/api/v1/practice/evidence-desk` |
| practice | GET | `/api/v1/practice/evidence-desk/export` |
| practice | POST | `/api/v1/practice/evidence-desk/scan` |
| practice | POST | `/api/v1/practice/evidence-desk/scan-all` |
| practice | POST | `/api/v1/practice/limitation/add-to-matter` |
| practice | POST | `/api/v1/practice/limitation/calculate` |
| practice | GET | `/api/v1/practice/limitation/presets` |
| practice | POST | `/api/v1/practice/litigation/ai` |
| practice | GET | `/api/v1/practice/litigation/analytics` |
| practice | GET | `/api/v1/practice/litigation/calendar` |
| practice | GET | `/api/v1/practice/litigation/dashboard` |
| practice | GET | `/api/v1/practice/litigation/diagnostics` |
| practice | GET | `/api/v1/practice/litigation/hearings` |
| practice | POST | `/api/v1/practice/litigation/hearings` |
| practice | PATCH | `/api/v1/practice/litigation/hearings/{hearing_id}` |
| practice | GET | `/api/v1/practice/litigation/limitation/deadlines` |
| practice | GET | `/api/v1/practice/litigation/notifications` |
| practice | GET | `/api/v1/practice/litigation/orders` |
| practice | POST | `/api/v1/practice/litigation/orders` |
| practice | DELETE | `/api/v1/practice/litigation/orders/{order_id}` |
| practice | PATCH | `/api/v1/practice/litigation/orders/{order_id}` |
| practice | GET | `/api/v1/practice/litigation/tasks` |
| practice | POST | `/api/v1/practice/litigation/tasks` |
| practice | DELETE | `/api/v1/practice/litigation/tasks/{task_id}` |
| practice | PATCH | `/api/v1/practice/litigation/tasks/{task_id}` |
| practice | GET | `/api/v1/practice/litigation/war-room/{matter_id}` |
| practice | GET | `/api/v1/practice/litigation/watchlist-dashboard` |
| practice | GET | `/api/v1/practice/overview` |
| practice | POST | `/api/v1/practice/public-intake` |
| research_log | POST | `/api/v1/research/expand` |
| research_log | POST | `/api/v1/research/feedback` |
| research_log | GET | `/api/v1/research/history` |
| research_log | POST | `/api/v1/research/log` |
| saas_metrics | GET | `/api/v1/saas-metrics/kpi` |
| scim | GET | `/api/v1/scim/v2/Users` |
| scim | POST | `/api/v1/scim/v2/Users` |
| sessions | GET | `/api/v1/sessions/by-id/{session_id}` |
| sessions | DELETE | `/api/v1/sessions/history` |
| sessions | GET | `/api/v1/sessions/history` |
| sessions | DELETE | `/api/v1/sessions/threads/{thread_id}` |
| sessions | GET | `/api/v1/sessions/threads/{thread_id}` |
| sessions | DELETE | `/api/v1/sessions/threads/{thread_id}/attachment` |
| sessions | GET | `/api/v1/sessions/threads/{thread_id}/attachment` |
| sessions | POST | `/api/v1/sessions/threads/{thread_id}/attachment` |
| speech | POST | `/api/v1/speech/polish` |
| speech | GET | `/api/v1/speech/status` |
| speech | POST | `/api/v1/speech/transcribe` |
| sso | POST | `/api/v1/sso/callback` |
| sso | GET | `/api/v1/sso/login` |
| sso | GET | `/api/v1/sso/status` |
| subscriptions | GET | `/api/v1/subscriptions/payments` |
| subscriptions | GET | `/api/v1/subscriptions/plans` |
| subscriptions | GET | `/api/v1/subscriptions/portal` |
| subscriptions | GET | `/api/v1/subscriptions/status` |
| subscriptions | POST | `/api/v1/subscriptions/subscribe` |
| templates | GET | `/api/v1/templates` |
| templates | POST | `/api/v1/templates` |
| templates | GET | `/api/v1/templates/{template_id}` |
| templates | POST | `/api/v1/templates/{template_id}/generate` |
| trust | GET | `/api/v1/trust/account` |
| trust | GET | `/api/v1/trust/transactions` |
| trust | POST | `/api/v1/trust/transactions` |


---

# Appendix W — Complete Environment Variables Catalog

Every variable from project env templates. Set secrets on server only; never commit real keys.

## W..env.example
**Source file:** `.env.example` — Root application (.env)

| Variable | Example value | Notes |
|----------|---------------|-------|
| `LLM_BACKEND` | `ollama` | ============================================================================= LA |
| `CLOUD_GEMINI_KB` | `0` | Laptop/local: keep 0. AWS EC2 only: CLOUD_GEMINI_KB=1 (see deploy/aws/.env.produ |
| `LM_STUDIO_URL` | `http://127.0.0.1:1234` |  |
| `LM_STUDIO_MODEL` | `meta-llama-3.1-8b-instruct` |  |
| `OLLAMA_BASE_URL` | `http://127.0.0.1:11434` |  |
| `OLLAMA_MODEL` | `legalease-tuned` |  |
| `LLM_ROUTER_ENABLED` | `1` | Task router — defaults to OLLAMA_MODEL (legalease-tuned) for every Ollama task |
| `OLLAMA_MODEL_LEGAL` | `legalease-tuned` |  |
| `OLLAMA_MODEL_FAST` | `legalease-tuned` |  |
| `OLLAMA_MODEL_LEGAL_FALLBACK` | `legalease-tuned` |  |
| `LLM_CLASSIFY_MAX_TOKENS` | `320` | Optional Qwen (only if you explicitly set different FAST vs LEGAL models): OLLAM |
| `LLM_CLASSIFY_TIMEOUT_SEC` | `8` |  |
| `LLM_LEGAL_TIMEOUT_SEC` | `90` |  |
| `LLM_INTAKE_USE_RAG` | `1` |  |
| `LLM_INTAKE_RAG_K` | `3` |  |
| `LLM_INTAKE_FULL_ANALYSIS` | `1` |  |
| `INTAKE_PUBLIC_ENABLED` | `0` | Public website intake → assign leads to firm user/org |
| `INTAKE_PUBLIC_KEY` | `` |  |
| `INTAKE_ORG_USER_ID` | `` |  |
| `OPENROUTER_API_KEY` | `` | Web intelligence fallback chain (after Gemini quota/errors) |
| `OPENROUTER_MODEL` | `google/gemma-2-9b-it:free` |  |
| `DEEPSEEK_API_KEY` | `` |  |
| `QWEN_API_KEY` | `` |  |
| `DASHSCOPE_API_KEY` | `` |  |
| `GEMINI_API_KEY` | `` | ============================================================================== G |
| `GEMINI_FREE_MODEL` | `gemini-2.5-flash` |  |
| `WEB_INTELLIGENCE_DEBUG` | `0` |  |
| `STRICT_CITATIONS` | `0` |  |
| `LEGACY_WEB` | `0` |  |
| `JURISPRUDENCE_KB_K` | `14` |  |
| `GEMINI_DAILY_FREE` | `15` |  |
| `GEMINI_DAILY_PRO` | `200` |  |
| `GEMINI_DAILY_LEGAL_PRO` | `1000` |  |
| `GEMINI_OLLAMA_TUNING` | `0` | Settings-only: Gemini coaches Ollama via feedback analysis (never used in KB cha |
| `GEMINI_COACH_MODEL` | `gemini-2.5-flash` |  |
| `GEMINI_COACH_FEEDBACK_LIMIT` | `25` |  |
| `COACH_AUTO_SCHEDULE` | `1` | Scheduled auto-coaching (daily when new feedback exists) |
| `COACH_AUTO_INTERVAL_DAYS` | `1` |  |
| `COACH_AUTO_MIN_NEW_FEEDBACK` | `1` |  |
| `COACH_AUTO_CHECK_INTERVAL_SEC` | `1800` |  |
| `COACH_AUTO_EXPORT_MODELFILE` | `1` |  |
| `COACH_AUTO_ENABLE_ON_FEEDBACK` | `1` |  |
| `IMPROVEMENT_AUTO` | `1` | Full improvement automation — feedback → neural train → KB re-index → ollama cre |
| `OLLAMA_AUTO_REINDEX` | `1` |  |
| `OLLAMA_AUTO_CREATE` | `1` |  |
| `OLLAMA_AUTO_USE_TUNED` | `1` |  |
| `OLLAMA_AUTO_EXPORT_MIN_THUMBS` | `20` |  |
| `OLLAMA_TUNED_MODEL_NAME` | `legalease-tuned` |  |
| `OLLAMA_CREATE_TIMEOUT_SEC` | `900` |  |
| `GEMINI_KB_SYNTHESIS` | `0` | KB: Gemini NEVER answers or modifies retrieval (Ollama + indexed PDFs only) |
| `GEMINI_KB_RETRIEVAL_HINTS` | `0` |  |
| `GEMINI_KB_RERANK` | `0` |  |
| `KB_BLOCK_RUNTIME_COACH` | `1` |  |
| `KB_BLOCK_LEARNING_INJECT` | `1` |  |
| `TAVILY_API_KEY` | `` | Gemini is allowed ONLY for Settings feedback/tuning (thumbs, coach, neural expor |
| `TAVILY_SEARCH_URL` | `https://api.tavily.com/search` |  |
| `LEGAL_ONLY_WEB` | `1` | When Gemini quota is exhausted, Web Intel falls back to Tavily → Serp → Google C |
| `WEB_INTEL_FAST` | `1` | Practice SaaS — public intake form (website → CRM) INTAKE_PUBLIC_ENABLED=1 INTAK |
| `WEB_INTEL_USE_LLM` | `0` |  |
| `WEB_SKIP_TAVILY_MCP` | `1` |  |
| `WEB_PREFER_TAVILY_REST` | `1` |  |
| `WEB_SEARCH_MAX_RESULTS` | `6` |  |
| `TAVILY_REST_TIMEOUT` | `12` |  |
| `TAVILY_MCP_TIMEOUT` | `8` |  |
| `WEB_LLM_MAX_TOKENS_FAST` | `900` |  |
| `WEB_LLM_MAX_TOKENS_CASE` | `1100` |  |
| `OCR_ENABLED` | `1` | OCR (EasyOCR) |
| `OCR_LANGUAGES` | `en` |  |
| `OCR_GPU` | `0` |  |
| `GOOGLE_API_KEY` | `` | Google Custom Search JSON API (optional — legacy; new Google CSE signups often b |
| `GOOGLE_CSE_ID` | `` |  |
| `SERP_API_KEY` | `` | SerpAPI — Google results fallback when Tavily fails (https://serpapi.com) |
| `SERP_TIMEOUT` | `10` |  |
| `SERP_ENGINE` | `google` |  |
| `HF_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | RAG/Uploads Embeddings for RAG (never use LLM for vectors) |
| `HF_EMBEDDING_FALLBACK` | `BAAI/bge-base-en-v1.5` |  |
| `RAG_PREFER_BASE_EMBEDDINGS` | `1` | 1 = fast MiniLM at startup/KB (recommended). 0 = load fine-tuned weights (slower |
| `RAG_USE_LANGCHAIN_HF` | `0` | 0 = SentenceTransformer only (recommended on Windows; avoids WinError 1455 from  |
| `RAG_SCORE_THRESHOLD` | `1.6` |  |
| `RAG_CONFIDENCE_THRESHOLD` | `0.52` |  |
| `RAG_ENABLE_CROSS_ENCODER` | `0` | 0 = fast heuristic reranking (recommended on CPU). 1 = cross-encoder (slower, sl |
| `RAG_RERANK_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` |  |
| `RAG_RERANK_POOL_SIZE` | `12` |  |
| `MAX_UPLOAD_MB` | `200` |  |
| `PDF_MAX_PAGES` | `0` | Large PDFs: 0 = no page cap; sparse OCR only on low-text pages (fast) |
| `OCR_MAX_PAGES` | `0` |  |
| `OCR_SPARSE_ONLY` | `1` |  |
| `OCR_WORKERS` | `4` |  |
| `OCR_MIN_CHARS_PER_PAGE` | `120` |  |
| `RAG_CHUNK_SIZE` | `1000` |  |
| `RAG_CHUNK_OVERLAP` | `200` |  |
| `RAG_MAX_CHUNK` | `1400` |  |
| `RAG_INDEX_EMBED_BATCH` | `128` | Chunks embedded per batch during index build (64 = faster; lower if RAM is tight |
| `RAG_FAST_INDEX` | `1` |  |
| `INDEX_JOB_WORKERS` | `1` |  |
| `INDEX_JOB_USE_PROCESS` | `1` |  |
| `RAG_MAX_QUERY_EXPANSIONS` | `5` |  |
| `RAG_TOP_K_KEYWORD` | `24` |  |
| `FAISS_VS_CACHE_MAX` | `8` |  |
| `OLLAMA_KB_LOCK_MODEL` | `1` |  |
| `PDF_UPLOAD_TIMEOUT_SEC` | `900` |  |
| `KB_PIPELINE_DEBUG` | `1` | KB pipeline |
| `KB_CACHE_TTL_SEC` | `300` |  |
| `KB_CACHE_MAX_ENTRIES` | `256` |  |
| `RATE_LIMIT_ENABLED` | `1` | API rate limiting |
| `RATE_LIMIT_PER_MINUTE` | `120` |  |
| `RATE_LIMIT_CHAT_PER_MINUTE` | `40` |  |
| `RATE_LIMIT_CHAT_EXEMPT` | `1` | Messaging exempt by default — Firm Chat, voice notes, AI assistant (no 429) |
| `RATE_LIMIT_COLLAB_EXEMPT` | `1` |  |
| `SECURITY_HEADERS_ENABLED` | `1` | ============================================================================== S |
| `FORCE_HTTPS` | `1` |  |
| `HSTS_MAX_AGE` | `31536000` |  |
| `DATA_ENCRYPTION_KEY` | `` | Fernet key for optional field encryption at rest: py -c "from backend.app.core.c |
| `FIREWALL_ENABLED` | `0` | Application-layer IP allowlist (comma-separated). Off by default. If FIREWALL_EN |
| `FIREWALL_ALLOWED_IPS` | `` |  |
| `FIREWALL_TRUST_PROXY` | `1` |  |
| `CORS_ALLOW_LOCALHOST_REGEX` | `0` | Production: disable localhost CORS regex (strict HTTPS origins only) |
| `PASSWORD_MIN_LENGTH` | `12` |  |
| `RAG_RETRIEVAL_K` | `8` | Retrieval depth (defaults in code: comparison k=10, summary k=12) |
| `RAG_FINAL_TOP_K` | `10` |  |
| `RAG_TOP_K_DENSE` | `16` |  |
| `RAG_MMR_LAMBDA` | `0.7` |  |
| `LEGALEASE_DB_PATH` | `` | ============================================================================== D |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |  |
| `SESSION_TTL_SEC` | `86400` |  |
| `JWT_SECRET` | `change-me-in-production` |  |
| `PUBLIC_APP_URL` | `http://localhost:3000` | Client portal / e-sign / public app URL for mock sign links |
| `ESIGN_PROVIDER` | `mock` |  |
| `LLM_FINETUNE_ENABLED` | `1` | In-app LLM LoRA SFT/DPO + inference-time RLHF/RLAIF |
| `LLM_FINETUNE_AUTO` | `1` |  |
| `LLM_FINETUNE_BASE_MODEL` | `google/gemma-2-2b-it` |  |
| `LLM_FINETUNE_MIN_SFT` | `5` |  |
| `LLM_FINETUNE_MIN_DPO` | `2` |  |
| `LLM_USE_TRAINED_ADAPTER` | `1` |  |
| `INFERENCE_REWARD_ENABLED` | `1` |  |
| `INFERENCE_REWARD_RERANK` | `1` |  |
| `CHAT_COACH_RUNTIME` | `1` |  |
| `CHAT_COACH_POSITIVE_EVERY` | `3` |  |
| `GPU_PROFILE` | `balanced` | GPU profile for 6GB VRAM laptops (RTX 4050): balanced / max_stt / max_chat — see |
| `STT_ENABLED` | `1` | Speech-to-text (faster-whisper; lazy-loaded on first mic press — requires ffmpeg |
| `STT_ENGINE` | `faster_whisper` |  |
| `STT_MODEL` | `small` |  |
| `STT_DEVICE` | `cuda` |  |
| `STT_COMPUTE_TYPE` | `float16` |  |
| `STT_PRELOAD` | `0` |  |
| `STT_MAX_SECONDS` | `90` |  |
| `STT_MAX_UPLOAD_MB` | `12` |  |
| `STT_FALLBACK_BROWSER` | `1` |  |
| `STT_POLISH_DEFAULT` | `0` |  |
| `KB_LLM_TEMPERATURE` | `0.23` | KB strict grounding (Ollama paraphrase only — documents are source of truth) |
| `RAG_MIN_ACCEPT_SCORE` | `0.50` |  |
| `KB_INDEX_MIN_VECTORS_WARN` | `20` |  |
| `KB_LLM_TOP_P` | `0.1` |  |
| `SAAS_PRODUCTION` | `0` | ============================================================================== P |
| `SAAS_PRODUCTION_STRICT` | `1` | Set SAAS_PRODUCTION=1 on public deploy — enforces Stripe, blocks mock billing, v |
| `ALLOW_MOCK_BILLING` | `1` |  |
| `SAAS_AUTO_POSTGRES_LEGACY` | `1` | With DATABASE_URL=postgresql://..., auto-read auth/chat from Postgres in product |
| `SAAS_USE_POSTGRES_LEGACY` | `0` |  |
| `ML_USE_QUEUE` | `1` | ML jobs off API thread (requires Redis + py scripts/ml_worker.py or docker ml-wo |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |  |
| `PLAN_DOC_LIMIT_FREE` | `2` |  |
| `PLAN_DOC_LIMIT_PRO` | `500` |  |
| `PLAN_DOC_LIMIT_LEGAL_PRO` | `5000` |  |
| `JWT_SECRET` | `change_this_jwt_secret_min_32_chars` |  |
| `LEGALEASE_API_SECRET` | `` |  |
| `REDIS_URL` | `redis://127.0.0.1:6379/0` |  |
| `PUBLIC_APP_URL` | `http://localhost:3000` |  |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0....` |  |
| `STRIPE_SECRET_KEY` | `` | Stripe (subscription payments — /settings/subscription) |
| `STRIPE_WEBHOOK_SECRET` | `` |  |
| `STRIPE_PRICE_PRO` | `` |  |
| `STRIPE_PRICE_LEGAL_PRO` | `` |  |
| `STRIPE_PRICE_PRO_INR` | `999` |  |
| `STRIPE_PRICE_LEGAL_PRO_INR` | `4999` |  |
| `STRIPE_SUCCESS_PATH` | `/settings/subscription?checkout=success` |  |
| `STRIPE_CANCEL_PATH` | `/settings/subscription?checkout=cancel` |  |
| `MATTER_STRICT_SCOPE_ENFORCEMENT` | `1` | Matter / org hardening |
| `MATTER_STRICT_ROLE_WRITE` | `1` |  |
| `LEARNING_SCOPE_PROMOTION_ENABLED` | `0` |  |
| `ORG_SEATS_FREE` | `1` |  |
| `ORG_SEATS_PRO` | `3` |  |
| `ORG_SEATS_LEGAL_PRO` | `10` |  |
| `EMAIL_PROVIDER` | `console` | ============================================================================== P |
| `EMAIL_FROM` | `noreply@your-domain.com` |  |
| `EMAIL_FROM_NAME` | `LegalEase` |  |
| `SUPERADMIN_USERNAMES` | `admin` | ============================================================================== P |

## W..env.local.example
**Source file:** `.env.local.example` — Laptop overrides (.env.local)

| Variable | Example value | Notes |
|----------|---------------|-------|
| `LEGALEEASE_LOCAL_DEV` | `1` |  |
| `SAAS_PRODUCTION` | `0` |  |
| `SAAS_PRODUCTION_STRICT` | `0` |  |
| `SAAS_USE_POSTGRES_LEGACY` | `0` |  |
| `SAAS_ALL_FEATURES_FREE` | `1` |  |
| `SAAS_ALLOW_FREE_HYBRID` | `1` |  |
| `ALLOW_MOCK_BILLING` | `1` |  |
| `DATABASE_URL` | `` |  |
| `LLM_BACKEND` | `ollama` |  |
| `CLOUD_GEMINI_KB` | `0` |  |
| `OLLAMA_AUTO_START` | `1` |  |
| `CORS_ORIGINS` | `http://localhost:3000,http://127.0.0....` |  |
| `CORS_ALLOW_LOCALHOST_REGEX` | `1` |  |
| `PUBLIC_APP_URL` | `http://localhost:3000` |  |
| `NEXT_PUBLIC_API_URL` | `http://127.0.0.1:8000` |  |
| `NEXT_PUBLIC_APP_URL` | `http://localhost:3000` |  |

## W..env.docker.example
**Source file:** `.env.docker.example` — Docker Compose local production

| Variable | Example value | Notes |
|----------|---------------|-------|
| `POSTGRES_USER` | `legalease` | --- Secrets (change in production) --- |
| `POSTGRES_PASSWORD` | `change_this_strong_password` |  |
| `POSTGRES_DB` | `legalease` |  |
| `JWT_SECRET` | `change_this_jwt_secret_min_32_chars` |  |
| `LEGALEASE_API_SECRET` | `change_this_api_secret_min_32_chars` |  |
| `DATABASE_URL` | `postgresql://legalease:change_this_st...` | PostgreSQL — all app tables when SAAS_USE_POSTGRES_LEGACY=1 (Docker default) |
| `SAAS_USE_POSTGRES_LEGACY` | `1` |  |
| `SAAS_AUTO_POSTGRES_LEGACY` | `1` |  |
| `SAAS_PRODUCTION` | `1` |  |
| `LEGALEASE_DB_PATH` | `/data/legalease.db` | Optional SQLite fallback path (unused when legacy Postgres is on) |
| `REDIS_URL` | `redis://redis:6379/0` | Redis — sessions + ML/e-discovery job queues |
| `SESSION_TTL_SEC` | `86400` |  |
| `ML_USE_QUEUE` | `1` |  |
| `NEXT_PUBLIC_API_URL` | `https://your-domain.com/api` | Frontend must call API through nginx (/api prefix) |
| `CORS_ORIGINS` | `https://your-domain.com` |  |
| `PUBLIC_APP_URL` | `https://your-domain.com` |  |
| `LLM_BACKEND` | `lmstudio` | LLM — LM Studio on host or Ollama sidecar |
| `LM_STUDIO_URL` | `http://host.docker.internal:1234` |  |
| `LM_STUDIO_MODEL` | `meta-llama-3.1-8b-instruct` |  |
| `GEMINI_API_KEY` | `` | Gemini (Open Law / Hybrid) |
| `GEMINI_DAILY_FREE` | `15` |  |
| `GEMINI_DAILY_PRO` | `200` |  |
| `GEMINI_DAILY_LEGAL_PRO` | `1000` |  |
| `EMAIL_PROVIDER` | `console` | Email (console / smtp / sendgrid) |
| `EMAIL_FROM` | `noreply@your-domain.com` |  |
| `SMTP_HOST` | `` |  |
| `SMTP_PORT` | `587` |  |
| `SMTP_USER` | `` |  |
| `SMTP_PASSWORD` | `` |  |
| `SENDGRID_API_KEY` | `` |  |
| `STRIPE_SECRET_KEY` | `` | Stripe subscriptions |
| `STRIPE_WEBHOOK_SECRET` | `` |  |
| `STRIPE_PRICE_PRO` | `` |  |
| `STRIPE_PRICE_LEGAL_PRO` | `` |  |
| `SUPERADMIN_USERNAMES` | `admin` | Admin + monitoring |
| `SENTRY_DSN` | `` |  |
| `SENTRY_ENVIRONMENT` | `production` |  |
| `SENTRY_TRACES_SAMPLE_RATE` | `0.1` |  |
| `RAG_ENABLE_CROSS_ENCODER` | `0` | Performance |
| `KB_PIPELINE_DEBUG` | `0` |  |
| `RATE_LIMIT_ENABLED` | `1` |  |
| `TAVILY_API_KEY` | `` |  |

## W.deploy/aws/.env.production.example
**Source file:** `deploy/aws/.env.production.example` — EC2 production template

| Variable | Example value | Notes |
|----------|---------------|-------|
| `POSTGRES_USER` | `legalease` |  |
| `POSTGRES_PASSWORD` | `(set on server - see section 7.4.5)` |  |
| `POSTGRES_DB` | `legalease` |  |
| `JWT_SECRET` | `(set on server - rotate_secrets.ps1)` |  |
| `LEGALEASE_API_SECRET` | `(set on server - rotate_secrets.ps1)` |  |
| `DATA_ENCRYPTION_KEY` | `(set on server - rotate_secrets.ps1)` |  |
| `DATABASE_URL` | `postgresql://legalease:POSTGRES_PASSW...` |  |
| `SAAS_USE_POSTGRES_LEGACY` | `1` |  |
| `SAAS_AUTO_POSTGRES_LEGACY` | `1` |  |
| `SAAS_PRODUCTION` | `1` |  |
| `SAAS_PRODUCTION_STRICT` | `1` |  |
| `ALLOW_MOCK_BILLING` | `0` |  |
| `LEGALEASE_DB_PATH` | `/data/legalease.db` |  |
| `REDIS_URL` | `redis://redis:6379/0` |  |
| `SESSION_TTL_SEC` | `86400` |  |
| `ML_USE_QUEUE` | `1` |  |
| `PUBLIC_APP_URL` | `https://legalease.duckdns.org` |  |
| `CORS_ORIGINS` | `https://legalease.duckdns.org` |  |
| `CORS_ALLOW_LOCALHOST_REGEX` | `0` |  |
| `NEXT_PUBLIC_API_URL` | `https://legalease.duckdns.org/api` |  |
| `LLM_BACKEND` | `gemini` |  |
| `GEMINI_API_KEY` | `(set on server - rotate_secrets.ps1)` |  |
| `GEMINI_KB_SYNTHESIS` | `0` |  |
| `CLOUD_GEMINI_KB` | `1` |  |
| `LEGALEEASE_HF_CACHE` | `/data/hf_cache` |  |
| `HF_HOME` | `/data/hf_cache` |  |
| `LOW_RESOURCE_MODE` | `1` |  |
| `RAG_ENABLE_CROSS_ENCODER` | `0` |  |
| `EMAIL_PROVIDER` | `brevo` |  |
| `BREVO_API_KEY` | `` |  |
| `STRIPE_SECRET_KEY` | `` |  |
| `STRIPE_WEBHOOK_SECRET` | `` |  |
| `STRIPE_PRICE_PRO` | `` |  |
| `STRIPE_PRICE_LEGAL_PRO` | `` |  |
| `FORCE_HTTPS` | `1` |  |
| `SECURITY_HEADERS_ENABLED` | `1` |  |
| `RATE_LIMIT_ENABLED` | `1` |  |
| `FIREWALL_ENABLED` | `0` |  |
| `FIREWALL_ALLOWED_IPS` | `` |  |
| `FIREWALL_TRUST_PROXY` | `1` |  |
| `SUPERADMIN_USERNAMES` | `admin` |  |


---

*Complete documentation built 2026-06-05 17:35 UTC. Production URL: https://legalease.duckdns.org*
