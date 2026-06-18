# LegalEase.AI — Start Here

## Production stack (FastAPI + Next.js) — recommended

```powershell
# Terminal 1 — Backend API http://127.0.0.1:8000
.\run_backend.ps1

# Terminal 2 — Next.js UI http://localhost:3000
.\run_web.ps1
```

- UI strictly mirrors Streamlit layout (see `MIGRATION_MAP.md`)
- Chat uses **SSE streaming** (`POST /api/v1/chat/stream`)
- RAG + memory run **only on the backend**

`web/.env.local` should contain:

```
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000
```

### Connection issues

1. **Backend must run separately** from Streamlit:
   ```powershell
   .\stop_backend.ps1
   .\run_backend.ps1
   ```
2. Test in browser: http://127.0.0.1:8000/api/v1/ping → should show `{"status":"ok"}`
3. **Use the same username/password** as Streamlit login (shared `legalease.db`).
4. First chat answer may take 1–2 minutes (AI libraries load once).

---

## Streamlit (legacy, Windows)

## Run the app

```powershell
cd "C:\Users\ASUS\Desktop\Legal_ai (1)\Legal_ai\Legal_AI_Final 3"
.\run_app.ps1
```

Browser opens automatically: **http://localhost:8501**

**First launch:** the page may stay blank for **1–3 minutes** while Python loads AI libraries. Keep the Streamlit terminal open, then press **F5** in the browser.

Login and register in the **left sidebar**. Same database: `legalease.db`.

**Do not use** `py -m streamlit run app.py` unless you use the project venv — prefer `.\run_app.ps1`.

## If the page does not open

```powershell
.\stop_app.ps1
.\run_app.ps1
```

## Requirements

- Python 3.12 (venv `.venv_win` is created on first run)
- LM Studio at `http://127.0.0.1:1234` for AI replies
- Optional: `TAVILY_API_KEY` in `.env` for web search mode

## Other launchers

| Script | Purpose |
|--------|---------|
| `run_app.ps1` | **Use this** — Streamlit |
| `run_app.bat` | Same as `run_app.ps1` |
| `run_windows.bat` | Streamlit with venv setup |
| `stop_app.ps1` | Free port 8501 |

## React / FastAPI (archived)

Moved to `legacy_saas/`. Not supported for daily use. Do not run old React launchers.

## RAG check

```powershell
.\.venv_win\Scripts\python.exe scripts\verify_rag_proof.py
```
