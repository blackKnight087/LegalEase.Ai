#!/usr/bin/env python3
"""
Generate LegalEase complete system architecture HTML flowchart (detailed edition).
Output: docs/LegalEase_System_Architecture.html
"""
from __future__ import annotations

import html
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_HTML = ROOT / "docs" / "LegalEase_System_Architecture.html"
DESKTOP_COPY = Path.home() / "Desktop" / "LegalEase_System_Architecture.html"
ROUTER_PY = ROOT / "backend" / "app" / "api" / "v1" / "router.py"
ENDPOINTS_DIR = ROOT / "backend" / "app" / "api" / "v1" / "endpoints"

C = {
    "bg": "#0b0f14",
    "panel": "#0d1117",
    "box": "#161b22",
    "box_alt": "#1c2128",
    "border": "#30363d",
    "text": "#e6edf3",
    "dim": "#8b949e",
    "fe": "#388bfd",
    "be": "#3fb950",
    "ai": "#a371f7",
    "data": "#d29922",
    "learn": "#f778ba",
    "warn": "#ffa657",
    "deploy": "#56d4dd",
    "ext": "#79c0ff",
}

PROD_URL = "https://legalease.duckdns.org"
PROD_API = "https://legalease.duckdns.org/api"
EC2_IP = "18.61.68.82"
EC2_PATH = "/opt/legalease"
SSH_KEY = r"%USERPROFILE%\.ssh\legalease-aws.pem"

ENV_FILES = [
    (".env.example", "Root .env (API keys + shared)"),
    (".env.local.example", "Laptop overrides .env.local"),
    (".env.docker.example", "Docker Compose local production"),
    ("deploy/aws/.env.production.example", "EC2 production /opt/legalease/.env"),
    ("web/.env.local.example", "Next.js web overrides"),
    (".env.pilot.example", "Pilot program template"),
]

# All API modules with prefix and purpose
API_MODULES = [
    ("health", "/health", "Live, ready, public, LLM, schema probes"),
    ("chat", "/chat", "POST /chat, /chat/stream SSE"),
    ("documents", "/documents", "Upload, index, jobs, KB smoke"),
    ("matters", "/matters", "CRUD, timeline, tasks, intel, evidence"),
    ("sessions", "/sessions", "Thread list, history, attachments"),
    ("learning", "/learning", "Feedback, signals, coach, neural tune"),
    ("feedback", "/feedback-learning", "Legacy feedback alias"),
    ("memory", "/memory", "Persona, facts, summaries, prune UI"),
    ("ediscovery", "/ediscovery", "Evidence upload, repo, contradictions"),
    ("drafting", "/drafting", "Studio v2/v3/v4 workspace, court bundle"),
    ("crm", "/crm", "Intake leads, kanban, analyze, convert"),
    ("billing", "/billing", "Time entries, invoices, PDF export"),
    ("subscriptions", "/subscriptions", "Stripe plans, webhook"),
    ("practice", "/practice", "Cause lists, litigation desk, war room"),
    ("enterprise", "/enterprise", "Firm settings, pilot, branding"),
    ("enterprise_workspace", "/enterprise/workspace", "DMS, court orders, KB entries"),
    ("collab", "/collaboration", "Firm chat rooms, SSE, WebSocket"),
    ("portal", "/portal", "Client magic link, upload, status"),
    ("esign", "/esign", "Signing requests workflow"),
    ("ipc_bns_v3", "/ipc-bns/v3", "IPC to BNS official converter"),
    ("legal_conversion", "/legal-conversion", "Statute conversion tools"),
    ("templates", "/templates", "Document templates library"),
    ("clauses", "/clauses", "Reusable clause library"),
    ("trust", "/trust", "Client trust ledger accounts"),
    ("orgs", "/orgs", "Organizations, invites, members"),
    ("account", "/account", "Profile, export, delete account"),
    ("admin", "/admin", "Superadmin, users, suspension"),
    ("sso", "/sso", "Enterprise SSO config"),
    ("scim", "/scim/v2", "User provisioning stub"),
    ("speech", "/speech", "STT faster_whisper + browser"),
    ("engines", "/engines", "Engine status, Ollama health"),
    ("kb_debug", "/kb", "KB pipeline debug endpoints"),
    ("research_log", "/research", "Research query logging"),
    ("dashboard", "/dashboard", "Firm dashboard metrics"),
    ("saas_metrics", "/saas-metrics", "Internal SaaS metrics"),
]

DEPLOY_STEPS_EC2 = [
    ("Prerequisites", "AWS EC2 Ubuntu, port 80 open, DuckDNS A record -> 18.61.68.82, SSH key legalease-aws.pem"),
    ("First .env on server", "Copy deploy/aws/.env.production.example to /opt/legalease/.env — set POSTGRES_PASSWORD, JWT_SECRET, GEMINI_API_KEY, Stripe keys"),
    ("Deploy from laptop", "scripts\\aws_update.ps1 -VmIp 18.61.68.82 -PublicUrl https://legalease.duckdns.org"),
    ("Remote script chain", "fix-ec2-env.sh -> fix-postgres-password.sh -> ec2-go-live.sh (rebuild api+web)"),
    ("Verify health", "curl https://legalease.duckdns.org/api/v1/health/live and /health/public"),
    ("Post-deploy smoke", "Login, KB chat, Evidence upload, thumbs feedback ok:true"),
]

DEPLOY_STEPS_LAPTOP = [
    ("One-time setup", "scripts\\setup_local_env.ps1 creates .env.local from template"),
    ("API keys", "Gemini/Tavily in .env — laptop overrides in .env.local"),
    ("Start backend", "run_backend.ps1 — SQLite, Ollama GPU, SAAS_PRODUCTION=0"),
    ("Start frontend", "run_web.ps1 — http://localhost:3000"),
    ("Never mix env", "Do not copy EC2 .env to laptop — aws_update excludes .env"),
]

TROUBLESHOOT = [
    ("502 Bad Gateway on /api", "docker compose logs api — wait 90s start_period; API container may be starting"),
    ("CORS error in browser", "CORS_ORIGINS must exactly match https://legalease.duckdns.org (no trailing slash)"),
    ("Postgres password authentication failed", "bash deploy/aws/fix-postgres-password.sh on EC2"),
    ("Thumbs feedback not saving", "Deploy latest code: adaptive_mode_stats not_found_count + adaptive_learning commit fix"),
    ("Web shows wrong API", "Re-run ec2-go-live.sh to rebuild web with NEXT_PUBLIC_API_URL baked in"),
    ("KB returns NOT_FOUND", "Upload PDFs, click Index All, verify faiss_indexes volume on EC2"),
    ("STRIPE_SECRET_KEY placeholder", "Add live Stripe keys or set SAAS_PRODUCTION_STRICT=0 temporarily"),
    ("Ollama connection refused on EC2", "Expected — set LLM_BACKEND=gemini and CLOUD_GEMINI_KB=1"),
    ("Port 8000 in use on laptop", "Run stop_backend.ps1 then run_backend.ps1"),
    ("DuckDNS timeout", "Open AWS security group port 80 or use Cloudflare tunnel"),
    ("Sessions lost between requests", "Set REDIS_URL=redis://redis:6379/0 on EC2"),
    ("Login works locally not EC2", "DATABASE_URL must use @postgres:5432 not @localhost in Docker .env"),
    ("Web build fails premium/page", "aws_update.ps1 removes stale web/app/(app)/premium automatically"),
    ("TLS handshake error", "Verify deploy/nginx/ssl/cert.pem and key.pem paths"),
    ("Index job stuck on EC2", "ML_USE_QUEUE=0 on low RAM — index from UI or enable worker profile"),
    ("Deploy tarball huge", "aws_update excludes Data, faiss_indexes, node_modules, .env"),
]

