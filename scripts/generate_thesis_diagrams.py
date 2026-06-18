#!/usr/bin/env python3
"""Generate architecture diagram PNGs for LegalEase SaaS Thesis."""
from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "diagrams"

# LegalEase brand palette
NAVY = "#142850"
BLUE = "#27496D"
TEAL = "#0C7B93"
ACCENT = "#00A8CC"
LIGHT = "#E8F4F8"
WHITE = "#FFFFFF"
GRAY = "#64748B"
GREEN = "#059669"
ORANGE = "#EA580C"
PURPLE = "#7C3AED"


def _box(ax, x, y, w, h, text, color=BLUE, text_color=WHITE, fontsize=8, bold=False):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.02,rounding_size=0.08",
        facecolor=color, edgecolor=NAVY, linewidth=1.2, zorder=2,
    )
    ax.add_patch(patch)
    weight = "bold" if bold else "normal"
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fontsize, color=text_color, weight=weight, wrap=True, zorder=3)


def _arrow(ax, x1, y1, x2, y2, color=NAVY):
    ax.add_patch(FancyArrowPatch(
        (x1, y1), (x2, y2),
        arrowstyle="-|>", mutation_scale=12, linewidth=1.4,
        color=color, zorder=1, connectionstyle="arc3,rad=0.0",
    ))


def _save(fig, name: str) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=WHITE, edgecolor="none")
    plt.close(fig)
    print(f"  {path.name}")
    return path


def diagram_system_architecture():
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("LegalEase.AI — High-Level System Architecture", fontsize=14, weight="bold", color=NAVY, pad=16)

    _box(ax, 0.3, 7.2, 2.4, 0.9, "Next.js 15\nWeb App", TEAL, fontsize=9, bold=True)
    _box(ax, 3.0, 7.2, 2.4, 0.9, "Streamlit\n(Legacy Demo)", GRAY, fontsize=8)
    _box(ax, 5.7, 7.5, 2.6, 0.6, "nginx TLS\nReverse Proxy", NAVY, fontsize=8)

    _box(ax, 1.5, 5.5, 3.2, 1.0, "FastAPI 3.0\n/api/v1/*", NAVY, fontsize=10, bold=True)
    _box(ax, 5.2, 5.5, 2.0, 1.0, "E-Discovery\nWorker", ORANGE, fontsize=8)
    _box(ax, 7.5, 5.5, 2.0, 1.0, "ML Worker\n(Neural Train)", PURPLE, fontsize=8)

    _box(ax, 0.3, 3.2, 2.2, 0.9, "PostgreSQL 16\nMulti-tenant", BLUE, fontsize=8)
    _box(ax, 2.8, 3.2, 1.8, 0.9, "Redis 7\nQueues", BLUE, fontsize=8)
    _box(ax, 4.9, 3.2, 2.2, 0.9, "FAISS Indexes\nPer User/Matter", BLUE, fontsize=8)
    _box(ax, 7.4, 3.2, 2.0, 0.9, "File Storage\nData/", BLUE, fontsize=8)

    _box(ax, 0.5, 1.0, 2.4, 0.9, "Ollama\nlegalease-tuned", GREEN, fontsize=8, bold=True)
    _box(ax, 3.2, 1.0, 2.4, 0.9, "Gemini 2.5\nWeb Intel", ACCENT, fontsize=8, bold=True)
    _box(ax, 5.9, 1.0, 2.4, 0.9, "SentenceTransformers\nEmbeddings", GREEN, fontsize=8)
    _box(ax, 8.6, 1.0, 2.2, 0.9, "faster-whisper\nSpeech-to-Text", GREEN, fontsize=8)

    _box(ax, 10.5, 5.5, 2.8, 1.0, "Stripe\nSubscriptions", ORANGE, fontsize=8)

    _arrow(ax, 1.5, 7.2, 2.5, 6.5)
    _arrow(ax, 4.2, 7.2, 3.0, 6.5)
    _arrow(ax, 6.5, 7.5, 3.1, 6.5)
    _arrow(ax, 3.1, 5.5, 1.4, 4.1)
    _arrow(ax, 3.1, 5.5, 3.7, 4.1)
    _arrow(ax, 3.1, 5.5, 6.0, 4.1)
    _arrow(ax, 3.1, 5.5, 8.4, 4.1)
    _arrow(ax, 3.1, 5.0, 1.7, 1.9)
    _arrow(ax, 3.1, 5.0, 4.4, 1.9)
    _arrow(ax, 3.1, 5.0, 7.1, 1.9)
    _arrow(ax, 6.2, 5.5, 6.2, 4.1)
    _arrow(ax, 8.5, 5.5, 11.9, 5.5)
    _arrow(ax, 6.2, 5.0, 9.7, 1.9)

    legend = [
        mpatches.Patch(color=TEAL, label="Client Layer"),
        mpatches.Patch(color=NAVY, label="Application Layer"),
        mpatches.Patch(color=BLUE, label="Data Layer"),
        mpatches.Patch(color=GREEN, label="AI / ML Layer"),
    ]
    ax.legend(handles=legend, loc="lower right", fontsize=8, framealpha=0.9)
    return _save(fig, "system_architecture.png")


