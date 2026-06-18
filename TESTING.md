# LegalEase Automated Testing

## Quick run

```powershell
.\run_tests.ps1
python scripts/e2e_kb_smoke.py
```

Or:

```powershell
py -m pytest tests/ -v
```

CI runs automatically via `.github/workflows/ci.yml` on push/PR.

## Test categories

| Marker | Scope |
|--------|--------|
| `unit` | Fast isolated logic (intent, validation, formatting) |
| `integration` | DB, mocked FAISS, API TestClient |
| `regression` | Product success criteria (comparison, summary, offences) |

Run by marker:

```powershell
py -m pytest tests/ -m regression -v
py -m pytest tests/ -m unit -q
```

## Suite coverage (170+ tests)

- **KB intent** — `test_intent_engine.py`, `test_kb_query_types.py`
- **Retrieval** — `test_rag.py`, `test_kb_retrieval.py`, `test_kb_rag_decision.py`
- **Document scan** — `test_kb_document_scan.py`
- **Pipeline** — `test_kb_pipeline.py`, `test_saas_regression.py`
- **Answers** — `test_kb_response_state.py`, `test_answer_orchestrator_kb.py`, `test_kb_validate.py`
- **Chat persistence** — `test_chat_persistence.py`
- **Premium Suite** — `test_premium_services.py`, `test_api_premium.py` (witness, precedent, BNS auditor, deal rooms, redline, PII)
- **Adaptive learning** — `test_adaptive_learning.py` (feedback loops, query expansion, chunk boosts, thresholds)
- **Enterprise DB** — `test_enterprise_db.py` (deal rooms, witness sessions, judgments SQL)
- **OCR router** — `test_ocr_router.py` (150 chars/page gate, dual-path)
- **Hybrid PII** — `test_pii_hybrid.py` (RegEx + spaCy NER)
- **Parametrize matrix** — `test_parametrize_legal.py` (IPC/BNS, compare, audit, modes)
- **API** — `test_api_saas.py`, `test_api_chat_mocked.py` (health, auth, sessions, stream)
- **Golden** — `test_golden_kb.py` (comparison table, offences summary)
- **Tools / OCR / prompts** — existing tests

## Regression scenarios enforced

- Difference between 300 and 307 → both sections required
- Compare 299 300 307 → three entities
- Summarize all criminal offences → document scan, not NOT_FOUND
- List all IPC sections → full-document mode
- Follow-up memory with conversation history
- Chat save/load/thread reuse

## CI-friendly

Exit code is non-zero on any failure. Tests use temp SQLite and mocked indexes — no GPU or live API keys required.
