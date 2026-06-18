"""One-click hearing prep pack from matter intelligence data."""
from __future__ import annotations

import os
from typing import Any, Dict, List

from backend.app.core.matter_repo import get_matter, list_matter_documents


def _ai_prep_enabled() -> bool:
    return os.getenv("LITIGATION_PREP_AI", "1").lower() in {"1", "true", "yes"}


def _build_ai_litigation_brief(user_id: str, matter_id: str, matter: Dict[str, Any], base_md: str) -> str:
    if not _ai_prep_enabled() or not base_md.strip():
        return ""
    try:
        from llms import get_generator

        client = get_generator(user_id=user_id)
        if not client:
            return ""
        prompt = (
            f"You are an Indian litigation counsel. Matter: {matter.get('matter_name')}. "
            f"Case: {matter.get('case_number')}. Court: {matter.get('venue')}. "
            "Based on the prep notes below, write a concise hearing brief with: "
            "(1) key issues for today, (2) 3 arguments to advance, (3) documents to carry, "
            "(4) risks. Use markdown bullets. Max 400 words.\n\nPREP NOTES:\n"
            f"{base_md[:6000]}"
        )
        return (client.generate(prompt, max_tokens=900, temperature=0.3) or "").strip()
    except Exception:
        return ""


def build_hearing_prep_pack(user_id: str, matter_id: str, *, use_ai: bool = True) -> Dict[str, Any]:
    """Compose markdown prep pack without extra LLM calls."""
    m = get_matter(user_id, matter_id)
    if not m:
        return {"ok": False, "error": "Matter not found", "markdown": ""}

    sections: List[str] = [
        f"# Hearing Prep Pack — {m.get('matter_name', 'Matter')}",
        "",
        f"**Case number:** {m.get('case_number') or '—'}  ",
        f"**Court / venue:** {m.get('venue') or '—'}  ",
        f"**Client:** {m.get('client_name') or '—'}  ",
        f"**Opposing:** {m.get('opposing_party') or '—'}  ",
        "",
    ]

    try:
        from backend.app.core.matter_qa import answer_matter_query

        summary = answer_matter_query(user_id, matter_id, "case summary facts incident")
        if summary:
            sections.extend(["## Case summary", "", summary, ""])
    except Exception:
        pass

    try:
        from backend.app.core.matter_entities import list_entities

        ents = list_entities(user_id, matter_id)
        if ents:
            sections.append("## Key parties & entities")
            by_type: Dict[str, List[str]] = {}
            for e in ents:
                t = e.get("entity_type", "other")
                role = (e.get("metadata") or {}).get("role", "")
                lbl = e.get("label", "")
                if role:
                    lbl = f"{lbl} ({role})"
                by_type.setdefault(t, []).append(lbl)
            for t, labels in sorted(by_type.items()):
                sections.append(f"\n**{t.replace('_', ' ').title()}:** " + ", ".join(labels[:12]))
            sections.append("")
    except Exception:
        pass

    try:
        from backend.app.core.matter_evidence import list_evidence

        ev = list_evidence(user_id, matter_id)
        if ev:
            sections.append("## Evidence")
            for i, item in enumerate(ev[:15], 1):
                title = item.get("title") or item.get("category") or "Evidence"
                imp = item.get("importance") or item.get("strength") or ""
                sections.append(f"{i}. **{title}**" + (f" ({imp})" if imp else ""))
            sections.append("")
    except Exception:
        pass

    try:
        from backend.app.core.matter_hearings_intel import list_hearings

        hearings = list_hearings(user_id, matter_id)
        if hearings:
            sections.append("## Hearings")
            for h in hearings[:8]:
                sections.append(
                    f"- **{h.get('hearing_date', '—')}** — {h.get('court_name', '')} "
                    f"{('· ' + h.get('purpose', '')) if h.get('purpose') else ''}"
                )
                if h.get("judge"):
                    sections.append(f"  - Judge: {h['judge']}")
                if h.get("next_hearing_date"):
                    sections.append(f"  - Next: {h['next_hearing_date']}")
            sections.append("")
    except Exception:
        pass

    try:
        from backend.app.core.matter_qa import answer_matter_query

        witnesses = answer_matter_query(user_id, matter_id, "witness statement")
        if witnesses:
            sections.extend(["## Witness overview", "", witnesses, ""])
    except Exception:
        pass

    try:
        from backend.app.core.matter_enhancements import analyze_contradictions

        cx = analyze_contradictions(user_id, matter_id)
        pairs = cx.get("pairs") or []
        if pairs:
            sections.append("## Contradictions to watch")
            for p in pairs[:6]:
                sections.append(f"- {p.get('summary', p)}")
            sections.append("")
    except Exception:
        pass

    docs = list_matter_documents(user_id, matter_id)
    if docs:
        sections.append("## Linked documents")
        for d in docs[:10]:
            sections.append(f"- {d.get('filename', d.get('document_id'))}")
        sections.append("")

    sections.extend(
        [
            "## Strategy notes",
            "",
            "- Review latest order and compliance deadlines before court.",
            "- Confirm exhibits and witness availability.",
            "- Align with client on settlement / bail / interim relief position.",
            "",
            "## Opponent position (outline)",
            "",
            f"- Opposing party: {m.get('opposing_party') or '—'}",
            "- Anticipate prosecution/defence arguments from prior hearings and pleadings.",
            "",
            "## Previous orders",
            "",
        ]
    )
    try:
        from backend.app.core.litigation_os import list_court_orders

        orders = list_court_orders(user_id, matter_id=matter_id, limit=8)
        if orders:
            for o in orders:
                sections.append(f"- **{o.get('order_date', '—')}** — {o.get('title', 'Order')} ({o.get('order_type', '')})")
        else:
            sections.append("- No structured orders on file — upload under Litigation Desk → Orders.")
    except Exception:
        sections.append("- Orders repository available on Litigation Desk.")
    sections.append("")

    markdown = "\n".join(sections).strip()
    ai_brief = ""
    if use_ai:
        ai_brief = _build_ai_litigation_brief(user_id, matter_id, m, markdown)
        if ai_brief:
            markdown = markdown + "\n\n## AI hearing notes\n\n" + ai_brief

    return {
        "ok": True,
        "matter_id": matter_id,
        "markdown": markdown,
        "document_count": len(docs),
        "ai_brief_included": bool(ai_brief),
    }


