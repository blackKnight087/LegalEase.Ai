"""Cinematic guest login UI for LegalEase.AI (Streamlit)."""
from __future__ import annotations

import base64
from html import escape
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

# Main workspace (right) — cool off-white / light gray, no gold tint
LOGIN_MAIN_BG = "#f0f2f5"
LOGIN_MAIN_BG_GRAD = "linear-gradient(180deg, #f4f6f9 0%, #f0f2f5 55%, #eef1f6 100%)"

# Sidebar (left) — deep navy
LOGIN_SIDEBAR_GRAD = "linear-gradient(180deg, #0b1f3a 0%, #102a4d 65%, #183e70 100%)"

LOGIN_SIDEBAR_FEATURES = [
    ("📚", "Document Intelligence", "RAG-powered search through your legal documents"),
    ("🌐", "Live Legal Discovery", "Real-time web search for latest case laws"),
    ("⚖️", "Case Analyzer", "Deep legal research with structured reports"),
    ("📝", "Auto Legal Drafter", "Generate notices, affidavits, contracts instantly"),
    ("💰", "Court Fee Calculator", "Calculate Ad Valorem fees by state"),
    ("📈", "Case Prediction", "Predict case outcomes using AI"),
    ("🔄", "IPC-BNS Converter", "Convert old IPC sections to new BNS"),
    ("📋", "Contract Review", "AI-powered contract analysis"),
    ("🤝", "ODR Platform", "Online dispute resolution"),
]