FULL_DEPLOY_SECTIONS = [
    ("7.1 Production Summary", [
        f"Public URL: {PROD_URL}",
        f"API base: {PROD_API}",
        f"Health: {PROD_API}/v1/health/live",
        f"EC2 IP: {EC2_IP} | Path: {EC2_PATH} | SSH: ubuntu@{EC2_IP}",
        f"SSH key: {SSH_KEY}",
        "Stack: Docker Compose nginx + web + api + postgres + redis",
    ]),
    ("7.2 EC2 First Deploy", [
        "Launch Ubuntu EC2, open ports 22 80 443",
        "Point legalease.duckdns.org A record to EC2 IP",
        f"Copy deploy/aws/.env.production.example to {EC2_PATH}/.env",
        "Set POSTGRES_PASSWORD, JWT_SECRET, LEGALEASE_API_SECRET, GEMINI_API_KEY, Stripe keys",
        f'From laptop: .\\scripts\\aws_update.ps1 -VmIp {EC2_IP} -PublicUrl "{PROD_URL}"',
        "Remote runs: fix-ec2-env.sh -> fix-postgres-password.sh -> ec2-go-live.sh",
    ]),
    ("7.3 Re-Deploy After Code Changes", [
        f'Full update: .\\scripts\\aws_update.ps1 -PublicUrl "{PROD_URL}"',
        f'Hotfix: .\\scripts\\aws_go_live.ps1 -VmIp {EC2_IP} -PublicUrl "{PROD_URL}"',
        "Verify: curl health/live, hard refresh browser Ctrl+Shift+R",
        "Smoke: login, KB chat, Evidence upload, thumbs feedback returns ok:true",
    ]),
    ("7.4 Laptop Development", [
        ".\\scripts\\setup_local_env.ps1 — creates .env.local",
        ".\\run_backend.ps1 — SQLite, Ollama GPU, SAAS_PRODUCTION=0",
        ".\\run_web.ps1 — http://localhost:3000",
        "Never upload laptop .env to EC2 — aws_update excludes .env and .env.local",
    ]),
    ("7.5 Docker Compose Services", [
        "nginx:80/443 — reverse proxy, TLS, 300s SSE timeout",
        "web:3000 — Next.js, NEXT_PUBLIC_API_URL baked at build",
        "api:8000 — FastAPI UVICORN_WORKERS=1 on 8GB EC2",
        "postgres:16 — postgres_data volume, all SaaS tables",
        "redis:7 — redis_data volume, sessions + ML queues",
        "worker / ml-worker — profile workers, OFF by default on 8GB",
        "Volumes: app_data, faiss_indexes/, Data/",
    ]),
    ("7.6 Memory Tiers (apply-ec2-tier.sh)", [
        "low (<=8GB): ML_USE_QUEUE=0, LOW_RESOURCE_MODE=1, STT_MODEL=tiny",
        "medium: ML_USE_QUEUE=1, STT small",
        "high (>16GB): workers optional, LOW_RESOURCE_MODE=0",
        "Compose: docker-compose.yml + deploy/aws/docker-compose.override.yml + optional https/highmem",
    ]),
    ("7.7 nginx + TLS + DuckDNS", [
        "Config: deploy/nginx/nginx.conf, nginx-ssl.conf",
        "Certs: deploy/nginx/ssl/cert.pem + key.pem",
        "Let's Encrypt: certbot then copy to deploy/nginx/ssl/",
        "Cloudflare fallback: ec2-go-live.sh starts cloudflared if port 80 blocked",
    ]),
    ("7.8 Stripe Billing", [
        "STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRICE_PRO, STRIPE_PRICE_LEGAL_PRO",
        f"Webhook endpoint: {PROD_API}/v1/subscriptions/webhook",
        "Set SAAS_PRODUCTION_STRICT=1 only after live Stripe keys configured",
    ]),
    ("7.9 Backup and Rollback", [
        "Backup: py scripts/backup_legalease.py --out backups/manual",
        "Postgres: pg_dump postgres_data volume",
        "Restore: stop api, pg_restore, restore faiss_indexes + Data, ec2-go-live.sh",
        "Rollback code: git checkout last-good + aws_update.ps1",
    ]),
    ("7.10 Security Checklist", [
        "JWT_SECRET and LEGALEASE_API_SECRET — 32+ char random",
        "GEMINI_API_KEY only on server .env, never committed",
        "FORCE_HTTPS=1, SECURITY_HEADERS_ENABLED=1 on production",
        "SUPERADMIN_USERNAMES=admin (trusted only)",
        "SSH key-only, restrict security group port 22 to your IP",
    ]),
    ("7.11 fix-ec2-env.sh behavior", [
        "Forces SAAS_USE_POSTGRES_LEGACY=1",
        "Rewrites localhost to postgres/redis Docker hostnames",
        "Sets CORS_ORIGINS, PUBLIC_APP_URL, NEXT_PUBLIC_API_URL from public URL",
        "Configures CPU STT (tiny model), rebuilds api+web",
    ]),
    ("7.12 ec2-go-live.sh behavior", [
        "Sets SAAS_PRODUCTION=1, runs apply-ec2-tier.sh",
        "docker compose up -d --build full stack",
        "Cloudflare tunnel if port 80 unreachable",
        "Health check loop 60 attempts, prints live URL",
    ]),
]

BACKEND_CORE_SERVICES = [
    ("chat_service.py", "Chat orchestration, SSE streaming"),
    ("kb_pipeline.py", "KB intent, retrieval, validation"),
    ("rag.py", "FAISS hybrid dense+sparse+MMR"),
    ("mode_router.py", "KB / OpenLaw / Hybrid routing"),
    ("user_memory.py", "Persona, facts, thread summaries"),
    ("adaptive_learning.py", "Feedback, chunk boosts, mode stats"),
    ("evidence_intelligence.py", "Classification, entities, privilege"),
    ("evidence_extraction.py", "Multi-format OCR extraction"),
    ("ediscovery_service.py", "Evidence batches, repository"),
    ("matter_repo.py", "Matter CRUD, timeline, tasks"),
    ("matter_policy.py", "Scope validation, RBAC"),
    ("crm_service.py", "Intake leads, kanban, convert"),
    ("practice_billing_service.py", "Time entries, invoices"),
    ("enterprise_workspace.py", "DMS, court orders, KB"),
    ("collab_service.py", "Firm chat rooms, messages"),
    ("web_intelligence.py", "Gemini Open Law web search"),
    ("gemini_ollama_coach.py", "Settings-only coach pipeline"),
    ("neural_finetuning.py", "Embedding tuning from feedback"),
    ("session_store.py", "Redis shared sessions"),
    ("ocr_router.py", "EasyOCR / Tesseract gate"),
    ("ipc_bns_engine_v3.py", "Official IPC to BNS dataset"),
    ("invoice_service.py", "Billing PDF export"),
    ("client_portal_service.py", "Magic link portal access"),
    ("payment_service.py", "Stripe integration"),
    ("chat_persistence.py", "SQLite/Postgres chat_history"),
]

DEPLOY_SCRIPTS = [
    ("scripts/aws_update.ps1", "Full EC2 deploy from Windows — tar upload, rebuild, go-live"),
    ("scripts/aws_go_live.ps1", "Hotfix deploy — 5 files + go-live only"),
    ("scripts/setup_local_env.ps1", "Create .env.local for laptop"),
    ("scripts/apply_local_env.ps1", "Merge laptop env overrides"),
    ("scripts/rotate_secrets.ps1", "Generate JWT/Postgres secrets"),
    ("scripts/backup_legalease.py", "Backup Postgres, SQLite, FAISS, Data"),
    ("deploy/aws/ec2-go-live.sh", "Production go-live on EC2"),
    ("deploy/aws/fix-ec2-env.sh", "Fix Docker hostnames and API URL"),
    ("deploy/aws/fix-postgres-password.sh", "Sync Postgres password with .env"),
    ("deploy/aws/apply-ec2-tier.sh", "Memory tier compose overlays"),
    ("deploy/aws/detect-ec2-tier.sh", "Detect low/medium/high RAM"),
    ("run_backend.ps1", "Start FastAPI on laptop port 8000"),
    ("run_web.ps1", "Start Next.js on laptop port 3000"),
    ("run_tests.ps1", "Run pytest suite"),
]


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def extract_routes() -> list[tuple[str, str, str]]:
    prefix_map: dict[str, str] = {}
    if ROUTER_PY.exists():
        text = ROUTER_PY.read_text(encoding="utf-8")
        for m in re.finditer(r'include_router\(\s*(\w+)\.router\s*,\s*prefix\s*=\s*"([^"]+)"', text):
            prefix_map[m.group(1)] = m.group(2)
        for m in re.finditer(r'include_router\(\s*(\w+)\.router\s*\)', text):
            if m.group(1) not in prefix_map:
                prefix_map[m.group(1)] = ""
    routes: list[tuple[str, str, str]] = []
    for f in sorted(ENDPOINTS_DIR.glob("*.py")):
        mod = f.stem
        text = f.read_text(encoding="utf-8")
        local_prefix = ""
        m = re.search(r'router\s*=\s*APIRouter\([^)]*prefix\s*=\s*"([^"]*)"', text)
        if m:
            local_prefix = m.group(1)
        router_prefix = prefix_map.get(mod, "")
        for m in re.finditer(r'@router\.(get|post|put|patch|delete|websocket)\(\s*"([^"]*)"', text):
            method = m.group(1).upper()
            path = "/api/v1" + router_prefix + local_prefix + m.group(2)
            path = re.sub(r"//+", "/", path)
            routes.append((mod, method, path))
    routes.sort(key=lambda x: (x[2], x[1]))
    return routes


