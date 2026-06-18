#!/usr/bin/env python3
"""
Generate compact LegalEase system architecture for PowerPoint (16:9 slides).
Output: docs/LegalEase_System_Architecture_PPT.html
"""
from __future__ import annotations

import html
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "LegalEase_System_Architecture_PPT.html"
DESKTOP = Path.home() / "Desktop" / "LegalEase_System_Architecture_PPT.html"

# Reuse codebase extractors from the detailed architecture generator
_spec = importlib.util.spec_from_file_location(
    "arch_full", ROOT / "scripts" / "render_system_architecture_html.py"
)
arch = importlib.util.module_from_spec(_spec)
assert _spec.loader
_spec.loader.exec_module(arch)

PROD_URL = arch.PROD_URL
EC2_IP = arch.EC2_IP
API_MODULES = arch.API_MODULES


def esc(s: str) -> str:
    return html.escape(s, quote=True)


def chip(text: str, color: str = "#1e40af") -> str:
    return (
        f'<span class="chip" style="border-color:{color};color:{color}">'
        f"{esc(text)}</span>"
    )


def bullet_list(items: list[str], cols: int = 2) -> str:
    mid = (len(items) + cols - 1) // cols
    chunks = [items[i : i + mid] for i in range(0, len(items), mid)]
    parts = []
    for chunk in chunks[:cols]:
        lis = "".join(f"<li>{esc(x)}</li>" for x in chunk)
        parts.append(f"<ul>{lis}</ul>")
    return f'<div class="cols-{cols}">{"".join(parts)}</div>'