def diagram_request_flow():
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Request Flow: User Query to AI Response", fontsize=14, weight="bold", color=NAVY, pad=14)

    steps = [
        (0.3, 3.5, "User\nBrowser"),
        (2.0, 3.5, "Next.js\n/api proxy"),
        (3.7, 3.5, "FastAPI\nJWT Auth"),
        (5.4, 3.5, "Mode\nRouter"),
        (7.1, 4.8, "KB Pipeline\nFAISS+Ollama"),
        (7.1, 3.5, "Open Law\nGemini Web"),
        (7.1, 2.2, "Hybrid\nFusion"),
        (9.0, 3.5, "Response\nFormatter"),
        (10.7, 3.5, "SSE/JSON\nResponse"),
    ]
    colors = [TEAL, TEAL, NAVY, NAVY, GREEN, ACCENT, PURPLE, NAVY, TEAL]
    for (x, y, t), c in zip(steps, colors):
        _box(ax, x, y, 1.4, 1.0, t, c, fontsize=7)

    for i in range(len(steps) - 2):
        if i < 3:
            _arrow(ax, steps[i][0] + 1.4, steps[i][1] + 0.5, steps[i + 1][0], steps[i + 1][1] + 0.5)
    _arrow(ax, 6.8, 4.0, 7.1, 5.0)
    _arrow(ax, 6.8, 3.5, 7.1, 3.8)
    _arrow(ax, 6.8, 3.0, 7.1, 2.6)
    _arrow(ax, 8.5, 5.3, 9.0, 4.0)
    _arrow(ax, 8.5, 4.0, 9.0, 3.8)
    _arrow(ax, 8.5, 2.7, 9.0, 3.2)
    _arrow(ax, 10.4, 4.0, 10.7, 4.0)

    ax.text(7.1, 6.2, "Parallel in Hybrid mode", ha="center", fontsize=9, color=GRAY, style="italic")
    return _save(fig, "request_flow.png")


def diagram_rag_pipeline():
    fig, ax = plt.subplots(figsize=(12, 10))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("RAG Pipeline: Document Upload to Grounded Answer", fontsize=14, weight="bold", color=NAVY, pad=14)

    flow = [
        (4.5, 9.0, "PDF/Image Upload\nPOST /documents/upload"),
        (4.5, 7.8, "OCR (EasyOCR)\n+ Text Extract"),
        (4.5, 6.6, "Chunking\n500 tokens, 100 overlap"),
        (4.5, 5.4, "Embedding\nBGE / MiniLM"),
        (4.5, 4.2, "FAISS Index\nGlobal + Matter"),
        (4.5, 3.0, "Query Expansion\n+ Dense Retrieval"),
        (4.5, 1.8, "Rerank + MMR\nThreshold Gate"),
        (4.5, 0.6, "Ollama Synthesis\nCited Answer / NOT_FOUND"),
    ]
    for x, y, t in flow:
        _box(ax, x, y, 3.0, 0.9, t, BLUE if y > 4 else GREEN, fontsize=8)

    for i in range(len(flow) - 1):
        _arrow(ax, 6.0, flow[i][1], 6.0, flow[i + 1][1] + 0.9)

    side = [
        (0.5, 5.4, "faiss_indexes/\nPer-user paths"),
        (8.5, 5.4, "RAG_CONFIDENCE\nthreshold 0.52"),
        (0.5, 1.8, "Cross-encoder\n(optional rerank)"),
        (8.5, 1.8, "kb_rag_decision\nFOUND / NOT_FOUND"),
    ]
    for x, y, t in side:
        _box(ax, x, y, 2.8, 0.8, t, LIGHT, GRAY, fontsize=7)
    return _save(fig, "rag_pipeline.png")


def diagram_chat_mode_decision():
    fig, ax = plt.subplots(figsize=(12, 9))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("Chat Mode Decision Tree", fontsize=14, weight="bold", color=NAVY, pad=14)

    _box(ax, 4.5, 7.8, 3.0, 0.8, "User Selects Mode\n(ModePills UI)", NAVY, fontsize=9, bold=True)
    _box(ax, 1.0, 5.8, 2.5, 0.8, "knowledge_base\n(KB Mode)", GREEN, fontsize=8)
    _box(ax, 4.75, 5.8, 2.5, 0.8, "open_law / web_search", ACCENT, fontsize=8)
    _box(ax, 8.5, 5.8, 2.5, 0.8, "hybrid / deep_case", PURPLE, fontsize=8)

    _box(ax, 0.5, 3.8, 3.0, 1.0, "FAISS retrieve\nOllama synthesize\nGEMINI blocked", GREEN, fontsize=7)
    _box(ax, 4.5, 3.8, 3.0, 1.0, "Gemini grounded\nsearch + fallbacks\nTavily/Serp/DDG", ACCENT, fontsize=7)
    _box(ax, 8.5, 3.8, 3.0, 1.0, "KB + Web parallel\nGemini fusion report\nPro+ only", PURPLE, fontsize=7)

    _box(ax, 4.5, 1.5, 3.0, 0.8, "Plan Gate: Free tier\n→ downgrade hybrid", ORANGE, fontsize=8)

    _arrow(ax, 5.2, 7.8, 2.25, 6.6)
    _arrow(ax, 6.0, 7.8, 6.0, 6.6)
    _arrow(ax, 6.8, 7.8, 9.75, 6.6)
    _arrow(ax, 2.0, 5.8, 2.0, 4.8)
    _arrow(ax, 6.0, 5.8, 6.0, 4.8)
    _arrow(ax, 9.75, 5.8, 10.0, 4.8)
    _arrow(ax, 9.75, 5.8, 6.0, 2.3)
    return _save(fig, "chat_mode_decision.png")


