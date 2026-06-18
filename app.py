"""
LegalEase.AI - Professional Legal AI Platform
==============================================
India's Most Advanced AI-Powered Legal Assistant

Features:
- Document Intelligence (RAG) with FAISS
- Live Legal Discovery (Web Search)
- Strategic Case Analyzer (Deep Analysis)
- Automated Legal Drafter
- Court Fee Calculator
- IPC-to-BNS Converter
- Contract Review & Analysis
- Case Outcome Prediction
- E-Discovery Tools
- Client Intake Automation
- Online Dispute Resolution
- Voice-to-Text Legal Dictation
- Smart Citator

Powered by: LM Studio (Local LLM) + HuggingFace Embeddings
"""

import os
import logging
import sqlite3
import uuid
import bcrypt
import re
import shutil
from html import escape
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent
load_dotenv(_PROJECT_ROOT / ".env")
if os.getenv("LEGALEEASE_LOCAL_DEV", "").lower() in ("1", "true", "yes") and (
    _PROJECT_ROOT / ".env.local"
).is_file():
    load_dotenv(_PROJECT_ROOT / ".env.local", override=True)
load_dotenv()

try:
    import streamlit as st
except ModuleNotFoundError:
    st = None
try:
    import pandas as pd
except ModuleNotFoundError:
    pd = None
try:
    import plotly.express as px
except ModuleNotFoundError:
    px = None
from PyPDF2 import PdfReader
from deep_translator import GoogleTranslator


def _utc_iso() -> str:
    """UTC timestamp for SQLite (timezone-aware, no deprecated utcnow())."""
    return datetime.now(timezone.utc).isoformat()


try:
    import streamlit as _st_for_cache  # alias so cache decorator works during module init
except ModuleNotFoundError:
    class _NoStreamlitCache:
        def cache_data(self, *args, **kwargs):
            def _deco(fn):
                return fn

            return _deco

    _st_for_cache = _NoStreamlitCache()


@_st_for_cache.cache_data(ttl=15, show_spinner=False)
def cached_generator_status() -> Dict[str, Any]:
    """
    Cached LM Studio status (15s TTL).

    Streamlit re-runs the script on every interaction; without caching the
    /v1/models probe would block the sidebar render every time. The Recheck
    button clears this cache.
    """
    from llms import generator_status as _gs
    return _gs()


# LegalEase.AI Modules
from llms import (
    DEFAULT_LM_STUDIO_URL,
    get_generator, search_web, generator_status, reset_generator, web_search_status,
    generate_legal_draft, analyze_contract, predict_case_outcome,
    check_citation_validity, process_voice_to_legal_text,
    client_intake_interview, generate_odr_resolution, extract_evidence_summary
)
from prompts import web_prompt, deepcase_prompt, NOT_FOUND_PHRASE
from rag import (
    query_kb,
    build_faiss_index as build_index_pipeline,
    append_documents_to_index,
    handle_legal_query,
    index_exists,
    retrieval_has_signal,
    get_last_query_error,
    get_last_query_diagnostics,
    diagnose_kb_health,
    ENTERPRISE_NOT_FOUND,
    NOT_FOUND_PHRASE as RAG_NOT_FOUND_PHRASE,
)
from legal_tools import (
    map_law_references, extract_timeline, extract_case_entities,
    convert_ipc_to_bns, bulk_ipc_to_bns_convert, get_bns_by_category,
)
from drafting import generate_draft, save_docx, get_available_templates, get_template_fields
from utils.court_fee import get_fee_breakdown, get_available_regions
from ocr_engine import extract_text_from_image_bytes, extract_text_with_ocr, ocr_status, should_run_ocr
try:
    from login_cinematic import (
        inject_login_cinematic_css,
        render_cinematic_login,
        render_sidebar_login_features,
    )
    from saas_chat import (
        inject_nuclear_layout_css,
        inject_chat_page_css,
        inject_chat_scroll_script,
        execute_new_chat,
        apply_session_prompt_bridge,
        queue_user_message,
        render_mode_pills,
        render_chat_viewport,
        render_input_dock,
        render_action_pills,
        render_chat_shell_start,
        render_chat_messages_zone_start,
        render_chat_messages_zone_end,
        render_chat_shell_end,
        suggest_follow_ups,
    )
except (ModuleNotFoundError, ImportError):

    def inject_nuclear_layout_css() -> None:
        pass

    def inject_chat_page_css() -> None:
        pass

    def inject_chat_scroll_script() -> None:
        pass

    def inject_login_cinematic_css(*_a, **_kw) -> None:
        pass

    def execute_new_chat() -> None:
        pass

    def apply_session_prompt_bridge() -> None:
        pass

    def queue_user_message(*_a, **_kw) -> None:
        pass

    def render_mode_pills(*_a, **_kw):
        return "knowledge_base"

    def render_chat_viewport(*_a, **_kw) -> None:
        pass

    def render_input_dock(*_a, **_kw):
        return ""

    def render_action_pills(*_a, **_kw) -> None:
        pass

    def render_chat_shell_start() -> None:
        pass

    def render_chat_messages_zone_start() -> None:
        pass

    def render_chat_messages_zone_end() -> None:
        pass

    def render_chat_shell_end() -> None:
        pass

    def render_cinematic_login(*_a, **_kw) -> None:
        pass

    def render_sidebar_login_features() -> None:
        pass

    def suggest_follow_ups(question: str, answer: str, mode: str) -> List[str]:
        from backend.app.services.follow_ups import suggest_follow_ups as _sf

        return _sf(question, answer, mode)

from kb_response_state import KB_NOT_FOUND_MESSAGE

# ---------------------------
# CONFIGURATION
# ---------------------------
BASE_DIR = _PROJECT_ROOT
DATA_DIR = BASE_DIR / "Data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
FAISS_BASE_DIR = BASE_DIR / "faiss_indexes"
FAISS_BASE_DIR.mkdir(parents=True, exist_ok=True)
DRAFT_DIR = BASE_DIR / "draft_outputs"
DRAFT_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = Path(os.getenv("LEGALEASE_DB_PATH", str(BASE_DIR / "legalease.db")))

# Model Configuration
EMBEDDING_MODEL = os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
LLM_BACKEND = os.getenv("LLM_BACKEND", "ollama")
LLM_MODEL = os.getenv("LM_STUDIO_MODEL") or os.getenv("LLM_MODEL", "meta-llama-3.1-8b-instruct")

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "200"))
RAG_MAX_CHUNK = int(os.getenv("RAG_MAX_CHUNK", "1400"))
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))
RAG_SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "1.6"))
RAG_DEBUG = os.getenv("RAG_DEBUG", "").lower() in {"1", "true", "yes"}

logger = logging.getLogger(__name__)
if RAG_DEBUG:
    logging.basicConfig(level=logging.DEBUG)


def _safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", value or "unknown")


def get_user_index_dir(user_id: str) -> Path:
    from backend.app.core.matter_index import get_user_index_dir as _matter_user_dir

    return _matter_user_dir(user_id)


def get_matter_index_dir(user_id: str, matter_id: str) -> Path:
    from backend.app.core.matter_index import get_matter_index_dir as _matter_dir

    return _matter_dir(user_id, matter_id)


def get_unlinked_index_dir(user_id: str) -> Path:
    from backend.app.core.matter_index import get_unlinked_index_dir as _unlinked_dir

    return _unlinked_dir(user_id)


def resolve_rag_index_dir(
    user_id: str,
    matter_id: Optional[str] = None,
    **kwargs,
) -> Path:
    from backend.app.core.matter_index import resolve_rag_index_dir as _resolve

    return _resolve(user_id, matter_id, **kwargs)


def get_scoped_document_count(user_id: str, matter_id: Optional[str] = None) -> int:
    mid = (matter_id or "").strip()
    if mid:
        row = run_query(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ? AND matter_id = ?",
            (user_id, mid),
            fetch=True,
        )
    else:
        row = run_query(
            "SELECT COUNT(*) FROM documents WHERE uploader_id = ? AND COALESCE(matter_id, '') = ''",
            (user_id,),
            fetch=True,
        )
    return int(row[0][0]) if row else 0


def get_kb_status_id(user_id: Optional[str]) -> str:
    return f"kb_status_{_safe_id(user_id)}" if user_id else "kb_status_1"


_ALLOWED_UPLOAD_EXT = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"
}


def sanitize_filename(filename: str, *, default_ext: str = ".pdf") -> str:
    """Keep real extension for PDFs and images (do not force everything to .pdf)."""
    name = Path(filename or "").name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    ext = Path(name).suffix.lower()
    if ext not in _ALLOWED_UPLOAD_EXT:
        ext = default_ext if default_ext in _ALLOWED_UPLOAD_EXT else ".pdf"
        stem = Path(name).stem[:100].strip(" .") if name else "document"
        name = f"{stem or 'document'}{ext}"
    else:
        stem = Path(name).stem[:100].strip(" .") or "document"
        name = f"{stem}{ext}"
    return name


def html_text(text: Any) -> str:
    return escape(str(text or "")).replace("\n", "<br>")

