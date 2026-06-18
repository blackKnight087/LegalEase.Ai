"""
LegalEase premium chat UI — Streamlit-safe (no clipped widgets, no HTML wrappers around inputs).
"""
from __future__ import annotations

import re
import uuid
from html import escape
from typing import Any, Dict, List, Optional

import streamlit as st

from ocr_engine import extract_text_from_image_bytes

MODE_MAP = {
    "Knowledge Base": "knowledge_base",
    "Open Law": "web_search",
    "Hybrid": "deep_case",
}


def inject_nuclear_layout_css() -> None:
    """Call at top of main() before sidebar — base resets only."""
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Playfair+Display:wght@600;700&display=swap');
        header, footer, [data-testid="stHeader"], [data-testid="stFooter"] {
            visibility: hidden !important;
            height: 0 !important;
            padding: 0 !important;
            margin: 0 !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_chat_page_css() -> None:
    """
    Chat-only layout. CRITICAL: no overflow:hidden on .block-container (clips input & messages).
    """
    st.markdown(
        """
        <style>
        section[data-testid="stSidebar"] {
            width: 280px !important;
            max-width: 280px !important;
        }
        section[data-testid="stSidebar"] > div {
            background: #0f172a !important;
            padding-top: 0.65rem !important;
        }

        section.main[data-testid="stMain"] .block-container {
            padding: 0.4rem 1.25rem 0.5rem 1.25rem !important;
            max-width: 1080px !important;
            margin: 0 auto !important;
            min-height: auto !important;
            height: auto !important;
            max-height: none !important;
            overflow: visible !important;
            background: #f8fafc !important;
        }

        section.main[data-testid="stMain"] [data-testid="stVerticalBlock"] {
            gap: 0.35rem !important;
        }
        section.main[data-testid="stMain"] [data-testid="stVerticalBlock"] > div {
            gap: 0.25rem !important;
            padding-bottom: 0 !important;
            margin-bottom: 0 !important;
        }

        .le-chat-header-title {
            font-family: 'Playfair Display', serif;
            font-size: 1.35rem;
            font-weight: 700;
            color: #0f172a;
            margin: 0;
            padding: 0;
        }

        section.main[data-testid="stMain"] [data-testid="stRadio"] > div {
            gap: 0.35rem !important;
            flex-wrap: wrap !important;
        }
        section.main[data-testid="stMain"] [data-testid="stRadio"] label {
            background: #fff !important;
            border: 1px solid #cbd5e1 !important;
            border-radius: 999px !important;
            padding: 0.28rem 0.75rem !important;
            font-size: 0.75rem !important;
            font-weight: 600 !important;
            color: #475569 !important;
        }
        section.main[data-testid="stMain"] [data-testid="stRadio"] label:has(input:checked) {
            background: #0f172a !important;
            color: #fff !important;
            border-color: #0f172a !important;
        }

        .saas-chat-viewport {
            min-height: 180px;
            max-height: calc(100vh - 280px);
            overflow-y: auto;
            overflow-x: hidden;
            padding: 0.25rem 0.1rem 0.5rem 0.1rem;
            margin: 0 0 0.5rem 0;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            scroll-behavior: smooth;
        }

        /* User: RIGHT */
        .row-alignment-user {
            display: flex;
            justify-content: flex-end;
            width: 100%;
            margin: 0.35rem 0;
        }
        .bubble-style-user {
            background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%);
            color: #ffffff;
            padding: 0.85rem 1.2rem;
            border-radius: 20px 20px 4px 20px;
            max-width: 72%;
            box-shadow: 0 6px 16px rgba(37, 99, 235, 0.18);
            font-family: 'Inter', sans-serif;
            font-size: 0.94rem;
            line-height: 1.5;
            word-wrap: break-word;
        }

        /* Assistant: LEFT */
        .row-alignment-assistant {
            display: flex;
            justify-content: flex-start;
            width: 100%;
            margin: 0.35rem 0;
        }
        .card-style-assistant {
            background: #ffffff;
            color: #1e293b;
            padding: 1.1rem 1.2rem;
            border-radius: 20px 20px 20px 4px;
            max-width: 78%;
            border: 1px solid #e2e8f0;
            border-left: 4px solid #d97706;
            box-shadow: 0 4px 20px rgba(15, 23, 42, 0.06);
            font-family: 'Inter', sans-serif;
            font-size: 0.94rem;
            line-height: 1.58;
            word-wrap: break-word;
        }
        .le-intel-badge {
            font-size: 0.72rem;
            color: #d97706;
            font-weight: 700;
            letter-spacing: 0.05em;
            margin-bottom: 0.45rem;
        }

        .le-hero-empty {
            text-align: center;
            padding: 1.25rem 0.75rem 0.75rem;
        }
        .le-hero-empty h1 {
            font-family: 'Playfair Display', serif;
            font-size: 1.85rem;
            color: #0f172a;
            margin: 0 0 0.35rem 0;
        }
        .le-hero-empty p {
            font-family: 'Inter', sans-serif;
            color: #64748b;
            font-size: 0.92rem;
            max-width: 520px;
            margin: 0 auto;
            line-height: 1.5;
        }

        .loading-skeleton-card {
            height: 64px;
            width: min(78%, 520px);
            margin-right: auto;
            margin-left: 0;
            border-radius: 16px;
            background: linear-gradient(90deg, #f1f5f9 25%, #e2e8f0 50%, #f1f5f9 75%);
            background-size: 200% 100%;
            animation: leShimmer 1.2s infinite;
            border: 1px solid #e2e8f0;
        }
        .le-suggestions-row {
            margin: 0.35rem 0 0.5rem 0;
        }
        .le-suggestions-row .stButton > button {
            border-radius: 999px !important;
            padding: 0.45rem 0.85rem !important;
            font-size: 0.8rem !important;
            background: #fff !important;
            border: 1px solid #cbd5e1 !important;
            color: #334155 !important;
            transition: all 0.15s ease !important;
        }
        .le-suggestions-row .stButton > button:hover {
            border-color: #2563eb !important;
            color: #1e40af !important;
            background: #eff6ff !important;
        }
        .le-chat-shell {
            display: flex;
            flex-direction: column;
            min-height: calc(100vh - 120px);
        }
        .le-chat-shell .le-chat-messages-zone {
            flex: 1 1 auto;
            order: 1;
        }
        .le-chat-shell .le-chat-input-zone {
            order: 2;
            position: sticky;
            bottom: 0;
            z-index: 5;
            background: linear-gradient(180deg, rgba(248,250,252,0) 0%, #f8fafc 18%);
            padding-bottom: 0.25rem;
        }
        @keyframes leShimmer {
            0% { background-position: 200% 0; }
            100% { background-position: -200% 0; }
        }

        .legal-citation-pill {
            background: rgba(217, 119, 6, 0.1);
            color: #d97706;
            border: 1px solid rgba(217, 119, 6, 0.25);
            padding: 0.1rem 0.35rem;
            border-radius: 5px;
            font-size: 0.76rem;
            font-weight: 600;
            display: inline-block;
            margin: 0 0.1rem;
        }

        /* Input dock — sticky in flow (never position:fixed; avoids vanishing) */
        .le-chat-input-zone {
            margin-top: 0.35rem;
            padding-top: 0.35rem;
            border-top: 1px solid #e2e8f0;
            background: #f8fafc;
        }
        section.main[data-testid="stMain"] div[data-testid="stChatInput"] {
            position: relative !important;
            bottom: auto !important;
            left: auto !important;
            right: auto !important;
            z-index: 1 !important;
        }
        section.main[data-testid="stMain"] div[data-testid="stChatInput"] > div {
            border: 1px solid #cbd5e1 !important;
            border-radius: 14px !important;
            background: #ffffff !important;
            box-shadow: 0 2px 14px rgba(15, 23, 42, 0.08) !important;
        }

        section.main[data-testid="stMain"] .stButton > button {
            background: #fff !important;
            color: #0f172a !important;
            border: 1px solid #e2e8f0 !important;
            border-radius: 8px !important;
            font-size: 0.78rem !important;
        }
        section.main[data-testid="stMain"] .stButton > button[kind="primary"] {
            background: #0f172a !important;
            color: #fff !important;
        }

        div[data-testid="stChatMessage"] { display: none !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def inject_saas_chat_css() -> None:
    inject_chat_page_css()


def get_premium_chat_css() -> str:
    return ""


def execute_new_chat() -> None:
    st.session_state["messages"] = []
    st.session_state["chat_attachment"] = None
    st.session_state["session_prompt_bridge"] = None
    st.session_state.pop("pending_prompt", None)
    st.session_state["pending_assistant"] = False
    st.session_state["conversation_id"] = str(uuid.uuid4())


def clear_and_reset_chat_context() -> None:
    execute_new_chat()


def queue_user_message(text: str) -> None:
    """Append user turn and mark assistant response as pending."""
    content = str(text or "").strip()
    if not content:
        return
    msgs = st.session_state.setdefault("messages", [])
    if msgs and msgs[-1].get("role") == "user" and msgs[-1].get("content") == content:
        st.session_state["pending_assistant"] = True
        return
    msgs.append({"role": "user", "content": content})
    st.session_state["pending_assistant"] = True


def apply_session_prompt_bridge() -> bool:
    """
    Consume session_prompt_bridge / pending_prompt.
    Returns True if a new user turn was queued.
    """
    text = st.session_state.pop("session_prompt_bridge", None)
    if not text:
        text = st.session_state.pop("pending_prompt", None)
    if not text or not str(text).strip():
        return False
    queue_user_message(str(text).strip())
    return True


def render_mode_pills(membership: str) -> str:
    options = ["Knowledge Base", "Open Law"]
    if membership in ("Pro", "Legal Pro"):
        options.append("Hybrid")
    current = st.session_state.get("conversation_mode", "knowledge_base")
    rev = {v: k for k, v in MODE_MAP.items()}
    label = rev.get(current, "Knowledge Base")
    if label not in options:
        label = options[0]
    selected = st.radio(
        "Engine Route",
        options=options,
        index=options.index(label),
        horizontal=True,
        label_visibility="collapsed",
        key="le_mode_pills",
    )
    mode = MODE_MAP[selected]
    st.session_state["conversation_mode"] = mode
    return mode


def format_body_html(text: str) -> str:
    raw = escape((text or "").strip())
    if not raw:
        return "<p><em>No response.</em></p>"
    raw = re.sub(r"\s*\[\[[^\]]+:\d+\]\]\s*", " ", raw)
    raw = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", raw)
    parts = [p.strip() for p in re.split(r"\n\n+", raw) if p.strip()] or [raw]
    return "".join(f"<p>{p.replace(chr(10), '<br>')}</p>" for p in parts)


def user_message_html(content: str) -> str:
    body = escape((content or "").strip()).replace("\n", "<br>")
    return f'<div class="row-alignment-user"><div class="bubble-style-user">{body}</div></div>'


def assistant_message_html(content: str, sources_html: str = "") -> str:
    body = format_body_html(content)
    src = (
        f'<div style="margin-top:0.5rem;font-size:0.76rem;color:#64748b;">{sources_html}</div>'
        if sources_html else ""
    )
    return f"""
    <div class="row-alignment-assistant">
        <div class="card-style-assistant">
            <div class="le-intel-badge">LEGALEASE CORE INTEL</div>
            <div>{body}</div>
            {src}
        </div>
    </div>
    """


def render_user_message_html(content: str) -> None:
    st.markdown(user_message_html(content), unsafe_allow_html=True)


def render_assistant_message_html(content: str, sources_html: str = "") -> None:
    st.markdown(assistant_message_html(content, sources_html), unsafe_allow_html=True)


def build_sources_html(
    similar_cases: Optional[List[dict]] = None,
    web_sources: Optional[List[dict]] = None,
) -> str:
    parts = []
    if similar_cases:
        c0 = similar_cases[0]
        fname = escape(str(c0.get("filename", "document")))
        page = c0.get("page") or c0.get("page_number") or ""
        chunk = c0.get("chunk_index", "")
        if page not in ("", None):
            parts.append(f"Source: {fname}, Page {escape(str(page))}")
        elif chunk != "":
            parts.append(f"Source: {fname} (excerpt {escape(str(chunk))})")
        else:
            parts.append(f"Source: {fname}")
    if web_sources and (web_sources[0].get("provider") or "") != "LegalEase":
        s0 = web_sources[0]
        title = escape((s0.get("title") or "Web")[:80])
        href = s0.get("href") or ""
        if href:
            parts.append(f'<a href="{escape(href)}" target="_blank" style="color:#d97706;">{title}</a>')
        else:
            parts.append(title)
    return " &middot; ".join(parts)


def render_chat_viewport(messages: List[dict], *, show_loading: bool = False) -> None:
    parts = ['<div class="saas-chat-viewport">']
    if not messages and not show_loading:
        parts.append(
            """
            <div class="le-hero-empty">
                <h1>Active Legal Intelligence Engine</h1>
                <p>Query statutory provisions, synthesize evidence from your documents,
                or research live Indian law with cited sources.</p>
            </div>
            """
        )
    for msg in messages:
        if msg.get("role") == "user":
            parts.append(user_message_html(msg.get("content", "")))
        else:
            parts.append(
                assistant_message_html(
                    msg.get("content", ""),
                    sources_html=build_sources_html(
                        msg.get("similar_cases"), msg.get("web_sources")
                    ),
                )
            )
    if show_loading:
        parts.append(
            """
            <div class="row-alignment-assistant">
                <div class="card-style-assistant" style="opacity:0.92;">
                    <div class="le-intel-badge">LEGALEASE CORE INTEL</div>
                    <div class="loading-skeleton-card" style="border:none;box-shadow:none;height:48px;margin:0;"></div>
                    <p style="margin:0.5rem 0 0;font-size:0.8rem;color:#64748b;">Analyzing your documents…</p>
                </div>
            </div>
            """
        )
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_action_pills(follow_ups: List[str]) -> None:
    """Suggestion chips — queue message and rerun (same path as typed input)."""
    if not follow_ups:
        return
    conv_id = st.session_state.get("conversation_id", "default")
    st.markdown('<div class="le-suggestions-row">', unsafe_allow_html=True)
    st.caption("Suggestions")
    cols = st.columns(min(len(follow_ups), 3))
    for idx, (col, label) in enumerate(zip(cols, follow_ups[:3])):
        with col:
            if st.button(
                label,
                use_container_width=True,
                key=f"suggest_{conv_id}_{idx}",
            ):
                queue_user_message(label)
                st.session_state.pop("session_prompt_bridge", None)
                st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


def render_attach_button() -> None:
    with st.popover("Attach", help="OCR on scanned legal images"):
        st.caption("PNG / JPG")
        img = st.file_uploader(
            "img",
            type=["png", "jpg", "jpeg", "webp"],
            key="le_ocr_file",
            label_visibility="collapsed",
        )
        if st.button("Extract text", type="primary", use_container_width=True, key="le_ocr_go"):
            if img:
                text, _ = extract_text_from_image_bytes(img.getvalue(), img.name)
                if text.strip():
                    st.session_state["chat_attachment"] = {
                        "filename": img.name,
                        "text": text,
                        "chars": len(text),
                    }
                    st.success(f"{len(text):,} chars ready")
                else:
                    st.error("No text found.")
            else:
                st.warning("Select an image.")
        if st.button("Clear attachment", use_container_width=True, key="le_ocr_clr"):
            st.session_state["chat_attachment"] = None
            st.rerun()
    if att := st.session_state.get("chat_attachment"):
        st.caption(f"Attached: {att.get('filename')}")


def render_input_dock(*, key_suffix: str = "main") -> Optional[str]:
    st.markdown('<div class="le-chat-input-zone">', unsafe_allow_html=True)
    c1, c2 = st.columns([1, 12])
    with c1:
        render_attach_button()
    with c2:
        prompt = st.chat_input(
            "Ask about statutes, precedents, contracts, constitutional law...",
            key=f"le_chat_input_{key_suffix}",
        )
    st.markdown("</div>", unsafe_allow_html=True)
    return prompt


def render_chat_shell_start() -> None:
    st.markdown('<div class="le-chat-shell">', unsafe_allow_html=True)


def render_chat_messages_zone_start() -> None:
    st.markdown('<div class="le-chat-messages-zone">', unsafe_allow_html=True)


def render_chat_messages_zone_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def render_chat_shell_end() -> None:
    st.markdown("</div>", unsafe_allow_html=True)


def inject_chat_scroll_script() -> None:
    st.markdown(
        """
        <script>
        (function(){
            const v = window.parent.document.querySelector('.saas-chat-viewport');
            if (v) setTimeout(function(){ v.scrollTop = v.scrollHeight; }, 80);
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )


def suggest_follow_ups(question: str, answer: str, mode: str) -> List[str]:
    stored = st.session_state.get("last_follow_ups")
    if isinstance(stored, list) and stored:
        return [str(s) for s in stored[:3]]
    q = (question or "").lower()
    if mode == "web_search":
        return ["Latest court position", "Practical next steps", "Related sections"]
    if "section" in q or re.search(r"\b\d{3}\b", q):
        return ["Explain in simple language", "What is the punishment?", "Compare related sections"]
    return ["Summarize key points", "Explain for a non-lawyer", "What should I do next?"]


# Aliases
inject_follow_up_chips = render_follow_up_chips = render_action_pills
render_user_bubble = render_user_message_html
render_assistant_bubble = render_assistant_message_html
render_chat_hero = render_mode_banner = render_empty_state = render_ocr_dock = render_chat_topbar = (
    lambda *_a, **_k: None
)
render_sources_panel = render_quick_prompts = lambda *_a, **_k: None
def stream_text_display(text: str, role: str = "assistant") -> None:
    if role == "user":
        render_user_message_html(text)
    else:
        render_assistant_message_html(text)