def diagram_auth_flow():
    fig, ax = plt.subplots(figsize=(11, 8))
    ax.set_xlim(0, 11)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("Authentication & Authorization Flow", fontsize=14, weight="bold", color=NAVY, pad=14)

    steps = [
        (0.5, 6.5, "POST /auth/login\nusername + password"),
        (3.0, 6.5, "bcrypt verify\nlegalease_auth"),
        (5.5, 6.5, "HMAC JWT\nbase64(payload).sig"),
        (8.0, 6.5, "Store token\nlocalStorage"),
        (0.5, 4.5, "API Request\nAuthorization: Bearer"),
        (3.0, 4.5, "get_current_user\ndecode + suspend check"),
        (5.5, 4.5, "Refresh membership\nfrom DB"),
        (8.0, 4.5, "Attach org_id\nprimary org"),
        (3.0, 2.5, "RBAC + Plan Gate\nPro features"),
        (5.5, 2.5, "Tenant scope\nuser_id + org_id"),
        (8.0, 2.5, "Endpoint handler\nscoped query"),
    ]
    for i, (x, y, t) in enumerate(steps):
        c = TEAL if i < 4 else NAVY
        _box(ax, x, y, 2.2, 0.9, t, c, fontsize=7)

    for i in [0, 1, 2, 4, 5, 6, 7, 8, 9]:
        if i < 3:
            _arrow(ax, steps[i][0] + 2.2, steps[i][1] + 0.45, steps[i + 1][0], steps[i + 1][1] + 0.45)
        elif i == 4:
            _arrow(ax, steps[3][0] + 1.1, steps[3][1], steps[4][0] + 1.1, steps[4][1] + 0.9)
        elif i < 7:
            _arrow(ax, steps[i][0] + 2.2, steps[i][1] + 0.45, steps[i + 1][0], steps[i + 1][1] + 0.45)
        elif i == 7:
            _arrow(ax, steps[7][0] + 1.1, steps[7][1], steps[8][0] + 1.1, steps[8][1] + 0.9)
        elif i == 8:
            _arrow(ax, steps[8][0] + 2.2, steps[8][1] + 0.45, steps[9][0], steps[9][1] + 0.45)
            _arrow(ax, steps[9][0] + 2.2, steps[9][1] + 0.45, steps[10][0], steps[10][1] + 0.45)
    return _save(fig, "auth_flow.png")


def diagram_multi_tenant():
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("Multi-Tenant Data Isolation", fontsize=14, weight="bold", color=NAVY, pad=14)

    _box(ax, 4.5, 6.8, 3.0, 0.8, "Organization\n(org_id)", NAVY, fontsize=9, bold=True)
    _box(ax, 0.5, 4.8, 2.5, 0.8, "Owner", TEAL, fontsize=8)
    _box(ax, 3.5, 4.8, 2.5, 0.8, "Lawyer", TEAL, fontsize=8)
    _box(ax, 6.5, 4.8, 2.5, 0.8, "Member", TEAL, fontsize=8)
    _box(ax, 9.5, 4.8, 2.0, 0.8, "Viewer", TEAL, fontsize=8)

    _box(ax, 0.5, 2.5, 3.5, 1.2, "Matters\nuser_id OR org_id IN (...)", BLUE, fontsize=8)
    _box(ax, 4.5, 2.5, 3.5, 1.2, "CRM Leads\norg_id filter", BLUE, fontsize=8)
    _box(ax, 8.5, 2.5, 3.0, 1.2, "Documents\norg_id column", BLUE, fontsize=8)

    _box(ax, 2.0, 0.5, 4.0, 1.0, "FAISS: faiss_indexes/{user_id}/\nPer-user vector isolation", GREEN, fontsize=8)
    _box(ax, 6.5, 0.5, 4.5, 1.0, "Plan enforcement:\nPLAN_DOC_LIMIT_* per tier", ORANGE, fontsize=8)

    for x in [1.75, 4.75, 7.75, 10.5]:
        _arrow(ax, 6.0, 6.8, x, 5.6)
    for x, w in [(0.5, 3.5), (4.5, 3.5), (8.5, 3.0)]:
        _arrow(ax, x + w / 2, 4.8, x + w / 2, 3.7)
    return _save(fig, "multi_tenant_isolation.png")


def diagram_document_ingestion():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Document Ingestion Pipeline", fontsize=14, weight="bold", color=NAVY, pad=14)

    steps = [
        (0.3, 3.0, "Upload\nWeb/Matter"),
        (2.0, 3.0, "Validate\nMAX_UPLOAD_MB"),
        (3.7, 3.0, "Save Data/\nHash dedup"),
        (5.4, 3.0, "OCR if image\nPDF extract"),
        (7.1, 3.0, "Queue Job\nembedding_queue"),
        (8.8, 3.0, "Chunk + Embed\nBatch index"),
        (10.5, 3.0, "FAISS Update\nindex_status=OK"),
    ]
    for x, y, t in steps:
        _box(ax, x, y, 1.4, 1.2, t, BLUE, fontsize=7)
    for i in range(len(steps) - 1):
        _arrow(ax, steps[i][0] + 1.4, 3.6, steps[i + 1][0], 3.6)
    _box(ax, 3.0, 1.0, 6.0, 0.8, "Optional: Matter-scoped index faiss_indexes/{user}/{matter_id}/", LIGHT, GRAY, fontsize=8)
    _arrow(ax, 6.0, 3.0, 6.0, 1.8)
    return _save(fig, "document_ingestion.png")


