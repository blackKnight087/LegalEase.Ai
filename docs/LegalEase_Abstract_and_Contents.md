# LegalEase.AI — Abstract & Contents

**Product:** LegalEase.AI (Legal_AI_Final 3)  
**Version:** 3.0  
**Date:** June 2026  
**Market:** Indian legal practice (advocates, law firms, in-house counsel)

---

## Abstract

LegalEase.AI is an AI-powered legal intelligence SaaS for Indian law practice, integrating matter management, OCR document ingestion (EasyOCR/Tesseract), drafting studio, CRM, billing, litigation OS, and an Evidence Intelligence Center. Its conversational layer exposes three research modes only: Knowledge Base (RAG over uploaded PDFs with cited filenames and NOT_FOUND safeguards), Web Intel (Gemini-grounded live Indian law research with Tavily/Serp fallbacks), and Hybrid (KB evidence merged with live web synthesis).

The AI engine combines per-user and per-matter FAISS indexes, dense-plus-sparse hybrid retrieval, MMR diversification, cross-encoder reranking, and intent routing for IPC/BNS sections, comparisons, constitutional queries, and case captions, delivered through SSE-streamed chat using local Ollama (legalease-tuned) and cloud Gemini. Model improvement is layered: adaptive learning retunes query expansion and chunk boosts from thumbs feedback without GPU retraining; SentenceTransformer embedding fine-tuning learns firm-specific dense retrieval; in-app LoRA supervised fine-tuning and DPO optimize chat adapters from human preference pairs; RLHF/RLAIF reward shaping guides style; JSONL and Ollama Modelfile exports enable external model refresh after verified coaching data.

Built on Next.js 15, FastAPI, SQLite/PostgreSQL, Redis, Docker/nginx, with persistent threads, long-term attorney memory, 503+ REST routes, 126+ pytest tests, and premium tools—BNS compliance audit, witness simulation, deal-room diligence, AI redlining, and PII redaction—for secure production deployment.