def build_flow_svg() -> str:
    """Single end-to-end diagram — 1280×520, light PPT palette."""
    return """
<svg viewBox="0 0 1280 520" xmlns="http://www.w3.org/2000/svg" class="flow-svg">
  <defs>
    <marker id="arr" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
      <polygon points="0 0, 8 3, 0 6" fill="#64748b"/>
    </marker>
  </defs>
  <rect x="0" y="0" width="1280" height="520" fill="#f8fafc" rx="8"/>
  <!-- Row 1: Users -->
  <rect x="40" y="24" width="1200" height="72" rx="10" fill="#eff6ff" stroke="#3b82f6" stroke-width="2"/>
  <text x="60" y="50" fill="#1e40af" font-size="13" font-weight="700">CLIENTS</text>
  <rect x="180" y="38" width="200" height="44" rx="6" fill="#fff" stroke="#93c5fd"/>
  <text x="280" y="56" text-anchor="middle" fill="#1e293b" font-size="11" font-weight="600">Lawyer / Paralegal</text>
  <text x="280" y="70" text-anchor="middle" fill="#64748b" font-size="9">Browser + JWT</text>
  <rect x="400" y="38" width="180" height="44" rx="6" fill="#fff" stroke="#93c5fd"/>
  <text x="490" y="56" text-anchor="middle" fill="#1e293b" font-size="11" font-weight="600">Client Portal</text>
  <text x="490" y="70" text-anchor="middle" fill="#64748b" font-size="9">Magic link upload</text>
  <rect x="600" y="38" width="200" height="44" rx="6" fill="#fff" stroke="#67e8f9"/>
  <text x="700" y="56" text-anchor="middle" fill="#0e7490" font-size="11" font-weight="600">Laptop Dev</text>
  <text x="700" y="70" text-anchor="middle" fill="#64748b" font-size="9">:3000 / :8000 Ollama</text>
  <rect x="820" y="38" width="380" height="44" rx="6" fill="#fff" stroke="#67e8f9"/>
  <text x="1010" y="56" text-anchor="middle" fill="#0e7490" font-size="11" font-weight="600">Production EC2</text>
  <text x="1010" y="70" text-anchor="middle" fill="#64748b" font-size="9">legalease.duckdns.org · Docker Compose</text>

  <!-- Row 2: Edge -->
  <rect x="40" y="112" width="1200" height="80" rx="10" fill="#ecfeff" stroke="#06b6d4" stroke-width="2"/>
  <text x="60" y="138" fill="#0e7490" font-size="13" font-weight="700">EDGE</text>
  <rect x="160" y="126" width="280" height="52" rx="6" fill="#fff" stroke="#a5f3fc"/>
  <text x="300" y="148" text-anchor="middle" fill="#1e293b" font-size="11" font-weight="600">nginx :80 / :443</text>
  <text x="300" y="164" text-anchor="middle" fill="#64748b" font-size="9">/api/* → api:8000 · /* → web:3000 · TLS · SSE 300s</text>
  <rect x="460" y="126" width="240" height="52" rx="6" fill="#fff" stroke="#a5f3fc"/>
  <text x="580" y="148" text-anchor="middle" fill="#1e293b" font-size="11" font-weight="600">DuckDNS + SSL</text>
  <text x="580" y="164" text-anchor="middle" fill="#64748b" font-size="9">Let's Encrypt · Cloudflare fallback</text>
  <rect x="720" y="126" width="500" height="52" rx="6" fill="#fff" stroke="#a5f3fc"/>
  <text x="970" y="148" text-anchor="middle" fill="#1e293b" font-size="11" font-weight="600">Deploy: aws_update.ps1 → fix-ec2-env → ec2-go-live.sh</text>
  <text x="970" y="164" text-anchor="middle" fill="#64748b" font-size="9">GitHub Actions CI · ~126 pytest · rate limit · CORS · RBAC</text>

  <!-- Row 3: Apps -->
  <rect x="40" y="208" width="580" height="140" rx="10" fill="#eff6ff" stroke="#3b82f6" stroke-width="2"/>
  <text x="60" y="234" fill="#1e40af" font-size="13" font-weight="700">FRONTEND — Next.js 15 · React 19</text>
  <text x="60" y="258" fill="#334155" font-size="10">Chat SSE · Documents · Matters · Evidence Intel · Drafting v4</text>
  <text x="60" y="274" fill="#334155" font-size="10">Intake CRM · Billing · Litigation · Firm Chat · Enterprise DMS</text>
  <text x="60" y="290" fill="#334155" font-size="10">IPC↔BNS · Analytics · Settings/Memory · Admin · Portal</text>
  <text x="60" y="314" fill="#64748b" font-size="9">Providers: Auth · ChatSession · ApiConnection · Stripe</text>
  <text x="60" y="330" fill="#64748b" font-size="9">Saved chats · thread URL · matter scope · mobile nav</text>

  <rect x="640" y="208" width="600" height="140" rx="10" fill="#f0fdf4" stroke="#22c55e" stroke-width="2"/>
  <text x="660" y="234" fill="#166534" font-size="13" font-weight="700">BACKEND — FastAPI · Uvicorn</text>
  <text x="660" y="258" fill="#334155" font-size="10">38 endpoint modules · 493 REST routes · SSE /chat/stream</text>
  <text x="660" y="274" fill="#334155" font-size="10">chat · documents · matters · ediscovery · drafting · crm · billing</text>
  <text x="660" y="290" fill="#334155" font-size="10">learning · memory · collab WS · subscriptions · enterprise · admin</text>
  <text x="660" y="314" fill="#64748b" font-size="9">Middleware: CORS · RateLimit · MemoryGuard · JWT auth</text>
  <text x="660" y="330" fill="#64748b" font-size="9">Services: chat_service · kb_pipeline · rag · adaptive_learning</text>

  <line x1="620" y1="278" x2="640" y2="278" stroke="#64748b" stroke-width="2" marker-end="url(#arr)"/>

  <!-- Row 4: AI -->
  <rect x="40" y="364" width="760" height="132" rx="10" fill="#faf5ff" stroke="#a855f7" stroke-width="2"/>
  <text x="60" y="390" fill="#6b21a8" font-size="13" font-weight="700">AI &amp; INTELLIGENCE</text>
  <text x="60" y="414" fill="#334155" font-size="10">Modes: Knowledge Base (RAG) · Web Intel · Hybrid · Deep Case · Open Law</text>
  <text x="60" y="430" fill="#334155" font-size="10">RAG: FAISS dense + BM25 sparse + MMR + cross-encoder rerank · matter/global scope</text>
  <text x="60" y="446" fill="#334155" font-size="10">Memory: persona · facts · thread summaries · past-chat RAG · prompt budgets</text>
  <text x="60" y="462" fill="#334155" font-size="10">Learning: thumbs feedback · chunk boosts · query expansion · JSONL export · coach</text>
  <text x="60" y="478" fill="#64748b" font-size="9">LLM: Ollama (laptop KB) · Gemini (EC2 web/hybrid) · Tavily search · STT Whisper</text>

  <!-- Row 4: Data -->
  <rect x="820" y="364" width="420" height="132" rx="10" fill="#fffbeb" stroke="#f59e0b" stroke-width="2"/>
  <text x="840" y="390" fill="#b45309" font-size="13" font-weight="700">DATA LAYER</text>
  <text x="840" y="414" fill="#334155" font-size="10">PostgreSQL (prod) / SQLite (dev) — 121 tables</text>
  <text x="840" y="430" fill="#334155" font-size="10">Redis: sessions · ML queues · rate-limit buckets</text>
  <text x="840" y="446" fill="#334155" font-size="10">FAISS indexes · Data/ uploads · faiss_indexes/ volume</text>
  <text x="840" y="462" fill="#334155" font-size="10">chat_history · matters · evidence · drafting · billing · CRM</text>
  <text x="840" y="478" fill="#64748b" font-size="9">Stripe webhooks · S3-ready paths · backup_legalease.py</text>

  <line x1="800" y1="430" x2="820" y2="430" stroke="#64748b" stroke-width="2" marker-end="url(#arr)"/>
</svg>"""