def discover_frontend_pages() -> list[tuple[str, str, str]]:
    web_app = ROOT / "web" / "app"
    pages: list[tuple[str, str, str]] = []
    for f in sorted(web_app.rglob("page.tsx")):
        rel = f.relative_to(web_app)
        segs = [p for p in rel.parts[:-1] if not (p.startswith("(") and p.endswith(")"))]
        route = "/" + "/".join(segs) if segs else "/"
        file_path = str(f.relative_to(ROOT)).replace("\\", "/")
        pages.append((route, file_path, "Next.js App Router page"))
    return pages


def extract_db_tables() -> list[str]:
    tables: set[str] = set()
    for f in (ROOT / "backend").rglob("*.py"):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"CREATE TABLE IF NOT EXISTS (\w+)", text):
            tables.add(m.group(1))
    return sorted(tables)


def parse_env_file(path: Path) -> list[tuple[str, str, str]]:
    if not path.exists():
        return []
    rows: list[tuple[str, str, str]] = []
    comment_buf: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            comment_buf = []
            continue
        if stripped.startswith("#"):
            comment_buf.append(stripped.lstrip("#").strip())
            continue
        if "=" not in stripped:
            continue
        name, _, val = stripped.partition("=")
        rows.append((name.strip(), val.strip(), " ".join(comment_buf)))
        comment_buf = []
    return rows


def format_env_val(name: str, val: str, source: str) -> str:
    if "production.example" in source:
        val = val.replace("YOUR.DOMAIN", "legalease.duckdns.org")
    return val


def extract_all_env_vars() -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for rel, title in ENV_FILES:
        path = ROOT / rel
        for name, val, comment in parse_env_file(path):
            val = format_env_val(name, val, rel)
            rows.append((rel, name, val, comment or title))
    return rows


def list_endpoint_files() -> list[str]:
    return sorted(p.name for p in ENDPOINTS_DIR.glob("*.py") if p.name != "__init__.py")


def build_route_table(routes: list[tuple[str, str, str]]) -> str:
    rows = "".join(
        f'<tr class="searchable"><td data-label="Module"><code>{esc(m)}</code></td>'
        f'<td data-label="Method"><span class="method method-{meth.lower()}">{esc(meth)}</span></td>'
        f'<td data-label="Path"><code class="path-cell">{esc(path)}</code></td></tr>'
        for m, meth, path in routes
    )
    return f"""<div class="table-wrap"><table class="data-table">
<thead><tr><th>Module</th><th>Method</th><th>Path</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


def build_env_table(env_rows: list[tuple[str, str, str, str]]) -> str:
    rows = "".join(
        f'<tr class="searchable"><td data-label="Source"><code>{esc(src)}</code></td>'
        f'<td data-label="Variable"><code>{esc(name)}</code></td>'
        f'<td data-label="Value"><code>{esc(val[:80] + ("..." if len(val) > 80 else ""))}</code></td>'
        f'<td data-label="Notes">{esc(comment)}</td></tr>'
        for src, name, val, comment in env_rows
    )
    return f"""<div class="table-wrap"><table class="data-table">
<thead><tr><th>Source file</th><th>Variable</th><th>Example value</th><th>Notes</th></tr></thead>
<tbody>{rows}</tbody></table></div>"""


def build_deploy_full_html() -> str:
    parts = []
    for title, bullets in FULL_DEPLOY_SECTIONS:
        lis = "".join(f"<li>{esc(b)}</li>" for b in bullets)
        parts.append(f'<div class="deploy-section searchable"><h3>{esc(title)}</h3><ul>{lis}</ul></div>')
    return "".join(parts)


def build_db_table_html(tables: list[str]) -> str:
    cards = "".join(
        f'<div class="module-card searchable" style="border-left:3px solid {C["data"]}">'
        f'<div class="mc-title"><code>{esc(t)}</code></div></div>'
        for t in tables
    )
    return f'<div class="module-grid dense">{cards}</div>'


def svg_box(x, y, w, h, title, lines, stroke, fill=None, fs_title=11, fs_body=9, nid=""):
    fill = fill or C["box"]
    body = "".join(f'<tspan x="{x + w/2}" dy="1.1em">{esc(line)}</tspan>' for line in lines)
    data = f' data-title="{esc(title)}" data-desc="{esc(" | ".join(lines))}"' if nid else ""
    cls = f' class="node"' if nid else ""
    return f"""
<g{cls}{data}>
  <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" ry="8"
        fill="{fill}" stroke="{stroke}" stroke-width="1.5"/>
  <text x="{x + w/2}" y="{y + 16}" text-anchor="middle" fill="{C['text']}"
        font-size="{fs_title}" font-weight="600">{esc(title)}</text>
  <text x="{x + w/2}" y="{y + 28}" text-anchor="middle" fill="{C['dim']}"
        font-size="{fs_body}">{body}</text>
</g>"""


def svg_section(x, y, w, h, label, color):
    return f"""
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" ry="12"
      fill="{C['panel']}" stroke="{color}" stroke-width="2" opacity="0.95"/>
