# Archived: React + FastAPI stack

This folder is **not used** by the main LegalEase app. The project runs on **Streamlit only** (`app.py`).

It was moved here because of port conflicts (8000/5173) and login issues with the React UI.

## Contents

- `api_server.py`, `api_routes.py`, auth helpers — FastAPI backend
- `frontend/` — React + Vite UI
- `run_saas.ps1`, `stop_saas.ps1` — old launchers (do not use unless you know how to fix ports)

## To run Streamlit (recommended)

From the project root:

```powershell
.\run_app.ps1
```

Open **http://localhost:8501**
