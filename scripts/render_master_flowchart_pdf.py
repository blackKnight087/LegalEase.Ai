#!/usr/bin/env python3
"""Render LegalEase master system flowchart to PDF."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]
OUT_PDF = ROOT / "docs" / "blueprint" / "master-system-flowchart.pdf"

MASTER_DIAGRAM = r"""
================================================================================
                    LEGALEASE — COMPLETE SYSTEM (MASTER FLOWCHART)
================================================================================

                              [ USER / LAWYER ]
                                      |
                                      v
+-----------------------------------------------------------------------------+
|                         FRONTEND — Next.js (web/)                           |
|  +-----------------------------------------------------------------------+  |
|  | Shell: layout.tsx | Auth | ApiConnection | ChatSession               |  |
|  +-----------------------------------------------------------------------+  |
|  | PAGES                                                                 |  |
|  |  / (Chat)     /documents    /matters/*     /settings    /dashboard   |  |
|  |  /billing     /intake      /discovery      /premium     /tools       |  |
|  |  /drafting    /analytics   /portal/[token] /login                    |  |
|  +-----------------------------------------------------------------------+  |
|  | HOOKS / UI                                                            |  |
|  |  useChat + streamChat | MatterDashboard | SpeechPanel | api.ts       |  |
|  +-----------------------------------------------------------------------+  |
+------------------------------------|----------------------------------------+
                                     |  HTTP REST + SSE (/api/v1/*)
                                     |  Bearer JWT (legalease_token)
                                     v
+-----------------------------------------------------------------------------+
|                      BACKEND — FastAPI (backend/app/)                       |
|  main.py: CORS | RateLimit | MemoryGuard | Startup thread | Auth routes    |
+------------------------------------|----------------------------------------+
                                     |
         +---------------------------+---------------------------+
         |                           |                           |
         v                           v                           v
+------------------+    +----------------------+    +----------------------+
| CHAT DOMAIN      |    | DOCUMENTS / KB       |    | MATTERS DOMAIN       |
| /chat            |    | /documents           |    | /matters             |
| /chat/stream     |    | upload, index, jobs  |    | CRUD, dashboard      |
| /sessions        |    | kb/health, smoke     |    | timeline, tasks      |
| chat_service     |    | OCR, entities        |    | archive/restore      |
| mode_router      |    | index_jobs           |    | matter_policy        |
| hybrid_orchestr. |    | matter_index paths   |    | matter_repo          |
+--------+---------+    +----------+-----------+    +----------+-----------+
         |                           |                           |
         |              +------------+------------+                |
         |              |            |            |                |
         v              v            v            v                v
+------------------+  +--------+  +--------+  +--------+  +------------------+
| LEARNING         |  | MEMORY |  | SPEECH |  | ENGINES|  | SAAS MODULES   |
| /learning        |  |/memory |  |/speech |  |/engines|  | /billing       |
| feedback, coach  |  |persona |  |STT     |  |status  |  | /crm /trust    |
| neural tune      |  |facts   |  |polish  |  |        |  | /ediscovery    |
| scope promotion  |  |        |  |        |  |        |  | /premium       |
| automation       |  |        |  |        |  |        |  | /portal /esign |
+--------+---------+  +--------+  +--------+  +--------+  | /templates...  |
         |                                                  +--------+-------+
         |                                                           |
         +---------------------------+-------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|                         AI / INTELLIGENCE LAYER                             |
|                                                                             |
|   +---------------- MODE ROUTER (per message) ----------------+            |
|   |                                                            |            |
|   |   knowledge_base          web_search          deep_case      |            |
|   |        |                      |                  |         |            |
|   |        v                      v                  v         |            |
|   |   +----------+          +----------+      +-------------+  |            |
|   |   | RAG/KB   |          | Open Law |      | HYBRID      |  |            |
|   |   | FAISS    |          | Gemini + |      | KB + Web +  |  |            |
|   |   | dense +  |          | Google   |      | Gemini fuse |  |            |
|   |   | sparse + |          | search   |      +-------------+  |            |
|   |   | rerank   |          +----------+                        |            |
|   |   | confidence|                                             |            |
|   |   | gate     |                                             |            |
|   |   +----+-----+                                             |            |
|   |        |                                                   |            |
|   |        v                                                   |            |
|   |   OLLAMA / LM STUDIO  (KB answers ONLY — never Gemini)    |            |
|   |   GEMINI API          (web + hybrid + coach meta ONLY)     |            |
|   +------------------------------------------------------------+            |
|                                                                             |
|   SCOPE ISOLATION:                                                          |
|   Global KB: faiss_indexes/user_X/_unlinked/     (no matter_id)            |
|   Matter KB: faiss_indexes/user_X/matter_Y/      (matter_id in chat)       |
|   Learning:  scope_key global  vs  matter:<id>    (barrier + admin promote) |
+------------------------------------|----------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|                         PERSISTENCE & RUNTIME                                 |
|                                                                             |
|   SQLite (legalease.db)          FAISS vector indexes (faiss_indexes/)      |
|   - users, auth, membership      - per user + per matter scope              |
|   - chat_history, threads        - chunks + embeddings metadata             |
|   - matters, docs, tasks...                                                 |
|   - learning, billing, CRM       Data/ uploads, exports, ollama_exports     |
|                                                                             |
|   Optional: Redis (sessions, ediscovery queue)   Background: index_jobs,      |
|   reindex_scheduler, coach_scheduler, improvement_automation threads          |
+-----------------------------------------------------------------------------+
                                     |
                                     v
+-----------------------------------------------------------------------------+
|                    CONTINUOUS LOOP (every interaction)                      |
|   Chat turn -> log interaction -> user feedback/signals -> adaptive learn  |
|   -> optional neural train / reindex / Modelfile export -> better next Q   |
+-----------------------------------------------------------------------------+

================================================================================
  LEGEND:  -----> request/data flow   |   vertical = layered dependency
           X--> forbidden (Gemini must not answer raw KB from documents)
================================================================================
""".strip()


def _ascii_safe(text: str) -> str:
    replacements = {
        "\u2014": "-",
        "\u2013": "-",
        "\u2192": "->",
        "\u2190": "<-",
        "\u2022": "*",
        "\u00b7": ".",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text.encode("ascii", errors="replace").decode("ascii")


class FlowchartPDF(FPDF):
    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, f"Page {self.page_no()}/{{nb}}", align="C")


def build_pdf() -> Path:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf = FlowchartPDF(orientation="L", unit="mm", format="A3")
    pdf.alias_nb_pages()
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.set_margins(10, 10, 10)

    # Cover
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 28)
    pdf.set_text_color(30, 58, 95)
    pdf.ln(30)
    pdf.cell(0, 14, "LegalEase AI Platform", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 18)
    pdf.set_text_color(68, 85, 102)
    pdf.cell(0, 10, "Master System Flowchart", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 11)
    pdf.cell(0, 8, f"Generated: {generated}", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, "Single-page architecture: Frontend -> API -> Domains -> AI -> Data -> Learning", align="C", new_x="LMARGIN", new_y="NEXT")

    # Diagram page(s)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 10, "Complete System Flow (Top to Bottom)", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    pdf.set_font("Courier", "", 5.2)
    pdf.set_text_color(20, 20, 20)
    left = pdf.l_margin
    usable_w = pdf.w - pdf.l_margin - pdf.r_margin

    for line in MASTER_DIAGRAM.splitlines():
        safe = _ascii_safe(line)
        if pdf.get_y() > pdf.h - 14:
            pdf.add_page()
            pdf.set_font("Courier", "", 5.2)
        pdf.set_x(left)
        # Truncate very long lines for page width
        max_chars = 200
        pdf.multi_cell(usable_w, 2.6, safe[:max_chars] if len(safe) > max_chars else safe)

    # Legend summary page
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 58, 95)
    pdf.cell(0, 10, "How to Read This Flowchart", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(30, 30, 30)
    bullets = [
        "1. User interacts with Next.js pages and hooks (useChat, MatterDashboard, api.ts).",
        "2. All protected calls go to FastAPI /api/v1 with JWT auth and middleware.",
        "3. Work is routed to domain modules: Chat, Documents/KB, Matters, Learning, SaaS.",
        "4. Chat uses mode_router to pick Knowledge Base, Open Law, or Hybrid paths.",
        "5. KB answers use Ollama + FAISS only; Gemini is used for web/hybrid/coach meta.",
        "6. Global KB and Matter KB indexes are isolated (separate FAISS paths + scope_key).",
        "7. SQLite stores metadata; FAISS stores vectors; background jobs handle indexing/tuning.",
        "8. Every chat turn feeds the learning loop for continuous improvement.",
    ]
    for b in bullets:
        pdf.set_x(left)
        pdf.multi_cell(usable_w, 7, _ascii_safe(b))
        pdf.ln(1)

    OUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUT_PDF))
    return OUT_PDF


if __name__ == "__main__":
    path = build_pdf()
    print(path)