def group_frontend_pages(pages: list[tuple[str, str, str]]) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {
        "Core": [],
        "Matters & Cases": [],
        "Practice Ops": [],
        "Enterprise & Tools": [],
        "Account": [],
    }
    for route, _, _ in pages:
        r = route
        if r in ("/", "/dashboard", "/documents", "/discovery"):
            groups["Core"].append(r)
        elif r.startswith("/matters") or r.startswith("/drafting"):
            groups["Matters & Cases"].append(r)
        elif any(r.startswith(p) for p in ("/intake", "/billing", "/litigation", "/collaboration", "/crm")):
            groups["Practice Ops"].append(r)
        elif any(r.startswith(p) for p in ("/enterprise", "/tools", "/analytics", "/admin")):
            groups["Enterprise & Tools"].append(r)
        elif r.startswith("/settings") or r.startswith("/portal") or r.startswith("/login"):
            groups["Account"].append(r)
        else:
            groups["Core"].append(r)
    return {k: v for k, v in groups.items() if v}


def group_api_modules() -> dict[str, list[tuple[str, str, str]]]:
    groups: dict[str, list[tuple[str, str, str]]] = {
        "AI & Chat": [],
        "Documents & KB": [],
        "Practice Management": [],
        "Enterprise & Billing": [],
        "Platform & Admin": [],
    }
    ai = {"chat", "sessions", "learning", "feedback", "memory", "speech", "engines", "research_log", "kb_debug"}
    docs = {"documents", "ediscovery", "templates", "clauses", "ipc_bns_v3", "legal_conversion"}
    practice = {"matters", "drafting", "crm", "practice", "portal", "esign", "collab"}
    ent = {"billing", "subscriptions", "enterprise", "enterprise_workspace", "trust", "orgs"}
    for mod in API_MODULES:
        name = mod[0]
        if name in ai:
            groups["AI & Chat"].append(mod)
        elif name in docs:
            groups["Documents & KB"].append(mod)
        elif name in practice:
            groups["Practice Management"].append(mod)
        elif name in ent:
            groups["Enterprise & Billing"].append(mod)
        else:
            groups["Platform & Admin"].append(mod)
    return groups