def diagram_database_er():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("Conceptual Database ER Diagram (PostgreSQL)", fontsize=14, weight="bold", color=NAVY, pad=14)

    tables = [
        (0.5, 8.0, "users\nid, username, membership, role"),
        (3.5, 8.0, "organizations\norg_id, plan, seats"),
        (6.5, 8.0, "org_members\norg_id, user_id, role"),
        (9.5, 8.0, "subscriptions\nstripe_*, plan"),
        (0.5, 6.0, "matters\nmatter_id, org_id, user_id"),
        (3.5, 6.0, "documents\nid, uploader, matter_id"),
        (6.5, 6.0, "chat_history\nuser, mode, thread"),
        (9.5, 6.0, "crm_leads\norg_id, stage, score"),
        (0.5, 4.0, "financial_records\ntime entries"),
        (3.5, 4.0, "invoices\nmatter, amount"),
        (6.5, 4.0, "ediscovery_batches\nitems, jobs"),
        (9.5, 4.0, "trust_accounts\nledger"),
        (0.5, 2.0, "collab_rooms\nmessages"),
        (3.5, 2.0, "matter_timeline\nevents"),
        (6.5, 2.0, "audit_events\nadmin log"),
        (9.5, 2.0, "ml_jobs\nqueue status"),
    ]
    for x, y, t in tables:
        _box(ax, x, y, 2.8, 1.2, t, BLUE, fontsize=7)

    # Key relationships (simplified lines)
    rels = [
        ((3.3, 8.6), (3.5, 8.6)), ((6.3, 8.6), (6.5, 8.6)),
        ((1.9, 8.0), (1.9, 7.2)), ((4.9, 7.2), (4.9, 6.0)),
        ((2.0, 6.6), (3.5, 6.6)), ((5.0, 6.6), (6.5, 6.6)),
    ]
    for (x1, y1), (x2, y2) in rels:
        ax.plot([x1, x2], [y1, y2], color=NAVY, linewidth=1, zorder=1)
    return _save(fig, "database_er.png")


def diagram_docker_deployment():
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("Docker Compose Deployment Topology", fontsize=14, weight="bold", color=NAVY, pad=14)

    _box(ax, 5.0, 6.5, 3.0, 0.9, "nginx :80\nPublic Entry", NAVY, fontsize=9, bold=True)
    _box(ax, 2.0, 4.5, 2.5, 0.9, "web :3000\nNext.js", TEAL, fontsize=8)
    _box(ax, 5.5, 4.5, 2.5, 0.9, "api :8000\nFastAPI", NAVY, fontsize=8)
    _box(ax, 0.5, 2.0, 2.5, 0.9, "postgres :5432", BLUE, fontsize=8)
    _box(ax, 3.5, 2.0, 2.5, 0.9, "redis :6379", BLUE, fontsize=8)
    _box(ax, 6.5, 2.0, 2.5, 0.9, "worker\nediscovery", ORANGE, fontsize=8)
    _box(ax, 9.5, 2.0, 2.5, 0.9, "ml-worker", PURPLE, fontsize=8)

    _box(ax, 9.0, 4.5, 3.5, 0.9, "Volumes: postgres_data,\nredis_data, app_data,\nfaiss_indexes, Data/", LIGHT, GRAY, fontsize=7)

    _arrow(ax, 6.5, 6.5, 3.25, 5.4)
    _arrow(ax, 6.5, 6.5, 6.75, 5.4)
    _arrow(ax, 6.75, 4.5, 1.75, 2.9)
    _arrow(ax, 6.75, 4.5, 4.75, 2.9)
    _arrow(ax, 6.75, 4.5, 7.75, 2.9)
    _arrow(ax, 6.75, 4.5, 10.75, 2.9)
    return _save(fig, "docker_deployment.png")


def diagram_billing_flow():
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("Billing & Subscription Flow", fontsize=14, weight="bold", color=NAVY, pad=14)

    _box(ax, 0.5, 6.0, 2.5, 0.9, "User clicks\nUpgrade Pro", TEAL, fontsize=8)
    _box(ax, 3.5, 6.0, 2.5, 0.9, "POST /billing/subscribe\nStripe Checkout", ORANGE, fontsize=8)
    _box(ax, 6.5, 6.0, 2.5, 0.9, "Stripe Payment\nSession", ORANGE, fontsize=8)
    _box(ax, 9.5, 6.0, 2.0, 0.9, "Webhook\n/api/billing/stripe", ORANGE, fontsize=8)

    _box(ax, 3.5, 4.0, 2.5, 0.9, "upgrade_user_\nmembership()", NAVY, fontsize=8)
    _box(ax, 6.5, 4.0, 2.5, 0.9, "sync_org_plan\nsubscriptions row", NAVY, fontsize=8)
    _box(ax, 9.5, 4.0, 2.0, 0.9, "Plan gates\nHybrid, doc limits", GREEN, fontsize=8)

    _box(ax, 0.5, 1.5, 3.5, 1.0, "Internal Billing\nTime entries + Invoices\n(financial_records)", BLUE, fontsize=8)
    _box(ax, 4.5, 1.5, 3.5, 1.0, "Trust Accounts\nIOLTA ledger", BLUE, fontsize=8)
    _box(ax, 8.5, 1.5, 3.0, 1.0, "Dev: ALLOW_MOCK_BILLING\nDirect plan upgrade", GRAY, fontsize=7)

    for pairs in [(1.75, 6.45, 3.5, 6.45), (6.0, 6.45, 6.5, 6.45), (9.0, 6.45, 9.5, 6.45),
                  (10.5, 6.0, 10.5, 4.9), (4.75, 4.0, 6.5, 4.45), (7.75, 4.0, 9.5, 4.45)]:
        _arrow(ax, *pairs)
    return _save(fig, "billing_flow.png")