<text x="{x + 12}" y="{y + 22}" fill="{color}" font-size="13" font-weight="700">{esc(label)}</text>"""


def svg_arrow(x1, y1, x2, y2, color=None, dashed=False):
    color = color or C["dim"]
    dash = 'stroke-dasharray="6 4"' if dashed else ""
    return f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="1.5" {dash} marker-end="url(#ah)"/>'


def build_master_svg() -> str:
    W = 1400
    parts = [
        f'<defs><marker id="ah" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{C["dim"]}"/></marker></defs>',
        svg_section(20, 10, W - 40, 95, "CLIENT & ACCESS LAYER", C["fe"]),
        svg_box(580, 35, 240, 55, "Lawyer / Paralegal / Client", ["Browser HTTPS", "JWT legalease_token"], C["fe"], C["box_alt"], nid="1"),
        svg_box(40, 35, 200, 55, "Laptop Dev", ["localhost:3000", "127.0.0.1:8000"], C["deploy"], nid="1"),
        svg_box(880, 35, 220, 55, "Production", [PROD_URL, f"EC2 {EC2_IP}"], C["deploy"], nid="1"),
        svg_section(20, 115, W - 40, 145, "EDGE — nginx + TLS + DuckDNS", C["deploy"]),
        svg_box(40, 145, 200, 95, "nginx reverse proxy", ["/api/* -> api:8000", "/* -> web:3000", "proxy_read_timeout 300s"], C["deploy"], nid="1"),
        svg_box(260, 145, 200, 95, "Docker Compose", ["postgres redis api web", "compose overlays by RAM tier"], C["deploy"], nid="1"),
        svg_box(480, 145, 200, 95, "Deploy scripts", ["aws_update.ps1", "ec2-go-live.sh", "fix-ec2-env.sh"], C["deploy"], nid="1"),
        svg_box(700, 145, 200, 95, "CI/CD", ["GitHub Actions pytest", "Next.js build gate", "~126 tests"], C["deploy"], nid="1"),
        svg_box(920, 145, 220, 95, "LLM routing", ["EC2: Gemini web/hybrid", "Laptop: Ollama KB", "GEMINI_KB_SYNTHESIS=0"], C["ai"], nid="1"),
        svg_box(1160, 145, 200, 95, "Security", ["Rate limit JWT RBAC", "HTTPS HSTS headers", "matter_policy scope"], C["warn"], nid="1"),
    ]
    # Frontend - 3 rows
    parts.append(svg_section(20, 275, W - 40, 200, "FRONTEND — Next.js 15 + React 19 (web/app/)", C["fe"]))
    fe_row1 = [
        ("AI Chat /", "SSE streamChat"), ("Documents", "/documents index"),
        ("Matters", "/matters/* 13 pages"), ("Discovery", "EvidenceWorkspace"),
        ("Drafting", "v4 studio review"), ("Intake CRM", "/intake board"),
        ("Billing", "invoices trust"), ("Litigation", "cause list desk"),
    ]
    fe_row2 = [
        ("Enterprise", "DMS court orders"), ("Collaboration", "firm chat WS"),
        ("IPC-BNS", "/tools/ipc-bns"), ("Analytics", "judicial stats"),
        ("Settings", "memory team sub"), ("Admin", "superadmin users"),
        ("Portal", "/portal/{token}"), ("Dashboard", "firm widgets"),
    ]
    x0, bw, gap = 35, 155, 12
    for i, (t, s) in enumerate(fe_row1):
        parts.append(svg_box(x0 + i * (bw + gap), 305, bw, 52, t, [s], C["fe"], fs_title=10, fs_body=8, nid="1"))
    for i, (t, s) in enumerate(fe_row2):
        parts.append(svg_box(x0 + i * (bw + gap), 365, bw, 52, t, [s], C["fe"], fs_title=10, fs_body=8, nid="1"))
    parts.append(svg_box(35, 425, W - 70, 38, "Shared: AuthProvider | ApiConnectionProvider | ChatSessionProvider | web/lib/api.ts (493 routes)",
                         [], C["fe"], C["box_alt"], fs_title=10, nid="1"))

    # API gateway row
    parts.append(svg_section(20, 490, W - 40, 115, "API GATEWAY — FastAPI backend/app/main.py", C["be"]))
    gw = [
        ("Middleware", "CORS RateLimit MemoryGuard"), ("Auth", "JWT bcrypt suspend"),
        ("Router v1", "38 modules 493 routes"), ("Health", "live ready public llm"),
        ("Sessions", "Redis multi-worker"), ("Speech", "STT tiny/small CPU"),
        ("SSE Stream", "/chat/stream 180s"), ("WebSocket", "collaboration rooms"),
    ]
    for i, (t, s) in enumerate(gw):
        parts.append(svg_box(35 + i * 168, 520, 158, 65, t, [s], C["be"], fs_title=10, fs_body=8, nid="1"))

    # 6 domain columns
    cols = [
        (20, 620, 215, "CHAT + MEMORY", C["be"], [
            ("chat.py", "POST /chat /stream"),
            ("chat_service.py", "run_chat_turn SSE"),
            ("mode_router.py", "KB OpenLaw Hybrid"),
            ("kb_pipeline.py", "intent validate retry"),
            ("rag.py", "dense sparse MMR rerank"),
            ("user_memory.py", "persona facts 512 tok"),
            ("chat_conversation_rag", "past thread RAG"),
            ("adaptive_learning.py", "log interaction id"),
        ]),
        (250, 620, 215, "DOCUMENTS + INDEX", C["data"], [
            ("documents.py", "upload reindex jobs"),
            ("pdf_extraction", "PyMuPDF text layer"),
            ("ocr_router.py", "EasyOCR Tesseract"),
            ("kb_preprocess", "chunk overlap embed"),
            ("matter_index.py", "FAISS path routing"),
            ("index_jobs.py", "thread/process workers"),
            ("kb_cache.py", "TTL 300s query cache"),
            ("index_status", "queued processing ready"),
        ]),
        (480, 620, 215, "MATTERS + LITIGATION", C["be"], [
            ("matters.py", "53 routes CRUD intel"),
            ("matter_repo.py", "timeline hearings tasks"),
            ("matter_policy.py", "scope write RBAC"),
            ("matter_intelligence", "entities contradictions"),
            ("practice.py", "cause list war room"),
            ("research_log.py", "query audit trail"),
            ("legal_conversion", "statute tools"),
            ("ipc_bns_v3.py", "official IPC BNS map"),
        ]),
        (710, 620, 215, "PRACTICE OPS", C["be"], [
            ("crm.py", "leads kanban convert"),
            ("billing.py", "time expenses invoice"),
            ("trust.py", "client trust ledger"),
            ("subscriptions.py", "Stripe webhook Pro"),
            ("portal.py", "client magic links"),
            ("esign.py", "signing workflow"),
            ("templates.py", "document templates"),
            ("clauses.py", "clause library feedback"),
        ]),
        (940, 620, 215, "EVIDENCE + E-DISCOVERY", C["ai"], [
            ("ediscovery.py", "evidence/* routes"),
            ("evidence_extraction", "PDF DOCX EML ZIP"),
            ("evidence_intelligence", "classify privilege"),
            ("entity timeline", "parties dates events"),
            ("contradiction engine", "cross-doc compare"),
            ("statute finder", "BNS IPC sections"),
            ("court order match", "firm KB search"),
            ("discovery_items PG", "metadata_json cols"),
        ]),
        (1170, 620, 210, "ENTERPRISE + COLLAB", C["ai"], [
            ("enterprise.py", "firm pilot branding"),
            ("enterprise_workspace", "DMS folders orders"),
            ("collab.py", "rooms SSE WebSocket"),
            ("orgs.py", "members invites"),
            ("sso.py", "enterprise SSO"),
            ("scim/v2", "user provisioning"),
            ("admin.py", "superadmin suspend"),
            ("account.py", "GDPR export delete"),
        ]),
    ]
    for cx, cy, cw, title, color, nodes in cols:
        parts.append(svg_section(cx, cy, cw, 340, title, color))
        ny = cy + 35
        for t, s in nodes:
            parts.append(svg_box(cx + 10, ny, cw - 20, 36, t, [s], color, fs_title=9, fs_body=8, nid="1"))
            ny += 38

    # AI layer
    parts.append(svg_section(20, 975, 680, 145, "AI INTELLIGENCE MODES", C["ai"]))
    modes = [
        ("Knowledge Base", "FAISS hybrid retrieve", "Ollama legalease-tuned", "Citations required NOT_FOUND"),
        ("Open Law", "Gemini + Google Search", "Tavily Serp fallback", "web_sources[] array"),
        ("Hybrid / Deep Case", "Parallel KB + web", "Gemini fusion report", "Pro / Legal Pro gate"),
        ("Premium AI Tools", "Witness simulator", "BNS auditor deal rooms", "Redline PII redactor"),
    ]
    for i, (t, l1, l2, l3) in enumerate(modes):
        parts.append(svg_box(35 + i * 165, 1005, 155, 95, t, [l1, l2, l3], C["ai"], fs_title=10, fs_body=8, nid="1"))

    parts.append(svg_section(715, 975, 665, 145, "LEARNING & IMPROVEMENT LOOP", C["learn"]))
    learn = [
        ("Thumbs feedback", "POST /learning/feedback", "interaction_id required"),
        ("Chunk boosts", "adaptive_chunk_boosts", "per user scope_key"),
        ("Query expansion", "adaptive_query_patterns", "not_found_count fix"),
        ("Coach pipeline", "gemini_ollama_coach", "Settings only never KB"),
        ("Neural export", "neural_finetuning JSONL", "ollama create tuned"),
    ]
    for i, (t, l1, l2) in enumerate(learn):
        parts.append(svg_box(730 + i * 128, 1005, 118, 95, t, [l1, l2], C["learn"], fs_title=9, fs_body=7, nid="1"))

    # Persistence
    parts.append(svg_section(20, 1135, W - 40, 175, "PERSISTENCE, VOLUMES & EXTERNAL SERVICES", C["data"]))
    stores = [
        ("PostgreSQL 16", "EC2 production", "SAAS_USE_POSTGRES_LEGACY=1", "postgres_data volume"),
        ("SQLite", "legalease.db laptop", "SAAS_PRODUCTION=0", "single file dev"),
        ("Redis 7", "SESSION_TTL 86400", "ML_USE_QUEUE jobs", "redis_data AOF"),
        ("FAISS indexes", "user_X/_unlinked", "user_X/matter_Y", "faiss_indexes/ mount"),
        ("File storage", "Data/ PDFs uploads", "HF cache embeddings", "app_data /data"),
        ("Ollama", "legalease-tuned model", "OLLAMA_AUTO_START laptop", "KB answers ONLY"),
        ("Gemini API", "GEMINI_API_KEY EC2", "CLOUD_GEMINI_KB=1", "web hybrid coach"),
        ("Tavily / Serp", "web search fallback", "LEGAL_ONLY_WEB=1", "when Gemini quota hit"),
    ]
    for i, (t, l1, l2, l3) in enumerate(stores):
        parts.append(svg_box(35 + i * 168, 1170, 158, 115, t, [l1, l2, l3], C["data"], fs_title=10, fs_body=7, nid="1"))

    # Arrows
    for ax, ay, bx, by in [(700, 90, 700, 115), (700, 260, 700, 275), (700, 475, 700, 490), (700, 605, 127, 620), (700, 960, 350, 975), (350, 1120, 125, 1170)]:
        parts.append(svg_arrow(ax, ay, bx, by, C["fe"]))

    return f'<svg viewBox="0 0 {W} 1320" xmlns="http://www.w3.org/2000/svg" class="diagram">{"".join(parts)}</svg>'


def build_deploy_svg() -> str:
    parts = [
        f'<defs><marker id="ah2" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{C["deploy"]}"/></marker></defs>',
        svg_section(30, 15, 1140, 55, f"PRODUCTION — {PROD_URL}  |  EC2 {EC2_IP}  |  /opt/legalease", C["deploy"]),
    ]
    flow_y = 90
    steps = [
        ("1. Laptop", "aws_update.ps1\npack tar upload SCP"),
        ("2. Extract", "tar -xzf on EC2\nfix line endings .sh"),
        ("3. fix-ec2-env", "postgres/redis hostnames\nNEXT_PUBLIC_API_URL"),
        ("4. apply-ec2-tier", "low/medium/high RAM\ncompose file stack"),
        ("5. Rebuild", "docker compose build\napi + web + nginx"),
        ("6. go-live", "health loop 60x2s\nCORS PUBLIC_APP_URL"),
    ]
    for i, (t, s) in enumerate(steps):
        parts.append(svg_box(40 + i * 185, flow_y, 170, 75, t, s.split("\n"), C["deploy"], fs_title=10, fs_body=8, nid="1"))
        if i < len(steps) - 1:
            parts.append(f'<line x1="{210+i*185}" y1="{flow_y+38}" x2="{225+i*185}" y2="{flow_y+38}" stroke="{C["deploy"]}" stroke-width="2" marker-end="url(#ah2)"/>')

    parts.append(svg_section(30, 185, 550, 280, "DOCKER SERVICES (docker-compose.yml + deploy/aws overrides)", C["deploy"]))
    svcs = [
        ("nginx", "80:443", "TLS rate limit", "300s SSE timeout"),
        ("web", "Next.js :3000", "NEXT_PUBLIC baked", "1536M RAM limit"),
        ("api", "FastAPI :8000", "UVICORN_WORKERS=1", "Gemini 4G limit"),
        ("postgres", ":5432 internal", "postgres_data vol", "init_postgres.sql"),
        ("redis", ":6379 internal", "appendonly yes", "sessions + queues"),
        ("worker", "profile workers", "ediscovery_worker", "OFF on 8GB tier"),
        ("ml-worker", "profile workers", "ml_worker reindex", "OFF on 8GB tier"),
        ("volumes", "app_data", "faiss_indexes/", "Data/ bind mount"),
    ]
    for i, row in enumerate(svcs):
        x, y = 45 + (i % 4) * 130, 220 + (i // 4) * 115
        parts.append(svg_box(x, y, 120, 100, row[0], list(row[1:]), C["deploy"], fs_title=10, fs_body=7, nid="1"))

    parts.append(svg_section(600, 185, 570, 280, "ENV PROFILES — Laptop vs EC2", C["warn"]))
    env_rows = [
        "SAAS_PRODUCTION: 0 laptop | 1 EC2",
        "DATABASE_URL: empty SQLite | postgresql://@postgres:5432",
        "LLM_BACKEND: ollama | gemini",
        "CLOUD_GEMINI_KB: 0 | 1",
        "NEXT_PUBLIC_API_URL: http://127.0.0.1:8000 | /api on domain",
        "IMPROVEMENT_AUTO: 1 laptop | 0 EC2",
        "STT_MODEL: base GPU | tiny CPU EC2",
    ]
    for i, line in enumerate(env_rows):
        parts.append(svg_box(615, 215 + i * 32, 540, 28, line, [], C["warn"], fs_title=9, fs_body=8, nid="1"))

    parts.append(svg_section(30, 485, 1140, 200, "LAPTOP DEV PARALLEL STACK", C["fe"]))
    parts.extend([
        svg_box(45, 515, 250, 140, "run_backend.ps1", [
            "apply_local_env.ps1", "LEGALEASE_DB_PATH=legalease.db",
            "Ollama auto-start GPU", "uvicorn :8000 minimal startup",
        ], C["fe"], fs_title=11, fs_body=8, nid="1"),
        svg_box(310, 515, 250, 140, "run_web.ps1", [
            "npm run dev :3000", ".env.local CORS localhost",
            "NEXT_PUBLIC -> 127.0.0.1:8000", "Hard refresh after deploy",
        ], C["fe"], fs_title=11, fs_body=8, nid="1"),
        svg_box(575, 515, 250, 140, "setup_local_env.ps1", [
            "Copies .env.local.example", "SAAS_ALL_FEATURES_FREE=1",
            "ALLOW_MOCK_BILLING=1", "Never deployed to EC2",
        ], C["fe"], fs_title=11, fs_body=8, nid="1"),
        svg_box(840, 515, 310, 140, "Backup & rollback", [
            "scripts/backup_legalease.py", "pg_dump postgres_data",
            "git checkout + aws_update rollback", "RUNBOOK.md troubleshooting",
        ], C["deploy"], fs_title=11, fs_body=8, nid="1"),
    ])
    return f'<svg viewBox="0 0 1200 720" xmlns="http://www.w3.org/2000/svg" class="diagram">{"".join(parts)}</svg>'


def build_chat_svg() -> str:
    parts = [f'<defs><marker id="ah3" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="{C["ai"]}"/></marker></defs>']
    parts.append(svg_section(30, 15, 1140, 45, "CHAT REQUEST PIPELINE — Full sequence with persistence & feedback", C["ai"]))
    steps = [
        ("1 User types", "MessageFeedback.tsx", "matter_id optional"),
        ("2 useChat.ts", "streamChat POST", "thread_id UUID"),
        ("3 /chat/stream", "SSE 180s timeout", "JWT Bearer auth"),
        ("4 chat_service", "plan gate Pro tier", "validate_chat_scope"),
        ("5 mode_router", "KB OpenLaw Hybrid", "deep_case path"),
        ("6 kb_pipeline", "query_parser intent", "comparison summary"),
        ("7 user_memory", "512 tok budget", "facts persona summary"),
        ("8 adaptive_learning", "chunk boosts expand", "mode_stats bump"),
        ("9 rag.query_kb", "FAISS hybrid K=12", "cross_encoder off CPU"),
        ("10 LLM call", "Ollama KB only", "Gemini web/hybrid"),
        ("11 Persist", "chat_history row", "interaction_id meta"),
        ("12 SSE tokens", "meta token done", "sources[] citations"),
        ("13 Feedback", "POST /learning/feedback", "thumbs ok:true PG fix"),
    ]
    # 2 rows
    for i, (t, l1, l2) in enumerate(steps[:7]):
        parts.append(svg_box(35 + i * 160, 75, 148, 72, t, [l1, l2], C["ai"], fs_title=9, fs_body=7, nid="1"))
    for i, (t, l1, l2) in enumerate(steps[7:]):
        parts.append(svg_box(35 + i * 160, 165, 148, 72, t, [l1, l2], C["ai"], fs_title=9, fs_body=7, nid="1"))
    parts.append(svg_section(30, 255, 1140, 90, "DOCUMENT INGEST PIPELINE (parallel path)", C["data"]))
    ingest = ["Upload PDF", "documents table", "Extract text", "OCR if <120 chars", "Chunk 1000 overlap 200", "MiniLM embeddings", "FAISS write", "index_status ready"]
    for i, label in enumerate(ingest):
        parts.append(svg_box(35 + i * 140, 285, 128, 45, label, [], C["data"], fs_title=9, nid="1"))
    return f'<svg viewBox="0 0 1200 360" xmlns="http://www.w3.org/2000/svg" class="diagram">{"".join(parts)}</svg>'


def build_evidence_svg() -> str:
    parts = [svg_section(30, 15, 1140, 45, "EVIDENCE INTELLIGENCE CENTER — EvidenceWorkspace.tsx 5 tabs", C["ai"])]
    tabs = [
        ("Upload", "Drag-drop batch", "POST evidence/upload", "create_evidence_batch"),
        ("Repository", "Filter by matter", "list_evidence_repository", "strength privilege tags"),
        ("Timeline", "Chronological view", "entity dates events", "matter_timeline sync"),
        ("Contradiction", "Pick 2 documents", "POST contradictions", "AI conflict report"),
        ("Statute & Orders", "BNS IPC finder", "court order KB match", "statute risk flags"),
    ]
    for i, (t, l1, l2, l3) in enumerate(tabs):
        parts.append(svg_box(40 + i * 225, 70, 210, 110, t, [l1, l2, l3], C["ai"], fs_title=11, fs_body=8, nid="1"))
    parts.append(svg_section(30, 200, 1140, 130, "BACKEND PROCESSING CHAIN", C["ai"]))
    chain = [
        ("evidence_extraction.py", "multi-format parse"),
        ("OCR gate 150 chars", "EasyOCR images"),
        ("Classification", "doc type strength"),
        ("Entity extraction", "parties orgs dates"),
        ("Privilege detection", "attorney-client flags"),
        ("discovery_items", "PostgreSQL JSON cols"),
        ("matter_evidence link", "matter_id FK"),
    ]
    for i, (t, s) in enumerate(chain):
        parts.append(svg_box(40 + i * 158, 230, 148, 75, t, [s], C["ai"], fs_title=9, fs_body=8, nid="1"))
    return f'<svg viewBox="0 0 1200 350" xmlns="http://www.w3.org/2000/svg" class="diagram">{"".join(parts)}</svg>'


def build_drafting_svg() -> str:
    parts = [svg_section(30, 15, 1140, 45, "DRAFTING STUDIO v2 / v3 / v4 — Full document lifecycle", C["be"])]
    states = ["draft", "in_review", "partner_review", "approved", "filed", "archived"]
    for i, st in enumerate(states):
        parts.append(svg_box(40 + i * 185, 70, 170, 45, st, [], C["be"], fs_title=10, nid="1"))
        if i < len(states) - 1:
            parts.append(f'<line x1="{210+i*185}" y1="92" x2="{225+i*185}" y2="92" stroke="{C["be"]}" stroke-width="2"/>')
    modules = [
        ("drafting_studio.py", "v2 templates"),
        ("drafting_workspace.py", "versions comments"),
        ("drafting_v3.py", "copilot commands"),
        ("drafting_v4.py", "court bundle PDF"),
        ("clauses.py", "reusable clauses"),
        ("templates.py", "firm templates"),
        ("redline engine", "AI diff revision"),
        ("filing readiness", "checklist score"),
    ]
    for i, (t, s) in enumerate(modules):
        parts.append(svg_box(40 + (i % 4) * 280, 140 + (i // 4) * 90, 265, 75, t, [s], C["be"], fs_title=10, fs_body=8, nid="1"))
    return f'<svg viewBox="0 0 1200 320" xmlns="http://www.w3.org/2000/svg" class="diagram">{"".join(parts)}</svg>'


def canvas_block(svg: str, hint: str = "Pinch or scroll to explore diagram") -> str:
    return f'<span class="canvas-hint">{esc(hint)}</span><div class="canvas-wrap">{svg}</div>'


def card_grid(items: list[tuple[str, str, str]], color: str) -> str:
    cards = []
    for a, b, c in items:
        cards.append(f"""
