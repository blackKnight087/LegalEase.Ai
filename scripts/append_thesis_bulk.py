#!/usr/bin/env python3
"""Append bulk appendices and diagram embeds to thesis for 100+ page PDF."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THESIS = ROOT / "docs" / "LegalEase_SAAS_Thesis.md"
ENV = ROOT / ".env.example"
MARKER = "## Conclusion"
INSERT_TAG = "<!-- THESIS_BULK_APPEND -->"

DIAGRAMS = [
    ("database_er_detailed.png", "Detailed database ER"),
    ("ai_flow.png", "AI inference flow"),
    ("rag_architecture_detailed.png", "RAG architecture detailed"),
    ("matter_workflow.png", "Matter workflow"),
    ("collaboration_workflow.png", "Collaboration workflow"),
    ("auth_flow_enhanced.png", "Authentication enhanced"),
    ("deployment_enhanced.png", "Deployment enhanced"),
    ("learning_pipeline.png", "Learning pipeline"),
    ("ai_governance_trust.png", "AI governance trust layer"),
    ("matter_intelligence_pipeline.png", "Matter intelligence pipeline"),
    ("kb_accuracy_pipeline.png", "KB accuracy pipeline"),
    ("chat_routing_tree.png", "Chat routing tree"),
]


def _env_appendix() -> str:
    lines = ["### Appendix F — Complete Environment Variable Reference", "", "Sourced from `.env.example` in repository.", ""]
    if ENV.exists():
        lines.append("| Variable | Default / value |")
        lines.append("|----------|-----------------|")
        for raw in ENV.read_text(encoding="utf-8").splitlines():
            s = raw.strip()
            if not s or s.startswith("#"):
                continue
            if "=" in s:
                k, _, v = s.partition("=")
                lines.append(f"| `{k.strip()}` | `{v.strip()[:80]}` |")
    lines.append("")
    return "\n".join(lines)


def _test_appendix() -> str:
    tests_dir = ROOT / "tests"
    files = sorted(tests_dir.glob("test_*.py"))
    lines = [
        "### Appendix G — Automated Test Suite Index",
        "",
        f"**{len(files)} test modules** under `tests/` (pytest).",
        "",
        "| Test module | Focus area |",
        "|-------------|------------|",
    ]
    for f in files:
        name = f.stem.replace("test_", "").replace("_", " ")
        lines.append(f"| `{f.name}` | {name.title()} |")
    lines.append("")
    return "\n".join(lines)


def _diagrams_section() -> str:
    lines = [
        "## System Diagrams Catalog (Extended)",
        "",
        INSERT_TAG,
        "",
        "Regenerate: `py scripts/generate_thesis_diagrams.py`. **24 PNG files** in `docs/diagrams/`.",
        "",
    ]
    for i, (fname, cap) in enumerate(DIAGRAMS, 13):
        lines.append(f"![{cap}](diagrams/{fname})")
        lines.append("")
        lines.append(f"**Figure {i}:** {cap}.")
        lines.append("")
    return "\n".join(lines)


def _implementation_deep_dive() -> str:
    """Additional CTO narrative pages."""
    return """
## Implementation Deep Dive — Core Modules

### Module map (production paths)

| Module path | Lines (approx.) | Responsibility |
|-------------|-----------------|----------------|
| `app.py` | 3,800 | Legacy Streamlit monolith |
| `llms.py` | 1,700 | LLM clients, web search, synthesis helpers |
| `rag.py` | 2,500+ | FAISS retrieval, scoring, indexing |
| `kb_pipeline.py` | 1,000+ | KB orchestration entry |
| `backend/app/main.py` | 400+ | FastAPI app, middleware |
| `backend/app/services/chat_service.py` | 1,200+ | Chat turn execution |
| `web/lib/api.ts` | 1,500+ | Typed API client |

### Chat service branching (reference)

The function `run_chat_turn()` in `chat_service.py` is the single production entry for SaaS chat. It:

1. Resolves routing via `_resolve_chat_routing()` (shared with streaming).
2. Applies `_apply_plan_route_guard()` so Free users never receive Hybrid fusion.
3. Dispatches to `_run_kb_turn`, `_run_open_law_turn`, or hybrid/jurisprudence handlers.
4. Records learning signals via `_record_mode_interaction()` when enabled.
5. Returns formatted markdown with optional `sources` array for UI rendering.

Matter-scoped chat on `/matters/[id]/ai` passes `matter_id` and uses matter FAISS paths under `faiss_indexes/{user_id}/{matter_id}/`.

### Database dual-store note

LegalEase uses PostgreSQL for core SaaS tables (auth, chat, memory, subscriptions) when `DATABASE_URL` is set, and a practice data store (SQLite file or Postgres legacy) for matters, documents, CRM, and collaboration. Migration scripts: `migrate_core_to_postgres.py`, `migrate_sqlite_to_pg.py`. Operators should run both paths before cutover.

### Worker processes

| Worker | Script | Queue |
|--------|--------|-------|
| E-discovery | `scripts/ediscovery_worker.py` | `legalease:ediscovery:queue` |
| ML training | `scripts/ml_worker.py` | `legalease:ml:queue` |

Workers call `ensure_app_schemas()` on startup to avoid schema drift vs API.

### Frontend API proxy pattern

Next.js rewrites `/api/v1/*` to `NEXT_PUBLIC_API_URL`. Tokens in `localStorage` key `legalease_token`. This keeps cookies off the critical path for local dev; production hardening should migrate to httpOnly cookies (technical debt item).

### Indian jurisdiction features (implemented)

| Feature | Code entry |
|---------|------------|
| IPC → BNS mapping | `/api/tools/ipc-bns` |
| Limitation calculator | `practice/limitation` |
| BNS auditor (premium) | `premium_services` |
| Law code comparison in KB | `test_conceptual_comparison` |
| CrPC vs BNSS routing fix | mode router + query parser |

### Operational runbooks (document index)

| Document | Purpose |
|----------|---------|
| `RUNBOOK.md` | Incidents, backup restore |
| `docs/PILOT_LAUNCH.md` | Pilot checklist |
| `docs/PRODUCTION_CHECKLIST.md` | Go-live gates |
| `DEPLOY.md` | Docker production |
| `docs/DEPLOY_ZERO_BUDGET.md` | Laptop demo |
| `SAAS_STATUS.md` | Sprint status truth |

---

"""


def _api_appendix() -> str:
    import re

    api_root = ROOT / "backend" / "app" / "api" / "v1" / "endpoints"
    lines = [
        "### Appendix H — API v1 Route Catalog (generated)",
        "",
        "Mounted under `/api/v1` via `router.py`. Auth required unless noted.",
        "",
        "| Method | Path suffix | Source file |",
        "|--------|-------------|-------------|",
    ]
    pat = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*["\']([^"\']*)', re.I)
    for py in sorted(api_root.glob("*.py")):
        try:
            content = py.read_text(encoding="utf-8")
        except OSError:
            continue
        prefix = py.stem.replace("_", "-")
        if prefix in ("health",):
            prefix = ""
        for m in pat.finditer(content):
            method, path = m.group(1).upper(), m.group(2)
            full = f"/api/v1/{prefix}{path}" if prefix and not path.startswith("/") else f"/api/v1{path}"
            lines.append(f"| {method} | `{full}` | `{py.name}` |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    text = THESIS.read_text(encoding="utf-8")
    if INSERT_TAG in text:
        # Allow one-time API appendix append
        if "### Appendix H —" not in text:
            text = text.replace(MARKER, _api_appendix() + "\n---\n\n" + MARKER, 1)
            THESIS.write_text(text, encoding="utf-8")
            print("Appended API catalog appendix.")
        else:
            print("Bulk append already present.")
        return
    bulk = (
        _diagrams_section()
        + _implementation_deep_dive()
        + _env_appendix()
        + _test_appendix()
        + "\n---\n\n"
    )
    if MARKER not in text:
        raise SystemExit("Conclusion marker not found")
    text = text.replace(MARKER, bulk + MARKER, 1)
    THESIS.write_text(text, encoding="utf-8")
    print(f"Appended bulk sections ({len(text.splitlines())} lines total)")


if __name__ == "__main__":
    main()