def diagram_crm_workflow():
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("CRM 2.0 Intake Pipeline Workflow", fontsize=14, weight="bold", color=NAVY, pad=14)

    stages = [
        "NEW_INTAKE", "CONTACTED", "CONSULTATION", "ENGAGED",
        "PROPOSAL", "RETAINED", "CLOSED_WON", "CLOSED_LOST",
    ]
    w = 1.4
    for i, s in enumerate(stages):
        x = 0.3 + i * 1.55
        color = GREEN if s == "RETAINED" else (GRAY if "CLOSED" in s else TEAL)
        _box(ax, x, 3.5, w, 0.9, s.replace("_", "\n"), color, fontsize=6)
        if i < len(stages) - 1:
            _arrow(ax, x + w, 3.95, x + 1.55, 3.95)

    _box(ax, 0.5, 1.5, 3.0, 1.0, "Public Intake Form\nINTAKE_PUBLIC_KEY", LIGHT, GRAY, fontsize=7)
    _box(ax, 4.0, 1.5, 3.0, 1.0, "AI Lead Analysis\nScore + evidence", ACCENT, fontsize=7)
    _box(ax, 7.5, 1.5, 3.0, 1.0, "Convert to Matter\nTasks + deadlines", GREEN, fontsize=7)
    _box(ax, 11.0, 1.5, 1.8, 1.0, "Kanban\nBoard UI", TEAL, fontsize=7)

    _arrow(ax, 2.0, 2.5, 2.0, 3.5)
    _arrow(ax, 5.5, 2.5, 5.5, 3.5)
    _arrow(ax, 9.0, 2.5, 9.0, 3.5)
    return _save(fig, "crm_workflow.png")


def diagram_ediscovery_pipeline():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("E-Discovery Processing Pipeline", fontsize=14, weight="bold", color=NAVY, pad=14)

    _box(ax, 0.5, 4.5, 2.2, 1.0, "Upload Docs\nor paste text", TEAL, fontsize=8)
    _box(ax, 3.2, 4.5, 2.2, 1.0, "Triage API\nRule + keyword", NAVY, fontsize=8)
    _box(ax, 5.9, 4.5, 2.2, 1.0, "Create Batch\n>=5 docs → async", NAVY, fontsize=8)
    _box(ax, 8.6, 4.5, 2.5, 1.0, "Redis Queue\nediscovery_worker", ORANGE, fontsize=8)

    _box(ax, 1.5, 2.0, 2.5, 1.0, "Relevance Score\nTag weights", BLUE, fontsize=8)
    _box(ax, 4.5, 2.0, 2.5, 1.0, "Privilege Detect\nReview UI", BLUE, fontsize=8)
    _box(ax, 7.5, 2.0, 3.0, 1.0, "Feedback Loop\nPremiumFeedback", GREEN, fontsize=8)

    _arrow(ax, 2.7, 5.0, 3.2, 5.0)
    _arrow(ax, 5.4, 5.0, 5.9, 5.0)
    _arrow(ax, 8.1, 5.0, 8.6, 5.0)
    _arrow(ax, 9.85, 4.5, 2.75, 3.0)
    _arrow(ax, 9.85, 4.5, 5.75, 3.0)
    _arrow(ax, 9.85, 4.5, 9.0, 3.0)
    return _save(fig, "ediscovery_pipeline.png")


def diagram_database_er_detailed():
    fig, ax = plt.subplots(figsize=(16, 11))
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 11)
    ax.axis("off")
    ax.set_title("Database ER Diagram — Core + Practice + Collab", fontsize=14, weight="bold", color=NAVY, pad=14)

    core = [
        (0.3, 9.2, "users\nPK id, membership, role"),
        (3.3, 9.2, "organizations\nPK org_id, plan"),
        (6.3, 9.2, "org_members\nFK org_id, user_id"),
        (9.3, 9.2, "subscriptions\nstripe_*"),
        (12.3, 9.2, "audit_events\naction, ip"),
    ]
    practice = [
        (0.3, 7.0, "matters\nFK user_id, org_id"),
        (3.3, 7.0, "documents\nFK matter_id"),
        (6.3, 7.0, "matter_timeline\nevents"),
        (9.3, 7.0, "matter_entities\nparties"),
        (12.3, 7.0, "matter_contradictions\npairs"),
    ]
    crm = [
        (0.3, 4.8, "crm_leads\nstage, score"),
        (3.3, 4.8, "financial_records\ntime entries"),
        (6.3, 4.8, "invoices\namount"),
        (9.3, 4.8, "trust_accounts\nledger"),
        (12.3, 4.8, "ediscovery_batches\njobs"),
    ]
    collab = [
        (0.3, 2.6, "collab_rooms\nmatter_id?"),
        (3.3, 2.6, "collab_messages\nFK room"),
        (6.3, 2.6, "chat_history\nmode, thread"),
        (9.3, 2.6, "ml_jobs\nqueue"),
        (12.3, 2.6, "user_profiles\npersona"),
    ]
    for x, y, t in core + practice + crm + collab:
        _box(ax, x, y, 2.7, 1.0, t, BLUE, fontsize=6)
    ax.text(8, 0.8, "PostgreSQL (core) + SQLite/Postgres practice DB | FK lines simplified", ha="center", fontsize=8, color=GRAY)
    return _save(fig, "database_er_detailed.png")