<div class="module-card searchable" style="border-left:3px solid {color}">
  <div class="mc-title">{esc(a)}</div>
  <div class="mc-sub">{esc(b)}</div>
  <div class="mc-desc">{esc(c)}</div>
</div>""")
    return f'<div class="module-grid">{"".join(cards)}</div>'


def step_list(steps: list[tuple[str, str]], color: str) -> str:
    rows = "".join(
        f'<div class="step-row"><span class="step-num" style="background:{color}">{i}</span>'
        f'<div><strong>{esc(t)}</strong><p>{esc(d)}</p></div></div>'
        for i, (t, d) in enumerate(steps, 1)
    )
    return f'<div class="step-list">{rows}</div>'


def build_html() -> str:
    routes = extract_routes()
    frontend_pages = discover_frontend_pages()
    db_tables = extract_db_tables()
    env_rows = extract_all_env_vars()
    endpoint_files = list_endpoint_files()

    master = build_master_svg()
    deploy = build_deploy_svg()
    chat = build_chat_svg()
    evidence = build_evidence_svg()
    drafting = build_drafting_svg()
    api_cards = [(m[0], m[1], m[2]) for m in API_MODULES]
    fe_cards = [(p[0], p[1], p[2]) for p in frontend_pages]
    route_table = build_route_table(routes)
    env_table = build_env_table(env_rows)
    deploy_full = build_deploy_full_html()
    db_html = build_db_table_html(db_tables)
    n_routes = len(routes)
    n_pages = len(frontend_pages)
    n_tables = len(db_tables)
    n_env = len(env_rows)
    n_endpoints = len(endpoint_files)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LegalEase.AI — 100% Complete System Architecture</title>
<style>
:root {{
  --bg:{C['bg']}; --panel:{C['panel']}; --text:{C['text']}; --dim:{C['dim']}; --border:{C['border']};
  --header-h: auto;
  --tap: 44px;
}}
*{{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}}
html{{scroll-behavior:smooth}}
body{{
  background:var(--bg);color:var(--text);
  font-family:'Segoe UI',system-ui,-apple-system,BlinkMacSystemFont,sans-serif;
  line-height:1.5;padding-bottom:env(safe-area-inset-bottom,0)
}}
header{{
  position:sticky;top:0;z-index:200;background:rgba(11,15,20,.98);
  border-bottom:1px solid var(--border);
  padding:12px 16px;padding-top:max(12px,env(safe-area-inset-top));
  backdrop-filter:blur(10px)
}}
header h1{{font-size:clamp(1rem,4vw,1.35rem);font-weight:700;line-height:1.3}}
header .sub{{color:var(--dim);font-size:clamp(.75rem,2.5vw,.82rem);margin-top:6px;line-height:1.45}}
.toolbar{{display:flex;flex-direction:column;gap:10px;margin-top:12px}}
.toolbar-row{{display:flex;flex-wrap:wrap;gap:8px;align-items:center}}
nav{{display:none}}
.tab-select{{
  width:100%;min-height:var(--tap);background:#161b22;border:1px solid var(--border);
  color:var(--text);padding:10px 12px;border-radius:10px;font-size:1rem;appearance:none;
  background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%238b949e' d='M1 1l5 5 5-5'/%3E%3C/svg%3E");
  background-repeat:no-repeat;background-position:right 14px center;padding-right:36px
}}
.toolbar button,.toolbar .search-box{{
  min-height:var(--tap);font-size:.9rem;border-radius:10px
}}
.toolbar button{{
  flex:1;min-width:calc(33% - 6px);background:#161b22;border:1px solid var(--border);
  color:var(--text);padding:10px 12px;cursor:pointer
}}
.search-box{{
  width:100%;background:#161b22;border:1px solid var(--border);color:var(--text);
  padding:10px 14px;font-size:16px
}}
.search-box:focus{{outline:2px solid #388bfd;outline-offset:2px}}
#tooltip{{
  display:none;position:fixed;z-index:300;background:#1c2128;border:1px solid #388bfd;
  padding:10px 14px;border-radius:8px;max-width:min(320px,90vw);font-size:.85rem;
  pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.5)
}}
#tooltip strong{{color:#388bfd;display:block;margin-bottom:4px}}
.legend{{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:10px;font-size:.72rem}}
.legend span{{display:flex;align-items:center;gap:6px;color:var(--dim)}}
.legend i{{width:11px;height:11px;border-radius:3px;flex-shrink:0}}
main{{padding:12px 16px;max-width:1600px;margin:0 auto}}
.panel{{display:none}}.panel.active{{display:block}}
.canvas-wrap{{
  background:var(--panel);border:1px solid var(--border);border-radius:12px;
  overflow:auto;padding:8px;max-height:min(70dvh,560px);
  -webkit-overflow-scrolling:touch;overscroll-behavior:contain
}}
.canvas-hint{{
  display:block;font-size:.72rem;color:var(--dim);text-align:center;padding:6px 0 2px
}}
.diagram{{
  width:100%;max-width:100%;height:auto;display:block;
  transition:transform .15s ease;touch-action:pan-x pan-y
}}
.node:hover rect,.node:active rect{{filter:brightness(1.15);stroke-width:2.5}}
.info-grid{{display:grid;grid-template-columns:1fr;gap:12px;margin-top:16px}}
.info-card{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px}}
.info-card h3{{font-size:.9rem;margin-bottom:8px;color:#388bfd}}
.info-card ul{{padding-left:18px;color:var(--dim);font-size:.85rem;line-height:1.65}}
.module-grid{{display:grid;grid-template-columns:1fr;gap:10px;margin-top:12px}}
.module-grid.dense{{grid-template-columns:repeat(2,1fr)}}
.module-card{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px}}
.mc-title{{font-weight:600;font-size:.9rem;color:var(--text);word-break:break-word}}
.mc-sub{{font-size:.78rem;color:#388bfd;margin:4px 0;font-family:ui-monospace,monospace;word-break:break-all}}
.mc-desc{{font-size:.8rem;color:var(--dim);line-height:1.5}}
.step-list{{margin-top:12px}}
.step-row{{display:flex;gap:12px;padding:14px 0;border-bottom:1px solid var(--border);align-items:flex-start}}
.step-num{{
  flex-shrink:0;width:32px;height:32px;border-radius:50%;display:flex;align-items:center;
  justify-content:center;font-size:.8rem;font-weight:700;color:#0b0f14
}}
.step-row p{{color:var(--dim);font-size:.85rem;margin-top:4px}}
.two-col{{display:grid;grid-template-columns:1fr;gap:16px;margin-top:12px}}
.stat-bar{{
  display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin:12px 0;padding:12px;
  background:var(--panel);border:1px solid var(--border);border-radius:10px;font-size:.75rem;color:var(--dim)
}}
.stat-bar>div{{padding:8px;background:#161b22;border-radius:8px;text-align:center}}
.stat-bar b{{color:var(--text);font-size:1.1rem;display:block;margin-bottom:2px}}
.table-wrap{{
  overflow-x:auto;max-height:min(65dvh,520px);border:1px solid var(--border);
  border-radius:10px;margin-top:12px;-webkit-overflow-scrolling:touch
}}
.data-table{{width:100%;border-collapse:collapse;font-size:.8rem;min-width:0}}
.data-table th{{background:#161b22;color:var(--dim);text-align:left;padding:10px;position:sticky;top:0;z-index:1}}
.data-table td{{padding:10px;border-top:1px solid var(--border);vertical-align:top;word-break:break-word}}
.data-table code{{font-size:.78rem;word-break:break-all}}
.path-cell{{display:block;max-width:100%}}
.data-table tr:hover{{background:#161b22}}
.method{{padding:3px 8px;border-radius:4px;font-size:.72rem;font-weight:700;white-space:nowrap}}
.method-get{{background:#1a3d2e;color:#3fb950}}.method-post{{background:#1a3d4d;color:#388bfd}}
.method-put{{background:#3d2e1a;color:#d29922}}.method-patch{{background:#3d1a3d;color:#a371f7}}
.method-delete{{background:#3d1a1a;color:#f778ba}}.method-websocket{{background:#1a3d3d;color:#56d4dd}}
.deploy-section{{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:10px}}
.deploy-section h3{{color:{C['deploy']};font-size:.9rem;margin-bottom:8px}}
.deploy-section ul{{padding-left:18px;color:var(--dim);font-size:.85rem;line-height:1.65}}
.panel-head{{font-size:1rem;margin-bottom:6px;line-height:1.35}}
.panel-sub{{color:var(--dim);font-size:.85rem;margin-bottom:12px;line-height:1.45}}
.complete-badge{{
  display:inline-block;background:#1a3d2e;color:#3fb950;padding:3px 8px;border-radius:6px;
  font-size:.65rem;font-weight:600;margin-left:0;margin-top:6px;vertical-align:middle
}}
footer{{
  text-align:center;padding:16px;padding-bottom:max(16px,env(safe-area-inset-bottom));
  color:var(--dim);font-size:.72rem;border-top:1px solid var(--border);margin-top:32px
}}

/* Mobile: card-style tables */
@media(max-width:767px){{
  .data-table thead{{display:none}}
  .data-table tbody tr{{
    display:block;margin-bottom:10px;background:var(--panel);border:1px solid var(--border);
    border-radius:10px;padding:10px 12px
  }}
  .data-table td{{display:block;padding:4px 0;border:none}}
  .data-table td::before{{
    content:attr(data-label);display:block;font-size:.68rem;font-weight:600;
    color:var(--dim);text-transform:uppercase;letter-spacing:.04em;margin-bottom:2px
  }}
  .module-grid.dense{{grid-template-columns:1fr}}
  header h1 .complete-badge{{display:block;margin-left:0;margin-top:8px;width:fit-content}}
}}

/* Tablet+ */
@media(min-width:768px){{
  .legend{{display:flex;flex-wrap:wrap;grid-template-columns:unset}}
  .stat-bar{{grid-template-columns:repeat(3,1fr)}}
  .module-grid{{grid-template-columns:repeat(auto-fill,minmax(220px,1fr))}}
  .module-grid.dense{{grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}}
  .info-grid{{grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}}
  .two-col{{grid-template-columns:1fr 1fr}}
  .toolbar-row.zoom-row button{{flex:0;min-width:auto}}
}}

/* Desktop: show tab buttons, hide select */
@media(min-width:900px){{
  nav{{display:flex;flex-wrap:wrap;gap:6px}}
  nav button{{
    background:var(--panel);border:1px solid var(--border);color:var(--text);
    padding:7px 14px;border-radius:8px;cursor:pointer;font-size:.8rem;transition:.15s
  }}
  nav button:hover,nav button.active{{border-color:#388bfd;background:#161b22;color:#fff}}
  .tab-select{{display:none}}
  .toolbar{{flex-direction:row;flex-wrap:wrap;align-items:center}}
  .search-box{{width:240px;flex:0 1 auto;font-size:.85rem;min-height:38px}}
  .toolbar button{{flex:0;min-width:auto;min-height:38px;padding:7px 14px;font-size:.8rem}}
  .stat-bar{{display:flex;flex-wrap:wrap;grid-template-columns:unset}}
  .stat-bar>div{{background:transparent;padding:0;text-align:left}}
  .canvas-wrap{{max-height:82vh;padding:12px}}
  .diagram{{min-width:960px;width:100%}}
}}
</style>
</head>
<body>
<div id="tooltip"></div>
<header>
  <h1>LegalEase.AI — 100% Complete System Architecture<span class="complete-badge">STRICT COVERAGE</span></h1>
  <p class="sub">Auto-generated from codebase: {n_routes} API routes · {n_endpoints} endpoint files · {n_pages} frontend pages · {n_tables} DB tables · {n_env} env vars · full deployment guide</p>
  <div class="toolbar">
    <select class="tab-select" id="tab-select" aria-label="Choose section">
      <option value="master">Master Overview</option>
      <option value="deploy">Deployment Diagram</option>
      <option value="deployfull">Full Deploy Guide</option>
      <option value="routes">All {n_routes} API Routes</option>
      <option value="chat">Chat &amp; Ingest</option>
      <option value="evidence">Evidence Intel</option>
      <option value="drafting">Drafting</option>
      <option value="modules">API Modules</option>
      <option value="frontend">All {n_pages} Pages</option>
      <option value="env">All {n_env} Env Vars</option>
      <option value="data">All {n_tables} DB Tables</option>
      <option value="backend">Backend Services</option>
      <option value="scripts">Deploy Scripts</option>
    </select>
    <nav>
      <button class="active" data-panel="master">Master Overview</button>
      <button data-panel="deploy">Deployment Diagram</button>
      <button data-panel="deployfull">Full Deploy Guide</button>
      <button data-panel="routes">All {n_routes} API Routes</button>
      <button data-panel="chat">Chat & Ingest</button>
      <button data-panel="evidence">Evidence Intel</button>
      <button data-panel="drafting">Drafting</button>
      <button data-panel="modules">API Modules</button>
      <button data-panel="frontend">All {n_pages} Pages</button>
      <button data-panel="env">All {n_env} Env Vars</button>
      <button data-panel="data">All {n_tables} DB Tables</button>
      <button data-panel="backend">Backend Services</button>
      <button data-panel="scripts">Deploy Scripts</button>
    </nav>
    <input type="search" class="search-box" id="search" placeholder="Search routes, pages, env vars..." oninput="filterAll(this.value)" autocomplete="off">
    <div class="toolbar-row zoom-row">
      <button type="button" onclick="zoom(1.12)" aria-label="Zoom in">Zoom +</button>
      <button type="button" onclick="zoom(0.88)" aria-label="Zoom out">Zoom −</button>
      <button type="button" onclick="zoomReset()" aria-label="Reset zoom">Reset</button>
    </div>
  </div>
  <div class="legend">
    <span><i style="background:{C['fe']}"></i>Frontend</span>
    <span><i style="background:{C['be']}"></i>Backend</span>
    <span><i style="background:{C['ai']}"></i>AI</span>
    <span><i style="background:{C['data']}"></i>Data</span>
    <span><i style="background:{C['learn']}"></i>Learning</span>
    <span><i style="background:{C['deploy']}"></i>Deploy</span>
    <span><i style="background:{C['warn']}"></i>Security</span>
  </div>
</header>
<main>
  <div class="stat-bar">
    <div><b>{n_routes}</b>API routes (every route)</div>
    <div><b>{n_endpoints}</b>endpoint .py files</div>
    <div><b>{n_pages}</b>frontend pages (auto-scanned)</div>
    <div><b>{n_tables}</b>database tables</div>
    <div><b>{n_env}</b>environment variables</div>
    <div><b>{PROD_URL.replace('https://','')}</b>production</div>
  </div>

  <div id="master" class="panel active">
    {canvas_block(master)}
    <div class="info-grid">
      <div class="info-card"><h3>What this diagram shows</h3><ul>
        <li>Complete path from browser to PostgreSQL/FAISS/Ollama/Gemini</li>
        <li>All 6 backend domain columns with 8 services each</li>
        <li>16 frontend modules + shared providers</li>
        <li>AI modes, learning loop, premium tools, external APIs</li>
      </ul></div>
      <div class="info-card"><h3>Recent work included</h3><ul>
        <li>Evidence Intelligence Center (upload, OCR, entities, timeline)</li>
        <li>Feedback/thumbs Postgres fix (adaptive_mode_stats)</li>
        <li>Laptop vs EC2 env separation (.env.local)</li>
        <li>EC2 deploy via aws_update.ps1 to DuckDNS production</li>
      </ul></div>
      <div class="info-card"><h3>Key files</h3><ul>
        <li>backend/app/main.py — gateway</li>
        <li>backend/app/services/chat_service.py — chat orchestration</li>
        <li>web/components/evidence/EvidenceWorkspace.tsx — discovery UI</li>
        <li>scripts/aws_update.ps1 — production deploy</li>
      </ul></div>
    </div>
  </div>

  <div id="deploy" class="panel">
    {canvas_block(deploy, "Swipe horizontally on small screens for full deploy diagram")}
    <div class="two-col">
      <div class="info-card"><h3>EC2 deploy steps</h3>{step_list(DEPLOY_STEPS_EC2, C['deploy'])}</div>
      <div class="info-card"><h3>Laptop dev steps</h3>{step_list(DEPLOY_STEPS_LAPTOP, C['fe'])}</div>
    </div>
    <div class="info-card" style="margin-top:16px"><h3>Troubleshooting matrix (complete)</h3>
    <div class="module-grid">{"".join(f'<div class="module-card searchable" style="border-left:3px solid {C["warn"]}"><div class="mc-title">{esc(a)}</div><div class="mc-desc">{esc(b)}</div></div>' for a,b in TROUBLESHOOT)}</div></div>
  </div>

  <div id="deployfull" class="panel">
    <p class="panel-head">Complete Deployment Guide (Document 7 equivalent)</p>
    <p class="panel-sub">Every production and laptop deploy step — no placeholders. Values: {PROD_URL}, EC2 {EC2_IP}, path {EC2_PATH}</p>
    {deploy_full}
  </div>

  <div id="routes" class="panel">
    <p class="panel-head">All {n_routes} API Routes — auto-extracted from backend/app/api/v1/endpoints/</p>
    <p class="panel-sub">Every @router.get/post/put/patch/delete/websocket in the codebase. Use search to filter.</p>
    {route_table}
  </div>

  <div id="chat" class="panel">{canvas_block(chat)}</div>
  <div id="evidence" class="panel">{canvas_block(evidence)}</div>
  <div id="drafting" class="panel">{canvas_block(drafting)}</div>

  <div id="modules" class="panel">
    <p class="panel-head">All {len(API_MODULES)} API Endpoint Modules (grouped)</p>
    {card_grid(api_cards, C['be'])}
  </div>

  <div id="frontend" class="panel">
    <p class="panel-head">All {n_pages} Frontend Pages — auto-scanned from web/app/**/page.tsx</p>
    <p class="panel-sub">Includes auth, legal, portal, intake, matters, esign — every page.tsx in the repo.</p>
    {card_grid(fe_cards, C['fe'])}
  </div>

  <div id="env" class="panel">
    <p class="panel-head">All {n_env} Environment Variables — from every .env*.example file</p>
    <p class="panel-sub">Sources: .env.example, .env.local.example, .env.docker.example, deploy/aws/.env.production.example, web/.env.local.example, .env.pilot.example</p>
    {env_table}
  </div>

  <div id="data" class="panel">
    <p class="panel-head">All {n_tables} Database Tables — auto-extracted from CREATE TABLE in backend/</p>
    {db_html}
    <div class="info-grid" style="margin-top:20px">
      <div class="info-card"><h3>FAISS index paths</h3><ul>
        <li>Global KB: faiss_indexes/user_&lt;id&gt;/_unlinked/</li>
        <li>Matter scope: faiss_indexes/user_&lt;id&gt;/matter_&lt;uuid&gt;/</li>
        <li>Past chats: faiss_indexes/user_&lt;id&gt;/conversations/</li>
      </ul></div>
      <div class="info-card"><h3>Docker volumes</h3><ul>
        <li>postgres_data, redis_data, app_data</li>
        <li>./faiss_indexes, ./Data bind mounts</li>
      </ul></div>
      <div class="info-card"><h3>Endpoint files ({n_endpoints})</h3><ul>
        {"".join(f"<li><code>{esc(f)}</code></li>" for f in endpoint_files)}
      </ul></div>
    </div>
  </div>

  <div id="backend" class="panel">
    <p class="panel-head">Core Backend Services ({len(BACKEND_CORE_SERVICES)} key modules)</p>
    <p class="panel-sub">backend/app/core/ and backend/app/services/ — intelligence and domain logic</p>
    {card_grid([(a, "backend", b) for a, b in BACKEND_CORE_SERVICES], C['be'])}
  </div>

  <div id="scripts" class="panel">
    <p class="panel-head">All Deploy & Ops Scripts ({len(DEPLOY_SCRIPTS)})</p>
    {card_grid([(a, "script", b) for a, b in DEPLOY_SCRIPTS], C['deploy'])}
  </div>
</main>
<footer>LegalEase.AI 100% Architecture Reference · {n_routes} routes · {n_pages} pages · {n_tables} tables · {n_env} env vars · Generated from codebase · {PROD_URL}</footer>
<script>
let scale=1;
const tip=document.getElementById('tooltip');

function switchPanel(id){{
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.panel===id));
  const sel=document.getElementById('tab-select');
  if(sel&&sel.value!==id)sel.value=id;
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('active'));
  const panel=document.getElementById(id);
  if(panel)panel.classList.add('active');
  document.getElementById('search').value='';
  filterAll('');
  if(window.innerWidth<900)window.scrollTo({{top:document.querySelector('main').offsetTop-8,behavior:'smooth'}});
}}

document.getElementById('tab-select')?.addEventListener('change',e=>switchPanel(e.target.value));
document.querySelectorAll('nav button').forEach(btn=>btn.addEventListener('click',()=>switchPanel(btn.dataset.panel)));

function showTip(n,e){{
  const t=n.dataset.title,d=n.dataset.desc;
  if(!t)return;
  tip.innerHTML='<strong>'+t+'</strong><br>'+(d||'');
  tip.style.display='block';
  const x=(e&&e.clientX)?e.clientX+14:14;
  const y=(e&&e.clientY)?e.clientY+14:80;
  tip.style.left=Math.min(x,window.innerWidth-280)+'px';
  tip.style.top=Math.min(y,window.innerHeight-120)+'px';
}}
document.querySelectorAll('.node').forEach(n=>{{
  n.addEventListener('mouseenter',e=>showTip(n,e));
  n.addEventListener('mousemove',e=>{{tip.style.left=Math.min(e.clientX+14,window.innerWidth-280)+'px';tip.style.top=Math.min(e.clientY+14,window.innerHeight-120)+'px';}});
  n.addEventListener('mouseleave',()=>{{tip.style.display='none';}});
  n.addEventListener('click',e=>{{showTip(n,e);setTimeout(()=>{{tip.style.display='none';}},2500);}});
}});

function zoom(f){{scale*=f;document.querySelectorAll('.diagram').forEach(s=>{{s.style.transform='scale('+scale+')';s.style.transformOrigin='top left';}});}}
function zoomReset(){{scale=1;document.querySelectorAll('.diagram').forEach(s=>s.style.transform='');}}
function filterAll(q){{
  q=q.toLowerCase();
  document.querySelectorAll('.module-card,.deploy-section,.searchable').forEach(el=>{{
    el.style.display=el.textContent.toLowerCase().includes(q)?'':'none';
  }});
}}
</script>
</body>
</html>"""


def main() -> None:
    content = build_html()
    routes = extract_routes()
    pages = discover_frontend_pages()
    tables = extract_db_tables()
    envs = extract_all_env_vars()
    OUT_HTML.parent.mkdir(parents=True, exist_ok=True)
    OUT_HTML.write_text(content, encoding="utf-8")
    DESKTOP_COPY.write_text(content, encoding="utf-8")
    print(f"Generated: {OUT_HTML} ({len(content.splitlines())} lines)")
    print(f"  Routes: {len(routes)} | Pages: {len(pages)} | DB tables: {len(tables)} | Env vars: {len(envs)}")
    print(f"Copied to: {DESKTOP_COPY}")


if __name__ == "__main__":
    main()