def build_html() -> str:
    routes = arch.extract_routes()
    pages = arch.discover_frontend_pages()
    tables = arch.extract_db_tables()
    envs = arch.extract_all_env_vars()
    endpoints = arch.list_endpoint_files()
    fe_groups = group_frontend_pages(pages)
    api_groups = group_api_modules()

    fe_section = ""
    colors = ["#1e40af", "#0e7490", "#166534", "#7c3aed", "#b45309"]
    for i, (title, routes_list) in enumerate(fe_groups.items()):
        c = colors[i % len(colors)]
        route_chips = " ".join(chip(r, c) for r in sorted(routes_list))
        fe_section += f"""
<div class="group-block">
  <h3 style="color:{c}">{esc(title)} <span class="cnt">({len(routes_list)})</span></h3>
  <div class="chip-row">{route_chips}</div>
</div>"""

    api_section = ""
    for i, (title, mods) in enumerate(api_groups.items()):
        c = colors[i % len(colors)]
        items = "".join(
            f"<li><strong>{esc(m[0])}</strong> <code>{esc(m[1])}</code> — {esc(m[2][:55])}</li>"
            for m in mods
        )
        api_section += f"""
<div class="group-block half">
  <h3 style="color:{c}">{esc(title)} <span class="cnt">({len(mods)} modules)</span></h3>
  <ul class="compact">{items}</ul>
</div>"""

    deploy_bullets = [
        f"Production: {PROD_URL} · EC2 {EC2_IP} · /opt/legalease",
        "Stack: nginx + web + api + postgres + redis (Docker Compose)",
        "Deploy: .\\scripts\\aws_update.ps1 -PublicUrl https://legalease.duckdns.org",
        "Laptop: setup_local_env.ps1 → run_backend.ps1 → run_web.ps1",
        "Env: 6 template files · 314 vars · never copy EC2 .env to laptop",
        "Memory tiers: low ≤8GB · medium · high >16GB (apply-ec2-tier.sh)",
        "Backup: py scripts/backup_legalease.py · pg_dump · faiss restore",
        "Smoke: health/live · login · KB chat · evidence · thumbs ok:true",
    ]

    data_bullets = [
        f"{len(tables)} PostgreSQL/SQLite tables (auto-scanned CREATE TABLE)",
        "Core: users · chat_history · matters · documents · faiss_meta",
        "Evidence: discovery_items · evidence_intel · thread_attachments",
        "Drafting: drafting_documents · versions · comments · annexures",
        "Billing: time_entries · invoices · trust_accounts · subscriptions",
        "Learning: adaptive_interactions · adaptive_mode_stats · thread_summaries",
        "Enterprise: deal_rooms · orgs · collab_rooms · enterprise_kb",
    ]

    security_bullets = [
        "JWT + bcrypt · SUPERADMIN_USERNAMES · account suspension",
        "Rate limit: global 180/min · read 400/min · chat exempt · auth 20/min",
        "CORS_ORIGINS exact match · FORCE_HTTPS · SECURITY_HEADERS_ENABLED",
        "matter_policy scope · per-user FAISS · row-level user_id on all queries",
        "Stripe webhook signature · SAAS_PRODUCTION_STRICT gate",
        "PII redactor · privilege flags · client portal magic links",
    ]

    flow_svg = build_flow_svg()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LegalEase.AI — System Architecture (PPT)</title>