def diagram_ai_flow():
    fig, ax = plt.subplots(figsize=(13, 8))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("AI Inference Flow — Ollama vs Gemini", fontsize=14, weight="bold", color=NAVY, pad=14)
    _box(ax, 0.5, 5.5, 2.5, 1.0, "User Query", TEAL, fontsize=8)
    _box(ax, 3.5, 6.2, 2.5, 0.8, "KB Path", GREEN, fontsize=8, bold=True)
    _box(ax, 3.5, 4.8, 2.5, 0.8, "Open Law", ACCENT, fontsize=8, bold=True)
    _box(ax, 3.5, 3.4, 2.5, 0.8, "Hybrid", PURPLE, fontsize=8, bold=True)
    _box(ax, 6.8, 6.2, 2.2, 0.9, "FAISS\nRetrieve", GREEN, fontsize=7)
    _box(ax, 9.5, 6.2, 2.5, 0.9, "Ollama\nSynthesize", GREEN, fontsize=8, bold=True)
    _box(ax, 6.8, 4.8, 2.2, 0.9, "Gemini\nGrounded", ACCENT, fontsize=7)
    _box(ax, 9.5, 4.8, 2.5, 0.9, "Fallback\nTavily/Serp", ACCENT, fontsize=7)
    _box(ax, 6.8, 3.4, 2.2, 0.9, "Parallel\nKB+Web", PURPLE, fontsize=7)
    _box(ax, 9.5, 3.4, 2.5, 0.9, "Gemini\nFusion", PURPLE, fontsize=7)
    _arrow(ax, 3.0, 6.0, 3.5, 6.5)
    _arrow(ax, 3.0, 6.0, 3.5, 5.2)
    _arrow(ax, 3.0, 6.0, 3.5, 3.8)
    _arrow(ax, 6.0, 6.65, 6.8, 6.65)
    _arrow(ax, 9.0, 6.65, 9.5, 6.65)
    _arrow(ax, 6.0, 5.2, 6.8, 5.2)
    _arrow(ax, 9.0, 5.2, 9.5, 5.2)
    return _save(fig, "ai_flow.png")


def diagram_rag_architecture_detailed():
    fig, ax = plt.subplots(figsize=(14, 10))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("RAG Architecture — Retrieval to Grounded Answer", fontsize=14, weight="bold", color=NAVY, pad=14)
    cols = [
        (0.5, ["Query", "Legal Parser", "Expansion"]),
        (3.5, ["Dense k=16", "Keyword k=24", "MMR λ=0.7"]),
        (6.5, ["Rerank pool", "Score gate", "Confidence"]),
        (9.5, ["Ollama ctx", "Cite/refuse", "NOT_FOUND"]),
    ]
    y0 = 8.0
    for x, labels in cols:
        for i, lab in enumerate(labels):
            _box(ax, x, y0 - i * 1.3, 2.6, 0.9, lab, BLUE if i < 2 else GREEN, fontsize=7)
        if x < 9.5:
            _arrow(ax, x + 2.6, y0 - 0.5, x + 3.5, y0 - 0.5)
    _box(ax, 4.5, 0.8, 5.0, 0.8, "kb_rag_decision: FOUND | NOT_FOUND | LOW_CONFIDENCE", ORANGE, fontsize=7)
    return _save(fig, "rag_architecture_detailed.png")


def diagram_matter_workflow():
    fig, ax = plt.subplots(figsize=(13, 6))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 6)
    ax.axis("off")
    ax.set_title("Matter Lifecycle Workflow", fontsize=14, weight="bold", color=NAVY, pad=14)
    steps = ["Create Matter", "Upload Docs", "Index FAISS", "Intel Pipeline", "Timeline", "Hearing Prep", "Billing"]
    for i, s in enumerate(steps):
        x = 0.3 + i * 1.75
        _box(ax, x, 3.2, 1.55, 0.9, s.replace(" ", "\n"), TEAL if i < 3 else GREEN, fontsize=6)
        if i < len(steps) - 1:
            _arrow(ax, x + 1.55, 3.65, x + 1.75, 3.65)
    _box(ax, 2.0, 1.2, 9.0, 0.9, "Matter AI chat + contradictions + export ZIP", NAVY, fontsize=8)
    _arrow(ax, 6.5, 3.2, 6.5, 2.1)
    return _save(fig, "matter_workflow.png")