def inject_login_cinematic_css(login_page: bool) -> None:
    """Inject login page styles: deep blue sidebar + gray main area."""
    login_surface = ""
    if login_page:
        login_surface = f"""
    html, body,
    [data-testid="stApp"],
    [data-testid="stAppViewContainer"],
    section.main,
    .stApp,
    .main,
    .main > div,
    [data-testid="stMain"],
    [data-testid="stMainBlockContainer"],
    [data-testid="stVerticalBlock"],
    [data-testid="stHeader"] {{
        background-color: {LOGIN_MAIN_BG} !important;
        background-image: {LOGIN_MAIN_BG_GRAD} !important;
    }}
    .main .block-container {{
        background: {LOGIN_MAIN_BG_GRAD} !important;
        background-color: {LOGIN_MAIN_BG} !important;
    }}
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div {{
        background: {LOGIN_SIDEBAR_GRAD} !important;
        background-image: {LOGIN_SIDEBAR_GRAD} !important;
        min-width: 27rem !important;
        width: 27rem !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {{
        color: #f1f5f9 !important;
    }}
    section[data-testid="stSidebar"] .logo-text {{
        background: none !important;
        -webkit-background-clip: unset !important;
        -webkit-text-fill-color: #f8fafc !important;
        color: #f8fafc !important;
    }}
    section[data-testid="stSidebar"] .logo-tagline {{
        color: #94a3b8 !important;
    }}
        """

    st.markdown(
        f"""
    <style>
    {login_surface}
    body.cin-page-mode,
    body.cin-page-mode [data-testid="stApp"],
    body.cin-page-mode [data-testid="stAppViewContainer"],
    body.cin-page-mode section.main,
    body.cin-page-mode .main,
    body.cin-page-mode .main > div,
    body.cin-page-mode .main .block-container,
    body.cin-page-mode [data-testid="stMain"],
    body.cin-page-mode [data-testid="stMainBlockContainer"],
    body.cin-page-mode [data-testid="stVerticalBlock"],
    body.cin-page-mode [data-testid="stHeader"] {{
        background-color: {LOGIN_MAIN_BG} !important;
        background-image: none !important;
    }}
    body.cin-page-mode section[data-testid="stSidebar"],
    body.cin-page-mode section[data-testid="stSidebar"] > div {{
        background: {LOGIN_SIDEBAR_GRAD} !important;
        background-image: {LOGIN_SIDEBAR_GRAD} !important;
    }}
    body.cin-page-mode .main .block-container {{
        max-width: 1100px !important;
        padding: 0.35rem 1rem 1.2rem !important;
        margin: 0 auto !important;
    }}
    body.cin-page-mode section[data-testid="stSidebar"] {{
        opacity: 1;
        filter: none;
        min-width: 27rem !important;
        width: 27rem !important;
        flex: 0 0 27rem !important;
    }}
    body.cin-page-mode section[data-testid="stSidebar"] > div {{
        width: 27rem !important;
        min-width: 27rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
    }}
    body.cin-page-mode [data-testid="stSidebarCollapsedControl"],
    body.cin-page-mode [data-testid="collapsedControl"] {{
        display: none;
    }}
    body.cin-page-mode section[data-testid="stSidebar"] [data-testid="stAlert"],
    body.cin-page-mode section[data-testid="stSidebar"] [data-baseweb="notification"] {{
        display: none !important;
    }}
    body.cin-page-mode [data-testid="stHtml"],
    body.cin-page-mode [data-testid="stHtml"] > div {{
        background: transparent !important;
        padding: 0 !important;
    }}
    body.cin-page-mode .cin-stage-wrap [data-testid="stHtml"] iframe {{
        width: 100% !important;
        min-height: 260px !important;
        height: 300px !important;
        max-height: 300px !important;
        border-radius: 18px !important;
        background: #03060c !important;
    }}
    body.cin-page-mode [data-testid="stHorizontalBlock"]:has([data-testid="stForm"]),
    body.cin-page-mode [data-testid="stHorizontalBlock"]:has(.auth-segment-control) {{
        opacity: 0;
        filter: blur(14px);
        transform: translateY(32px) scale(0.98);
        pointer-events: none;
        animation: authPanelReveal 1.6s cubic-bezier(0.22, 1, 0.36, 1) 10.5s forwards;
    }}
    body.cin-page-mode .auth-terminal-shell {{
        max-width: 520px;
        margin: 0 auto;
    }}
    body.cin-page-mode .auth-panel-glass {{
        border-radius: 16px;
        border: 1px solid rgba(148, 163, 184, 0.35);
        padding: 1rem 1.1rem 0.4rem;
        background: linear-gradient(165deg, rgba(8, 17, 32, 0.94) 0%, rgba(12, 28, 52, 0.88) 100%);
        box-shadow: 0 20px 44px rgba(5, 12, 28, 0.25);
        margin-bottom: 0.65rem;
    }}
    body.cin-page-mode .auth-panel-glass .auth-panel-title {{
        font-family: 'Playfair Display', serif;
        color: #f8fafc;
        font-size: 1.35rem;
        margin: 0 0 0.2rem 0;
    }}
    body.cin-page-mode .auth-panel-glass .auth-panel-sub {{
        color: #94a3b8;
        font-size: 0.84rem;
        margin-bottom: 0.5rem;
    }}
    body.cin-page-mode .auth-segment-control {{
        gap: 0.45rem !important;
        margin-bottom: 0.65rem !important;
    }}
    body.cin-page-mode .main .stButton > button {{
        background: #ffffff !important;
        color: #1e3a5f !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }}
    body.cin-page-mode .auth-segment-control button,
    body.cin-page-mode .main [data-testid="stHorizontalBlock"]:has(.auth-segment-control) button {{
        background: rgba(15, 23, 42, 0.7) !important;
        color: #cbd5e1 !important;
        border: 1px solid rgba(148, 163, 184, 0.35) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }}
    body.cin-page-mode .auth-segment-control button.auth-seg-active {{
        background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        border-color: #3b82f6 !important;
    }}
    body.cin-page-mode .main .cin-field-label {{
        color: #e2e8f0 !important;
        font-size: 0.82rem;
        font-weight: 600;
        margin: 0.35rem 0 0.2rem 0;
    }}
    body.cin-page-mode .main [data-testid="stTextInput"] input {{
        background: #f9fafb !important;
        color: #0f172a !important;
        border: 1.5px solid rgba(148, 163, 184, 0.45) !important;
        border-radius: 10px !important;
    }}
    body.cin-page-mode .main [data-testid="stFormSubmitButton"] button,
    body.cin-page-mode .main [data-testid="stForm"] .stButton > button {{
        background: linear-gradient(135deg, #1e40af 0%, #2563eb 100%) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 10px !important;
    }}
    .sidebar-note {{
        border: 1px solid rgba(147, 197, 253, 0.28);
        background: rgba(10, 24, 46, 0.35);
        border-radius: 12px;
        padding: 0.8rem;
        color: #dbeafe;
        font-size: 0.8rem;
        line-height: 1.45;
        margin-bottom: 0.65rem;
    }}
    section[data-testid="stSidebar"] .sidebar-features-wrap {{
        margin-top: 0.35rem;
        padding: 0.15rem 0.1rem 0.5rem 0;
        max-height: calc(100vh - 10rem);
        overflow-y: auto;
        scrollbar-width: thin;
    }}
    section[data-testid="stSidebar"] .sidebar-feature-card {{
        display: flex;
        gap: 0.6rem;
        align-items: flex-start;
        background: rgba(255, 255, 255, 0.06);
        border: 1px solid rgba(148, 163, 184, 0.2);
        border-left: 3px solid #3b82f6;
        border-radius: 10px;
        padding: 0.58rem 0.72rem;
        margin-bottom: 0.48rem;
    }}
    section[data-testid="stSidebar"] .sidebar-feature-title {{
        color: #f1f5f9;
        font-weight: 600;
        font-size: 0.84rem;
    }}
    section[data-testid="stSidebar"] .sidebar-feature-desc {{
        color: #c9d8f2;
        font-size: 0.74rem;
        line-height: 1.35;
    }}
    @keyframes authPanelReveal {{
        to {{
            opacity: 1;
            filter: blur(0);
            transform: translateY(0) scale(1);
            pointer-events: auto;
        }}
    }}
    </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_login_features() -> None:
    st.markdown('<div class="sidebar-features-wrap">', unsafe_allow_html=True)
    for icon, title, description in LOGIN_SIDEBAR_FEATURES:
        st.markdown(
            f"""
            <div class="sidebar-feature-card">
                <div class="sidebar-feature-icon">{icon}</div>
                <div>
                    <div class="sidebar-feature-title">{escape(title)}</div>
                    <div class="sidebar-feature-desc">{escape(description)}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _logo_data_uri(base_dir: Path) -> str:
    logo_path = base_dir / "assets" / "legalease_scales_logo.png"
    if not logo_path.exists():
        return ""
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _cinematic_login_scene_html(base_dir: Path) -> str:
    template_path = base_dir / "assets" / "cinematic_login_scene.html"
    if not template_path.exists():
        return "<html><body style='background:#03060c'></body></html>"
    html = template_path.read_text(encoding="utf-8", errors="replace")
    return html.replace("__LOGO_URI__", _logo_data_uri(base_dir))


def _sync_auth_segment_styles(auth_mode: str) -> None:
    mode = "login" if auth_mode == "login" else "register"
    st.markdown(
        f"""
        <script>
        (function () {{
          const mode = "{mode}";
          document.querySelectorAll('[data-testid="stHorizontalBlock"]').forEach((block) => {{
            const buttons = Array.from(block.querySelectorAll('button'));
            if (buttons.length !== 2) return;
            const text = buttons.map((b) => (b.innerText || "").trim().toLowerCase()).join("|");
            if (!text.includes("login") || !text.includes("register")) return;
            block.classList.add("auth-segment-control");
            buttons.forEach((btn) => {{
              const label = (btn.innerText || "").trim().toLowerCase();
              const active = (mode === "login" && label === "login") ||
                             (mode === "register" && label === "register");
              btn.classList.toggle("auth-seg-active", active);
            }});
          }});
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )


def render_cinematic_login(
    base_dir: Path,
    *,
    authenticate_user,
    create_user,
) -> None:
    if "auth_mode" not in st.session_state:
        st.session_state["auth_mode"] = "login"

    st.markdown(
        """
        <script>
        document.documentElement.classList.add('cin-page-mode', 'login-page-active');
        document.body.classList.add('cin-page-mode', 'login-page-active');
        </script>
        """,
        unsafe_allow_html=True,
    )

    _pad_l, cin_stage, _pad_r = st.columns([0.03, 0.94, 0.03])
    with cin_stage:
        st.markdown('<div class="cin-stage-wrap">', unsafe_allow_html=True)
        components.html(_cinematic_login_scene_html(base_dir), height=300, scrolling=False)
        st.markdown("</div>", unsafe_allow_html=True)

    _lp, auth_col, _rp = st.columns([0.08, 1.0, 0.08])
    with auth_col:
        st.markdown('<div class="auth-terminal-shell">', unsafe_allow_html=True)
        st.markdown(
            """
            <div class="auth-panel-glass">
                <div class="auth-panel-title">Intelligence Access Terminal</div>
                <div class="auth-panel-sub">Authenticate to enter the constitutional intelligence layer.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        seg1, seg2 = st.columns(2)
        with seg1:
            if st.button("Login", use_container_width=True, key="auth_seg_login"):
                st.session_state["auth_mode"] = "login"
                st.rerun()
        with seg2:
            if st.button("Register", use_container_width=True, key="auth_seg_register"):
                st.session_state["auth_mode"] = "register"
                st.rerun()
        _sync_auth_segment_styles(st.session_state.get("auth_mode", "login"))

        if st.session_state.get("auth_mode", "login") == "login":
            with st.form("login_form_cinematic"):
                st.markdown('<p class="cin-field-label">Username</p>', unsafe_allow_html=True)
                username = st.text_input(
                    "Username",
                    key="cin_login_user",
                    label_visibility="collapsed",
                    placeholder="Enter your username",
                )
                st.markdown('<p class="cin-field-label">Password</p>', unsafe_allow_html=True)
                password = st.text_input(
                    "Password",
                    type="password",
                    key="cin_login_pass",
                    label_visibility="collapsed",
                    placeholder="Enter your password",
                )
                if st.form_submit_button("Access Intelligence Layer", use_container_width=True):
                    user = authenticate_user(username, password)
                    if user:
                        st.session_state["user"] = user
                        st.success("Access granted. Opening workspace...")
                        st.rerun()
                    else:
                        st.error("Invalid credentials")
        else:
            with st.form("register_form_cinematic"):
                st.markdown('<p class="cin-field-label">Choose Username</p>', unsafe_allow_html=True)
                new_user = st.text_input(
                    "Choose Username",
                    key="cin_reg_user",
                    label_visibility="collapsed",
                    placeholder="Create a username",
                )
                st.markdown('<p class="cin-field-label">Password</p>', unsafe_allow_html=True)
                new_pass = st.text_input(
                    "Choose Password",
                    type="password",
                    key="cin_reg_pass",
                    label_visibility="collapsed",
                    placeholder="Create a password",
                )
                st.markdown('<p class="cin-field-label">Confirm Password</p>', unsafe_allow_html=True)
                confirm_pass = st.text_input(
                    "Confirm Password",
                    type="password",
                    key="cin_reg_confirm",
                    label_visibility="collapsed",
                    placeholder="Re-enter password",
                )
                if st.form_submit_button("Create Account", use_container_width=True):
                    if new_pass != confirm_pass:
                        st.error("Passwords don't match")
                    elif len(new_pass) < 6:
                        st.error("Password must be 6+ characters")
                    elif create_user(new_user, new_pass):
                        st.success("Account created. Please login.")
                    else:
                        st.error("Username already exists")
        st.markdown("</div>", unsafe_allow_html=True)