<style>
@page {{ size: landscape; margin: 0.4in; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: 'Segoe UI', Calibri, system-ui, sans-serif;
  background: #e2e8f0; color: #0f172a; line-height: 1.35;
}}
.toolbar {{
  position: sticky; top: 0; z-index: 99; background: #1e293b; color: #fff;
  padding: 10px 20px; display: flex; flex-wrap: wrap; gap: 12px; align-items: center;
  font-size: 13px;
}}
.toolbar button {{
  background: #3b82f6; color: #fff; border: none; padding: 8px 16px;
  border-radius: 6px; cursor: pointer; font-size: 13px;
}}
.toolbar button:hover {{ background: #2563eb; }}
.deck {{ max-width: 1280px; margin: 24px auto; display: flex; flex-direction: column; gap: 28px; }}
.slide {{
  width: 100%; aspect-ratio: 16/9; background: #fff; border-radius: 8px;
  box-shadow: 0 4px 24px rgba(15,23,42,.12); padding: 36px 44px 32px;
  page-break-after: always; overflow: hidden; display: flex; flex-direction: column;
}}
.slide.cover {{
  background: linear-gradient(135deg, #1e3a5f 0%, #1e40af 50%, #0e7490 100%);
  color: #fff; justify-content: center;
}}
.slide.cover h1 {{ font-size: 2.4rem; font-weight: 700; margin-bottom: 8px; }}
.slide.cover .tag {{ font-size: 1rem; opacity: .9; margin-bottom: 28px; }}
.stats {{
  display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-top: 8px;
}}
.stat {{
  background: rgba(255,255,255,.15); border-radius: 8px; padding: 12px; text-align: center;
}}
.stat b {{ display: block; font-size: 1.6rem; }}
.stat span {{ font-size: .72rem; opacity: .85; }}
.slide h2 {{
  font-size: 1.35rem; color: #1e40af; margin-bottom: 14px;
  border-bottom: 3px solid #3b82f6; padding-bottom: 6px; flex-shrink: 0;
}}
.slide .sub {{ font-size: .78rem; color: #64748b; margin: -8px 0 12px; }}
.slide-body {{ flex: 1; min-height: 0; overflow: hidden; }}
.flow-svg {{ width: 100%; height: auto; display: block; }}
.group-block {{ margin-bottom: 12px; }}
.group-block.half {{ width: 48%; display: inline-block; vertical-align: top; margin-right: 2%; }}
.group-block h3 {{ font-size: .82rem; margin-bottom: 6px; }}
.cnt {{ font-weight: 400; color: #64748b; font-size: .75rem; }}
.chip-row {{ display: flex; flex-wrap: wrap; gap: 5px; }}
.chip {{
  display: inline-block; font-size: .62rem; padding: 2px 7px; border-radius: 4px;
  border: 1px solid; background: #f8fafc; white-space: nowrap;
}}
ul.compact {{ font-size: .62rem; color: #334155; padding-left: 16px; columns: 1; }}
ul.compact li {{ margin-bottom: 2px; break-inside: avoid; }}
ul.compact code {{ font-size: .58rem; color: #0e7490; }}
.cols-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; font-size: .78rem; }}
.cols-2 ul {{ padding-left: 18px; color: #334155; }}
.cols-2 li {{ margin-bottom: 4px; }}
.three-col {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 14px; height: 100%; }}
.three-col .col h3 {{ font-size: .8rem; margin-bottom: 8px; color: #1e40af; }}
.three-col .col ul {{ font-size: .68rem; padding-left: 16px; color: #334155; }}
.three-col .col li {{ margin-bottom: 3px; }}
.footer-note {{ font-size: .65rem; color: #94a3b8; margin-top: auto; padding-top: 8px; }}
@media print {{
  body {{ background: #fff; }}
  .toolbar {{ display: none; }}
  .deck {{ margin: 0; gap: 0; max-width: none; }}
  .slide {{ box-shadow: none; border-radius: 0; page-break-after: always; }}
}}
</style>
</head>
<body>
<div class="toolbar">
  <strong>LegalEase PPT Architecture</strong>
  <span>6 slides · 16:9 · Print or screenshot into PowerPoint</span>
  <button type="button" onclick="window.print()">Print / Save as PDF</button>
</div>

<div class="deck">

<!-- SLIDE 1: Cover -->
<section class="slide cover">
  <h1>LegalEase.AI</h1>
  <p class="tag">Complete System Architecture — Indian Legal Intelligence Platform</p>
  <div class="stats">
    <div class="stat"><b>{len(routes)}</b><span>API routes</span></div>
    <div class="stat"><b>{len(endpoints)}</b><span>API modules</span></div>
    <div class="stat"><b>{len(pages)}</b><span>Frontend pages</span></div>
    <div class="stat"><b>{len(tables)}</b><span>DB tables</span></div>
    <div class="stat"><b>{len(envs)}</b><span>Env variables</span></div>
  </div>
  <p style="margin-top:20px;font-size:.85rem;opacity:.9">{esc(PROD_URL)} · FastAPI + Next.js 15 · RAG + Memory + Adaptive Learning</p>
</section>

<!-- SLIDE 2: End-to-end flow -->
<section class="slide">
  <h2>End-to-End Platform Architecture</h2>
  <p class="sub">Client → Edge → Frontend → Backend → AI → Data — one view of the full stack</p>
  <div class="slide-body">{flow_svg}</div>
  <p class="footer-note">Auto-generated from codebase · {len(routes)} routes · {len(pages)} pages · {len(tables)} tables</p>
</section>

<!-- SLIDE 3: Frontend -->
<section class="slide">
  <h2>Frontend — {len(pages)} Pages (Next.js App Router)</h2>
  <p class="sub">All routes under web/app/**/page.tsx — grouped by product area</p>
  <div class="slide-body">{fe_section}</div>
</section>

<!-- SLIDE 4: Backend API -->
<section class="slide">
  <h2>Backend API — {len(endpoints)} Modules · {len(routes)} Routes</h2>
  <p class="sub">FastAPI /api/v1/* — every endpoint module with prefix and purpose</p>
  <div class="slide-body">{api_section}</div>
</section>

<!-- SLIDE 5: AI + Data + Security -->
<section class="slide">
  <h2>Intelligence · Data · Security</h2>
  <p class="sub">RAG pipeline, persistence layer, and production hardening</p>
  <div class="slide-body three-col">
    <div class="col">
      <h3>🧠 AI Pipeline</h3>
      <ul>
        <li>KB mode: upload PDF → chunk → embed → FAISS → retrieve → synthesize</li>
        <li>Web Intel: Tavily + Gemini live Indian law research</li>
        <li>Hybrid / Deep Case: matter-scoped KB + web fallback</li>
        <li>Thread memory + user persona + past-chat RAG injection</li>
        <li>Thumbs feedback → chunk boost + query expansion (adaptive_learning)</li>
        <li>Evidence Intel: extract · tag · contradict · privilege scan</li>
        <li>Drafting v4: copilot · redline · court bundle PDF export</li>
        <li>STT: faster-whisper + browser fallback</li>
      </ul>
    </div>
    <div class="col">
      <h3>🗄 Data Layer ({len(tables)} tables)</h3>
      <ul>
        {''.join(f'<li>{esc(b)}</li>' for b in data_bullets)}
      </ul>
    </div>
    <div class="col">
      <h3>🔒 Security &amp; Ops</h3>
      <ul>
        {''.join(f'<li>{esc(b)}</li>' for b in security_bullets)}
      </ul>
    </div>
  </div>
</section>

<!-- SLIDE 6: Deployment -->
<section class="slide">
  <h2>Deployment &amp; Operations</h2>
  <p class="sub">Laptop dev vs EC2 production — scripts, env, and verify checklist</p>
  <div class="slide-body cols-2">
    <div>
      <h3 style="color:#0e7490;font-size:.9rem;margin-bottom:8px">Production (EC2)</h3>
      <ul>
        {''.join(f'<li>{esc(b)}</li>' for b in deploy_bullets[:4])}
      </ul>
      <h3 style="color:#166534;font-size:.9rem;margin:14px 0 8px">Docker Services</h3>
      <ul>
        <li><strong>nginx</strong> — TLS reverse proxy, 300s SSE timeout</li>
        <li><strong>web</strong> — Next.js, NEXT_PUBLIC_API_URL baked at build</li>
        <li><strong>api</strong> — FastAPI Uvicorn workers=1 on 8GB tier</li>
        <li><strong>postgres</strong> — postgres_data volume, all SaaS tables</li>
        <li><strong>redis</strong> — sessions, ML queues, rate-limit buckets</li>
        <li><strong>worker / ml-worker</strong> — optional profiles (off on low RAM)</li>
      </ul>
    </div>
    <div>
      <h3 style="color:#1e40af;font-size:.9rem;margin-bottom:8px">Laptop + Verify</h3>
      <ul>
        {''.join(f'<li>{esc(b)}</li>' for b in deploy_bullets[4:])}
      </ul>
      <h3 style="color:#b45309;font-size:.9rem;margin:14px 0 8px">Key Scripts</h3>
      <ul>
        <li><code>scripts/aws_update.ps1</code> — full deploy tarball to EC2</li>
        <li><code>scripts/aws_go_live.ps1</code> — hotfix without full sync</li>
        <li><code>deploy/aws/ec2-go-live.sh</code> — rebuild api+web on server</li>
        <li><code>deploy/aws/fix-ec2-env.sh</code> — CORS, DB hostnames, URLs</li>
        <li><code>run_backend.ps1</code> / <code>run_web.ps1</code> — local dev</li>
        <li><code>scripts/backup_legalease.py</code> — manual backup</li>
      </ul>
    </div>
  </div>
  <p class="footer-note">Full reference: docs/LegalEase_System_Architecture.html · docs/LegalEase_Product_Architecture_Suite.pdf</p>
</section>

</div>
</body>
</html>"""


def main() -> None:
    html_out = build_html()
    OUT.write_text(html_out, encoding="utf-8")
    DESKTOP.write_text(html_out, encoding="utf-8")
    routes = len(arch.extract_routes())
    pages = len(arch.discover_frontend_pages())
    print(f"Generated: {OUT} ({len(html_out.splitlines())} lines)")
    print(f"  Slides: 6 | Routes: {routes} | Pages: {pages}")
    print(f"Copied to: {DESKTOP}")
    print("Open in browser -> Print / Save as PDF -> Import slides into PowerPoint")


if __name__ == "__main__":
    main()