# ---------------------------
# PAGE CONFIG (Streamlit UI only — API Docker image has no Streamlit)
# ---------------------------
if st is not None:
    st.set_page_config(
        page_title="LegalEase.AI - Legal Intelligence Platform",
        page_icon="⚖️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

# ---------------------------
# PROFESSIONAL CSS THEME
# ---------------------------
def load_custom_css(*, chat_active: bool = False, guest_login: bool = False):
    """Global theme; chat page uses inject_chat_page_css() — skip conflicting layout rules."""
    if chat_active:
        st.markdown("""
        <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header {visibility: hidden;}
        section[data-testid="stSidebar"] > div {
            background: linear-gradient(180deg, #0f172a 0%, #1e293b 100%) !important;
            padding-top: 0.65rem !important;
        }
        </style>
        """, unsafe_allow_html=True)
        return
    st.markdown("""
    <style>
    /* Import Professional Fonts */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Playfair+Display:wght@600;700&display=swap');
    
    /* Hide Streamlit Branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    
    /* Root Variables */
    :root {
        --primary-navy: #0f172a;
        --secondary-navy: #1e293b;
        --accent-gold: #f59e0b;
        --accent-blue: #3b82f6;
        --text-light: #f8fafc;
        --text-dark: #1e293b;
        --success: #10b981;
        --warning: #f59e0b;
        --error: #ef4444;
        --gradient-primary: linear-gradient(135deg, #1e40af 0%, #3b82f6 50%, #f59e0b 100%);
    }
    
    /* Sidebar Styling */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div {
        background: linear-gradient(180deg, var(--primary-navy) 0%, var(--secondary-navy) 100%) !important;
        background-image: linear-gradient(180deg, var(--primary-navy) 0%, var(--secondary-navy) 100%) !important;
        padding-top: 1rem;
    }
    
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {
        color: var(--text-light) !important;
    }
    
    section[data-testid="stSidebar"] .stRadio label {
        color: var(--text-light) !important;
        padding: 0.75rem 1rem;
        border-radius: 10px;
        transition: all 0.3s ease;
        margin: 0.25rem 0;
        display: block;
    }
    
    section[data-testid="stSidebar"] .stRadio label:hover {
        background: rgba(59, 130, 246, 0.2);
        transform: translateX(5px);
    }
    
    /* Main Container */
    .main .block-container {
        padding: 2rem 3rem;
        max-width: 1400px;
        background: linear-gradient(135deg, #f8fafc 0%, #eef1f6 100%);
    }
    
    /* Headers */
    h1 {
        font-family: 'Playfair Display', serif !important;
        background: var(--gradient-primary);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        background-clip: text;
        font-weight: 700;
        margin-bottom: 1.5rem;
    }
    
    h2, h3 {
        font-family: 'Inter', sans-serif !important;
        color: var(--primary-navy);
        font-weight: 600;
    }
    
    /* Professional Cards */
    .pro-card {
        background: white;
        border-radius: 16px;
        padding: 1.5rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.08);
        border: 1px solid #e2e8f0;
        transition: all 0.3s ease;
        margin-bottom: 1rem;
    }
    
    .pro-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 30px rgba(0,0,0,0.12);
    }
    
    /* Feature Cards */
    .feature-card {
        background: linear-gradient(135deg, white 0%, #f8fafc 100%);
        border-radius: 16px;
        padding: 1.5rem;
        border-left: 4px solid var(--accent-gold);
        box-shadow: 0 2px 15px rgba(0,0,0,0.05);
        transition: all 0.3s ease;
        cursor: pointer;
    }
    
    .feature-card:hover {
        transform: scale(1.02);
        border-left-color: var(--accent-blue);
        box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);
    }
    
    .feature-icon {
        font-size: 2rem;
        margin-bottom: 0.5rem;
    }
    
    .feature-title {
        font-weight: 600;
        color: var(--primary-navy);
        margin-bottom: 0.25rem;
    }
    
    .feature-desc {
        font-size: 0.85rem;
        color: #64748b;
    }
    
    /* Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, var(--primary-navy) 0%, var(--accent-blue) 100%);
        color: white;
        padding: 1.5rem;
        border-radius: 16px;
        text-align: center;
        box-shadow: 0 4px 20px rgba(30, 64, 175, 0.3);
    }
    
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
    }
    
    .metric-label {
        font-size: 0.9rem;
        opacity: 0.9;
    }
    
    /* Chat Messages */
    .user-message {
        background: linear-gradient(135deg, var(--primary-navy) 0%, var(--accent-blue) 100%);
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 18px 18px 4px 18px;
        margin: 0.75rem 0;
        max-width: 85%;
        margin-left: auto;
        box-shadow: 0 4px 15px rgba(30, 64, 175, 0.3);
        animation: slideInRight 0.3s ease;
    }
    
    .ai-message {
        background: white;
        color: var(--text-dark);
        padding: 1rem 1.5rem;
        border-radius: 18px 18px 18px 4px;
        margin: 0.75rem 0;
        max-width: 85%;
        border-left: 4px solid var(--accent-gold);
        box-shadow: 0 2px 10px rgba(0,0,0,0.08);
        animation: slideInLeft 0.3s ease;
    }

    /* Premium legal chat workspace */
    .main .block-container {
        background: linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%) !important;
    }
    div[data-testid="stChatMessage"] {
        border: 1px solid rgba(15, 23, 42, 0.08);
        border-radius: 16px;
        box-shadow: 0 8px 24px rgba(15, 23, 42, 0.06);
        padding: 0.85rem 1rem;
        margin-bottom: 0.85rem;
        max-width: 920px;
    }
    div[data-testid="stChatMessage"][data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 100%);
        margin-left: auto;
        border: none;
    }
    div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) [data-testid="stMarkdownContainer"] {
        color: #f8fafc !important;
    }
    div[data-testid="stChatMessage"]:not(:has([data-testid="chatAvatarIcon-user"])) {
        background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
        border-left: 4px solid #c9a227;
    }
    div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] {
        font-family: 'Inter', sans-serif;
        line-height: 1.62;
        color: #0f172a;
        font-size: 0.95rem;
    }
    div[data-testid="stChatMessage"] h3 {
        font-family: 'Playfair Display', serif;
        color: #0b1f3a;
        margin-top: 0.6rem;
    }
    div[data-testid="stChatMessage"] table {
        border-collapse: collapse;
        width: 100%;
        font-size: 0.9rem;
        margin: 0.5rem 0;
    }
    div[data-testid="stChatMessage"] table th,
    div[data-testid="stChatMessage"] table td {
        border: 1px solid #dbe4f0;
        padding: 0.55rem 0.65rem;
    }
    div[data-testid="stChatMessage"] table th {
        background: #0b1f3a;
        color: #f8fafc;
    }
    div[data-testid="stChatInput"] > div {
        border: 1px solid rgba(15, 23, 42, 0.12);
        border-radius: 16px;
        background: #ffffff;
        box-shadow: 0 4px 18px rgba(15, 23, 42, 0.08);
    }
    div[data-testid="stChatInput"] textarea {
        font-size: 0.95rem !important;
    }
    .mode-pill {
        display: inline-block;
        padding: 0.35rem 0.75rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 600;
        margin-right: 0.35rem;
        border: 1px solid rgba(15, 23, 42, 0.12);
        background: #fff;
    }
    
    @keyframes slideInRight {
        from { opacity: 0; transform: translateX(20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    
    @keyframes slideInLeft {
        from { opacity: 0; transform: translateX(-20px); }
        to { opacity: 1; transform: translateX(0); }
    }
    
    /* Buttons (default: professional navy, not orange) */
    .stButton > button {
        background: #ffffff;
        color: #1e3a5f;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 0.6rem 1.25rem;
        font-weight: 500;
        font-family: 'Inter', sans-serif;
        transition: all 0.2s ease;
        box-shadow: none;
    }
    
    .stButton > button:hover {
        background: #f1f5f9;
        border-color: #94a3b8;
        transform: none;
    }
    .stButton > button[kind="primary"],
    button[data-testid="baseButton-primary"] {
        background: #1e3a5f !important;
        color: #fff !important;
        border-color: #1e3a5f !important;
    }
    
    /* Secondary Button */
    .secondary-btn > button {
        background: white !important;
        color: var(--primary-navy) !important;
        border: 2px solid var(--primary-navy) !important;
    }
    
    /* Input Fields */
    .stTextInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stSelectbox > div > div {
        border-radius: 10px;
        border: 2px solid #e2e8f0;
        font-family: 'Inter', sans-serif;
        transition: all 0.3s ease;
    }
    
    .stTextInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus {
        border-color: var(--accent-blue);
        box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background: #f1f5f9;
        padding: 0.5rem;
        border-radius: 12px;
    }
    
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 0.75rem 1.5rem;
        font-weight: 500;
    }
    
    .stTabs [aria-selected="true"] {
        background: white !important;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: #f8fafc;
        border-radius: 10px;
        font-weight: 500;
    }
    
    /* Status Badges */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    
    .status-success {
        background: #d1fae5;
        color: #059669;
    }
    
    .status-warning {
        background: #fef3c7;
        color: #d97706;
    }
    
    .status-error {
        background: #fee2e2;
        color: #dc2626;
    }
    
    /* Tool Grid */
    .tool-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 1rem;
        margin: 1rem 0;
    }
    
    /* Progress Animation */
    .stProgress > div > div > div {
        background: linear-gradient(90deg, var(--accent-gold), var(--accent-blue), var(--accent-gold));
        background-size: 200% 100%;
        animation: progressShine 2s linear infinite;
    }
    
    @keyframes progressShine {
        0% { background-position: 200% 0; }
        100% { background-position: -200% 0; }
    }
    
    /* Scrollbar */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #f1f5f9;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #94a3b8;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #64748b;
    }
    
    /* Logo Animation */
    .logo-container {
        text-align: center;
        padding: 1rem 0;
    }
    
    .logo-text {
        font-family: 'Playfair Display', serif;
        font-size: 1.8rem;
        font-weight: 700;
        background: linear-gradient(135deg, #f59e0b 0%, #ffffff 50%, #3b82f6 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    
    .logo-tagline {
        font-size: 0.75rem;
        color: #94a3b8;
        margin-top: 0.25rem;
    }
    </style>
    """, unsafe_allow_html=True)
    if guest_login:
        st.markdown(
            """
    <style>
    /* Guest login — lock left panel deep blue, white brand text */
    section[data-testid="stSidebar"],
    section[data-testid="stSidebar"] > div,
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"],
    section[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
        background: linear-gradient(180deg, #0b1f3a 0%, #102a4d 65%, #183e70 100%) !important;
        background-image: linear-gradient(180deg, #0b1f3a 0%, #102a4d 65%, #183e70 100%) !important;
    }
    section[data-testid="stSidebar"] .logo-text {
        background: none !important;
        -webkit-background-clip: unset !important;
        -webkit-text-fill-color: #f8fafc !important;
        color: #f8fafc !important;
    }
    section[data-testid="stSidebar"] .sidebar-feature-card {
        border-left-color: #3b82f6 !important;
        border-color: rgba(148, 163, 184, 0.22) !important;
    }
    section[data-testid="stSidebar"] hr {
        border-color: rgba(148, 163, 184, 0.25) !important;
    }
    </style>
            """,
            unsafe_allow_html=True,
        )


# ---------------------------
# DATABASE FUNCTIONS
# ---------------------------
def init_db():
    """Initialize database with all required tables"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    
    # Users table
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        password_hash BLOB NOT NULL,
        membership TEXT NOT NULL DEFAULT 'Free',
        role TEXT NOT NULL DEFAULT 'user',
        created_at TEXT NOT NULL
    )""")
    
    # Documents table
    c.execute("""CREATE TABLE IF NOT EXISTS documents (
        id TEXT PRIMARY KEY,
        uploader_id TEXT NOT NULL,
        filename TEXT NOT NULL,
        saved_path TEXT NOT NULL,
        pages INTEGER NOT NULL,
        uploaded_at TEXT NOT NULL,
        FOREIGN KEY (uploader_id) REFERENCES users(id)
    )""")
    
    # Case Entities table
    c.execute("""CREATE TABLE IF NOT EXISTS case_entities (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        plaintiff TEXT,
        defendant TEXT,
        judge TEXT,
        court TEXT,
        case_number TEXT,
        sections TEXT,
        dates TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )""")
    
    # Timeline table
    c.execute("""CREATE TABLE IF NOT EXISTS document_timeline (
        id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL,
        event_date TEXT NOT NULL,
        mention_text TEXT,
        page INTEGER,
        source_filename TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (document_id) REFERENCES documents(id)
    )""")
    
    # ChatHistory table
    c.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        language TEXT NOT NULL DEFAULT 'English',
        mode TEXT NOT NULL DEFAULT 'knowledge_base',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")

    # Chat feedback table (like/dislike + optional regeneration notes)
    c.execute("""CREATE TABLE IF NOT EXISTS chat_feedback (
        id TEXT PRIMARY KEY,
        chat_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        rating TEXT NOT NULL,
        comment TEXT,
        created_at TEXT NOT NULL,
        UNIQUE(chat_id, user_id),
        FOREIGN KEY (chat_id) REFERENCES chat_history(id),
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    
    # Knowledge base status table
    c.execute("""CREATE TABLE IF NOT EXISTS knowledge_base_status (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        total_documents INTEGER NOT NULL,
        total_chunks INTEGER NOT NULL,
        last_updated TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    
    # Payments table
    c.execute("""CREATE TABLE IF NOT EXISTS payments (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        plan TEXT NOT NULL,
        amount REAL NOT NULL,
        payment_status TEXT NOT NULL,
        payment_id TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    
    # Team members table
    c.execute("""CREATE TABLE IF NOT EXISTS team_members (
        id TEXT PRIMARY KEY,
        team_owner_id TEXT NOT NULL,
        member_user_id TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'member',
        created_at TEXT NOT NULL,
        FOREIGN KEY (team_owner_id) REFERENCES users(id),
        FOREIGN KEY (member_user_id) REFERENCES users(id)
    )""")
    
    # Logs table
    c.execute("""CREATE TABLE IF NOT EXISTS logs (
        id TEXT PRIMARY KEY,
        user_id TEXT,
        action TEXT NOT NULL,
        detail TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    
    # Drafts table
    c.execute("""CREATE TABLE IF NOT EXISTS drafts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        draft_type TEXT NOT NULL,
        content TEXT NOT NULL,
        file_path TEXT,
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    
    # Contracts table
    c.execute("""CREATE TABLE IF NOT EXISTS contracts (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        contract_name TEXT NOT NULL,
        status TEXT DEFAULT 'draft',
        content TEXT,
        analysis TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )""")
    
    conn.commit()
    _migrate_chat_thread_column(conn)
    conn.close()
    try:
        from backend.app.core.schema_migrations import apply_migrations

        apply_migrations()
    except Exception:
        pass
    try:
        from backend.app.core.practice_schema import ensure_practice_schema

        ensure_practice_schema()
    except Exception:
        pass


def _migrate_chat_thread_column(conn=None) -> None:
    """Add thread_id to chat_history so multi-turn chats can be reopened."""
    own = conn is None
    if own:
        conn = sqlite3.connect(DB_PATH, timeout=30)
    try:
        c = conn.cursor()
        cols = {row[1] for row in c.execute("PRAGMA table_info(chat_history)").fetchall()}
        if "thread_id" not in cols:
            c.execute("ALTER TABLE chat_history ADD COLUMN thread_id TEXT")
            c.execute("UPDATE chat_history SET thread_id = id WHERE thread_id IS NULL OR thread_id = ''")
            conn.commit()
    finally:
        if own:
            conn.close()


def run_query(query, params=(), fetch=False):
    """Execute database query"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA foreign_keys = ON")
    c = conn.cursor()
    c.execute(query, params)
    if fetch:
        rows = c.fetchall()
        conn.close()
        return rows
    conn.commit()
    conn.close()
    return None

# ---------------------------
# AUTHENTICATION
# ---------------------------
def hash_password(password: str) -> bytes:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

def verify_password(password: str, pw_hash: bytes) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), pw_hash)
    except Exception:
        return False

def create_user(username: str, password: str, membership: str = "Free", role: str = "user") -> bool:
    username = (username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{3,64}", username):
        return False
    user_id = str(uuid.uuid4())
    pw_hash = hash_password(password)
    try:
        run_query(
            "INSERT INTO users (id, username, password_hash, membership, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, username, pw_hash, membership, role, _utc_iso())
        )
        log_action(user_id, "create_user", f"membership={membership}")
        return True
    except sqlite3.IntegrityError:
        return False

def authenticate_user(username: str, password: str) -> Optional[Dict]:
    res = run_query(
        "SELECT id, username, password_hash, membership, role FROM users WHERE username = ?",
        (username,),
        fetch=True
    )
    if not res:
        return None
    user_id, username, pw_hash, membership, role = res[0]
    if verify_password(password, pw_hash):
        log_action(user_id, "login", "User logged in")
        return {"id": user_id, "username": username, "membership": membership, "role": role}
    return None

def upgrade_user_membership(user_id: str, new_membership: str) -> bool:
    try:
        run_query("UPDATE users SET membership = ? WHERE id = ?", (new_membership, user_id))
        log_action(user_id, "upgrade_membership", f"to={new_membership}")
        return True
    except Exception:
        return False

def log_action(user_id: Optional[str], action: str, detail: str = ""):
    run_query(
        "INSERT INTO logs (id, user_id, action, detail, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id or "system", action, detail, _utc_iso())
    )

# ---------------------------
# DOCUMENT MANAGEMENT
# ---------------------------
def get_user_document_count(user_id: str) -> int:
    result = run_query("SELECT COUNT(*) FROM documents WHERE uploader_id = ?", (user_id,), fetch=True)
    return result[0][0] if result else 0

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}


def _file_content_hash(file_buffer: bytes) -> str:
    import hashlib

    return hashlib.sha256(file_buffer).hexdigest()


def find_existing_document(uploader_id: str, content_hash: str) -> Optional[tuple]:
    """Return (file_id, saved_path, pages) if this exact file was already uploaded."""
    if not content_hash:
        return None
    row = run_query(
        """
        SELECT id, saved_path, pages FROM documents
        WHERE uploader_id = ? AND content_hash = ?
        ORDER BY uploaded_at DESC LIMIT 1
        """,
        (uploader_id, content_hash),
        fetch=True,
    )
    if not row:
        return None
    return row[0][0], row[0][1], row[0][2]


def prune_duplicate_documents(user_id: str) -> int:
    """Remove duplicate rows (same content), keeping the newest upload."""
    import hashlib

    rows = run_query(
        """
        SELECT id, filename, saved_path, content_hash, uploaded_at FROM documents
        WHERE uploader_id = ? ORDER BY uploaded_at DESC
        """,
        (user_id,),
        fetch=True,
    ) or []
    seen: dict = {}
    to_delete: list = []
    for doc_id, filename, saved_path, db_hash, _uploaded_at in rows:
        content_hash = (db_hash or "").strip()
        if not content_hash:
            try:
                p = Path(str(saved_path))
                if p.is_file():
                    content_hash = hashlib.sha256(p.read_bytes()).hexdigest()
                    run_query(
                        "UPDATE documents SET content_hash = ? WHERE id = ?",
                        (content_hash, doc_id),
                    )
            except Exception:
                content_hash = f"{filename}:{saved_path}"
        if content_hash in seen:
            to_delete.append(str(doc_id))
        else:
            seen[content_hash] = str(doc_id)
    removed = 0
    for doc_id in to_delete:
        if delete_user_document(doc_id, user_id):
            removed += 1
    return removed


def save_uploaded_pdf(uploaded_file, uploader_id: str, matter_id: str = ""):
    from backend.app.core.document_upload import infer_ext_from_bytes

    file_buffer = uploaded_file.getbuffer()
    if isinstance(file_buffer, memoryview):
        file_buffer = bytes(file_buffer)
    elif not isinstance(file_buffer, (bytes, bytearray)):
        file_buffer = bytes(file_buffer)

    default_ext = infer_ext_from_bytes(file_buffer, getattr(uploaded_file, "name", "") or "")
    display_name = sanitize_filename(uploaded_file.name, default_ext=default_ext)

    size_mb = len(file_buffer) / (1024 * 1024)
    if size_mb > MAX_UPLOAD_MB:
        raise ValueError(f"{display_name} is {size_mb:.1f} MB. Max upload size is {MAX_UPLOAD_MB} MB.")

    content_hash = _file_content_hash(file_buffer)
    existing = find_existing_document(uploader_id, content_hash)
    if existing:
        if len(existing) >= 3:
            file_id, save_path, pages = existing[0], existing[1], existing[2]
        elif len(existing) == 2:
            file_id, save_path = existing[0], existing[1]
            pages = 0
        else:
            file_id, save_path, pages = existing[0], "", 0
        log_action(uploader_id, "upload_pdf_duplicate_skipped", display_name)
        return str(file_id), Path(str(save_path)), int(pages or 0), True

    ext = Path(display_name).suffix.lower()
    safe_name = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}_{display_name}"
    file_id = str(uuid.uuid4())
    save_path = DATA_DIR / safe_name

    with open(save_path, "wb") as f:
        f.write(file_buffer)

    pages = 0
    if ext == ".pdf":
        try:
            reader = PdfReader(str(save_path))
            pages = len(reader.pages)
        except Exception:
            pages = 0
    elif ext in _IMAGE_EXT:
        pages = 1

    linked_mid = (matter_id or "").strip()
    org_id = ""
    if linked_mid:
        try:
            rows = run_query(
                "SELECT COALESCE(org_id, '') FROM matters WHERE matter_id = ? LIMIT 1",
                (linked_mid,),
                fetch=True,
            )
            if rows and rows[0][0]:
                org_id = str(rows[0][0])
        except Exception:
            pass
    if not org_id:
        try:
            from backend.app.core.org_service import get_primary_org_id

            org_id = get_primary_org_id(str(uploader_id)) or ""
        except Exception:
            pass
    run_query(
        """
        INSERT INTO documents
        (id, uploader_id, filename, saved_path, pages, uploaded_at, content_hash, matter_id, org_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            file_id,
            uploader_id,
            display_name,
            str(save_path),
            pages,
            _utc_iso(),
            content_hash,
            linked_mid,
            org_id,
        ),
    )
    log_action(uploader_id, "upload_pdf", display_name)
    return file_id, save_path, pages, False

def _extract_cache_path(path: Path, use_ocr: bool) -> Path:
    tag = "ocr" if use_ocr else "native"
    return path.parent / f"{path.stem}.{tag}.extracted.txt"


def extract_text_from_file(path: Path, use_ocr: Optional[bool] = None) -> str:
    """PDF native + sparse OCR; images via EasyOCR."""
    path = Path(path)
    raw = path.read_bytes()
    is_image = path.suffix.lower() in _IMAGE_EXT
    if not is_image and len(raw) >= 4:
        if raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:3] == b"\xff\xd8\xff":
            is_image = True
    if is_image:
        from backend.app.core.document_upload import extract_image_text

        return extract_image_text(path, raw)

    from backend.app.core.pdf_index_quality import (
        invalidate_extraction_cache,
        is_weak_extraction,
        pdf_page_count,
    )

    page_count = pdf_page_count(path) if path.suffix.lower() == ".pdf" else 0

    def _read_cache_if_valid(cache_path: Path) -> str:
        try:
            if not cache_path.exists() or cache_path.stat().st_mtime < path.stat().st_mtime:
                return ""
            cached = cache_path.read_text(encoding="utf-8", errors="replace")
            if is_weak_extraction(cached, page_count):
                logger.warning(
                    "[PDF] Weak cached extraction for %s (%s chars, %s pages) — re-extracting",
                    path.name,
                    len(cached.strip()),
                    page_count,
                )
                invalidate_extraction_cache(path)
                return ""
            try:
                from kb_preprocess import clean_legal_text

                return clean_legal_text(cached)
            except Exception:
                return cached.strip()
        except OSError:
            return ""

    force = use_ocr is True
    cache_tag = "ocr" if force else "auto"
    cache = _extract_cache_path(path, force) if use_ocr is not None else path.parent / f"{path.stem}.{cache_tag}.extracted.txt"
    if use_ocr is None:
        for tag in ("auto", "native", "ocr"):
            c = path.parent / f"{path.stem}.{tag}.extracted.txt"
            hit = _read_cache_if_valid(c)
            if hit:
                logger.info("[PDF] cache hit %s | chars=%s", path.name, len(hit))
                return hit
    else:
        hit = _read_cache_if_valid(cache)
        if hit:
            return hit

    method = "unknown"
    try:
        from backend.app.core.pdf_extraction import extract_pdf_production

        text, method = extract_pdf_production(
            path,
            force_ocr=force,
            allow_ocr=use_ocr is not False,
        )
    except Exception as exc:
        logger.warning("pdf_extraction failed, legacy fallback: %s", exc)
        from backend.app.core.ocr_router import extract_text_routed

        text, method = extract_text_routed(path)

    try:
        from kb_preprocess import clean_legal_text

        text = clean_legal_text(text or "")
    except Exception:
        text = (text or "").strip()

    logger.info("[PDF] %s | method=%s | chars=%s", path.name, method, len(text))
    try:
        out_cache = path.parent / f"{path.stem}.auto.extracted.txt"
        out_cache.write_text(text, encoding="utf-8")
    except OSError:
        pass
    return text

def _infer_matter_id_for_docs(user_id: str, only_doc_ids: Optional[List[str]]) -> str:
    if not only_doc_ids:
        return ""
    row = run_query(
        "SELECT matter_id FROM documents WHERE uploader_id = ? AND id = ?",
        (user_id, str(only_doc_ids[0])),
        fetch=True,
    )
    if not row:
        return ""
    return str(row[0][0] or "").strip()


def _build_faiss_index_scoped(
    user_id: str,
    progress_callback=None,
    *,
    only_doc_ids: Optional[List[str]] = None,
    use_ocr: Optional[bool] = None,
    enrich_metadata: bool = False,
    incremental: bool = False,
    matter_id: str = "",
):
    """Build FAISS for one scope: a matter_id or unlinked (empty matter_id)."""
    mid = (matter_id or "").strip()
    if mid:
        from backend.app.core.matter_repo import get_matter

        if not get_matter(user_id, mid):
            return False, "Matter not found.", 0
        index_dir = get_matter_index_dir(user_id, mid)
        rows = run_query(
            "SELECT id, filename, saved_path FROM documents WHERE uploader_id = ? AND matter_id = ?",
            (user_id, mid),
            fetch=True,
        )
        scope_label = f"matter {mid[:8]}"
    else:
        from backend.app.core.matter_index import get_global_kb_write_dir

        index_dir = get_global_kb_write_dir(user_id)
        rows = run_query(
            """
            SELECT id, filename, saved_path FROM documents
            WHERE uploader_id = ? AND COALESCE(matter_id, '') = ''
            """,
            (user_id,),
            fetch=True,
        )
        scope_label = "unlinked documents"

    # region agent log
    try:
        from backend.app.core.debug_matter_index_log import matter_index_log

        matter_index_log(
            "H2",
            "app.py:_build_faiss_index_scoped:entry",
            "scope_resolved",
            {
                "matter_id": mid,
                "scope_label": scope_label,
                "index_dir": str(index_dir),
                "row_count": len(rows or []),
                "only_doc_ids": list(only_doc_ids or [])[:5],
                "incremental": bool(incremental),
            },
        )
    except Exception:
        pass
    # endregion

    if only_doc_ids:
        only_set = {str(d) for d in only_doc_ids}
        rows = [r for r in (rows or []) if str(r[0]) in only_set]

    if not rows:
        # #region agent log
        try:
            import json
            import time

            with open(Path(__file__).resolve().parent / "debug-cf6ca9.log", "a", encoding="utf-8") as lf:
                lf.write(
                    json.dumps(
                        {
                            "sessionId": "cf6ca9",
                            "runId": "upload-debug",
                            "hypothesisId": "H1",
                            "location": "app.py:_build_faiss_index_scoped",
                            "message": "no_rows_in_scope",
                            "data": {
                                "matter_id": mid,
                                "only_doc_ids": list(only_doc_ids or [])[:3],
                                "scope_label": scope_label,
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # #endregion
        if index_dir.exists() and (index_dir / "index.faiss").exists():
            for name in ("index.faiss", "index.pkl"):
                p = index_dir / name
                if p.exists():
                    p.unlink()
        return False, f"No documents in scope ({scope_label}).", 0

    documents = []
    for idx, row in enumerate(rows, start=1):
        doc_id = row[0]
        filename = str(row[1]) if row[1] is not None else "document.pdf"
        saved_path = str(row[2]) if row[2] is not None else ""
        if progress_callback:
            progress_callback(f"[{scope_label}] {filename} ({idx}/{len(rows)})...")
        if not saved_path:
            continue
        try:
            text = extract_text_from_file(Path(saved_path), use_ocr=use_ocr)
        except ValueError as exc:
            logger.warning("Extract failed for %s: %s", filename, exc)
            if only_doc_ids and len(rows) == 1:
                return False, str(exc), 0
            continue
        if text.strip():
            try:
                from backend.app.core.pdf_index_quality import extraction_report, is_weak_extraction

                pages_db = 0
                try:
                    prow = run_query(
                        "SELECT pages FROM documents WHERE id = ?",
                        (doc_id,),
                        fetch=True,
                    )
                    if prow and prow[0][0]:
                        pages_db = int(prow[0][0])
                except Exception:
                    pass
                rep = extraction_report(text, pages_db, filename=filename)
                if is_weak_extraction(text, pages_db):
                    logger.error(
                        "[INDEX] Weak PDF text for %s — %s chars, %s pages (need re-extract/OCR)",
                        filename,
                        rep["char_count"],
                        rep["page_count"],
                    )
                    if only_doc_ids and len(rows) == 1:
                        return (
                            False,
                            f"PDF text extraction too weak for {filename} "
                            f"({rep['char_count']} chars / {rep['page_count']} pages). "
                            "Use Re-index with OCR enabled.",
                            0,
                        )
                    continue
                logger.info(
                    "[INDEX] %s | chars=%s pages=%s expected_chunks>=%s",
                    filename,
                    rep["char_count"],
                    rep["page_count"],
                    rep["expected_min_chunks"],
                )
            except Exception:
                pass
            documents.append({"doc_id": doc_id, "filename": filename, "text": text})
            try:
                from document_classifier import classify_document, is_contract_family
                from contract_entity_extractor import extract_contract_entities
                from backend.app.core.document_entities import save_document_entities

                doc_type = classify_document(text, filename)
                if is_contract_family(doc_type):
                    entities = extract_contract_entities(text, doc_type)
                    save_document_entities(user_id, doc_id, filename, doc_type, entities)
            except Exception as exc:
                logger.debug("Contract entity index skipped for %s: %s", filename, exc)
            if not enrich_metadata:
                continue
            try:
                entities = extract_case_entities(text)
                run_query("DELETE FROM case_entities WHERE document_id = ?", (doc_id,))
                run_query(
                    "INSERT OR REPLACE INTO case_entities (id, document_id, plaintiff, defendant, judge, court, case_number, sections, dates, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), doc_id, entities.get("plaintiff"), entities.get("defendant"),
                     entities.get("judge"), entities.get("court"), entities.get("case_number"),
                     ", ".join(entities.get("sections", [])), ", ".join(entities.get("dates", [])),
                     _utc_iso())
                )
                events = extract_timeline(text, filename)
                run_query("DELETE FROM document_timeline WHERE document_id = ?", (doc_id,))
                for ev in events:
                    run_query(
                        "INSERT INTO document_timeline (id, document_id, event_date, mention_text, page, source_filename, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), doc_id, ev.get("date"), ev.get("mention_text"),
                         ev.get("page", 0), ev.get("source_filename"), _utc_iso())
                    )
            except Exception:
                pass

    if not documents:
        return False, f"No extractable text for {scope_label}.", 0

    use_append = bool(only_doc_ids) and (incremental or index_exists(index_dir))
    if use_append and index_exists(index_dir):
        ok, msg, added = append_documents_to_index(
            documents,
            progress_callback=progress_callback,
            index_dir=index_dir,
        )
        total_chunks = added if ok else 0
    else:
        ok, msg, total_chunks = build_index_pipeline(
            documents,
            progress_callback=progress_callback,
            index_dir=index_dir,
        )

    chunk_total = 0
    if ok:
        try:
            from rag import count_index_vectors

            chunk_total = count_index_vectors(index_dir)
        except Exception:
            chunk_total = int(total_chunks or 0)

    # region agent log
    try:
        from backend.app.core.debug_matter_index_log import matter_index_log
        from backend.app.core.faiss_index_stats import index_exists

        matter_index_log(
            "H3",
            "app.py:_build_faiss_index_scoped:exit",
            "index_build_complete",
            {
                "matter_id": mid,
                "index_dir": str(index_dir),
                "ok": bool(ok),
                "chunk_total": int(chunk_total or 0),
                "index_exists": bool(index_exists(index_dir)),
                "msg": str(msg or "")[:200],
                "documents_built": len(documents),
            },
        )
    except Exception:
        pass
    # endregion

    return ok, f"{scope_label}: {msg} ({chunk_total} chunks)", chunk_total


def build_faiss_index(
    user_id: str,
    progress_callback=None,
    *,
    only_doc_ids: Optional[List[str]] = None,
    use_ocr: Optional[bool] = None,
    enrich_metadata: bool = False,
    incremental: bool = False,
    matter_id: Optional[str] = None,
    rebuild_all: bool = False,
):
    from backend.app.core.matter_index import list_matters_with_documents

    status_id = get_kb_status_id(user_id)

    if rebuild_all and not only_doc_ids:
        messages = []
        any_ok = False
        total_chunks_all = 0
        for mid in list_matters_with_documents(user_id):
            ok, msg, n_chunks = _build_faiss_index_scoped(
                user_id,
                progress_callback,
                use_ocr=use_ocr,
                enrich_metadata=enrich_metadata,
                incremental=False,
                matter_id=mid,
            )
            messages.append(msg)
            any_ok = any_ok or ok
            total_chunks_all += int(n_chunks or 0)
        ok_u, msg_u, n_u = _build_faiss_index_scoped(
            user_id,
            progress_callback,
            use_ocr=use_ocr,
            enrich_metadata=enrich_metadata,
            incremental=False,
            matter_id="",
        )
        messages.append(msg_u)
        any_ok = any_ok or ok_u
        total_chunks_all += int(n_u or 0)
        total_docs = get_user_document_count(user_id)
        run_query(
            "INSERT OR REPLACE INTO knowledge_base_status (id, status, total_documents, total_chunks, last_updated, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (status_id, "active" if any_ok else "error", total_docs, total_chunks_all, _utc_iso(), _utc_iso()),
        )
        log_action(user_id, "build_index_all_matters", "; ".join(messages))
        return any_ok, "; ".join(messages)

    scoped_matter = (matter_id or "").strip()
    if not scoped_matter and only_doc_ids:
        scoped_matter = _infer_matter_id_for_docs(user_id, only_doc_ids)

    # region agent log
    try:
        from backend.app.core.debug_matter_index_log import matter_index_log

        matter_index_log(
            "H4",
            "app.py:build_faiss_index",
            "scoped_matter_resolved",
            {
                "matter_id_arg": (matter_id or "")[:36],
                "scoped_matter": scoped_matter[:36],
                "only_doc_ids": list(only_doc_ids or [])[:5],
                "incremental": bool(incremental),
                "rebuild_all": bool(rebuild_all),
            },
        )
    except Exception:
        pass
    # endregion

    ok, msg, chunk_total = _build_faiss_index_scoped(
        user_id,
        progress_callback,
        only_doc_ids=only_doc_ids,
        use_ocr=use_ocr,
        enrich_metadata=enrich_metadata,
        incremental=incremental,
        matter_id=scoped_matter,
    )

    total_docs = get_user_document_count(user_id)
    run_query(
        "INSERT OR REPLACE INTO knowledge_base_status (id, status, total_documents, total_chunks, last_updated, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (status_id, "active" if ok else "error", total_docs, int(chunk_total or 0), _utc_iso(), _utc_iso()),
    )
    log_action(user_id, "build_index", msg)
    return ok, msg

def get_knowledge_base_status(user_id: Optional[str] = None):
    result = run_query(
        "SELECT status, total_documents, total_chunks, last_updated FROM knowledge_base_status WHERE id = ?",
        (get_kb_status_id(user_id),), fetch=True
    )
    if result:
        return {"status": result[0][0], "total_documents": result[0][1], "total_chunks": result[0][2], "last_updated": result[0][3]}
    return {"status": "empty", "total_documents": 0, "total_chunks": 0, "last_updated": None}


def render_kb_health_panel(user_id: str, last_query_error: Optional[str] = None) -> None:
    """Show Knowledge Base health with file paths and fix steps."""
    kb = get_knowledge_base_status(user_id)
    doc_count = get_user_document_count(user_id)
    index_dir = get_user_index_dir(user_id)
    report = diagnose_kb_health(
        index_dir=index_dir,
        document_count=doc_count,
        db_chunk_count=kb.get("total_chunks", 0),
        db_status=kb.get("status", "empty"),
    )
    gen_status = cached_generator_status()
    if not gen_status.get("available"):
        report["issues"].append({
            "severity": "error",
            "message": gen_status.get("message", "LM Studio is not reachable."),
            "file": "llms.py → LMStudioClient._check_availability()",
            "fix": (
                "In LM Studio: load a model, open the Local Server tab, and click Start Server. "
                f"Then set LM_STUDIO_URL in .env to the server URL (often {DEFAULT_LM_STUDIO_URL}). "
                "Allow the port in Windows Firewall if you connect from another PC."
            ),
        })
        report["healthy"] = False

    if last_query_error:
        report["issues"].append({
            "severity": "error",
            "message": last_query_error,
            "file": "app.py → rag_query()",
            "fix": "Upload/index documents or check rag.py query_kb logs.",
        })
        report["healthy"] = False

    with st.expander("🩺 Knowledge Base Health", expanded=not report["healthy"]):
        if report["healthy"]:
            st.success("Knowledge base is ready for document-grounded Q&A.")
        else:
            st.error("Knowledge base has issues — fix these before expecting answers.")

        st.markdown(
            f"- **Index path:** `{report['index_path']}`\n"
            f"- **Index on disk:** {'Yes' if report['index_exists'] else 'No'}\n"
            f"- **Documents in DB:** {report['document_count']}\n"
            f"- **Indexed chunks (DB):** {report['db_chunk_count']}\n"
            f"- **Status:** {report['db_status']}\n"
            f"- **Score threshold:** {report['score_threshold']}"
        )

        if report["issues"]:
            st.markdown("#### Issues")
            for issue in report["issues"]:
                icon = "🔴" if issue["severity"] == "error" else "🟡"
                st.markdown(
                    f"{icon} **{issue['message']}**\n\n"
                    f"- **Where:** `{issue['file']}`\n"
                    f"- **Fix:** {issue['fix']}"
                )


def delete_user_document(doc_id: str, user_id: str) -> bool:
    row = run_query(
        "SELECT saved_path FROM documents WHERE id = ? AND uploader_id = ?",
        (doc_id, user_id),
        fetch=True,
    )
    if not row:
        return False

    saved_path = Path(row[0][0])
    try:
        resolved = saved_path.resolve()
        data_root = DATA_DIR.resolve()
        if resolved == data_root or data_root in resolved.parents:
            resolved.unlink(missing_ok=True)
    except Exception:
        pass

    run_query("DELETE FROM case_entities WHERE document_id = ?", (doc_id,))
    run_query("DELETE FROM document_timeline WHERE document_id = ?", (doc_id,))
    run_query("DELETE FROM documents WHERE id = ? AND uploader_id = ?", (doc_id, user_id))
    try:
        from backend.app.core.kb_status_sync import sync_kb_status_from_faiss

        sync_kb_status_from_faiss(user_id)
    except Exception:
        run_query(
            "INSERT OR REPLACE INTO knowledge_base_status (id, status, total_documents, total_chunks, last_updated, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (get_kb_status_id(user_id), "stale", get_user_document_count(user_id), 0, _utc_iso(), _utc_iso()),
        )
    log_action(user_id, "delete_pdf", doc_id)
    return True


# ---------------------------
# AI / RAG FUNCTIONS (3 MODES)
# ---------------------------

def _record_kb_error(message: Optional[str]) -> None:
    """Store last KB error for health panel (safe outside Streamlit reruns)."""
    try:
        st.session_state["last_kb_error"] = message
    except Exception:
        pass


def sanitize_assistant_response(text: str, fallback: str = "") -> str:
    """Never show raw {} / empty JSON to users; polish KB citation markers."""
    try:
        from legal_web_engine import sanitize_legal_display

        text = sanitize_legal_display(text, fallback="")
    except Exception:
        pass
    normalized = (text or "").strip()
    if _is_low_information_payload(normalized):
        return fallback or (
            "### Service Notice\n\n"
            "The intelligence layer returned an empty response. "
            "Please retry, or switch mode (Knowledge Base / Open Law / Jurisprudence). "
            "If this persists, verify LM Studio is connected under **Settings**."
        )
    if normalized.startswith("❌"):
        return normalized
    try:
        from citation_formatter import strip_inline_citation_markers

        normalized = strip_inline_citation_markers(normalized)
        from kb_response_state import contains_not_found_phrase, enforce_single_state

        if contains_not_found_phrase(normalized):
            if _is_low_information_payload(
                enforce_single_state(normalized, found=True)
            ):
                return fallback or KB_NOT_FOUND_MESSAGE
            normalized = enforce_single_state(normalized, found=True)
    except Exception:
        pass
    return normalized


def _is_low_information_payload(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return True
    bad_literals = {
        "{}", "{ }", "[]", "[ ]", "null", "none", '""', "''", "n/a", "na",
    }
    if normalized in bad_literals:
        return True
    # Extremely short non-alphanumeric output is almost always useless noise.
    if len(re.findall(r"[A-Za-z0-9]", normalized)) < 5:
        return True
    return False


def _extract_query_anchors(question: str) -> list:
    """
    Extract important explicit entities/phrases from the user question.
    Example: "Click Eat", "LegalEase.AI", etc.
    """
    q = str(question or "")
    anchors = []

    # Title-case multiword phrases (e.g., "Click Eat")
    for phrase in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", q):
        p = phrase.strip()
        if len(p) >= 4:
            anchors.append(p)

    # Product-like tokens with punctuation/casing
    for token in re.findall(r"\b[A-Za-z][A-Za-z0-9_.-]{3,}\b", q):
        if any(ch.isupper() for ch in token[1:]) or "." in token:
            anchors.append(token.strip())

    # Explicit known phrase normalization when present
    ql = q.lower()
    if "click eat" in ql:
        anchors.append("Click Eat")
    if "legalease" in ql:
        anchors.append("LegalEase")

    dedup = []
    seen = set()
    for a in anchors:
        key = a.lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(a)
    return dedup


def _compose_chunk_based_answer(chunks: list, question: str) -> str:
    """
    Deterministic fallback when model returns low-information payload.
    Produces an industry-style structured answer strictly from retrieved chunks.
    """
    if not chunks:
        return NOT_FOUND_PHRASE

    query_terms = {
        t for t in re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]{2,}", question.lower())
        if t not in {"what", "which", "when", "where", "who", "why", "how", "from", "with", "about", "based", "only", "would", "could"}
    }

    anchors = _extract_query_anchors(question)
    anchors_l = [a.lower() for a in anchors]

    ranked_sentences = []
    seen_sentences = set()
    for item in chunks[:8]:
        content = (item.get("content", "") or "").replace("\n", " ")
        meta = item.get("metadata", {})
        cite = f"[[{meta.get('filename', 'doc')}:{meta.get('chunk_index', 0)}]]"
        for sent in re.split(r"(?<=[.!?])\s+", content):
            cleaned = re.sub(r"\s+", " ", sent.strip().strip(" -"))
            if len(cleaned) < 22:
                continue
            key = cleaned.lower()
            if key in seen_sentences:
                continue
            seen_sentences.add(key)
            lower = cleaned.lower()
            overlap = sum(1 for t in query_terms if t in lower)
            score = (overlap * 3) + min(len(cleaned) / 120.0, 2.0)
            if anchors_l:
                # Strongly prioritize sentences containing explicit query entity/project names.
                exact_anchor_hits = sum(1 for a in anchors_l if a in lower)
                token_anchor_hits = sum(1 for a in anchors_l for part in a.split() if part in lower)
                score += (exact_anchor_hits * 8.0) + (token_anchor_hits * 1.25)
            ranked_sentences.append((score, cleaned, cite))

    if not ranked_sentences:
        return NOT_FOUND_PHRASE

    ranked_sentences.sort(key=lambda x: x[0], reverse=True)
    best = ranked_sentences[0]
    if anchors_l:
        anchor_rows = [row for row in ranked_sentences if any(a in row[1].lower() for a in anchors_l)]
        key_findings = (anchor_rows[:3] if anchor_rows else ranked_sentences[:3])
        evidence = (anchor_rows[:5] if anchor_rows else ranked_sentences[:5])
    else:
        key_findings = ranked_sentences[:3]
        evidence = ranked_sentences[:5]

    # If query asks for comparison/list/attributes, present a markdown table.
    q_lower = question.lower()
    table_mode = any(word in q_lower for word in ["compare", "difference", "differences", "list", "attributes", "skills", "technologies"])

    structured = ["### Answer", f"{best[1]} {best[2]}", ""]
    if table_mode:
        structured.extend(
            [
                "### Key Findings",
                "| Finding | Source |",
                "|---|---|",
                *[f"| {row[1].replace('|', ' ')} | {row[2]} |" for row in key_findings],
                "",
            ]
        )
    else:
        structured.extend(
            [
                "### Key Findings",
                *[f"- {row[1]} {row[2]}" for row in key_findings],
                "",
            ]
        )

    structured.extend(
        [
            "### Supporting Evidence",
            *[f'- "{row[1]}" {row[2]}' for row in evidence],
            "",
            "### Notes",
            "- This answer is generated strictly from uploaded document chunks.",
        ]
    )
    return "\n".join(structured)


def _kb_secondary_prompt(chunks: list, question: str) -> str:
    context_parts = []
    for item in chunks:
        meta = item.get("metadata", {})
        fname = meta.get("filename", "doc")
        idx = meta.get("chunk_index", 0)
        body = item.get("content", "")
        context_parts.append(f"[[{fname}:{idx}]]\n{body}")
    context_block = "\n\n---\n\n".join(context_parts)
    return (
        "Answer the QUESTION using ONLY the CONTEXT.\n"
        "Do NOT return JSON or braces. Return plain markdown.\n"
        "If answer is missing, return exactly: Information not found in document.\n\n"
        "Required format:\n"
        "## Answer\n"
        "<direct answer with citation>\n\n"
        "## Key Findings\n"
        "- <fact> [[filename:chunk]]\n"
        "- <fact> [[filename:chunk]]\n\n"
        "## Supporting Evidence\n"
        "- \"<short quote>\" [[filename:chunk]]\n\n"
        f"CONTEXT:\n{context_block}\n\n"
        f"QUESTION:\n{question}\n"
    )


def _build_similar_cases_from_chunks(chunks: list, limit: int = 5) -> list:
    """Format and dedupe retrieved chunks for metadata/source display."""
    similar_cases = []
    seen_chunks = set()
    for r in chunks:
        meta = r.get("metadata", {})
        chunk_key = (meta.get("filename", "unknown"), meta.get("chunk_index", 0))
        if chunk_key in seen_chunks:
            continue
        seen_chunks.add(chunk_key)

        score = float(r.get("score", 1.0))
        confidence = float(r.get("final_score", r.get("confidence", 0.0)) or 0.0)
        if confidence > 0:
            relevance = "High" if confidence >= 0.72 else ("Medium" if confidence >= 0.52 else "Low")
        else:
            relevance = "High" if score < 0.45 else ("Medium" if score < 0.9 else "Low")
        excerpt = (r.get("content", "") or "").strip().replace("\n", " ")
        if len(excerpt) > 320:
            excerpt = excerpt[:320].rstrip() + "..."

        similar_cases.append({
            "filename": meta.get("filename", "unknown"),
            "chunk_index": meta.get("chunk_index", 0),
            "excerpt": excerpt,
            "relevance": relevance,
            "score": round(score, 3),
            "confidence": round(confidence, 3),
        })
        if len(similar_cases) >= limit:
            break
    return similar_cases


def _select_generation_chunks(results: list, question: str, max_chunks: int = 5) -> list:
    """
    Build high-signal context window for answer synthesis.
    Comparison queries: guarantee one chunk per section (299 + 300 + …).
    """
    if not results:
        return []
    from conversation_context import extract_sections_from_text
    from kb_retrieval import (
        ensure_per_section_chunks,
        extract_comparison_sections,
        is_comparison_query,
    )
    from kb_preprocess import chunk_matches_target, is_intro_or_generic_chunk
    from rag import SIMILARITY_GATE

    target_sections = (
        extract_comparison_sections(question)
        if is_comparison_query(question)
        else extract_sections_from_text(question)
    )
    ranked = _rerank_chunks_for_query(results, question)

    if len(target_sections) >= 2:
        return ensure_per_section_chunks(ranked, target_sections, max_total=max_chunks)

    chosen: list = []
    for r in ranked:
        score = float(r.get("final_score", 0.0))
        content = str(r.get("content", ""))
        if score < SIMILARITY_GATE * 0.45 and target_sections:
            continue
        if target_sections and is_intro_or_generic_chunk(content):
            continue
        if target_sections and not chunk_matches_target(content, target_sections):
            continue
        chosen.append(r)
        if len(chosen) >= max_chunks:
            break
    if not chosen:
        chosen = [r for r in ranked if not is_intro_or_generic_chunk(str(r.get("content", "")))][:max_chunks]
    if not chosen:
        chosen = ranked[:max_chunks]
    return chosen


def _rerank_chunks_for_query(chunks: list, question: str) -> list:
    """Lightweight query-aware reranking to reduce irrelevant chunk leakage."""
    from conversation_context import extract_sections_from_text

    q = (question or "").lower()
    terms = [
        t for t in re.findall(r"[a-z0-9][a-z0-9._-]{2,}", q)
        if t not in {"what", "which", "where", "when", "who", "with", "from", "about", "only", "using", "based"}
    ]
    target_sections = extract_sections_from_text(question)
    has_resume_intent = ("resume" in q) or ("cv" in q)
    asks_name = ("name" in q) or ("who is" in q) or ("who's" in q)
    asks_click_eat = "click eat" in q

    scored = []
    for item in chunks:
        base = float(item.get("final_score", item.get("score", 1.0)))
        if base <= 1.0:
            base = 1.0 - base
        meta = item.get("metadata", {}) or {}
        filename = str(meta.get("filename", "")).lower()
        content = str(item.get("content", ""))
        content_l = content.lower()
        text_l = f"{filename} {content_l}"

        overlap = sum(1 for t in terms if t in text_l)
        adjusted = base + (0.06 * overlap)

        try:
            from kb_legal_query_rewrite import (
                chunk_matches_law_query,
                is_law_mapping_chunk,
                is_law_replacement_query,
            )

            if is_law_replacement_query(question):
                if is_law_mapping_chunk(content):
                    adjusted += 0.75
                if chunk_matches_law_query(content, question):
                    adjusted += 0.55
        except Exception:
            pass

        from kb_preprocess import extract_primary_section_number, is_intro_or_generic_chunk

        for sec in target_sections:
            if re.search(rf"\bsection\s*{re.escape(sec)}\b", content_l):
                adjusted += 0.65
            elif re.search(rf"\b(?:ipc|bns)\s*{re.escape(sec)}\b", content_l):
                adjusted += 0.55
            elif re.search(rf"\b{re.escape(sec)}\b", content_l):
                adjusted += 0.12
        if target_sections:
            primary = extract_primary_section_number(content)
            if primary and primary not in {s.lower() for s in target_sections}:
                adjusted -= 0.70
            if is_intro_or_generic_chunk(content):
                adjusted -= 0.55
            if re.search(r"\bgeneral principles\b|\bprimary criminal code\b", content_l):
                adjusted -= 0.35

        if has_resume_intent and any(k in filename for k in ["resume", "cv", "profile"]):
            adjusted -= 0.22
        if asks_click_eat and "click eat" in text_l:
            adjusted -= 0.30
        if asks_name and (re.search(r"\b[A-Z][A-Z ]{3,}\b", content) or "@" in content or "linkedin" in text_l):
            adjusted -= 0.18

        scored.append((adjusted, item))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


def regenerate_kb_answer_from_feedback(
    user_id: str,
    question: str,
    previous_answer: str,
    feedback_note: str = "",
) -> tuple:
    """
    Regenerate KB response after user dislike feedback.
    """
    index_dir = resolve_rag_index_dir(user_id, None)
    results = query_kb(question, k=14, index_dir=index_dir)
    if not results:
        return KB_NOT_FOUND_MESSAGE, []

    filtered = _select_generation_chunks(results, question, max_chunks=3)
    if not filtered:
        filtered = results[:3]

    refinement = (
        "User feedback on previous answer: "
        + (feedback_note or "Too generic and not specific enough. Answer the exact question only.")
        + f"\nPrevious answer to improve:\n{previous_answer}"
    )
    improved_query = (
        f"{question}\n\n"
        f"{refinement}\n\n"
        "Regenerate with stronger specificity, avoid unrelated profile sections, and keep only directly relevant evidence."
    )

    from intent_engine import classify_intent
    from kb_rag_decision import evaluate_retrieval
    from kb_response_state import build_found_answer, enforce_single_state

    found, _, _, _ = evaluate_retrieval(question, results)
    if not found:
        return KB_NOT_FOUND_MESSAGE, _build_similar_cases_from_chunks(results, limit=5)

    profile = classify_intent(improved_query)
    normalized = enforce_single_state(
        build_found_answer(improved_query, filtered, profile, use_llm=True),
        found=True,
    )
    if not normalized or _is_low_information_payload(normalized):
        return KB_NOT_FOUND_MESSAGE, _build_similar_cases_from_chunks(results, limit=5)

    return normalized, _build_similar_cases_from_chunks(results, limit=5)


def rag_query(
    user_id: str,
    question: str,
    k=5,
    find_similar_cases=True,
    conversation_history: Optional[list] = None,
    thread_id: Optional[str] = None,
    matter_id: Optional[str] = None,
    session_id: Optional[str] = None,
    *,
    retrieval_scope: str = "global",
) -> tuple:
    """
    Knowledge Base Q&A — always uses global_kb unless retrieval_scope='matter'.

    Global KB (default): statutes, constitution, case law — never matter documents.
    Matter scope: only when explicitly requested (Matter AI / matter workspace).
    """
    from intent_engine import classify_intent
    from answer_orchestrator import orchestrate_kb_answer

    scope = (retrieval_scope or "global").strip().lower()
    strict_matter = scope == "matter"
    index_dir = resolve_rag_index_dir(
        user_id,
        matter_id if strict_matter else None,
        require_matter_scope=strict_matter,
        retrieval_scope=scope,
    )
    doc_count = get_scoped_document_count(
        user_id, matter_id if strict_matter else None
    )
    # #region agent log
    try:
        with open(Path(__file__).resolve().parent / "debug-cf6ca9.log", "a", encoding="utf-8") as lf:
            lf.write(
                json.dumps(
                    {
                        "sessionId": "cf6ca9",
                        "runId": "matter-separation",
                        "hypothesisId": "H2",
                        "location": "app.py:rag_query",
                        "message": "rag_scope_resolved",
                        "data": {
                            "strict_matter": strict_matter,
                            "matter_id": matter_id or "",
                            "index_dir": str(index_dir),
                            "doc_count": int(doc_count or 0),
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

    if not index_exists(index_dir) and doc_count == 0:
        if strict_matter:
            return (
                "### Matter Knowledge Base Empty\n\n"
                "No documents are indexed for this matter yet.\n\n"
                "1. Open the **Matter workspace** → **Knowledge** tab.\n"
                "2. Upload FIRs, witness statements, evidence, or court orders.\n"
                "3. Run **Re-index**, then ask your question again.\n\n"
                "_This matter has not been indexed._"
            ), []
        return (
            "### Global Knowledge Base Empty\n\n"
            "No legal reference documents are indexed yet.\n\n"
            "1. Go to **Documents** and upload statute PDFs, constitution, or case law compilations "
            "**without** linking them to a matter.\n"
            "2. Run **Re-index all**, then ask again.\n\n"
            "For live web research, use **Open Law Intelligence** mode."
        ), []

    if doc_count > 0:
        try:
            from backend.app.core.faiss_index_stats import count_index_vectors

            vector_count = count_index_vectors(index_dir) if index_exists(index_dir) else 0
        except Exception:
            vector_count = 0
        if not index_exists(index_dir) or vector_count == 0:
            logger.info(
                "[INFO] FAISS index missing or empty for user %s matter=%s — rebuilding",
                user_id,
                matter_id or "unlinked",
            )
            build_faiss_index(
                user_id,
                matter_id=matter_id if strict_matter else None,
            )
            index_dir = resolve_rag_index_dir(
                user_id,
                matter_id if strict_matter else None,
                require_matter_scope=strict_matter,
                retrieval_scope=scope,
            )

    from kb_pipeline import kb_pipeline as run_kb_pipeline
    from kb_response_state import KB_NOT_FOUND_MESSAGE, log_kb_pipeline

    profile = classify_intent(question, conversation_history)
    effective_thread_id = thread_id
    try:
        import streamlit as st

        st.session_state["kb_conversation_state"] = profile.conversation_state
        if not effective_thread_id:
            effective_thread_id = st.session_state.get("active_thread_id")
    except Exception:
        pass

    try:
        normalized, filtered, pipe_diag = run_kb_pipeline(
            user_id,
            question,
            conversation_history,
            index_dir=index_dir,
            thread_id=effective_thread_id or None,
            session_id=session_id,
        )
    except Exception as e:
        logger.exception("Knowledge base pipeline failed")
        return f"Knowledge base error: {e}", []

    if RAG_DEBUG:
        logger.debug("KB pipeline diagnostics: %s", pipe_diag)
        err = get_last_query_error()
        if err:
            logger.debug("RAG retrieval note: %s", err)

    if normalized == "NOT_FOUND_IN_KB" or not normalized:
        err = get_last_query_error() or pipe_diag.get("vector_error") or "No relevant chunks."
        err_l = str(err).lower()
        if "meta tensor" in err_l or "embedding" in err_l:
            return (
                "### Knowledge Base Error\n\n"
                "Document search could not start because the embedding model failed to load.\n\n"
                f"Details: {err}\n\n"
                "Restart the backend (`run_backend.ps1`). If this repeats after reboot, "
                "close other heavy apps and ensure sentence-transformers can load on CPU."
            ), []
        _record_kb_error(err)
        log_kb_pipeline(
            query=question,
            decision="NOT_FOUND",
            best_score=pipe_diag.get("best_score", 0),
            threshold=(pipe_diag.get("eval") or {}).get("threshold", 0.28),
            chunks=[],
            answer=KB_NOT_FOUND_MESSAGE,
        )
        return "NOT_FOUND_IN_KB", []

    if normalized:
        try:
            from response_cleaner import finalize_display_answer
            from kb_rag_decision import extract_query_sections

            secs = extract_query_sections(question)
            ql = (question or "").lower()
            law_label = "BNS" if re.search(r"\bbns\b", ql) else "IPC"
            normalized, _ = finalize_display_answer(
                normalized,
                filtered,
                section_hint=f"Section {secs[0].upper()}" if secs else "",
                section=secs[0] if secs else "",
                law=law_label,
            )
        except Exception:
            pass

    try:
        import streamlit as st
        from answer_orchestrator import suggest_follow_ups as orch_suggest

        st.session_state["last_follow_ups"] = orch_suggest(question, normalized, profile)
        st.session_state["last_intent"] = profile.primary.value
    except Exception:
        pass

    _record_kb_error(None)
    similar_cases = (
        _build_similar_cases_from_chunks(filtered, limit=5) if find_similar_cases else []
    )
    log_kb_pipeline(
        query=question,
        decision="FOUND",
        best_score=pipe_diag.get("best_score", 0),
        threshold=(pipe_diag.get("eval") or {}).get("threshold", 0.58),
        chunks=filtered,
        answer=normalized,
    )
    return normalized, similar_cases[:5]


def query_from_ocr_attachment(
    question: str,
    ocr_text: str,
    filename: str,
    conversation_history: Optional[list] = None,
) -> str:
    """Answer using OCR text from a chat image upload."""
    if not (ocr_text or "").strip():
        return "No extractable text found in the uploaded image."
    chunk = {
        "content": ocr_text[:12000],
        "metadata": {"filename": filename, "source": "chat_ocr", "chunk_index": 0},
        "score": 0.0,
    }
    from answer_orchestrator import orchestrate_kb_answer

    result = orchestrate_kb_answer(
        question,
        [chunk],
        messages=conversation_history,
    )
    st.session_state["last_follow_ups"] = result.follow_ups
    return (result.text or "").strip() or "Could not generate an answer from the image text."


def _web_intel_unavailable_message() -> str:
    """Actionable Open Law error (FastAPI + Next.js; not Streamlit-specific)."""
    from llms import web_search_status

    try:
        from backend.app.core.web_intelligence import gemini_configured, web_intel_status

        gemini_on = gemini_configured()
        gemini_meta = web_intel_status()
    except Exception:
        gemini_on = False
        gemini_meta = {}

    ws = web_search_status()
    lines = [
        "### Web Intelligence Unavailable",
        "",
        "No web sources could be retrieved for this question.",
        "",
    ]
    if gemini_on:
        lines.append(
            "- **Gemini** is configured but hit its free-tier daily limit or failed. "
            "LegalEase tried backup search (DuckDuckGo/Tavily) but got no usable results."
        )
        lines.append(
            "- Wait until tomorrow for Gemini quota reset, enable billing in Google AI Studio, "
            "or add `TAVILY_API_KEY` in `.env` for a second search provider."
        )
    elif not ws.get("tavily_configured"):
        lines.append(
            "- Add `GEMINI_API_KEY` (recommended) or `TAVILY_API_KEY` to the project root `.env`."
        )
    else:
        lines.append("- Tavily is configured; the search request failed or returned no usable results.")
    if ws.get("ddgs_available"):
        lines.append("- DuckDuckGo fallback is installed but did not return results for this query.")
    else:
        lines.append(
            "- Install DuckDuckGo fallback: `py -m pip install duckduckgo-search` then restart the API."
        )
    lines.extend([
        "",
        "Restart the backend after changing `.env`:",
        "`cd` to the project root, stop the API terminal, then run `.\\run_backend.ps1`.",
    ])
    _ = gemini_meta
    return "\n".join(lines)


def _stash_follow_ups(follow_ups) -> None:
    try:
        if st is not None:
            st.session_state["last_follow_ups"] = follow_ups
    except Exception:
        pass


def web_search_query(question: str, conversation_history: Optional[list] = None, user_id: Optional[str] = None):
    """
    MODE 2: Open Law Intelligence — Gemini grounded search (primary) or legacy fallback.
    """
    from legal_web_query import build_web_search_query

    original = (question or "").strip()
    search_q = build_web_search_query(original, conversation_history)

    try:
        from legal_web_query import looks_legal_query_for_web, non_legal_web_refusal

        if not looks_legal_query_for_web(original, conversation_history):
            refusal = non_legal_web_refusal(original)
            return refusal, [{
                "title": "Legal-only mode",
                "href": "",
                "body": refusal,
                "provider": "LegalEase",
            }]
    except ImportError:
        pass

    gemini_failed = False
    try:
        from backend.app.core.web_intelligence import gemini_configured, run_grounded_legal_research

        if gemini_configured():
            answer, sources, follow_ups = run_grounded_legal_research(
                search_q, conversation_history, user_id=user_id
            )
            _stash_follow_ups(follow_ups)
            answer = sanitize_assistant_response(answer, fallback=answer)
            try:
                from backend.app.services.response_formatter import format_legal_response
                from backend.legal_engine.query_parser import parse_legal_query

                parse = parse_legal_query(search_q, conversation_history)
                answer = format_legal_response(
                    answer, intent=parse.intent, parse=parse.to_dict()
                )
            except Exception:
                pass
            return answer, sources
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("Gemini web intel failed, falling back: %s", exc)
        gemini_failed = True

    from answer_orchestrator import orchestrate_web_answer
    from legal_web_query import is_self_contained_web_query

    max_web = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6"))
    snippets = search_web(
        search_q,
        max_results=max_web,
        conversation_history=conversation_history,
        skip_gemini=True,
    )
    if snippets and snippets[0].get("provider") == "LegalEase":
        return snippets[0].get("body", ""), snippets
    if not snippets or (len(snippets) == 1 and snippets[0].get("provider") == "Unavailable"):
        from llms import clear_web_search_cache

        clear_web_search_cache()
        snippets = search_web(search_q, max_results=max_web, conversation_history=None, skip_gemini=True)
    if not snippets or (len(snippets) == 1 and snippets[0].get("provider") == "Unavailable"):
        return _web_intel_unavailable_message(), snippets

    synth_history = None if is_self_contained_web_query(original) else conversation_history
    synth_question = resolved
    result = orchestrate_web_answer(
        synth_question, snippets, messages=synth_history, user_id=user_id
    )
    _stash_follow_ups(result.follow_ups)
    answer = sanitize_assistant_response(
        result.text,
        fallback=_compose_web_answer_from_snippets(snippets, original),
    )
    if _is_low_information_payload(answer):
        answer = _compose_web_answer_from_snippets(snippets, original)
    try:
        from backend.app.services.response_formatter import format_legal_response
        from backend.legal_engine.query_parser import parse_legal_query

        parse = parse_legal_query(synth_question, synth_history)
        answer = format_legal_response(answer, intent=parse.intent, parse=parse.to_dict())
    except Exception:
        pass
    return answer, snippets


def deep_case_query(
    user_id: str,
    question: str,
    conversation_history: Optional[list] = None,
    *,
    matter_id: Optional[str] = None,
):
    """
    MODE 3: Jurisprudence Engine — KB RAG + Gemini web intelligence deep research report.
    """
    try:
        from backend.app.services.hybrid_orchestrator import run_jurisprudence_turn
        from backend.legal_engine.query_parser import parse_legal_query

        parse = parse_legal_query(question, conversation_history)
        answer, kb_results, web_results = run_jurisprudence_turn(
            user_id,
            question,
            conversation_history,
            matter_id=matter_id,
            parse=parse,
        )
        return answer, kb_results, web_results
    except Exception as exc:
        import logging
        logging.getLogger(__name__).warning("Jurisprudence engine fallback: %s", exc)

    try:
        kb_results = query_kb(question, k=50, index_dir=get_user_index_dir(user_id))
    except Exception:
        kb_results = []
    
    kb_text = "\n\n".join([r.get("content", "")[:500] for r in kb_results[:20]])
    web_results = search_web(question, max_results=5)
    web_text = "\n".join([f"{w.get('title', 'Source')}: {w.get('href', '')} - {w.get('body', '')[:200]}" for w in web_results])
    combined_context = f"From uploaded documents:\n{kb_text}\n\nFrom web search:\n{web_text}"
    prompt = deepcase_prompt(combined_context, question)
    generator = get_generator()
    answer = generator.generate(prompt, temperature=0.2, max_tokens=2048)
    fallback = _compose_web_answer_from_snippets(web_results, question)
    if kb_results:
        from rag import _compose_grounded_markdown
        fallback = _compose_grounded_markdown(kb_results[:3], question) or fallback
    answer = sanitize_assistant_response(answer, fallback=fallback)
    return answer, kb_results, web_results


def basic_query(question: str) -> str:
    """Basic AI query for simple questions."""
    prompt = f"You are LegalEase.AI, an expert Indian legal assistant. Answer clearly and professionally: {question}"
    generator = get_generator()
    return generator.generate(prompt, temperature=0.3, max_tokens=512)

def save_chat_message(
    user_id: str,
    question: str,
    answer: str,
    language: str = "English",
    mode: str = "knowledge_base",
    thread_id: Optional[str] = None,
) -> Dict[str, str]:
    """Persist one turn; returns chat_id and thread_id for continuation."""
    _migrate_chat_thread_column()
    chat_id = str(uuid.uuid4())
    tid = (thread_id or "").strip() or str(uuid.uuid4())
    run_query(
        """
        INSERT INTO chat_history
        (id, user_id, question, answer, language, mode, created_at, thread_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (chat_id, user_id, question, answer, language, mode, _utc_iso(), tid),
    )
    return {"chat_id": chat_id, "thread_id": tid}


def get_chat_threads(user_id: str, limit: int = 20):
    """List saved chat threads (most recent activity first)."""
    _migrate_chat_thread_column()
    rows = run_query(
        """
        SELECT COALESCE(h.thread_id, h.id), h.question, h.answer, h.mode, h.language, h.created_at
        FROM chat_history h
        INNER JOIN (
            SELECT COALESCE(thread_id, id) AS tid, MAX(created_at) AS max_created
            FROM chat_history
            WHERE user_id = ?
            GROUP BY tid
        ) latest
        ON COALESCE(h.thread_id, h.id) = latest.tid AND h.created_at = latest.max_created
        WHERE h.user_id = ?
        ORDER BY h.created_at DESC
        LIMIT ?
        """,
        (user_id, user_id, limit),
        fetch=True,
    )
    return rows or []


def get_chat_thread_messages(user_id: str, thread_id: str):
    """All turns in a thread, oldest first."""
    _migrate_chat_thread_column()
    rows = run_query(
        """
        SELECT id, question, answer, mode, language, created_at
        FROM chat_history
        WHERE user_id = ? AND (thread_id = ? OR id = ?)
        ORDER BY created_at ASC
        """,
        (user_id, thread_id, thread_id),
        fetch=True,
    )
    return rows or []


def save_chat_feedback(user_id: str, chat_id: str, rating: str, comment: str = "") -> None:
    """
    Persist per-answer user feedback.
    rating must be 'like' or 'dislike'.
    """
    safe_rating = "like" if str(rating).lower() == "like" else "dislike"
    run_query(
        """
        INSERT INTO chat_feedback (id, chat_id, user_id, rating, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id, user_id) DO UPDATE SET
            rating = excluded.rating,
            comment = excluded.comment,
            created_at = excluded.created_at
        """,
        (str(uuid.uuid4()), chat_id, user_id, safe_rating, comment or "", _utc_iso())
    )

def get_chat_history(user_id: str, limit: int = 50):
    """Legacy flat history (new code should use get_chat_threads)."""
    rows = get_chat_threads(user_id, limit=limit)
    return [(q, a, lang, created) for _, q, a, _mode, lang, created in rows]

# ---------------------------
# HELPER FUNCTIONS
# ---------------------------
def get_user_stats(user_id: str) -> Dict:
    docs = run_query("SELECT COUNT(*) FROM documents WHERE uploader_id = ?", (user_id,), fetch=True)
    queries = run_query("SELECT COUNT(*) FROM chat_history WHERE user_id = ?", (user_id,), fetch=True)
    return {"documents": docs[0][0] if docs else 0, "queries": queries[0][0] if queries else 0}

def get_system_stats() -> Dict:
    users = run_query("SELECT COUNT(*) FROM users", fetch=True)
    docs = run_query("SELECT COUNT(*) FROM documents", fetch=True)
    queries = run_query("SELECT COUNT(*) FROM chat_history", fetch=True)
    logs = run_query("SELECT COUNT(*) FROM logs", fetch=True)
    return {
        "users": users[0][0] if users else 0,
        "documents": docs[0][0] if docs else 0,
        "queries": queries[0][0] if queries else 0,
        "logs": logs[0][0] if logs else 0
    }

def get_team_members(owner_id: str):
    return run_query(
        """SELECT u.username, tm.role, tm.created_at FROM team_members tm 
           JOIN users u ON tm.member_user_id = u.id WHERE tm.team_owner_id = ?""",
        (owner_id,), fetch=True
    )

def add_team_member(owner_id: str, member_id: str, role: str = "member") -> bool:
    try:
        run_query(
            "INSERT INTO team_members (id, team_owner_id, member_user_id, role, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), owner_id, member_id, role, _utc_iso())
        )
        return True
    except Exception:
        return False

def process_payment(user_id: str, plan: str, amount: float) -> tuple:
    payment_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now.replace(year=now.year + 1)
    try:
        run_query(
            "INSERT INTO payments (id, user_id, plan, amount, payment_status, payment_id, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, plan, amount, "completed", payment_id, _utc_iso(), expires_at.isoformat())
        )
        upgrade_user_membership(user_id, plan)
        return True, payment_id
    except Exception as e:
        return False, str(e)

def get_payment_history(user_id: str):
    return run_query(
        "SELECT plan, amount, payment_status, created_at, expires_at FROM payments WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,), fetch=True
    )

def render_metric_card(title: str, value: str, icon: str = "📊"):
    st.markdown(f"""
    <div class="metric-card">
        <div style="font-size: 2rem;">{icon}</div>
        <div class="metric-value">{value}</div>
        <div class="metric-label">{title}</div>
    </div>
    """, unsafe_allow_html=True)

def render_feature_card(icon: str, title: str, description: str):
    st.markdown(f"""
    <div class="feature-card">
        <div class="feature-icon">{icon}</div>
        <div class="feature-title">{title}</div>
        <div class="feature-desc">{description}</div>
    </div>
    """, unsafe_allow_html=True)


def _expand_follow_up_query(question: str, messages: list) -> str:
    """Attach prior turn context for short follow-ups (ChatGPT-style)."""
    q = (question or "").strip()
    if not q or not messages:
        return q
    follow_up_cues = (
        "punishment", "penalty", "sentence", "explain", "simply", "difference",
        "compare", "what about", "and that", "also", "more", "why", "how",
    )
    if len(q.split()) > 12 and not any(c in q.lower() for c in follow_up_cues):
        return q

    last_user = ""
    last_assistant = ""
    for msg in reversed(messages):
        if msg.get("role") == "assistant" and not last_assistant:
            last_assistant = (msg.get("content") or "")[:1200]
        elif msg.get("role") == "user" and not last_user:
            last_user = (msg.get("content") or "")[:400]
        if last_user and last_assistant:
            break

    if not last_user:
        return q

    return (
        f"Follow-up question: {q}\n\n"
        f"Prior user question: {last_user}\n"
        f"Prior assistant answer (summary): {last_assistant[:600]}\n"
        "Answer the follow-up using the same legal topic and evidence rules as the prior turn."
    )


def _compose_web_answer_from_snippets(snippets: list, question: str) -> str:
    """Deterministic web answer when LLM returns empty/{}."""
    if not snippets:
        return (
            "### Web Intelligence\n\n"
            "No legal web sources were retrieved. Check **Tavily MCP** configuration in Settings."
        )
    if snippets[0].get("provider") == "LegalEase":
        return snippets[0].get("body", "")

    from legal_web_engine import intent_compose_from_snippets, resolve_web_response_kind
    from intent_engine import classify_intent

    kind = resolve_web_response_kind(question, classify_intent(question))
    text, _ = intent_compose_from_snippets(question, snippets, kind)
    return text


def render_chat_bubble(role: str, content: str):
    text = str(content or "")
    if role == "user":
        with st.chat_message("user", avatar="🧑‍💼"):
            st.markdown(text)
    else:
        with st.chat_message("assistant", avatar="⚖️"):
            st.markdown(sanitize_assistant_response(text))


def safe_link_url(url: str) -> str:
    url = (url or "").strip()
    if url.startswith(("http://", "https://")):
        return url
    return ""


# ---------------------------
# MAIN APPLICATION
# ---------------------------
def main():
    # Initialize
    init_db()
    
    # Session state initialization
    if "user" not in st.session_state:
        st.session_state["user"] = None
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    if "conversation_mode" not in st.session_state:
        st.session_state["conversation_mode"] = "knowledge_base"
    if "chat_attachment" not in st.session_state:
        st.session_state["chat_attachment"] = None
    if "conversation_id" not in st.session_state:
        st.session_state["conversation_id"] = str(uuid.uuid4())
    if "pending_assistant" not in st.session_state:
        st.session_state["pending_assistant"] = False
    if "session_prompt_bridge" not in st.session_state:
        st.session_state["session_prompt_bridge"] = None
    if "chat_lang" not in st.session_state:
        st.session_state["chat_lang"] = "English"
    if "theme_mode" not in st.session_state:
        st.session_state["theme_mode"] = "light"

    guest = not st.session_state.get("user")
    if guest:
        st.session_state["theme_mode"] = "light"

    # Nuclear CSS first — before any widgets (fixes layout voids on chat page)
    inject_nuclear_layout_css()
    nav_hint = st.session_state.get("nav", "🏠 Dashboard")
    chat_active = (not guest and nav_hint == "💬 AI Assistant")
    load_custom_css(chat_active=chat_active, guest_login=guest)
    if chat_active:
        inject_chat_page_css()
    inject_login_cinematic_css(login_page=guest)
    
    # Sidebar
    with st.sidebar:
        # Logo
        st.markdown("""
        <div class="logo-container">
            <div class="logo-text">⚖️ LegalEase.AI</div>
            <div class="logo-tagline">AI-Powered Legal Intelligence</div>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("---")
        
        if not st.session_state.get("user"):
            st.markdown(
                """
                <div class="sidebar-note">
                    <strong>Platform Capabilities</strong><br>
                    Explore what LegalEase.AI delivers before you sign in.
                </div>
                """,
                unsafe_allow_html=True,
            )
            render_sidebar_login_features()
        else:
            user = st.session_state["user"]
            st.markdown(f"### 👤 {user['username']}")
            
            # Membership badge
            membership = user.get("membership", "Free")
            badge_color = {"Free": "#94a3b8", "Pro": "#3b82f6", "Legal Pro": "#f59e0b"}.get(membership, "#94a3b8")
            st.markdown(f'<span class="status-badge" style="background: {badge_color}20; color: {badge_color};">{membership}</span>', unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Navigation
            menu_options = [
                "🏠 Dashboard",
                "💬 AI Assistant",
                "📂 Documents",
                "🛠️ Legal Tools",
                "📝 Drafting",
                "📊 Analytics",
                "⚙️ Settings"
            ]
            default_menu = st.session_state.get("nav", "🏠 Dashboard")
            default_index = menu_options.index(default_menu) if default_menu in menu_options else 0
            menu = st.radio(
                "Navigation",
                menu_options,
                index=default_index,
                label_visibility="collapsed"
            )
            st.session_state["nav"] = menu
            if menu == "💬 AI Assistant":
                inject_chat_page_css()
                if st.button("New Chat", use_container_width=True, type="primary", key="sb_new_chat"):
                    execute_new_chat()
                    st.rerun()
                st.markdown(
                    "<p style='font-size:0.72rem;color:#94a3b8;font-weight:600;"
                    "margin:0.45rem 0 0.15rem 0;'>RECENT SESSIONS</p>",
                    unsafe_allow_html=True,
                )
                past = get_chat_history(user["id"], limit=6)
                for i, row in enumerate(past or []):
                    q = (row[0] or "Question").strip()
                    short = (q[:30] + "...") if len(q) > 30 else q
                    if st.button(f"{short}", key=f"hist_{i}_{row[3]}", use_container_width=True):
                        st.session_state["messages"] = [
                            {"role": "user", "content": q},
                            {"role": "assistant", "content": row[1] or "", "question": q},
                        ]
                        st.session_state["pending_assistant"] = False
                        st.rerun()
                st.selectbox(
                    "Language",
                    ["English", "Hindi", "Tamil", "Marathi", "Bengali", "Gujarati"],
                    key="chat_lang",
                    label_visibility="collapsed",
                )
                st.markdown("---")
            
            st.markdown("---")
            
            # LLM Status (cached 15s — avoid blocking sidebar on every rerun)
            gen_status = cached_generator_status()
            backend_name = gen_status.get("backend", "LLM")
            if gen_status["available"]:
                st.success(f"🟢 {backend_name} Connected")
            else:
                st.error(f"🔴 {backend_name} Offline")
            
            st.markdown("---")
            
            if st.button("🚪 Logout", use_container_width=True):
                st.session_state["user"] = None
                st.session_state["messages"] = []
                st.rerun()
    
    # Main Content — cinematic guest login
    if not st.session_state.get("user"):
        render_cinematic_login(
            BASE_DIR,
            authenticate_user=authenticate_user,
            create_user=create_user,
        )
        return
    
    # Logged in user content
    user = st.session_state["user"]
    membership = user.get("membership", "Free")
    
    if menu == "🏠 Dashboard":
        render_dashboard(user)
    elif menu == "💬 AI Assistant":
        render_ai_assistant(user)
    elif menu == "📂 Documents":
        render_documents(user)
    elif menu == "🛠️ Legal Tools":
        render_legal_tools(user)
    elif menu == "📝 Drafting":
        render_drafting(user)
    elif menu == "📊 Analytics":
        render_analytics(user)
    elif menu == "⚙️ Settings":
        render_settings(user)


# ---------------------------
# DASHBOARD PAGE
# ---------------------------
def render_dashboard(user):
    st.markdown("# 🏠 Dashboard")
    st.markdown(f"Welcome back, **{user['username']}**!")
    
    # Stats Row
    stats = get_user_stats(user["id"])
    kb_status = get_knowledge_base_status(user["id"])
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        render_metric_card("Documents", str(stats["documents"]), "📄")
    with col2:
        render_metric_card("AI Queries", str(stats["queries"]), "💬")
    with col3:
        render_metric_card("KB Chunks", str(kb_status.get("total_chunks", 0)), "🧩")
    with col4:
        gen_status = cached_generator_status()
        status_icon = "✅" if gen_status["available"] else "❌"
        render_metric_card("LLM Status", status_icon, "🤖")
    
    st.markdown("---")
    
    # Quick Actions
    st.markdown("### ⚡ Quick Actions")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        if st.button("💬 Ask AI", use_container_width=True):
            st.session_state["nav"] = "💬 AI Assistant"
            st.rerun()
    
    with col2:
        if st.button("📤 Upload Docs", use_container_width=True):
            st.session_state["nav"] = "📂 Documents"
            st.rerun()
    
    with col3:
        if st.button("📝 Draft Document", use_container_width=True):
            st.session_state["nav"] = "📝 Drafting"
            st.rerun()
    
    with col4:
        if st.button("🔧 Legal Tools", use_container_width=True):
            st.session_state["nav"] = "🛠️ Legal Tools"
            st.rerun()
    
    st.markdown("---")
    
    # Recent Activity
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 📜 Recent Queries")
        history = get_chat_history(user["id"], limit=5)
        if history:
            for q, a, lang, created in history:
                with st.expander(f"🗨️ {q[:50]}..."):
                    st.write(a[:300] + "..." if len(a) > 300 else a)
                    st.caption(f"📅 {created[:10]}")
        else:
            st.info("No queries yet. Start asking questions!")
    
    with col2:
        st.markdown("### 📂 Recent Documents")
        docs = run_query(
            "SELECT filename, pages, uploaded_at FROM documents WHERE uploader_id = ? ORDER BY uploaded_at DESC LIMIT 5",
            (user["id"],), fetch=True
        )
        if docs:
            for fname, pages, uploaded in docs:
                st.markdown(f"📄 **{fname}** ({pages} pages)")
                st.caption(f"📅 {uploaded[:10]}")
        else:
            st.info("No documents uploaded yet.")

# ---------------------------
# AI ASSISTANT PAGE — SaaS-grade experience
# ---------------------------
def _run_chat_intelligence(
    user: dict,
    current_prompt: str,
    enriched_prompt: str,
    mode: str,
    lang: str,
    conversation_history: Optional[list] = None,
) -> tuple:
    """Execute KB / Web / Jurisprudence pipeline. Returns (response, similar_cases, web_sources)."""
    similar_cases: list = []
    web_sources: list = []
    history = conversation_history or []
    attachment = st.session_state.get("chat_attachment")

    if attachment and attachment.get("text"):
        ocr_context = attachment["text"]
        ocr_name = attachment.get("filename", "uploaded_image")
        if mode == "knowledge_base":
            response = query_from_ocr_attachment(
                current_prompt, ocr_context, ocr_name, conversation_history=history
            )
            similar_cases = [{
                "filename": ocr_name,
                "excerpt": ocr_context[:240] + ("..." if len(ocr_context) > 240 else ""),
                "relevance": "High",
                "score": "ocr",
                "chunk_index": 0,
            }]
        elif mode == "web_search":
            combined = f"{current_prompt}\n\n[OCR from {ocr_name}]:\n{ocr_context[:6000]}"
            response, web_sources = web_search_query(combined, conversation_history=history)
        elif mode == "deep_case":
            combined = f"{current_prompt}\n\n[OCR from {ocr_name}]:\n{ocr_context[:6000]}"
            response, kb_hits, web_sources = deep_case_query(user["id"], combined)
            similar_cases = [{
                "filename": ocr_name,
                "excerpt": ocr_context[:200] + "...",
                "relevance": "High",
            }]
        else:
            response = query_from_ocr_attachment(
                current_prompt, ocr_context, ocr_name, conversation_history=history
            )
    elif mode == "knowledge_base":
        response, similar_cases = rag_query(
            user["id"],
            current_prompt,
            k=14,
            find_similar_cases=True,
            conversation_history=history,
        )
        if str(response).startswith("NOT_FOUND_IN_KB"):
            response = KB_NOT_FOUND_MESSAGE
        elif str(response).startswith("### Knowledge Base Empty"):
            similar_cases = []
    elif mode == "web_search":
        response, web_sources = web_search_query(
            current_prompt, conversation_history=history
        )
    elif mode == "deep_case":
        response, kb_hits, web_sources = deep_case_query(user["id"], enriched_prompt)
        response = sanitize_assistant_response(
            response,
            fallback=_compose_web_answer_from_snippets(web_sources or [], enriched_prompt),
        )
        similar_cases = [
            {
                "filename": r.get("metadata", {}).get("filename", "doc"),
                "excerpt": (r.get("content", "") or "")[:200] + "...",
                "relevance": "High" if r.get("score", 1.0) < 0.3 else "Medium",
            }
            for r in kb_hits[:5]
        ]
    else:
        response = basic_query(current_prompt)

    response = sanitize_assistant_response(response)

    if lang != "English":
        try:
            lang_codes = {"Hindi": "hi", "Tamil": "ta", "Marathi": "mr", "Bengali": "bn", "Gujarati": "gu"}
            response = GoogleTranslator(source="auto", target=lang_codes.get(lang, "en")).translate(response)
        except Exception:
            pass

    return response, similar_cases, web_sources


def _complete_assistant_turn(user: dict, mode: str, lang: str) -> None:
    """Run backend after user message is already in session (never skip input dock)."""
    msgs = st.session_state.get("messages") or []
    if not msgs or msgs[-1].get("role") != "user":
        st.session_state["pending_assistant"] = False
        return

    current_prompt = msgs[-1].get("content", "").strip()
    prior = msgs[:-1]
    response, similar_cases, web_sources = _run_chat_intelligence(
        user, current_prompt, current_prompt, mode, lang, conversation_history=prior,
    )
    response = sanitize_assistant_response(response)
    saved = save_chat_message(user["id"], current_prompt, response, lang, mode)
    chat_id = saved.get("chat_id") if isinstance(saved, dict) else saved
    st.session_state["messages"].append({
        "role": "assistant",
        "content": response,
        "similar_cases": similar_cases,
        "web_sources": web_sources,
        "chat_id": chat_id,
        "question": current_prompt,
        "mode": mode,
        "feedback": None,
    })
    st.session_state["pending_assistant"] = False
    st.session_state["last_user_prompt"] = current_prompt
    st.session_state["last_follow_ups"] = suggest_follow_ups(
        current_prompt, response, mode
    )


def render_ai_assistant(user):
    inject_nuclear_layout_css()
    inject_chat_page_css()

    membership = user.get("membership", "Free")
    lang = st.session_state.get("chat_lang", "English")

    # 1) Suggestion pills / bridge — queue user turn
    apply_session_prompt_bridge()

    # 2) Header + mode pills (no Premium UI / duplicate New chat — use sidebar)
    h_left, h_mid = st.columns([2, 4])
    with h_left:
        st.markdown('<p class="le-chat-header-title">LegalEase Assistant</p>', unsafe_allow_html=True)
    with h_mid:
        mode = render_mode_pills(membership)

    render_chat_shell_start()

    # 3) Input first in code — sticky at bottom via CSS; captures send before thread paints
    user_query = render_input_dock(key_suffix=str(st.session_state.get("conversation_id", "main"))[:8])
    if user_query and (user_query := user_query.strip()):
        queue_user_message(user_query)
        st.session_state.pop("session_prompt_bridge", None)
        st.rerun()

    render_chat_messages_zone_start()

    msgs = st.session_state.get("messages") or []
    awaiting = (
        st.session_state.get("pending_assistant")
        and msgs
        and msgs[-1].get("role") == "user"
    )

    # 4) Show user message immediately; skeleton on left while thinking
    render_chat_viewport(msgs, show_loading=awaiting)

    # 5) Action pills after assistant replied (not while loading)
    if msgs and msgs[-1].get("role") == "assistant" and not awaiting:
        last_q = msgs[-1].get("question") or ""
        if not last_q:
            for m in reversed(msgs[:-1]):
                if m.get("role") == "user":
                    last_q = m.get("content", "")
                    break
        render_action_pills(
            st.session_state.get("last_follow_ups")
            or suggest_follow_ups(last_q, msgs[-1].get("content", ""), mode)
        )

    render_chat_messages_zone_end()

    # 6) Generate assistant reply after user message is visible
    if awaiting:
        _complete_assistant_turn(user, mode, lang)
        st.rerun()

    render_chat_shell_end()
    inject_chat_scroll_script()


# ---------------------------
# DOCUMENTS PAGE
# ---------------------------
def render_documents(user):
    st.markdown("# 📂 Document Management")
    render_kb_health_panel(user["id"], st.session_state.get("last_kb_error"))
    
    membership = user.get("membership", "Free")
    current_count = get_user_document_count(user["id"])
    
    # Quota Display
    if membership == "Free":
        st.warning(f"📊 **Free Plan:** {current_count}/2 documents uploaded")
    else:
        st.success(f"📊 **{membership} Plan:** {current_count} documents (Unlimited)")
    
    st.markdown("---")
    doc_col1, doc_col2 = st.columns(2)

    with doc_col1:
        with st.expander("📤 Upload Documents", expanded=True):
            uploaded_files = st.file_uploader(
                "Upload PDF Documents",
                type=["pdf"],
                accept_multiple_files=True,
                help="Upload legal documents for AI analysis"
            )

            if uploaded_files:
                if membership == "Free" and current_count + len(uploaded_files) > 2:
                    st.error("🚫 Free plan limit reached. Upgrade to Pro for unlimited uploads.")
                else:
                    if st.button("📥 Upload & Process", use_container_width=True):
                        progress = st.progress(0)
                        uploaded_ok = 0
                        for idx, file in enumerate(uploaded_files):
                            try:
                                save_uploaded_pdf(file, user["id"])
                                uploaded_ok += 1  # duplicates still count as handled
                            except Exception as exc:
                                st.error(str(exc))
                            progress.progress((idx + 1) / len(uploaded_files))
                        if uploaded_ok:
                            progress_text = st.empty()
                            ok, msg = build_faiss_index(user["id"], progress_callback=lambda t: progress_text.text(t))
                            if ok:
                                st.success(f"✅ Uploaded and indexed {uploaded_ok} file(s). {msg}")
                            else:
                                st.warning(f"Uploaded {uploaded_ok} file(s), but indexing needs attention: {msg}")

    with doc_col2:
        with st.expander("🔄 Build Knowledge Base", expanded=True):
            st.info("Index your documents to enable AI search (RAG)")
            if st.button("🔄 Index All Documents", use_container_width=True):
                progress_text = st.empty()
                progress_bar = st.progress(0)

                ok, msg = build_faiss_index(user["id"], progress_callback=lambda t: progress_text.text(t))
                progress_bar.progress(1.0)

                if ok:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"❌ {msg}")
    
    st.markdown("---")
    
    # Document List
    st.markdown("### 📋 Your Documents")
    
    docs = run_query(
        "SELECT id, filename, pages, uploaded_at FROM documents WHERE uploader_id = ? ORDER BY uploaded_at DESC",
        (user["id"],), fetch=True
    )
    
    if docs:
        for doc_id, filename, pages, uploaded in docs:
            with st.expander(f"📄 {filename} ({pages} pages)"):
                st.caption(f"Uploaded: {uploaded[:10]}")
                
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    if st.button("📊 Extract Timeline", key=f"timeline_{doc_id}"):
                        events = run_query(
                            "SELECT event_date, mention_text FROM document_timeline WHERE document_id = ? ORDER BY event_date",
                            (doc_id,), fetch=True
                        )
                        if events:
                            for date, text in events:
                                st.markdown(f"**{date}:** {text[:100]}...")
                        else:
                            st.info("No timeline events found")
                
                with col2:
                    if st.button("👥 Extract Entities", key=f"entities_{doc_id}"):
                        entities = run_query(
                            "SELECT plaintiff, defendant, judge, court, sections FROM case_entities WHERE document_id = ? LIMIT 1",
                            (doc_id,), fetch=True
                        )
                        if entities:
                            ent = entities[0]
                            st.write(f"**Plaintiff:** {ent[0] or 'N/A'}")
                            st.write(f"**Defendant:** {ent[1] or 'N/A'}")
                            st.write(f"**Judge:** {ent[2] or 'N/A'}")
                            st.write(f"**Court:** {ent[3] or 'N/A'}")
                            st.write(f"**Sections:** {ent[4] or 'N/A'}")
                        else:
                            st.info("No entities extracted")
                
                with col3:
                    if st.button("🗑️ Delete", key=f"delete_{doc_id}"):
                        if delete_user_document(doc_id, user["id"]):
                            build_faiss_index(user["id"])
                            st.success("Deleted and refreshed the knowledge base.")
                        else:
                            st.error("Document not found.")
                        st.rerun()
    else:
        st.info("📭 No documents uploaded yet")

# ---------------------------
# LEGAL TOOLS PAGE
# ---------------------------
def render_legal_tools(user):
    st.markdown("# 🛠️ Legal Tools")
    
    tool_tabs = st.tabs([
        "🔄 IPC-BNS Converter",
        "💰 Court Fee Calculator",
        "📋 Contract Review",
        "📈 Case Prediction",
        "✅ Smart Citator",
        "🤝 ODR Platform"
    ])
    
    # IPC-BNS Converter
    with tool_tabs[0]:
        st.markdown("### 🔄 IPC to BNS Converter")
        st.info("Convert Indian Penal Code sections to Bharatiya Nyaya Sanhita")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Single Conversion")
            ipc_section = st.text_input("Enter IPC Section (e.g., 302, 420)", placeholder="302")
            if st.button("Convert", key="convert_single"):
                if ipc_section:
                    result = convert_ipc_to_bns(ipc_section)
                    if result["status"] == "mapped":
                        st.success(f"✅ **{result['ipc_section']}** → **{result['bns_section']}**")
                        st.write(f"*{result['description']}*")
                    else:
                        st.warning(f"Section {ipc_section} not found in database")
        
        with col2:
            st.markdown("#### Bulk Conversion")
            sections_input = st.text_area("Enter sections (comma-separated)", placeholder="302, 420, 376, 498A")
            if st.button("Convert All", key="convert_bulk"):
                if sections_input:
                    sections = [s.strip() for s in sections_input.split(",")]
                    results = bulk_ipc_to_bns_convert(sections)
                    
                    df = pd.DataFrame([
                        {"IPC": r["ipc_section"], "BNS": r["bns_section"], "Description": r["description"]}
                        for r in results
                    ])
                    st.dataframe(df, use_container_width=True)
        
        st.markdown("---")
        st.markdown("#### Browse by Category")
        category = st.selectbox("Select Category", ["murder", "theft", "robbery", "assault", "sexual_offenses", "cheating", "forgery", "defamation", "kidnapping", "dowry", "trespass"])
        if st.button("Show Sections"):
            sections = get_bns_by_category(category)
            if sections:
                df = pd.DataFrame(sections)
                st.dataframe(df, use_container_width=True)
    
    # Court Fee Calculator
    with tool_tabs[1]:
        st.markdown("### 💰 Court Fee Calculator")
        st.info("Calculate Ad Valorem court fees for Indian jurisdictions")
        
        col1, col2 = st.columns(2)
        
        with col1:
            suit_value = st.number_input("Suit Value (₹)", min_value=0.0, value=100000.0, step=10000.0)
            region = st.selectbox("State/Jurisdiction", get_available_regions())
        
        with col2:
            suit_type = st.selectbox("Suit Type", ["Civil", "Appeal", "Revision", "Divorce", "Succession"])
            court_level = st.selectbox("Court Level", ["District", "High", "Supreme"])
        
        if st.button("Calculate Fee", use_container_width=True):
            breakdown = get_fee_breakdown(suit_value, region.lower().replace(" ", "_"), suit_type.lower(), court_level.lower())
            
            st.markdown(f"""
            <div class="pro-card">
                <h2 style="color: #f59e0b;">₹{breakdown['final_fee']:,.2f}</h2>
                <p>Estimated Court Fee</p>
            </div>
            """, unsafe_allow_html=True)
            
            with st.expander("📊 Fee Breakdown"):
                st.write(f"**Base Fee:** ₹{breakdown['base_fee']:,.2f}")
                st.write(f"**Multiplier:** {breakdown['multiplier']}x ({breakdown['multiplier_reason']})")
                st.write(f"**Adjusted Fee:** ₹{breakdown['adjusted_fee']:,.2f}")
                st.write(f"**Min/Max:** ₹{breakdown['minimum_fee']} - ₹{breakdown['maximum_fee']}")
                
                st.markdown("**Slab Breakdown:**")
                for slab in breakdown['slab_breakdown']:
                    st.write(f"- {slab['slab']}: {slab['rate']} = ₹{slab['fee']:,.2f}")
    
    # Contract Review
    with tool_tabs[2]:
        st.markdown("### 📋 AI Contract Review")
        st.info("Upload a contract for AI-powered risk analysis")
        
        contract_file = st.file_uploader("Upload Contract (PDF)", type=["pdf"], key="contract_upload")
        
        if contract_file:
            text = ""
            try:
                reader = PdfReader(contract_file)
                for page in reader.pages:
                    t = page.extract_text()
                    if t:
                        text += t + "\n"
            except Exception:
                st.error("Could not read PDF")
            
            if text and st.button("🔍 Analyze Contract", use_container_width=True):
                with st.spinner("Analyzing contract..."):
                    analysis = analyze_contract(text)
                    st.markdown(analysis)
    
    # Case Prediction
    with tool_tabs[3]:
        st.markdown("### 📈 Case Outcome Prediction")
        st.warning("⚠️ AI predictions are for informational purposes only")
        
        case_details = st.text_area("Describe your case", height=200, placeholder="Enter case facts, charges, evidence...")
        court_type = st.selectbox("Court Type", ["District Court", "High Court", "Supreme Court", "Consumer Forum", "Labour Court"])
        
        if st.button("🔮 Predict Outcome", use_container_width=True):
            if case_details:
                with st.spinner("Analyzing case..."):
                    prediction = predict_case_outcome(case_details, court_type)
                    st.markdown(prediction)
    
    # Smart Citator
    with tool_tabs[4]:
        st.markdown("### ✅ Smart Citator")
        st.info("Check if case citations are still valid (Good Law vs Bad Law)")
        
        citations_input = st.text_area("Enter case citations (one per line)", height=150, placeholder="AIR 2020 SC 1234\n(2019) 5 SCC 123")
        
        if st.button("🔍 Check Citations", use_container_width=True):
            if citations_input:
                citations = [c.strip() for c in citations_input.split("\n") if c.strip()]
                with st.spinner("Checking citations..."):
                    result = check_citation_validity(citations)
                    st.markdown(result)
    
    # ODR Platform
    with tool_tabs[5]:
        st.markdown("### 🤝 Online Dispute Resolution")
        st.info("Resolve minor disputes without going to court")
        
        col1, col2 = st.columns(2)
        
        with col1:
            complainant = st.text_input("Complainant Name")
            complaint_type = st.selectbox("Dispute Type", ["E-commerce Refund", "Service Complaint", "Small Claims", "Consumer Issue", "Contract Dispute"])
        
        with col2:
            respondent = st.text_input("Respondent Name")
            dispute_value = st.number_input("Dispute Value (₹)", min_value=0.0, value=10000.0)
        
        dispute_details = st.text_area("Describe the dispute", height=150)
        
        if st.button("📝 Generate Resolution Proposal", use_container_width=True):
            if complainant and respondent and dispute_details:
                with st.spinner("Generating proposal..."):
                    result = generate_odr_resolution({
                        "complainant": complainant,
                        "respondent": respondent,
                        "type": complaint_type,
                        "value": dispute_value,
                        "details": dispute_details
                    })
                    st.markdown(result)


# ---------------------------
# DRAFTING PAGE
# ---------------------------
def render_drafting(user):
    st.markdown("# 📝 Automated Legal Drafter")
    st.info("Generate professional legal documents instantly")
    
    # Template Selection
    templates = get_available_templates()
    template_info = {
        "LEGAL_NOTICE": ("📨", "Legal notice for disputes and demands"),
        "AFFIDAVIT": ("📜", "Sworn statement for court proceedings"),
        "CHARGESHEET": ("⚖️", "Police chargesheet for prosecution"),
        "CONTRACT": ("📋", "Business agreement between parties"),
        "BAIL_APPLICATION": ("🔓", "Application for bail in criminal cases")
    }
    
    st.markdown("### 📑 Select Document Type")
    
    cols = st.columns(3)
    for idx, template in enumerate(templates):
        with cols[idx % 3]:
            icon, desc = template_info.get(template, ("📄", "Legal document"))
            if st.button(f"{icon} {template.replace('_', ' ').title()}", key=f"tmpl_{template}", use_container_width=True):
                st.session_state["selected_template"] = template
    
    selected = st.session_state.get("selected_template", "LEGAL_NOTICE")
    
    st.markdown("---")
    st.markdown(f"### ✏️ Fill Details for {selected.replace('_', ' ').title()}")
    
    # Get template fields
    fields = get_template_fields(selected)
    context = {}
    
    # Dynamic form based on template
    if selected == "LEGAL_NOTICE":
        col1, col2 = st.columns(2)
        with col1:
            context["client_name"] = st.text_input("Your Name (Client)")
            context["client_address"] = st.text_area("Your Address", height=80)
            context["advocate_name"] = st.text_input("Advocate Name")
            context["advocate_enrollment"] = st.text_input("Advocate Enrollment No.")
        with col2:
            context["recipient_name"] = st.text_input("Recipient Name")
            context["recipient_address"] = st.text_area("Recipient Address", height=80)
            context["subject"] = st.text_input("Subject of Notice")
            context["notice_period"] = st.number_input("Notice Period (days)", value=15)
        context["facts"] = st.text_area("Facts of the Case", height=150)
        context["legal_grounds"] = st.text_area("Legal Grounds", height=100)
        context["demands"] = st.text_area("Demands", height=100)
    
    elif selected == "AFFIDAVIT":
        col1, col2 = st.columns(2)
        with col1:
            context["deponent_name"] = st.text_input("Deponent Name")
            context["deponent_relation"] = st.selectbox("Relation", ["S/o", "D/o", "W/o"])
            context["deponent_father"] = st.text_input("Father's/Husband's Name")
        with col2:
            context["deponent_age"] = st.number_input("Age", min_value=18, value=30)
            context["deponent_address"] = st.text_area("Address", height=80)
            context["deponent_capacity"] = st.text_input("Capacity (e.g., Petitioner, Applicant)")
        context["affidavit_content"] = st.text_area("Affidavit Content (numbered paragraphs)", height=200)
        context["verification_place"] = st.text_input("Verification Place")
    
    elif selected == "CONTRACT":
        col1, col2 = st.columns(2)
        with col1:
            context["party_a_name"] = st.text_input("First Party Name")
            context["party_a_address"] = st.text_area("First Party Address", height=80)
            context["party_a_pan"] = st.text_input("First Party PAN")
        with col2:
            context["party_b_name"] = st.text_input("Second Party Name")
            context["party_b_address"] = st.text_area("Second Party Address", height=80)
            context["party_b_pan"] = st.text_input("Second Party PAN")
        context["recitals"] = st.text_area("Recitals (Background)", height=100)
        context["scope"] = st.text_area("Scope of Agreement", height=100)
        context["consideration"] = st.text_area("Consideration/Payment Terms", height=100)
        col1, col2 = st.columns(2)
        with col1:
            context["start_date"] = st.date_input("Start Date").strftime("%d-%m-%Y")
        with col2:
            context["end_date"] = st.date_input("End Date").strftime("%d-%m-%Y")
        context["arbitration_seat"] = st.text_input("Arbitration Seat", value="New Delhi")
        context["jurisdiction"] = st.text_input("Jurisdiction", value="New Delhi")
    
    else:
        # Generic form for other templates
        for field in fields[:15]:  # Limit to 15 fields
            if field not in ["date", "time"]:
                context[field] = st.text_input(field.replace("_", " ").title())
    
    st.markdown("---")
    
    # Generate Button
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("📝 Generate Draft", use_container_width=True):
            with st.spinner("Generating document..."):
                draft = generate_draft(selected, context, use_ai=False)
                st.session_state["generated_draft"] = draft
    
    with col2:
        if st.button("🤖 AI-Enhanced Draft", use_container_width=True):
            context["enhance_with_ai"] = True
            with st.spinner("AI is enhancing your draft..."):
                draft = generate_draft(selected, context, use_ai=True)
                st.session_state["generated_draft"] = draft
    
    # Display Generated Draft
    if "generated_draft" in st.session_state:
        st.markdown("### 📄 Generated Document")
        st.text_area("Preview", st.session_state["generated_draft"], height=400)
        
        col1, col2 = st.columns(2)
        with col1:
            # Download as text
            st.download_button(
                "📥 Download as TXT",
                st.session_state["generated_draft"],
                file_name=f"{selected}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        with col2:
            # Save to database
            if st.button("💾 Save Draft", use_container_width=True):
                run_query(
                    "INSERT INTO drafts (id, user_id, draft_type, content, created_at) VALUES (?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), user["id"], selected, st.session_state["generated_draft"], _utc_iso())
                )
                st.success("✅ Draft saved!")

# ---------------------------
# ANALYTICS PAGE
# ---------------------------
def render_analytics(user):
    st.markdown("# 📊 Analytics Dashboard")
    
    # User Stats
    stats = get_user_stats(user["id"])
    
    col1, col2, col3 = st.columns(3)
    with col1:
        render_metric_card("Total Documents", str(stats["documents"]), "📄")
    with col2:
        render_metric_card("AI Queries", str(stats["queries"]), "💬")
    with col3:
        kb_status = get_knowledge_base_status(user["id"])
        render_metric_card("KB Status", kb_status["status"].title(), "🧩")
    
    st.markdown("---")
    
    # Query History Chart
    st.markdown("### 📈 Query Activity")
    
    history = run_query(
        "SELECT DATE(created_at) as date, COUNT(*) as count FROM chat_history WHERE user_id = ? GROUP BY DATE(created_at) ORDER BY date DESC LIMIT 30",
        (user["id"],), fetch=True
    )
    
    if history and pd is not None and px is not None and st is not None:
        df = pd.DataFrame(history, columns=["Date", "Queries"])
        fig = px.bar(df, x="Date", y="Queries", title="Daily Query Activity")
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    elif history and st is not None:
        st.info("Charts require pandas/plotly (not installed in API image).")
    elif st is not None:
        st.info("No query data yet")
    
    # Mode Distribution
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### 🎯 Query Mode Distribution")
        mode_data = run_query(
            "SELECT mode, COUNT(*) FROM chat_history WHERE user_id = ? GROUP BY mode",
            (user["id"],), fetch=True
        )
        if mode_data and pd is not None and px is not None and st is not None:
            df = pd.DataFrame(mode_data, columns=["Mode", "Count"])
            fig = px.pie(df, values="Count", names="Mode", title="Queries by Mode")
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        st.markdown("### 🌐 Language Distribution")
        lang_data = run_query(
            "SELECT language, COUNT(*) FROM chat_history WHERE user_id = ? GROUP BY language",
            (user["id"],), fetch=True
        )
        if lang_data and pd is not None and px is not None and st is not None:
            df = pd.DataFrame(lang_data, columns=["Language", "Count"])
            fig = px.pie(df, values="Count", names="Language", title="Queries by Language")
            st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# SETTINGS PAGE
# ---------------------------
def render_settings(user):
    st.markdown("# ⚙️ Account Settings")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.markdown("### 👤 Profile")
        st.markdown(f"**Username:** {user['username']}")
        st.markdown(f"**Role:** {user.get('role', 'user')}")
        
        membership = user.get("membership", "Free")
        badge_colors = {"Free": "#94a3b8", "Pro": "#3b82f6", "Legal Pro": "#f59e0b"}
        st.markdown(f"""
        <span class="status-badge" style="background: {badge_colors.get(membership, '#94a3b8')}20; color: {badge_colors.get(membership, '#94a3b8')};">
            {membership}
        </span>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown("### 💳 Upgrade Plan")
        
        if membership == "Free":
            st.markdown("""
            <div class="pro-card" style="background: linear-gradient(135deg, #3b82f6, #1e40af);">
                <h3>🚀 Upgrade to Pro</h3>
                <p>Unlimited documents, Jurisprudence Engine, Priority support</p>
                <h2>₹999/year</h2>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("⬆️ Upgrade to Pro", use_container_width=True):
                success, _ = process_payment(user["id"], "Pro", 999.0)
                if success:
                    st.success("✅ Upgraded to Pro!")
                    st.session_state["user"]["membership"] = "Pro"
                    st.rerun()
        
        elif membership == "Pro":
            st.markdown("""
            <div class="pro-card" style="background: linear-gradient(135deg, #f59e0b, #d97706);">
                <h3>👑 Upgrade to Legal Pro</h3>
                <p>Team collaboration, Advanced analytics, White-label options</p>
                <h2>₹4999/year</h2>
            </div>
            """, unsafe_allow_html=True)
            
            if st.button("⬆️ Upgrade to Legal Pro", use_container_width=True):
                success, _ = process_payment(user["id"], "Legal Pro", 4999.0)
                if success:
                    st.success("✅ Upgraded to Legal Pro!")
                    st.session_state["user"]["membership"] = "Legal Pro"
                    st.rerun()
        
        else:
            st.success("👑 You have the highest plan!")
    
    st.markdown("---")
    
    # Payment History
    st.markdown("### 💳 Payment History")
    payments = get_payment_history(user["id"])
    if payments:
        df = pd.DataFrame(payments, columns=["Plan", "Amount", "Status", "Date", "Expires"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No payment history")
    
    st.markdown("---")
    
    # LLM Status
    st.markdown("### 🤖 LLM Configuration")
    gen_status = cached_generator_status()
    backend_name = gen_status.get("backend", "LLM")
    is_ollama = str(backend_name).lower() == "ollama"
    default_url = "http://127.0.0.1:11434" if is_ollama else DEFAULT_LM_STUDIO_URL
    default_api = default_url if is_ollama else (default_url + "/v1")

    col1, col2 = st.columns(2)
    with col1:
        st.write(f"**Backend:** {backend_name}")
        st.write(f"**Configured Model:** `{gen_status.get('model', 'Unknown')}`")
        if st.button("🔁 Recheck Backend", use_container_width=True):
            reset_generator()
            cached_generator_status.clear()
            st.rerun()
        if st.button("🧪 Send Test Prompt", use_container_width=True):
            if not gen_status.get("available"):
                st.error(f"{backend_name} is not connected. Fix the connection first.")
            else:
                with st.spinner(f"Calling {backend_name}..."):
                    try:
                        reply = get_generator().generate(
                            "Reply with the single word PONG.",
                            temperature=0.0,
                            max_tokens=16,
                        )
                        st.success(f"{backend_name} replied: {reply[:200]}")
                    except Exception as exc:
                        st.error(f"Test call failed: {exc}")
    with col2:
        st.write(f"**Configured URL:** `{gen_status.get('configured_url', default_url)}`")
        st.write(f"**API URL:** `{gen_status.get('base_url', default_api)}`")
        st.caption(f"Chat endpoint: `{gen_status.get('chat_endpoint', 'Not selected')}`")
        if gen_status.get("available"):
            st.success(f"🟢 Connected to {backend_name}")
        else:
            st.error(f"🔴 {gen_status.get('message', 'Not connected')}")

    # Detailed diagnostics
    with st.expander(f"🔍 {backend_name} Diagnostics", expanded=not gen_status.get("available")):
        if gen_status.get("available"):
            models = gen_status.get("available_models") or []
            if models:
                st.markdown(f"**Models loaded in {backend_name}:**")
                for m in models:
                    marker = "✅" if m == gen_status.get("model") else "•"
                    st.markdown(f"- {marker} `{m}`")
                if not gen_status.get("model_loaded"):
                    if is_ollama:
                        st.warning(
                            f"Your configured model `{gen_status.get('model')}` is NOT one of the models available in Ollama. "
                            "Run `ollama list` and set OLLAMA_MODEL in .env to one of those names."
                        )
                    else:
                        st.warning(
                            f"Your configured model `{gen_status.get('model')}` is NOT one of the loaded models. "
                            "Either load it in LM Studio (Models → load) or change LM_STUDIO_MODEL in .env to one of the names above."
                        )
            else:
                if is_ollama:
                    st.info("Ollama is reachable but did not report any models. Run `ollama pull <model>` and retry.")
                else:
                    st.info("LM Studio is reachable but did not report any loaded models. Open LM Studio → Local Server → Load a model.")
        else:
            errors = gen_status.get("probe_errors") or []
            if errors:
                st.markdown("**Probe attempts (most recent first):**")
                for line in errors:
                    st.markdown(f"- `{line}`")
            if is_ollama:
                st.markdown(
                    "**Fix checklist:**\n"
                    "1. Ensure Ollama service is running.\n"
                    "2. Run `ollama list` to confirm the model exists.\n"
                    f"3. From this PC, open the URL in a browser: {gen_status.get('configured_url', '')}/api/tags. You should see JSON.\n"
                    "4. Set `LLM_BACKEND=ollama` and `OLLAMA_MODEL=<your-model>` in `.env`.\n"
                    "5. After fixing, click **Recheck Backend** above."
                )
            else:
                st.markdown(
                    "**Fix checklist:**\n"
                    "1. Open **LM Studio → Local Server** tab, load a model, then click **Start Server**.\n"
                    f"2. From this PC, open the URL in a browser: {gen_status.get('configured_url', '')}/v1/models. You should see a JSON list.\n"
                    "3. If LM Studio runs on this same PC, set `LM_STUDIO_URL=http://127.0.0.1:1234` in `.env`.\n"
                    "4. If LM Studio runs on a different PC, allow inbound TCP 1234 in Windows Firewall on that PC and make sure both machines are on the same network.\n"
                    "5. After fixing, click **Recheck Backend** above."
                )

    st.markdown("---")
    st.markdown("### 🌐 Web Intelligence")
    ws = web_search_status()
    if ws.get("tavily_mcp"):
        st.success("🟢 Tavily MCP connected (strict legal search)")
    elif ws.get("tavily_configured"):
        st.success("🟢 Tavily REST configured")
    else:
        st.warning("🟡 Tavily not configured — set TAVILY_API_KEY in .env")
    st.caption(
        f"Provider order: {ws.get('preferred_order', 'Tavily MCP first')} · "
        f"Legal-only filter: {'on' if ws.get('legal_only_web') else 'off'}"
    )
    ocr = ocr_status()
    st.markdown("### 🔍 OCR")
    if ocr.get("enabled"):
        st.success(f"🟢 EasyOCR enabled · languages: {', '.join(ocr.get('languages', []))}")
    else:
        st.warning("🟡 OCR disabled — set OCR_ENABLED=1 in .env")

# ---------------------------
# RUN APPLICATION
# ---------------------------
if __name__ == "__main__":
    main()
