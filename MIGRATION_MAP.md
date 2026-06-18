# LegalEase AI — Full Stack Migration Map

**Rule:** Strict UI mirror. Technical migration only. No layout redesign.

## Phase 0 — Current System Audit

### Pages

| Streamlit (`app.py`) | Route (Next.js `web/`) | Backend |
|---------------------|------------------------|---------|
| Guest login (`login_cinematic.py`) | `/login` | `POST /api/v1/auth/login` |
| Dashboard | `/dashboard` | `GET /api/v1/dashboard/full` |
| AI Assistant | `/` | `POST /api/v1/chat`, `POST /api/v1/chat/stream` |
| Documents | `/documents` | `POST /api/v1/documents/upload`, `GET /api/v1/documents` |
| Legal Tools (6 tabs) | `/tools` | `POST /api/v1/tools/*` |
| Drafting | `/drafting` | `GET/POST /api/v1/drafting/*` |
| Analytics | `/analytics` | `GET /api/v1/analytics` |
| Settings | `/settings` | `GET /api/v1/settings` |

### Sidebar (exact clone)

| Widget | Component | State / API |
|--------|-----------|-------------|
| Logo + tagline | `SidebarBrand` | — |
| Username + membership badge | `SidebarUserCard` | `GET /api/v1/auth/me` |
| Nav radio (7 items) | `SidebarNav` | Next.js routes |
| New Chat | `SidebarNewChat` | `window` event / new `session_id` |
| Recent sessions (6) | `SidebarRecentSessions` | `GET /api/v1/sessions` |
| Language (chat only) | `ChatHeader` lang select | `lang` in chat body |
| LLM status dot | `SidebarLlmStatus` | `GET /api/v1/health` |
| Logout | `SidebarLogout` | clear JWT |

### Chat UI (exact placement)

| Widget | Component | Backend |
|--------|-----------|---------|
| Title "LegalEase Assistant" | `ChatHeader` | — |
| Mode pills (KB / Open Law / Hybrid) | `ModePills` | `mode` field |
| User bubble **RIGHT** | `UserBubble` | — |
| Assistant card **LEFT** | `AssistantCard` | SSE / JSON |
| LEGALEASE CORE INTEL badge | `AssistantCard` | — |
| Suggestion pills | `SuggestionPills` | `follow_ups` |
| Attach popover | `AttachPopover` | `POST /api/v1/ocr` |
| Input dock (sticky bottom) | `InputDock` | chat endpoints |
| Empty hero | `ChatEmptyState` | — |
| Loading skeleton (left) | `ChatSkeleton` | streaming |

### Design tokens (do not change)

- Navy sidebar: `#0f172a` → `#1e293b`
- Canvas: `#f8fafc`
- User bubble: `#1e40af` → `#2563eb`, right, radius `20px 20px 4px 20px`
- Assistant: white, left, border-left `#d97706`
- Fonts: Playfair Display (titles), Inter (body)
- Chat max-width: `1080px`

### RAG pipeline (backend only)

```
Query → conversation_memory.enrich
     → intent_engine.classify_intent
     → rag.query_kb (hybrid + section boost)
     → answer_orchestrator.orchestrate_kb_answer
     → LLM (stream via SSE)
```

### Folder mapping

| Legacy | New |
|--------|-----|
| `rag.py` | `backend/app/core/rag_engine.py` (wrapper) |
| `conversation_context.py` | `backend/app/core/conversation_memory.py` |
| `legacy_saas/chat_service.py` | `backend/app/services/chat_service.py` |
| `legacy_saas/api_server.py` | `backend/app/main.py` + v1 routers |
| `frontend/` (Vite, deprecated) | `web/` (Next.js App Router) |

## Implementation status

- [x] Phase 0 audit (this document)
- [x] Phase 2 FastAPI `backend/` structure
- [x] Phase 3 Next.js `web/` mirror scaffold
- [x] Phase 4 API wiring
- [x] Phase 5 SSE streaming
- [x] Phase 6 RAG wrappers (existing `rag.py`)
- [x] Phase 7 Session memory API
- [x] Legal Tools page (6 tabs, full API wiring)
- [x] Settings page (profile, upgrade, payments, LLM test/recheck)

## Run commands

```powershell
# Backend (port 8000)
.\run_backend.ps1

# Next.js frontend (port 3000)
cd web
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL=http://127.0.0.1:8000` in `web/.env.local`.
