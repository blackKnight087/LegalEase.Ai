#!/usr/bin/env python3
"""
Render LegalEase master system flowchart — dark theme, boxes + arrows.
Output: docs/blueprint/master-system-flowchart-dark.pdf
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT_PDF = ROOT / "docs" / "blueprint" / "master-system-flowchart-dark.pdf"

# --- Dark theme palette ---
BG = "#0b0f14"
TEXT = "#e6edf3"
TEXT_DIM = "#8b949e"
BORDER = "#30363d"
BOX = "#161b22"
BOX_ALT = "#1c2128"
ACCENT_FE = "#388bfd"
ACCENT_BE = "#3fb950"
ACCENT_AI = "#a371f7"
ACCENT_DATA = "#d29922"
ACCENT_LEARN = "#f778ba"
ACCENT_WARN = "#ffa657"
ARROW = "#8b949e"
ARROW_HI = "#58a6ff"


@dataclass
class Node:
    nid: str
    label: str
    x: float
    y: float
    w: float
    h: float
    fc: str = BOX
    ec: str = BORDER
    fs: float = 6.5
    bold: bool = False


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    color: str = ARROW
    style: str = "-"


NODES: list[Node] = []
EDGES: list[Edge] = []


def n(
    nid: str,
    label: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    fc: str = BOX,
    ec: str = BORDER,
    fs: float = 6.5,
    bold: bool = False,
) -> None:
    NODES.append(
        Node(nid, label, x, y, w, h, fc=fc, ec=ec, fs=fs, bold=bold)
    )


def e(src: str, dst: str, label: str = "", color: str = ARROW, style: str = "-") -> None:
    EDGES.append(Edge(src, dst, label, color, style))


def _build_graph() -> None:
    """Define full master flowchart layout (coords 0..100)."""
    NODES.clear()
    EDGES.clear()

    # ---- Tier 0: User ----
    n("user", "USER / LAWYER\n(Browser)", 42, 97, 16, 2.2, fc=BOX_ALT, ec=ACCENT_FE, fs=8, bold=True)

    # ---- Tier 1: Frontend container ----
    n(
        "fe_shell",
        "FRONTEND — Next.js  (web/)\n"
        "Providers: AuthProvider | ApiConnectionProvider | ChatSessionProvider",
        2,
        90.5,
        96,
        5.5,
        fc="#0d1117",
        ec=ACCENT_FE,
        fs=6.5,
    )
    n("fe_chat", "Chat\n/ page.tsx\nuseChat", 4, 88.8, 11, 2.8, fc=BOX, ec=ACCENT_FE)
    n("fe_docs", "Documents\n/documents", 16, 88.8, 11, 2.8, fc=BOX, ec=ACCENT_FE)
    n("fe_mat", "Matters\n/matters/*\nMatterDashboard", 28, 88.8, 13, 2.8, fc=BOX, ec=ACCENT_FE)
    n("fe_set", "Settings\nAnalytics", 42, 88.8, 11, 2.8, fc=BOX, ec=ACCENT_FE)
    n("fe_saas", "SaaS UI\nBilling | CRM\nDiscovery | Premium", 54, 88.8, 14, 2.8, fc=BOX, ec=ACCENT_FE)
    n("fe_api", "API Client\nweb/lib/api.ts\nstreamChat | retry", 69, 88.8, 14, 2.8, fc=BOX, ec=ACCENT_FE)
    n("fe_speech", "Speech UI\nSpeechPanel\nuseSpeechToText", 84, 88.8, 13, 2.8, fc=BOX, ec=ACCENT_FE)

    e("user", "fe_shell")
    for child in ("fe_chat", "fe_docs", "fe_mat", "fe_set", "fe_saas", "fe_api", "fe_speech"):
        e("fe_shell", child, style=":")

    # ---- Tier 2: Transport ----
    n(
        "transport",
        "HTTP/HTTPS\nREST JSON  +  SSE Stream (/api/v1/chat/stream)\nJWT Bearer: legalease_token",
        20,
        84,
        60,
        3.2,
        fc=BOX_ALT,
        ec=ACCENT_FE,
        fs=7,
    )
    e("fe_api", "transport", color=ARROW_HI)
    e("fe_chat", "transport", style=":")
    e("fe_docs", "transport", style=":")

    # ---- Tier 3: API Gateway ----
    n(
        "api_gw",
        "FASTAPI GATEWAY  backend/app/main.py\n"
        "CORS | RateLimitMiddleware | MemoryGuard | Startup thread",
        2,
        78.5,
        96,
        4.2,
        fc="#0d1117",
        ec=ACCENT_BE,
        fs=6.5,
    )
    n("auth", "Auth\nlogin | register | me\nauth_tokens + legalease_auth", 4, 76.5, 18, 3.2, fc=BOX, ec=ACCENT_BE)
    n("health", "Health\nlive | ready | schema\nembeddings | kb", 24, 76.5, 18, 3.2, fc=BOX, ec=ACCENT_BE)
    n("router", "API Router\nbackend/app/api/v1/router.py\n19 endpoint modules", 44, 76.5, 22, 3.2, fc=BOX, ec=ACCENT_BE, bold=True)
    n("legacy", "Legacy aliases\n/api/documents\napi_routes", 68, 76.5, 16, 3.2, fc=BOX, ec=ACCENT_BE)

    e("transport", "api_gw", color=ARROW_HI)
    e("api_gw", "auth", style=":")
    e("api_gw", "health", style=":")
    e("api_gw", "router", color=ARROW_HI)
    e("api_gw", "legacy", style=":")

    # ---- Tier 4: Domain modules (detailed) ----
    # CHAT column
    n(
        "dom_chat",
        "CHAT DOMAIN",
        1,
        58,
        23,
        17,
        fc="#0d1117",
        ec=ACCENT_BE,
        fs=7,
        bold=True,
    )
    n("c_ep", "endpoints/chat.py\nPOST /chat\nPOST /chat/stream", 2, 71, 21, 2.6, fc=BOX)
    n("c_svc", "chat_service.py\nrun_chat_turn\nstream_chat_response", 2, 68, 21, 2.6, fc=BOX)
    n("c_scope", "Scope validate\nmatter_policy\nnormalize_chat_scope", 2, 65, 21, 2.6, fc=BOX, ec=ACCENT_WARN)
    n("c_router", "mode_router.py\nKB | OpenLaw | Hybrid", 2, 62, 21, 2.6, fc=BOX, ec=ACCENT_AI)
    n("c_sess", "sessions.py\nthread history\nattachments", 2, 59, 21, 2.6, fc=BOX)
    n("c_persist", "chat_persistence.py\nSQLite chat_history", 2, 56, 21, 2.6, fc=BOX, ec=ACCENT_DATA)

    e("router", "dom_chat", color=ARROW_HI)
    e("dom_chat", "c_ep", style=":")
    e("c_ep", "c_svc")
    e("c_svc", "c_scope")
    e("c_scope", "c_router")
    e("c_svc", "c_sess", style=":")
    e("c_svc", "c_persist")

    # DOCUMENTS/KB column
    n("dom_docs", "DOCUMENTS / KB", 25, 58, 23, 17, fc="#0d1117", ec=ACCENT_BE, fs=7, bold=True)
    n("d_ep", "documents.py\nupload | index | jobs", 26, 71, 21, 2.6, fc=BOX)
    n("d_extract", "PDF + OCR\npdf_extraction\nocr_engine", 26, 68, 21, 2.6, fc=BOX)
    n("d_chunk", "Chunk + Embed\nrag.py | kb_pipeline\nkb_preprocess", 26, 65, 21, 2.6, fc=BOX)
    n("d_index", "FAISS write\nmatter_index.py\nindex_jobs.py", 26, 62, 21, 2.6, fc=BOX, ec=ACCENT_DATA)
    n("d_status", "index_status\nprocessing->ready\nqueued | failed", 26, 59, 21, 2.6, fc=BOX, ec=ACCENT_WARN)
    n("d_health", "kb/health\nsmoke-test\nreindex-auto", 26, 56, 21, 2.6, fc=BOX)

    e("router", "dom_docs", color=ARROW_HI)
    e("dom_docs", "d_ep", style=":")
    e("d_ep", "d_extract")
    e("d_extract", "d_chunk")
    e("d_chunk", "d_index")
    e("d_index", "d_status")
    e("d_status", "d_health", style=":")

    # MATTERS column
    n("dom_mat", "MATTERS DOMAIN", 49, 58, 23, 17, fc="#0d1117", ec=ACCENT_BE, fs=7, bold=True)
    n("m_ep", "matters.py\nCRUD | dashboard", 50, 71, 21, 2.6, fc=BOX)
    n("m_policy", "matter_policy.py\nresolve_matter_context\nrole write checks", 50, 68, 21, 2.6, fc=BOX, ec=ACCENT_WARN)
    n("m_repo", "matter_repo.py\ntimeline | tasks\narchive | restore", 50, 65, 21, 2.6, fc=BOX)
    n("m_intel", "matter_intelligence\nsmoke | autopilot\ncontradictions", 50, 62, 21, 2.6, fc=BOX, ec=ACCENT_AI)
    n("m_scope_kb", "Matter-scoped KB\nfaiss .../matter_{id}/", 50, 59, 21, 2.6, fc=BOX, ec=ACCENT_DATA)
    n("m_del", "Lifecycle\narchive default\nhard delete ?hard=true", 50, 56, 21, 2.6, fc=BOX)

    e("router", "dom_mat", color=ARROW_HI)
    e("fe_mat", "dom_mat", color=ARROW_HI, style="--")
    e("dom_mat", "m_ep", style=":")
    e("m_ep", "m_policy")
    e("m_policy", "m_repo")
    e("m_repo", "m_intel")
    e("m_intel", "m_scope_kb")
    e("m_repo", "m_del", style=":")

    # LEARNING column
    n("dom_learn", "LEARNING / TUNING", 73, 58, 26, 17, fc="#0d1117", ec=ACCENT_LEARN, fs=7, bold=True)
    n("l_ep", "learning.py\nfeedback | signals", 74, 71, 24, 2.6, fc=BOX)
    n("l_adapt", "adaptive_learning.py\nchunk boosts\nquery expansion", 74, 68, 24, 2.6, fc=BOX)
    n("l_engine", "learning_engine.py\nanswer memory", 74, 65, 24, 2.6, fc=BOX)
    n("l_neural", "neural_finetuning.py\nembedding train", 74, 62, 24, 2.6, fc=BOX)
    n("l_coach", "gemini_ollama_coach\nSettings-only meta", 74, 59, 24, 2.6, fc=BOX, ec=ACCENT_AI)
    n("l_scope", "scope_key barrier\nglobal vs matter:<id>\nadmin promote", 74, 56, 24, 2.6, fc=BOX, ec=ACCENT_WARN)

    e("router", "dom_learn", color=ARROW_HI)
    e("dom_learn", "l_ep", style=":")
    e("l_ep", "l_adapt")
    e("l_adapt", "l_engine")
    e("l_engine", "l_neural", style=":")
    e("l_adapt", "l_coach", style=":")
    e("l_adapt", "l_scope")

    # Cross-domain links
    e("c_router", "dom_docs", label="KB query", color=ACCENT_AI, style="--")
    e("c_router", "dom_learn", label="log turn", color=ACCENT_LEARN, style="--")
    e("d_index", "m_scope_kb", label="scoped index", color=ACCENT_DATA)
    e("c_scope", "m_policy", label="access check", color=ACCENT_WARN, style="--")
    e("fe_docs", "dom_docs", color=ARROW_HI, style="--")

    # ---- Tier 5: AI Intelligence layer ----
    n(
        "ai_layer",
        "AI / INTELLIGENCE LAYER",
        2,
        38,
        96,
        16,
        fc="#0d1117",
        ec=ACCENT_AI,
        fs=8,
        bold=True,
    )

    n(
        "mode_kb",
        "KNOWLEDGE BASE MODE\n"
        "Query understand -> Memory inject -> Dense+Sparse retrieval\n"
        "Rerank -> Confidence gate -> Ollama synthesis",
        3,
        48,
        28,
        6.5,
        fc=BOX,
        ec=ACCENT_AI,
    )
    n(
        "mode_web",
        "OPEN LAW MODE\n"
        "Filter KB history -> Classify depth -> Gemini + Google Search\n"
        "KB-leak guard -> Format response + sources",
        35,
        48,
        28,
        6.5,
        fc=BOX,
        ec=ACCENT_AI,
    )
    n(
        "mode_hybrid",
        "HYBRID / JURISPRUDENCE\n"
        "Parallel KB chunks + Web search -> Gemini fusion report\n"
        "Conflict: documents win | Export DOCX/PDF",
        67,
        48,
        30,
        6.5,
        fc=BOX,
        ec=ACCENT_AI,
    )

    n("ollama", "OLLAMA / LM STUDIO\nKB answers ONLY\nGEMINI_KB_SYNTHESIS=0", 8, 40, 26, 3.5, fc=BOX_ALT, ec=ACCENT_BE, fs=7)
    n("gemini", "GEMINI API\nWeb + Hybrid + Coach\nNEVER raw KB answers", 66, 40, 28, 3.5, fc=BOX_ALT, ec=ACCENT_AI, fs=7)

    e("c_router", "ai_layer", color=ARROW_HI)
    e("ai_layer", "mode_kb", style=":")
    e("ai_layer", "mode_web", style=":")
    e("ai_layer", "mode_hybrid", style=":")
    e("mode_kb", "ollama", color=ARROW_HI)
    e("mode_web", "gemini", color=ARROW_HI)
    e("mode_hybrid", "ollama", style="--")
    e("mode_hybrid", "gemini", color=ARROW_HI)
    e("d_chunk", "mode_kb", color=ACCENT_DATA, style="--")
    e("l_coach", "ollama", label="style tune", color=ACCENT_LEARN, style=":")

    # Scope isolation box
    n(
        "scope_iso",
        "SCOPE ISOLATION\n"
        "Global KB: faiss_indexes/user_X/_unlinked/  (no matter_id)\n"
        "Matter KB: faiss_indexes/user_X/matter_Y/   (matter_id in chat)\n"
        "Chat strips matter_id when mode not KB-relevant",
        34,
        40,
        30,
        3.5,
        fc=BOX,
        ec=ACCENT_WARN,
        fs=6,
    )
    e("m_scope_kb", "scope_iso", color=ACCENT_WARN)
    e("c_scope", "scope_iso", color=ACCENT_WARN, style="--")

    # ---- Tier 6: Persistence ----
    n(
        "data_layer",
        "PERSISTENCE & RUNTIME",
        2,
        22,
        96,
        14,
        fc="#0d1117",
        ec=ACCENT_DATA,
        fs=8,
        bold=True,
    )
    n(
        "sqlite",
        "SQLite (legalease.db)\n"
        "users | chat_history | matters | documents\n"
        "learning | billing | CRM | discovery | trust",
        3,
        26,
        30,
        8,
        fc=BOX,
        ec=ACCENT_DATA,
    )
    n(
        "faiss_g",
        "FAISS Global\n_unlinked index\nDocuments page uploads",
        35,
        26,
        28,
        8,
        fc=BOX,
        ec=ACCENT_DATA,
    )
    n(
        "faiss_m",
        "FAISS Matter\nmatter_{id} index\nMatter dashboard uploads",
        65,
        26,
        30,
        8,
        fc=BOX,
        ec=ACCENT_DATA,
    )
    n(
        "runtime",
        "Background Workers\n"
        "index_jobs | reindex_scheduler\n"
        "coach_scheduler | improvement_automation\n"
        "Optional Redis: sessions / ediscovery queue",
        3,
        14,
        92,
        6,
        fc=BOX_ALT,
        ec=ACCENT_DATA,
        fs=6.5,
    )

    e("c_persist", "sqlite", color=ACCENT_DATA)
    e("m_repo", "sqlite", color=ACCENT_DATA, style="--")
    e("l_adapt", "sqlite", color=ACCENT_DATA, style="--")
    e("d_index", "faiss_g")
    e("d_index", "faiss_m")
    e("d_index", "runtime", style=":")
    e("ollama", "runtime", style=":")

    # ---- Tier 7: Continuous learning loop ----
    n(
        "loop",
        "CONTINUOUS IMPROVEMENT LOOP\n"
        "Chat turn -> record interaction -> thumbs/signals -> adaptive boosts\n"
        "-> neural train / reindex / Modelfile export -> better next answer",
        8,
        4,
        84,
        6,
        fc="#0d1117",
        ec=ACCENT_LEARN,
        fs=7,
        bold=True,
    )
    e("l_ep", "loop", color=ACCENT_LEARN)
    e("c_svc", "loop", color=ACCENT_LEARN, style="--")
    e("loop", "l_adapt", label="feedback", color=ACCENT_LEARN, style="--")
    e("loop", "c_router", label="improved retrieval", color=ACCENT_LEARN, style="--")

    # SaaS strip (side annotation)
    n(
        "saas",
        "SAAS MODULES (parallel)\n"
        "Billing | CRM/Intake | Trust | E-Discovery | Premium\n"
        "Portal | E-sign | Templates | Drafting | Clauses",
        73,
        30,
        25,
        10,
        fc=BOX,
        ec=ACCENT_BE,
        fs=6,
    )
    e("router", "saas", color=ARROW_HI, style="--")
    e("fe_saas", "saas", style="--")
    e("saas", "sqlite", color=ACCENT_DATA, style=":")


def _node_map() -> dict[str, Node]:
    return {x.nid: x for x in NODES}


def _box_center_bottom(node: Node) -> tuple[float, float]:
    return node.x + node.w / 2, node.y


def _box_center_top(node: Node) -> tuple[float, float]:
    return node.x + node.w / 2, node.y + node.h


def _draw_node(ax, node: Node) -> None:
    patch = FancyBboxPatch(
        (node.x, node.y),
        node.w,
        node.h,
        boxstyle="round,pad=0.02,rounding_size=0.15",
        linewidth=1.2,
        edgecolor=node.ec,
        facecolor=node.fc,
        transform=ax.transData,
        zorder=2,
    )
    ax.add_patch(patch)
    weight = "bold" if node.bold else "normal"
    ax.text(
        node.x + node.w / 2,
        node.y + node.h / 2,
        node.label,
        ha="center",
        va="center",
        fontsize=node.fs,
        color=TEXT,
        fontweight=weight,
        zorder=3,
        wrap=True,
    )


def _draw_edge(ax, edge: Edge, nodes: dict[str, Node]) -> None:
    if edge.src not in nodes or edge.dst not in nodes:
        return
    s = nodes[edge.src]
    d = nodes[edge.dst]
    x1, y1 = _box_center_bottom(s)
    x2, y2 = _box_center_top(d)
    if y1 < y2:
        x1, y1 = _box_center_top(s)
        x2, y2 = _box_center_bottom(d)
    arrow = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle="-|>",
        mutation_scale=10,
        linewidth=1.0,
        color=edge.color,
        linestyle=edge.style,
        connectionstyle="arc3,rad=0.08",
        zorder=1,
    )
    ax.add_patch(arrow)
    if edge.label:
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        ax.text(
            mx,
            my,
            edge.label,
            fontsize=5,
            color=TEXT_DIM,
            ha="center",
            va="center",
            bbox=dict(boxstyle="round,pad=0.15", facecolor=BG, edgecolor=BORDER, alpha=0.9),
            zorder=4,
        )


def _draw_legend(ax) -> None:
    items = [
        (ACCENT_FE, "Frontend"),
        (ACCENT_BE, "Backend / API"),
        (ACCENT_AI, "AI / Modes"),
        (ACCENT_DATA, "Data / Indexes"),
        (ACCENT_LEARN, "Learning loop"),
        (ACCENT_WARN, "Security / scope"),
    ]
    ax.text(1, 1.5, "LEGEND", fontsize=7, color=TEXT, fontweight="bold")
    for i, (col, lbl) in enumerate(items):
        ax.add_patch(
            FancyBboxPatch(
                (1 + i * 16, 0.2),
                2,
                0.8,
                boxstyle="round,pad=0.02",
                facecolor=col,
                edgecolor=BORDER,
                linewidth=0.8,
            )
        )
        ax.text(3.5 + i * 16, 0.6, lbl, fontsize=5.5, color=TEXT_DIM, va="center")


def build_pdf() -> Path:
    _build_graph()
    nodes = _node_map()

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)

    with PdfPages(OUT_PDF) as pdf:
        # Page 1 — full master flowchart
        fig, ax = plt.subplots(figsize=(24, 16), facecolor=BG)
        ax.set_facecolor(BG)
        ax.set_xlim(0, 100)
        ax.set_ylim(0, 100)
        ax.axis("off")

        ax.text(
            50,
            99.2,
            "LegalEase — Master System Flowchart (Dark)",
            ha="center",
            va="top",
            fontsize=16,
            color=TEXT,
            fontweight="bold",
        )
        ax.text(
            50,
            98.2,
            "End-to-end: User -> Frontend -> API Domains -> AI Modes -> Persistence -> Learning",
            ha="center",
            va="top",
            fontsize=8,
            color=TEXT_DIM,
        )

        for node in NODES:
            _draw_node(ax, node)
        for edge in EDGES:
            _draw_edge(ax, edge, nodes)
        _draw_legend(ax)

        fig.tight_layout(pad=0.5)
        pdf.savefig(fig, facecolor=BG, dpi=200)
        plt.close(fig)

        # Page 2 — relationship matrix / quick reference
        fig2, ax2 = plt.subplots(figsize=(16, 11), facecolor=BG)
        ax2.set_facecolor(BG)
        ax2.axis("off")
        ax2.set_xlim(0, 10)
        ax2.set_ylim(0, 10)
        ax2.text(
            5,
            9.5,
            "Process Relationships — Quick Reference",
            ha="center",
            fontsize=14,
            color=TEXT,
            fontweight="bold",
        )
        ref = """
CHAT uses MATTERS for scope validation (matter_policy) and FAISS matter index for retrieval.
DOCUMENTS feed FAISS (global or matter path) — same index CHAT queries in KB mode.
LEARNING reads chat interactions; writes boosts — never injects legal substance from Gemini into KB.
OPEN LAW / HYBRID use Gemini; KB mode uses Ollama only (GEMINI_KB_SYNTHESIS=0).
MATTER delete archives by default; documents unlinked from matter index on archive.
Frontend streamChat -> chat/stream -> chat_service -> mode_router -> (rag | web_intelligence).
Upload -> documents endpoint -> OCR/extract -> chunk/embed -> index_jobs -> FAISS + SQLite metadata.
Settings coach + neural tuning run in background; triggered by feedback, not during chat turn.
SaaS modules (billing, CRM, discovery) share SQLite user scope; independent API routers.
        """.strip()
        ax2.text(
            0.5,
            8.5,
            ref,
            ha="left",
            va="top",
            fontsize=9,
            color=TEXT,
            family="monospace",
            linespacing=1.6,
        )
        pdf.savefig(fig2, facecolor=BG, dpi=150)
        plt.close(fig2)

    return OUT_PDF


if __name__ == "__main__":
    path = build_pdf()
    print(path)