**Word count:** 200

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Problem Statement](#2-problem-statement)
3. [Product Overview](#3-product-overview)
4. [Three Chat Research Modes](#4-three-chat-research-modes)
5. [System Architecture](#5-system-architecture)
6. [Knowledge Base & RAG Pipeline](#6-knowledge-base--rag-pipeline)
7. [LLM Integration Strategy](#7-llm-integration-strategy)
8. [Model Training & Continuous Learning](#8-model-training--continuous-learning)
9. [Practice Management Modules](#9-practice-management-modules)
10. [Premium Legal Intelligence Suite](#10-premium-legal-intelligence-suite)
11. [Security, Multi-Tenancy & Compliance](#11-security-multi-tenancy--compliance)
12. [Deployment & Operations](#12-deployment--operations)
13. [Testing & Quality Assurance](#13-testing--quality-assurance)
14. [Conclusion](#14-conclusion)

---

## 1. Introduction

LegalEase.AI is a full-stack legal practice platform that unifies document-grounded artificial intelligence with day-to-day law firm operations. Unlike generic chatbots that answer from public internet knowledge alone, LegalEase anchors every Knowledge Base response to uploaded evidence—statutes, judgments, contracts, FIRs, affidavits, and firm reference libraries—while offering separate modes for live public-law research and fused hybrid analysis.

The platform is purpose-built for **Indian jurisdiction**: IPC/BNS section mapping, constitutional article retrieval, landmark case captions, Bharatiya Sanhita transition tooling, and Hindi/regional language support. It serves solo advocates on a free tier, growing firms on Pro plans, and enterprise teams requiring org RBAC, audit trails, and higher document quotas.

This document describes the product architecture, the three conversational research modes, retrieval-augmented generation internals, and the multi-layer model training pipeline that improves accuracy from attorney feedback without requiring full model retraining on every interaction.

---

## 2. Problem Statement

Indian legal practitioners face three structural challenges:

1. **Volume and transition** — Statutes are migrating (IPC → BNS, CrPC → BNSS). Case files are large PDF corpora. Manual search cannot scale with caseload growth.

2. **Confidentiality vs. intelligence** — Cloud LLMs answer general questions but must not invent facts from client documents. Firms need **cited answers from their own files** plus **live public law** when internal documents are insufficient.

3. **Tool fragmentation** — Research, drafting, intake, billing, discovery, and collaboration typically live in disconnected products, increasing cost and context-switching during litigation cycles.

LegalEase addresses these by combining private RAG indexes, grounded web intelligence, matter-scoped case files, and practice-management workflows in one deployable SaaS stack.

---

## 3. Product Overview

### 3.1 Vision

Become the default **AI-native practice operating system** for Indian law: every matter has scoped documents, every research query is logged and improvable, and every tenant is isolated, billable, and auditable.

### 3.2 Core Modules

| Module | Purpose |
|--------|---------|
| **Chat & Research** | Three-mode conversational AI (KB, Web Intel, Hybrid) |
| **Documents & KB** | Upload, OCR, chunk, index, re-index global and matter-scoped libraries |
| **Matters** | Case files, timelines, hearings, matter-scoped AI workspace |
| **Drafting Studio** | AI-assisted drafting with redline/diff engine |
| **CRM & Intake** | Lead pipeline, kanban, client conversion to matters |
| **Billing & Trust** | Time entries, invoices, trust accounting hooks |
| **Litigation OS** | Mission control, deadlines, workflow automation |
| **Evidence Intelligence** | E-discovery desk, batch processing, privilege review |
| **Enterprise Hub** | Firm-wide search, workspaces, knowledge governance |
| **Premium Suite** | Witness sim, BNS audit, deal rooms, PII redaction |
| **Settings & Memory** | Persona, facts, coaching, model training controls |

### 3.3 Subscription Tiers

| Tier | Documents | Hybrid Mode | Org Seats | Gemini Quota |
|------|-----------|-------------|-----------|--------------|
| Free | 2 | No | 1 | 15/day |
| Pro | 500 | Yes | 3 | 200/day |
| Legal Pro | 5,000 | Yes | 10 | 1,000/day |

---

## 4. Three Chat Research Modes

The main chat interface (`ModePills.tsx`) exposes **exactly three user-facing modes**. Backend aliases (`open_law`, `web_search`, `deep_case`) normalize to these routes; there is no fourth global chat pill.

### 4.1 Knowledge Base

- **UI label:** Knowledge Base (KB)
- **Engine:** FAISS + hybrid retrieval + local Ollama (`legalease-tuned`)
- **Scope:** Global unlinked reference documents (statutes, compilations, firm libraries)—**not** matter-linked case files in main chat
- **Policy:** Answers only from indexed uploads; returns cited filename/section; explicit NOT_FOUND when evidence is absent
- **Gemini policy:** Blocked from synthesizing KB answers (`GEMINI_KB_SYNTHESIS=0`)

### 4.2 Web Intel

- **UI label:** Web Intel
- **API mode:** `web_search` / `open_law`
- **Engine:** Gemini grounded legal research with Tavily, SerpAPI, DuckDuckGo fallbacks
- **Scope:** Live Indian public law—statutes, courts, gazettes, landmark judgments
- **Use case:** Research when no upload is required or KB has no relevant document

### 4.3 Hybrid

- **UI label:** Hybrid
- **Engine:** KB retrieval + Gemini web synthesis (jurisprudence fusion)
- **Scope:** Uploaded document evidence **merged** with live web intelligence
- **Plan gate:** Pro and Legal Pro tiers only; Free tier downgrades to Knowledge Base
- **Use case:** Compare firm documents against current public law; comprehensive research reports

### 4.4 Matter-Scoped AI (Separate from Main Chat)

The **Matter workspace** provides additional AI modes (`matter_only`, `hybrid`, `chronology`, `hearing_prep`, `evidence`) scoped to that case file's indexed documents. This is distinct from the three global chat pills.

---

## 5. System Architecture

```
Browser (Next.js 15 / React 19)
    ↓ REST + SSE streaming
nginx (TLS, reverse proxy)
    ↓
FastAPI 3.0 API (503+ routes, 38 endpoint modules)
    ↓
┌─────────────────┬──────────────────┬─────────────────┐
│ SQLite /        │ Redis            │ FAISS indexes   │
│ PostgreSQL      │ sessions, queues │ per-user/matter │
└─────────────────┴──────────────────┴─────────────────┘
    ↓
Ollama (local KB synthesis)  |  Gemini (web/hybrid)  |  Background workers
```

**Key services:** `chat_service.py`, `kb_pipeline.py`, `legal_orchestrator_v2.py`, `rag.py`, `adaptive_learning.py`, `neural_finetuning.py`, `llm_finetuning.py`

**Frontend:** 50 pages, persistent chat threads, sidebar history, URL deep-link `/?thread=<uuid>`, rate-limit-aware API client with 429 retry.

---

## 6. Knowledge Base & RAG Pipeline

### 6.1 Document Ingestion

1. PDF upload (global or matter-linked)
2. OCR gate (~150 chars/page) → EasyOCR or Tesseract when needed
3. Chunking with legal section detection (IPC, BNS, Article markers)
4. Embedding via SentenceTransformer (with optional per-user fine-tuned weights)
5. FAISS index build (`global_kb`, `_unlinked`, or `matter/{id}`)

### 6.2 Retrieval Stack

| Stage | Technique |
|-------|-----------|
| Query parsing | Intent classification: single section, comparison, constitutional, case law, document QA |
| Expansion | Follow-up merge, session memory, adaptive learned expansions |
| Dense search | FAISS cosine similarity |
| Sparse search | BM25-style lexical recall |
| Fusion | Hybrid scoring, MMR diversification |
| Rerank | Optional cross-encoder reranking |
| Validation | `kb_rag_decision.evaluate_retrieval()` — threshold, off-topic gate |
| Synthesis | Ollama structured answer with source footer |
| Enforcement | NOT_FOUND template when chunks fail validation |

### 6.3 Strict Scoping Rules

- **Global KB chat** searches unlinked/global indexes only—matter-linked documents are filtered out
- **Matter AI** searches matter index when `matter_mode` is set (witness, evidence, chronology)
- **Hybrid mode** retrieves global KB + matter chunks with strict separation and relevance gates

---

## 7. LLM Integration Strategy

| Duty | Model | When Used |
|------|-------|-----------|
| KB answer synthesis | Ollama `legalease-tuned` | Knowledge Base mode |
| Web research | Gemini (grounded) | Web Intel mode |
| Hybrid fusion | Gemini + KB chunks | Hybrid mode |
| Style coaching | Gemini (RLAIF, style-only) | Settings coach—not legal substance |
| Embeddings | SentenceTransformer / fine-tuned MiniLM | All retrieval |
| Speech | Whisper STT | Voice input |

**Design principle:** Local LLM for confidential document answers; cloud Gemini only for public web intel and hybrid reports. Enforced in `kb_gemini_safety.py` and `llms.py`.

---

## 8. Model Training & Continuous Learning

LegalEase improves through **five complementary layers**—not a single fine-tune button:

### 8.1 Adaptive Learning (No GPU)

**Module:** `adaptive_learning.py`

- Logs every interaction with mode, query, chunks, scores
- Thumbs up/down adjust **chunk reranking boosts** and **query expansion patterns**
- Per-user, per-mode statistics (hit rate, not-found rate)
- Implicit signals: re-asks, corrections, NOT_FOUND recovery
- Improves RAG routing like production feedback loops—**no neural weight updates**

### 8.2 Embedding Fine-Tuning (SentenceTransformer)

**Module:** `neural_finetuning.py`

- Collects (query, positive_passage) pairs from thumbs-up and successful KB turns
- Trains MiniLM-family SentenceTransformer on firm-specific phrasing
- Per-user scope under `Data/fine_tuned_models/embeddings/{user_id}/`
- Auto-trains when minimum pair threshold reached; triggers FAISS re-index
- Improves **dense retrieval quality** on uploaded documents

### 8.3 LLM LoRA Fine-Tuning (SFT + DPO)

**Module:** `llm_finetuning.py`

- **LoRA supervised fine-tuning (SFT)** on verified thumbs-up Q→A pairs
- **DPO (Direct Preference Optimization)** on chosen vs. rejected answer pairs
- Base model: configurable (default Gemma-2-2B-IT); adapters loaded at inference
- GPU-required; runs in background worker thread
- Per-user adapter paths under `Data/fine_tuned_models/llm/`

### 8.4 Human Training Pipeline (RLHF / RLAIF)

**Module:** `human_training.py`

- **SFT pairs:** Only from verified human approval—never auto-generated legal Q→A
- **Preference pairs:** chosen (thumbs-up) vs. rejected (thumbs-down) on similar queries
- **RLHF rewards:** Human signal weights (`HUMAN_REWARD_WEIGHT`)
- **RLAIF rewards:** Gemini scores **style only**—never legal correctness (`GEMINI_RLAIF_STYLE`)
- Exports: `export_sft_jsonl()`, `export_dpo_jsonl()`

### 8.5 Ollama Model Export

**Module:** `tuning_export.py`, `improvement_automation.py`

- Exports coaching dataset as **training.jsonl** + **Modelfile**
- Builds per-user Ollama model (e.g. `legalease-tuned`) for local KB synthesis
- Automation log: `Data/ollama_exports/{user_id}/`
- Enables external refresh without in-app GPU training

### 8.6 Training Data Flow

```
User chat → thumbs feedback → adaptive_interactions table
                          ↓
              ┌───────────┴───────────┐
              ↓                       ↓
    neural_tuning_pairs      preference_pairs / human_labels
              ↓                       ↓
    SentenceTransformer train   LoRA SFT + DPO
              ↓                       ↓
         FAISS re-index          Adapter at inference
              ↓                       ↓
         Better retrieval        Better synthesis style
                          ↓
              Ollama JSONL export → legalease-tuned refresh
```

---

## 9. Practice Management Modules

### 9.1 Matters & Case Files

- Matter types: Criminal, Civil, Family, Corporate, Property, etc.
- Per-matter document upload, FAISS index, timeline, hearings, next-date tracking
- Matter AI panel with scoped modes (matter_only, chronology, hearing_prep, evidence)

### 9.2 Documents

- Global KB library vs. matter-linked uploads
- Index All / Re-index, queue status, embedding health dashboard
- Document classification, section extraction, IPC/BNS tagging

### 9.3 Drafting Studio

- Instruction-based document revision
- AI redline engine with visual diff
- Template library and export

### 9.4 CRM & Billing

- Kanban intake pipeline with AI enrichment
- Client portal hooks, time entries, invoices, trust accounts
- Stripe subscription integration

### 9.5 Litigation OS & Evidence Desk

- Mission control dashboard, deadline alerts
- E-discovery batch jobs, privilege log, document review queues
- Firm chat with real-time WebSocket fan-out

---

## 10. Premium Legal Intelligence Suite

| Feature | Module | Function |
|---------|--------|----------|
| Witness Simulator | `premium_services/` | Mock cross-examination with disposition modes |
| BNS Auditor | IPC→BNS compliance line scan | Statute migration risk flags |
| Deal Rooms | Multi-doc M&A diligence | Contradiction and indemnity detection |
| Redline Engine | Drafting Studio | AI revision with tracked changes |
| PII Redactor | Regex + spaCy NER | Detect and redact sensitive entities |
| Judicial Analytics | Judgments DB | Bail rates, disposition breakdowns |
| IPC/BNS Engine v3 | Migration impact | Matter-level statute mapping |

---

## 11. Security, Multi-Tenancy & Compliance

- **Authentication:** HMAC JWT, session store (Redis), org RBAC
- **Tenant isolation:** Per-user FAISS paths, per-user embedding models, per-user Ollama exports
- **Matter scope enforcement:** `matter_policy.py` — KB chat ignores UI matter selection; matter scope only for matter AI and hybrid/deep_case
- **Rate limiting:** Read/write/auth buckets; 429-friendly frontend retry
- **IP firewall & memory guard:** Operator-configurable protection
- **Audit logging:** Admin actions, chat scope decisions, matter access denials
- **GDPR hooks:** Account export and deletion endpoints
- **PII handling:** Redaction module; coach blocked from injecting legal substance

---

## 12. Deployment & Operations

### 12.1 Stack

| Component | Technology |
|-----------|------------|
| Frontend | Next.js 15, React 19, Tailwind |
| Backend | FastAPI, Uvicorn, Python 3.12 |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Cache/Session | Redis |
| Vector store | FAISS on disk |
| LLM local | Ollama (`legalease-tuned`) |
| LLM cloud | Google Gemini |
| Proxy | nginx TLS |
| Containers | Docker Compose |

### 12.2 Environments

- **Local dev:** `run_backend.ps1`, `run_web.ps1`, Ollama on laptop GPU
- **Production:** `https://legalease.duckdns.org` (EC2), Docker stack
- **Key env vars:** `LLM_BACKEND=ollama`, `DATABASE_URL`, `REDIS_URL`, `GEMINI_API_KEY`, `NEURAL_FINETUNE_ENABLED`, `LLM_FINETUNE_ENABLED`

### 12.3 Observability

- KB retrieval debug console (`KB_RETRIEVAL_DEBUG`)
- Health endpoints: `/api/v1/kb/health`, embedding queue snapshot
- Sentry integration, structured event emission

---

## 13. Testing & Quality Assurance

- **126+ pytest tests** across KB, RAG, memory, premium, OCR, enterprise DB, chat modes
- **CI pipeline:** GitHub Actions — Python tests + Next.js production build on every push/PR
- **Key test suites:** `test_kb_retrieval_fixes.py`, `test_neural_finetuning.py`, `test_chat_mode_api.py`, `test_kb_document_scoping.py`
- **Runbook:** `RUNBOOK.md`, `DEPLOY.md`, operator health checks

---

## 14. Conclusion

LegalEase.AI delivers a production-grade, Indian-law-focused legal intelligence platform that separates **document-grounded answers**, **live web research**, and **hybrid fusion** into three clear chat modes. Its RAG pipeline combines modern retrieval techniques with strict evidence enforcement, while a layered training stack—adaptive learning, embedding fine-tuning, LoRA SFT/DPO, RLHF/RLAIF, and Ollama export—continuously improves accuracy from real attorney feedback.

Integrated with matter management, drafting, CRM, billing, e-discovery, and premium litigation tools, LegalEase represents a unified AI-native practice operating system designed for confidentiality, citation integrity, and scalable SaaS deployment.

---

*Document generated from Legal_AI_Final 3 production codebase — June 2026.*
