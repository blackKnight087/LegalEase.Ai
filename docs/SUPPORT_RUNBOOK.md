# LegalEase Support Runbook

Operational guide for KB/RAG failures, embedding issues, and SaaS health checks.

## Quick health checks

| Endpoint | Purpose |
|----------|---------|
| `GET /api/v1/health/live` | Liveness — instant, no ML |
| `GET /api/v1/health/ready` | Readiness — embeddings + FAISS deps |
| `GET /api/v1/health/public` | Public status (embeddings, LLM) |
| `GET /api/v1/documents/kb/health` | Per-user KB: vectors, scope, issues |
| `POST /api/v1/documents/kb/reindex-auto` | Auto-detect stale index + re-index |

## SLA targets (`.env`)

```env
SLA_EMBEDDING_LOAD_SEC=60
SLA_UPLOAD_SEC=900
SLA_INDEX_MIN_VECTORS=1
SLA_QUERY_P95_SEC=30
REINDEX_AUTO_ON_STALE=1
REINDEX_AUTO_STARTUP=0
```

## Symptom: "0 chunks" / KB can't answer anything

### Diagnosis

1. `GET /api/v1/documents/kb/health` → check:
   - `embeddings_ok: false` → embedding load failed
   - `faiss_chunks: 0` with `documents > 0` → index never built or wrong scope
   - `index_scope` — unlinked vs matter-scoped mismatch

2. Backend logs: search for `meta tensor`, `Embedding warmup failed`, `Index empty after upload`

### Fix

1. **Restart backend** — `.\run_backend.ps1` (uses `.venv_win\Scripts\python.exe`)
2. Confirm startup log: `RAG stack ready: embeddings_ok=True`
3. Documents page → **Auto-fix index** or **Re-index all**
4. If scanned PDF: enable OCR and re-index
5. Verify: `index_vectors > 0` in kb/health

## Symptom: Embeddings fail on Windows (meta tensor)

### Root cause

PyTorch/SentenceTransformer meta-device race on Windows, or corrupt fine-tuned model path.

### Fix

1. Set in `.env`:
   ```env
   RAG_EMBEDDING_DEVICE=cpu
   HF_EMBEDDING_MODEL=sentence-transformers/all-MiniLM-L6-v2
   ```
2. Restart backend (warmup runs 3 load strategies + base-model fallback)
3. If neural fine-tune broke weights: delete `Data/fine_tuned_models/embeddings/` and restart
4. Manual test:
   ```powershell
   .\.venv_win\Scripts\python.exe -c "from llms import warmup_rag_stack; print(warmup_rag_stack())"
   ```

## Symptom: Upload succeeds but indexing silent-fails

### UI signals

- Red banner: `0 searchable chunks`
- `error_code: ZERO_CHUNKS` in upload API response
- KB health panel shows **Active index: 0 vectors**

### Fix

1. Re-index with OCR if scanned/image PDF
2. Check `DATA_DIR` write permissions
3. `POST /api/v1/documents/kb/reindex-auto`

## Index scope (matter vs unlinked)

| Upload linked to | Index path | RAG scope |
|------------------|------------|-----------|
| No matter | `faiss_indexes/user_{id}/_unlinked/` | Global KB |
| Matter selected | `faiss_indexes/user_{id}/matter_{id}/` | Matter-only chat |

**Common mistake:** Upload without matter, query in matter-scoped chat → 0 chunks.

## Re-index automation

- `REINDEX_AUTO_ON_STALE=1` — logs stale indexes on startup
- `REINDEX_AUTO_STARTUP=1` — auto re-index (use cautiously in prod)
- Manual: `POST /api/v1/documents/kb/reindex-auto`

## Monitoring checklist (daily)

- [ ] `/api/v1/health/ready` → `ready: true`
- [ ] Sample user kb/health → `healthy: true`
- [ ] No `ZERO_FAISS_CHUNKS` in issues array
- [ ] LM Studio / Ollama reachable if using local LLM

## Escalation

1. Capture kb/health JSON + last 50 lines of backend log
2. Note: OS, Python path, `.env` RAG_* settings (redact secrets)
3. Run: `pytest tests/test_kb_e2e.py -q` — if fails, indexing pipeline regression

## Run tests before release

```powershell
.\.venv_win\Scripts\python.exe -m pytest tests/test_kb_e2e.py tests/test_kb_law_replacement.py tests/test_learning_engine.py -q
```