def diagram_collaboration_workflow():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Firm Collaboration Workflow", fontsize=14, weight="bold", color=NAVY, pad=14)
    _box(ax, 0.5, 4.5, 2.2, 1.0, "User Search\n@username", TEAL, fontsize=7)
    _box(ax, 3.0, 4.5, 2.2, 1.0, "DM Request\nor Room", TEAL, fontsize=7)
    _box(ax, 5.5, 4.5, 2.2, 1.0, "Post Message\n+ Attach", NAVY, fontsize=7)
    _box(ax, 8.0, 4.5, 2.5, 1.0, "Notify Members\n(poll)", NAVY, fontsize=7)
    _box(ax, 2.0, 2.0, 3.0, 1.0, "Matter Discussion\nlinked room", GREEN, fontsize=7)
    _box(ax, 5.5, 2.0, 3.0, 1.0, "Task/Deadline\nfrom message", GREEN, fontsize=7)
    _box(ax, 9.0, 2.0, 2.5, 1.0, "Planned:\nWebSocket", GRAY, fontsize=7)
    for pairs in [(2.7, 5.0, 3.0, 5.0), (5.2, 5.0, 5.5, 5.0), (7.7, 5.0, 8.0, 5.0)]:
        _arrow(ax, *pairs)
    return _save(fig, "collaboration_workflow.png")


def diagram_auth_flow_enhanced():
    fig, ax = plt.subplots(figsize=(13, 9))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("Authentication Flow — Login, JWT, RBAC, Plan Gate", fontsize=14, weight="bold", color=NAVY, pad=14)
    row1 = [(0.3, 7.0, "Login"), (2.5, 7.0, "bcrypt"), (4.7, 7.0, "JWT issue"), (6.9, 7.0, "localStorage")]
    row2 = [(0.3, 4.8, "API call"), (2.5, 4.8, "Verify sig"), (4.7, 4.8, "Load user"), (6.9, 4.8, "org_id")]
    row3 = [(2.5, 2.6, "RBAC check"), (4.7, 2.6, "Plan gate"), (6.9, 2.6, "Tenant scope"), (9.1, 2.6, "Handler")]
    for row in (row1, row2, row3):
        for x, y, t in row:
            _box(ax, x, y, 1.9, 0.85, t, NAVY, fontsize=7)
    _box(ax, 9.5, 7.0, 2.8, 0.85, "Refresh /me", TEAL, fontsize=7)
    _box(ax, 9.5, 4.8, 2.8, 0.85, "Rate limit", ORANGE, fontsize=7)
    return _save(fig, "auth_flow_enhanced.png")


def diagram_deployment_enhanced():
    fig, ax = plt.subplots(figsize=(14, 9))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.set_title("Deployment — Production + DR", fontsize=14, weight="bold", color=NAVY, pad=14)
    _box(ax, 5.5, 7.5, 3.0, 0.8, "Cloudflare / DNS", GRAY, fontsize=8)
    _box(ax, 5.5, 6.0, 3.0, 0.9, "nginx TLS :443", NAVY, fontsize=9, bold=True)
    _box(ax, 1.0, 4.0, 2.5, 0.9, "web x N", TEAL, fontsize=8)
    _box(ax, 4.0, 4.0, 2.5, 0.9, "api x N", NAVY, fontsize=8)
    _box(ax, 7.0, 4.0, 2.5, 0.9, "workers", ORANGE, fontsize=8)
    _box(ax, 10.0, 4.0, 2.5, 0.9, "Ollama host", GREEN, fontsize=8)
    _box(ax, 2.0, 1.5, 3.0, 0.9, "Postgres primary\n+ backup", BLUE, fontsize=8)
    _box(ax, 5.5, 1.5, 3.0, 0.9, "Redis AOF", BLUE, fontsize=8)
    _box(ax, 9.0, 1.5, 3.5, 0.9, "Volumes: Data,\nfaiss_indexes", BLUE, fontsize=8)
    _arrow(ax, 7.0, 7.5, 7.0, 6.9)
    _arrow(ax, 7.0, 6.0, 2.25, 4.9)
    _arrow(ax, 7.0, 6.0, 5.25, 4.9)
    return _save(fig, "deployment_enhanced.png")


def diagram_learning_pipeline():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("Learning Pipeline — Feedback to Tuned Model", fontsize=14, weight="bold", color=NAVY, pad=14)
    flow = ["Thumbs", "learning_signals", "Coach (Gemini)", "ML Queue", "Neural Train", "Re-index", "legalease-tuned"]
    for i, s in enumerate(flow):
        x = 0.3 + i * 1.6
        c = ACCENT if "Coach" in s or "Gemini" in s else GREEN
        _box(ax, x, 3.5, 1.4, 1.0, s.replace(" ", "\n"), c, fontsize=6)
        if i < len(flow) - 1:
            _arrow(ax, x + 1.4, 4.0, x + 1.6, 4.0)
    _box(ax, 2.0, 1.5, 8.0, 0.8, "KB_BLOCK_LEARNING_INJECT=1 — no training text in live KB answers", ORANGE, fontsize=7)
    return _save(fig, "learning_pipeline.png")


def diagram_ai_governance_trust():
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("AI Governance & Trust Layer", fontsize=14, weight="bold", color=NAVY, pad=14)
    _box(ax, 4.5, 6.5, 3.0, 0.8, "User Query", TEAL, fontsize=9)
    _box(ax, 0.5, 4.5, 2.5, 1.0, "Tenant\nIsolation", BLUE, fontsize=7)
    _box(ax, 3.5, 4.5, 2.5, 1.0, "Retrieval\nGate", GREEN, fontsize=7)
    _box(ax, 6.5, 4.5, 2.5, 1.0, "Gemini\nBlock KB", ORANGE, fontsize=7)
    _box(ax, 9.5, 4.5, 2.0, 1.0, "Citation\nValidate", GREEN, fontsize=7)
    _box(ax, 4.0, 2.0, 4.0, 1.0, "Ollama Answer or NOT_FOUND", NAVY, fontsize=8, bold=True)
    for x in [1.75, 4.75, 7.75, 10.5]:
        _arrow(ax, 6.0, 6.5, x, 5.5)
    for x in [2.5, 5.5, 8.5]:
        _arrow(ax, x, 4.5, 6.0, 3.0)
    return _save(fig, "ai_governance_trust.png")


