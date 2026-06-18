"""
LegalEase.AI — Production API + static React app.
Run: py -m uvicorn api_server:app --reload --port 8000
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from auth_tokens import create_access_token, decode_access_token

load_dotenv()

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="LegalEase API", version="2.0.0")
_bearer = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:5174,http://127.0.0.1:5174,"
        "http://localhost:5175,http://127.0.0.1:5175,"
        "http://localhost:8000,http://127.0.0.1:8000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _UploadAdapter:
    """Mimics Streamlit UploadedFile for save_uploaded_pdf."""

    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getbuffer(self):
        return memoryview(self._data)


@app.on_event("startup")
def _startup():
    from legalease_auth import ensure_db
    ensure_db()


def _current_user(
    creds: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> Dict[str, Any]:
    if not creds or creds.scheme.lower() != "bearer":
        raise HTTPException(401, "Not authenticated")
    payload = decode_access_token(creds.credentials)
    if not payload or not payload.get("sub"):
        raise HTTPException(401, "Invalid or expired token")
    return {
        "id": payload["sub"],
        "username": payload.get("username", ""),
        "membership": payload.get("membership", "Free"),
        "role": payload.get("role", "user"),
    }


# ---------- Auth ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirm_password: str


class AuthResponse(BaseModel):
    token: str
    user: Dict[str, Any]


@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest):
    from app import authenticate_user
    user = authenticate_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(401, "Invalid username or password")
    token = create_access_token(user)
    return AuthResponse(token=token, user=user)


@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    from legalease_auth import authenticate_user, create_user
    if req.password != req.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if not create_user(req.username.strip(), req.password):
        raise HTTPException(400, "Username invalid or already taken")
    user = authenticate_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(500, "Registration succeeded but login failed")
    return AuthResponse(token=create_access_token(user), user=user)


@app.get("/api/auth/me")
def me(user: Dict = Depends(_current_user)):
    return {"user": user}


# ---------- System status ----------

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "LegalEase API"}


@app.get("/api/status")
def system_status():
    from llms import generator_status, web_search_status
    from ocr_engine import ocr_status
    gen = generator_status()
    ws = web_search_status()
    ocr = ocr_status()
    return {
        "llm": {
            "online": bool(gen.get("online")),
            "label": gen.get("message") or gen.get("status", "unknown"),
            "model": gen.get("model"),
        },
        "web_search": {
            "configured": bool(ws.get("tavily_configured") or ws.get("google_configured")),
            "legal_only": ws.get("legal_only_web", True),
        },
        "ocr": {"enabled": ocr.get("enabled", False)},
    }


# ---------- Dashboard ----------

@app.get("/api/dashboard")
def dashboard(user: Dict = Depends(_current_user)):
    from app import get_user_stats, get_user_document_count, get_knowledge_base_status
    stats = get_user_stats(user["id"])
    doc_count = get_user_document_count(user["id"])
    kb = get_knowledge_base_status(user["id"]) or {}
    return {
        "username": user["username"],
        "membership": user["membership"],
        "documents": stats.get("documents", doc_count),
        "queries": stats.get("queries", 0),
        "kb_status": kb.get("status", "unknown"),
        "kb_chunks": kb.get("total_chunks", 0),
    }


# ---------- Chat history ----------

@app.get("/api/chat/history")
def chat_history(limit: int = 12, user: Dict = Depends(_current_user)):
    from app import get_chat_history
    rows = get_chat_history(user["id"], limit=limit) or []
    sessions = []
    for q, a, lang, created in rows:
        sessions.append({
            "question": (q or "")[:80],
            "preview": (a or "")[:120],
            "language": lang,
            "created_at": created,
        })
    return {"sessions": sessions}


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    mode: str = "knowledge_base"
    lang: str = "English"
    history: List[ChatMessage] = Field(default_factory=list)
    attachment: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    content: str
    similar_cases: List[dict] = Field(default_factory=list)
    web_sources: List[dict] = Field(default_factory=list)
    follow_ups: List[str] = Field(default_factory=list)
    chat_id: Optional[str] = None


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest, user: Dict = Depends(_current_user)):
    if not req.message.strip():
        raise HTTPException(400, "message is required")
    mode = req.mode if req.mode in ("knowledge_base", "web_search", "deep_case") else "knowledge_base"
    if mode == "deep_case" and user.get("membership") not in ("Pro", "Legal Pro"):
        mode = "knowledge_base"
    history = [{"role": m.role, "content": m.content} for m in req.history]

    try:
        from chat_service import run_chat_turn
        from saas_chat import suggest_follow_ups
        from app import save_chat_message

        content, similar_cases, web_sources = run_chat_turn(
            user["id"],
            req.message.strip(),
            mode,
            lang=req.lang,
            conversation_history=history,
            attachment=req.attachment,
        )
        chat_id = save_chat_message(
            user["id"], req.message.strip(), content, req.lang, mode
        )
        follow_ups = suggest_follow_ups(req.message, content, mode)
        return ChatResponse(
            content=content,
            similar_cases=similar_cases or [],
            web_sources=web_sources or [],
            follow_ups=follow_ups,
            chat_id=chat_id,
        )
    except Exception as exc:
        raise HTTPException(500, str(exc)) from exc


# ---------- OCR attach ----------

@app.post("/api/ocr")
async def ocr_image(file: UploadFile = File(...), user: Dict = Depends(_current_user)):
    from ocr_engine import extract_text_from_image_bytes
    data = await file.read()
    text, _ = extract_text_from_image_bytes(data, file.filename or "upload.png")
    if not text.strip():
        raise HTTPException(400, "No text found in image")
    return {
        "filename": file.filename,
        "text": text,
        "chars": len(text),
    }


# ---------- Documents ----------

@app.get("/api/documents")
def list_documents(user: Dict = Depends(_current_user)):
    from app import run_query, get_user_document_count, MAX_UPLOAD_MB
    rows = run_query(
        "SELECT id, filename, pages, uploaded_at FROM documents WHERE uploader_id = ? ORDER BY uploaded_at DESC",
        (user["id"],),
        fetch=True,
    ) or []
    return {
        "documents": [
            {"id": r[0], "filename": r[1], "pages": r[2], "uploaded_at": r[3]}
            for r in rows
        ],
        "count": get_user_document_count(user["id"]),
        "max_upload_mb": MAX_UPLOAD_MB,
        "membership": user["membership"],
        "free_limit": 2,
    }


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: Dict = Depends(_current_user),
):
    from app import save_uploaded_pdf, get_user_document_count, build_faiss_index, MAX_UPLOAD_MB
    from backend.app.api.v1.endpoints.documents import _detect_upload_kind

    data_peek = await file.read()
    if not data_peek:
        raise HTTPException(400, "Empty file.")
    try:
        _kind, safe_name = _detect_upload_kind(
            file.filename or "",
            file.content_type or "",
            data_peek,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    data = data_peek
    if user.get("membership") == "Free" and get_user_document_count(user["id"]) >= 2:
        raise HTTPException(403, "Free plan allows 2 documents. Upgrade to Pro for unlimited.")
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {MAX_UPLOAD_MB} MB limit")
    try:
        adapter = _UploadAdapter(safe_name, data)
        file_id, _, pages, _dup = save_uploaded_pdf(adapter, user["id"])
        build_faiss_index(user["id"])
        return {"id": file_id, "filename": file.filename, "pages": pages, "indexed": True}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/api/documents/index")
def reindex_documents(user: Dict = Depends(_current_user)):
    from app import build_faiss_index
    try:
        build_faiss_index(user["id"])
        return {"status": "ok", "message": "Knowledge base indexed"}
    except Exception as e:
        raise HTTPException(500, str(e)) from e


# ---------- Static React (production) ----------

if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="static")