def _sanitize_pdf_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("\u2014", "-").replace("\u2013", "-")
    text = text.replace("\u2192", "->").replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\u20b9", "Rs.")
    return text.encode("latin-1", errors="replace").decode("latin-1")


def render_prep_pack_pdf(user_id: str, matter_id: str, *, use_ai: bool = True) -> tuple[bytes, str]:
    """Generate PDF bytes from prep pack markdown."""
    pack = build_hearing_prep_pack(user_id, matter_id, use_ai=use_ai)
    if not pack.get("ok") and not pack.get("markdown"):
        raise ValueError(pack.get("error") or "Prep pack not available")

    from fpdf import FPDF

    m = get_matter(user_id, matter_id) or {}
    matter_name = _sanitize_pdf_text((m.get("matter_name") or "Matter").replace("/", "-")[:60])
    filename = f"HearingPrep_{matter_name.replace(' ', '_')}.pdf"

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.multi_cell(pdf.epw, 8, _sanitize_pdf_text(f"Hearing Prep Pack - {matter_name}"))
    pdf.ln(4)
    pdf.set_font("Helvetica", "", 9)

    for line in (pack.get("markdown") or "").splitlines():
        text = _sanitize_pdf_text(line.replace("**", "").replace("#", "").strip())
        if not text:
            pdf.ln(3)
            continue
        if line.startswith("## "):
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(pdf.epw, 6, text)
            pdf.set_font("Helvetica", "", 9)
        elif line.startswith("# "):
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(pdf.epw, 7, text)
            pdf.set_font("Helvetica", "", 9)
        else:
            try:
                pdf.multi_cell(pdf.epw, 5, text[:500])
            except Exception:
                pdf.multi_cell(pdf.epw, 5, text[:200])

    return bytes(pdf.output()), filename
