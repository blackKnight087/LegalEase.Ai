# AWS cloud vs laptop — LLM / KB behavior

Your **laptop** and **EC2** use different configs. They do not overwrite each other.

## Laptop (local dev) — unchanged project behavior

| Setting | Value |
|---------|--------|
| `LLM_BACKEND` | `ollama` |
| `CLOUD_GEMINI_KB` | `0` (default) or unset |
| KB answers | **Ollama `legalease-tuned`** only |
| Gemini in KB | **Blocked** (`GEMINI_KB_SYNTHESIS=0`, `kb_gemini_safety`) |
| Open Law / web | Gemini optional if you enable keys locally |

Run: `.\run_backend.ps1` + `.\run_web.ps1` — uses project root `.env`, **not** `deploy/aws/docker-compose.override.yml`.

## AWS EC2 — cloud-only overrides

| Setting | Value |
|---------|--------|
| `LLM_BACKEND` | `gemini` (no Ollama on 8 GB VM) |
| `CLOUD_GEMINI_KB` | `1` (set in `deploy/aws/docker-compose.override.yml`) |
| KB answers | Gemini from **document chunks** when Ollama absent |
| Open Law / web | Gemini |

Only files under `deploy/aws/` + server `/opt/legalease/.env` apply on EC2.

## Code guard

`cloud_kb_gemini_enabled()` is **true** only when **both**:

1. `CLOUD_GEMINI_KB=1`
2. `LLM_BACKEND=gemini`

Local `.env` with `LLM_BACKEND=ollama` → cloud KB path **never runs**, even after `git pull`.

## After pulling new code on laptop

Keep in `.env`:

```env
LLM_BACKEND=ollama
CLOUD_GEMINI_KB=0
```

Do not copy EC2 `.env` over your laptop `.env`.