def diagram_matter_intelligence_pipeline():
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 8)
    ax.axis("off")
    ax.set_title("Matter Intelligence Pipeline", fontsize=14, weight="bold", color=NAVY, pad=14)
    stages = ["Entities", "Evidence", "Timeline", "Hearings", "Contradictions", "Ready"]
    for i, s in enumerate(stages):
        x = 0.4 + i * 1.9
        _box(ax, x, 4.5, 1.7, 0.9, s, GREEN if s == "Ready" else BLUE, fontsize=7)
        if i < len(stages) - 1:
            _arrow(ax, x + 1.7, 4.95, x + 1.9, 4.95)
    _box(ax, 2.0, 2.0, 8.0, 0.9, "matter_intel_pipeline.py — status polling on matter AI tab", NAVY, fontsize=8)
    return _save(fig, "matter_intelligence_pipeline.png")


def diagram_kb_accuracy_pipeline():
    fig, ax = plt.subplots(figsize=(12, 7))
    ax.set_xlim(0, 12)
    ax.set_ylim(0, 7)
    ax.axis("off")
    ax.set_title("KB Accuracy Pipeline", fontsize=14, weight="bold", color=NAVY, pad=14)
    _box(ax, 0.5, 3.5, 2.0, 1.0, "Exact\nMatch", TEAL, fontsize=7)
    _box(ax, 2.8, 3.5, 2.0, 1.0, "Chunk\nValidate", BLUE, fontsize=7)
    _box(ax, 5.1, 3.5, 2.0, 1.0, "Confidence\n>=0.52", GREEN, fontsize=7)
    _box(ax, 7.4, 3.5, 2.0, 1.0, "Synthesize\nOllama", GREEN, fontsize=7)
    _box(ax, 9.7, 3.5, 2.0, 1.0, "Claim\nAudit", GREEN, fontsize=7)
    for i in range(4):
        _arrow(ax, 2.5 + i * 2.3, 4.0, 2.8 + i * 2.3, 4.0)
    _box(ax, 3.5, 1.5, 5.0, 0.8, "Fail path → NOT_FOUND (no hallucination)", ORANGE, fontsize=8)
    return _save(fig, "kb_accuracy_pipeline.png")


def diagram_chat_routing_tree():
    fig, ax = plt.subplots(figsize=(13, 10))
    ax.set_xlim(0, 13)
    ax.set_ylim(0, 10)
    ax.axis("off")
    ax.set_title("Chat Routing — All Modes", fontsize=14, weight="bold", color=NAVY, pad=14)
    _box(ax, 4.5, 8.5, 4.0, 0.8, "POST /api/v1/chat", NAVY, fontsize=9, bold=True)
    modes = [
        (0.3, 6.0, "knowledge_base"),
        (2.8, 6.0, "open_law"),
        (5.3, 6.0, "hybrid"),
        (7.8, 6.0, "matter AI"),
        (10.3, 6.0, "drafting"),
    ]
    for x, y, m in modes:
        _box(ax, x, y, 2.2, 0.8, m, GREEN if "kb" in m else ACCENT, fontsize=6)
        _arrow(ax, 6.5, 8.5, x + 1.1, 6.8)
    _box(ax, 0.3, 3.5, 2.5, 1.0, "rag_query\nOllama", GREEN, fontsize=7)
    _box(ax, 3.0, 3.5, 2.5, 1.0, "Gemini web\nfallbacks", ACCENT, fontsize=7)
    _box(ax, 5.7, 3.5, 2.5, 1.0, "Fusion\nPro+", PURPLE, fontsize=7)
    _box(ax, 8.4, 3.5, 2.5, 1.0, "matter_qa\nscope", GREEN, fontsize=7)
    _box(ax, 10.9, 3.5, 1.8, 1.0, "templates", BLUE, fontsize=7)
    _box(ax, 4.0, 1.2, 5.0, 0.8, "ediscovery + CRM assistant = separate API routes", GRAY, fontsize=7)
    return _save(fig, "chat_routing_tree.png")


def main() -> list[Path]:
    print("Generating thesis diagrams...")
    paths = [
        diagram_system_architecture(),
        diagram_request_flow(),
        diagram_rag_pipeline(),
        diagram_chat_mode_decision(),
        diagram_auth_flow(),
        diagram_multi_tenant(),
        diagram_document_ingestion(),
        diagram_database_er(),
        diagram_docker_deployment(),
        diagram_billing_flow(),
        diagram_crm_workflow(),
        diagram_ediscovery_pipeline(),
        diagram_database_er_detailed(),
        diagram_ai_flow(),
        diagram_rag_architecture_detailed(),
        diagram_matter_workflow(),
        diagram_collaboration_workflow(),
        diagram_auth_flow_enhanced(),
        diagram_deployment_enhanced(),
        diagram_learning_pipeline(),
        diagram_ai_governance_trust(),
        diagram_matter_intelligence_pipeline(),
        diagram_kb_accuracy_pipeline(),
        diagram_chat_routing_tree(),
    ]
    print(f"Done: {len(paths)} diagrams in {OUT}")
    return paths


if __name__ == "__main__":
    main()
