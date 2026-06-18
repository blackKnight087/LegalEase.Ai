# LegalEase — AI Legal Practice Platform

> **Recruiter quick view:** [Live app](https://legalease.duckdns.org) · [Architecture doc](docs/LegalEase_System_Architecture.html) · `backend/` + `web/` + `tests/` in this repo

Full-stack legal-tech SaaS for Indian law: RAG knowledge base, hybrid web intel, matter workspace, firm collaboration, and model-assisted drafting — deployed on AWS EC2 with PostgreSQL.

| Link | What to open |
|------|----------------|
| **Live product** | [https://legalease.duckdns.org](https://legalease.duckdns.org) — register, try Knowledge Base / Firm Chat |
| **This repo** | `backend/app/` (FastAPI), `web/` (Next.js), `tests/`, `deploy/` |
| **Architecture** | [docs/LegalEase_System_Architecture.html](docs/LegalEase_System_Architecture.html) |

---

## Highlights (for reviewers)

| Area | What it does |
|------|----------------|
| **Knowledge Base** | Upload PDFs → FAISS + hybrid retrieval → grounded answers with citations |
| **Web Intel** | Live legal research via Gemini + structured citations |
| **Hybrid mode** | Combines private KB with web sources |
| **Firm Chat** | User search, chat requests, DMs, practice channels (real-time) |
| **Matter OS** | Cases, hearings, tasks, documents, e-discovery triage |
| **Legal tools** | IPC↔BNS mapping, drafting studio, court sync, billing |
| **Training stack** | Adaptive learning, embedding fine-tuning, LoRA/DPO export paths |

---

## Tech stack

| Layer | Technologies |
|-------|----------------|
| Frontend | Next.js 15, React, TypeScript, Tailwind |
| Backend | FastAPI, Python 3.12, 500+ REST routes |
| Data | PostgreSQL, Redis, SQLite legacy bridge |
| AI / RAG | FAISS, SentenceTransformers, cross-encoder rerank, MMR |
| LLM | Ollama (`legalease-tuned`) locally · Gemini in production |
| Deploy | Docker Compose, nginx, AWS EC2, DuckDNS |
| Tests | pytest (126+ tests) |

---

## Architecture

```
Browser → nginx → Next.js (web) → FastAPI (api)
                      ↓
              PostgreSQL + Redis
                      ↓
         FAISS indexes · Gemini / Ollama · Firm Chat (SSE/WS)
```

Detailed docs: [`docs/LegalEase_System_Architecture.html`](docs/LegalEase_System_Architecture.html) · [`docs/LegalEase_Abstract_and_Contents.md`](docs/LegalEase_Abstract_and_Contents.md)

---

## Run locally (developers)

**Prerequisites:** Node 18+, Python 3.12+, optional Ollama

```powershell
# 1. Copy env template (never commit real .env)
copy .env.example .env

# 2. Backend (port 8000)
.\run_backend.ps1

# 3. Frontend (port 3000) — separate terminal
.\run_web.ps1
```

Open http://localhost:3000

**Laptop dev env:** run `.\scripts\setup_local_env.ps1` once to create `.env.local` (gitignored).

---

## Deploy (production)

| Platform | Guide |
|----------|--------|
| AWS EC2 | [`deploy/aws/DEPLOY_AWS.md`](deploy/aws/DEPLOY_AWS.md) |
| Oracle Free | [`docs/DEPLOY_ORACLE_FREE.md`](docs/DEPLOY_ORACLE_FREE.md) |
| Local demo tunnel | [`docs/DEPLOY_ZERO_BUDGET.md`](docs/DEPLOY_ZERO_BUDGET.md) |

```powershell
.\scripts\aws_update.ps1 -VmIp YOUR_IP -PublicUrl "https://your-domain"
```

---

## Repo notes

- **No secrets** in git — use `.env.example` as template
- **No uploaded documents** — `Data/` and FAISS indexes are gitignored; add PDFs via the app UI after setup
- **Streamlit legacy** — original `app.py` remains; production UI is `web/` + `backend/`

---

## Project structure

```
backend/app/     FastAPI API, services, RAG, collab
web/             Next.js frontend
deploy/          Docker, AWS, Oracle configs
docs/            Architecture, thesis content, deploy guides
tests/           pytest suite
legacy_saas/     Auth helpers, early SaaS modules
```

---

## Author

Built as a capstone / portfolio legal-AI platform — full-stack, production-deployed, recruiter-ready codebase.
