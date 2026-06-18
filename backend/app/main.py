"""
LegalEase Production API — FastAPI entry point.
Run: py -m uvicorn backend.app.main:app --reload --port 8000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
LEGACY = ROOT / "legacy_saas"
for p in (str(ROOT), str(LEGACY)):
    if p not in sys.path:
        sys.path.insert(0, p)

load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "backend" / ".env")
# Laptop only: require LEGALEEASE_LOCAL_DEV=1 (set by apply_local_env.ps1). Never auto-load
# .env.local just because the file exists — that breaks EC2 if a laptop file was copied up.
_local_env = ROOT / ".env.local"
if os.getenv("LEGALEEASE_LOCAL_DEV", "").lower() in ("1", "true", "yes") and _local_env.is_file():
    load_dotenv(_local_env, override=True)

_sentry_dsn = os.getenv("SENTRY_DSN", "").strip()
if _sentry_dsn:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        sentry_sdk.init(
            dsn=_sentry_dsn,
            integrations=[FastApiIntegration()],
            traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1")),
            environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        )
    except Exception:
        pass

from backend.app.api.v1.router import api_router
from backend.app.core.admin_auth import require_superadmin
from backend.app.core.auth import get_current_user
from backend.app.core.config import cors_middleware_kwargs

app = FastAPI(title="LegalEase API", version="3.0.0")

from backend.app.core.startup_state import get_startup_snapshot, update_startup_snapshot

try:
    from .middleware.memory_guard import MemoryEfficiencyMiddleware

    app.add_middleware(MemoryEfficiencyMiddleware)
except Exception:
    pass

try:
    from .middleware.rate_limit import RateLimitMiddleware

    app.add_middleware(RateLimitMiddleware)
except Exception:
    pass

try:
    from .middleware.request_guard import RequestGuardMiddleware

    app.add_middleware(RequestGuardMiddleware)
except Exception:
    pass

try:
    from .middleware.ip_firewall import IPFirewallMiddleware

    app.add_middleware(IPFirewallMiddleware)
except Exception:
    pass

try:
    from .middleware.security_headers import SecurityHeadersMiddleware

    app.add_middleware(SecurityHeadersMiddleware)
except Exception:
    pass

app.add_middleware(CORSMiddleware, **cors_middleware_kwargs())


@app.get("/api/v1/health/gpu")
@app.get("/api/health/gpu")
async def health_gpu_public():
    """GPU / STT / embedding accelerator status (no auth)."""
    from fastapi.concurrency import run_in_threadpool
    from backend.app.core.gpu_runtime import get_runtime_accelerator_status

    return await run_in_threadpool(get_runtime_accelerator_status)


@app.get("/api/v1/health/live")
@app.get("/api/health/live")
async def health_live():
    """Instant liveness probe — async so it never queues behind indexing threadpool work."""
    return {"status": "ok", "service": "LegalEase API", "live": True}


@app.get("/api/v1/health/security")
@app.get("/api/health/security")
async def health_security():
    """Non-secret security posture snapshot for ops dashboards."""
    import os

    from backend.app.core.crypto_vault import encryption_enabled
    from backend.app.core.production_config import production_config_summary

    return {
        "ok": True,
        "encryption_at_rest": encryption_enabled(),
        "security_headers": os.getenv("SECURITY_HEADERS_ENABLED", "1").lower()
        in ("1", "true", "yes"),
        "rate_limit": os.getenv("RATE_LIMIT_ENABLED", "1").lower() in ("1", "true", "yes"),
        "firewall": os.getenv("FIREWALL_ENABLED", "0").lower() in ("1", "true", "yes"),
        "force_https": os.getenv("FORCE_HTTPS", "1").lower() in ("1", "true", "yes"),
        "production": production_config_summary(),
    }


@app.get("/api/v1/health/diagnostics")
async def health_diagnostics(user: Dict[str, Any] = Depends(get_current_user)):
    """Deep RAM / API / embedding / index diagnostic for troubleshooting disconnects."""
    from fastapi.concurrency import run_in_threadpool
    from backend.app.core.system_diagnostics import run_system_diagnostics

    return await run_in_threadpool(run_system_diagnostics, str(user.get("id", "")))


@app.get("/api/v1/health/stability")
@app.get("/api/health/stability")
async def health_stability():
    """Lightweight stability profile — no auth, safe for UI boot checks."""
    from fastapi.concurrency import run_in_threadpool
    from backend.app.core.stability import operation_profile

    return await run_in_threadpool(operation_profile)


@app.get("/api/v1/health/schema")
@app.get("/api/health/schema")
async def health_schema(user: Dict[str, Any] = Depends(require_superadmin)):
    """Schema verification — superadmin only (exposes DB paths and migration state)."""
    _ = user
    from backend.app.core.schema_migrations import apply_migrations, verify_schema

    migrated = apply_migrations()
    report = verify_schema()
    try:
        from backend.app.core.resource_scheduler import scheduler_status

        sched = scheduler_status()
    except Exception:
        sched = {}

    return {
        "ok": bool(report.get("ok")),
        "db_path": report.get("db_path"),
        "migrations_applied": migrated.get("applied", []),
        "missing": report.get("missing", []),
        "tables": report.get("tables", {}),
        "scheduler": sched,
    }


@app.get("/api/v1/health/embeddings")
async def health_embeddings_root():
    from backend.app.core.embedding_manager import get_manager

    get_manager().start_background_load()
    st = get_manager().get_status()
    return {
        "ready": bool(st.get("ready")),
        "loaded": bool(st.get("loaded") or st.get("ready")),
        "loading": st.get("state") in ("LOADING_MODEL", "RECOVERING"),
        "state": st.get("state"),
        "model": st.get("model") or "",
        "model_name": st.get("model_name") or st.get("model") or "",
        "device": st.get("device") or "cpu",
        "error": st.get("error") or "",
        "last_error": st.get("last_error") or st.get("error") or "",
        "retry_count": int(st.get("retry_count") or st.get("load_attempts") or 0),
        "query_ready": st.get("state") == "READY",
        "low_resource_mode": bool(st.get("low_resource_mode")),
    }


@app.get("/api/v1/kb/health")
async def kb_health_public():
    """Production KB health — embedding state, vectors, queue (no auth for ops; use documents/kb/health for user scope)."""
    from backend.app.core.embedding_manager import get_manager
    from backend.app.core.embedding_queue import get_queue_snapshot
    from backend.app.core.faiss_index_stats import count_index_vectors, index_exists
    from backend.app.core.matter_index import get_unlinked_index_dir

    mgr = get_manager()
    mgr.start_background_load()
    est = mgr.get_status()
    queue = get_queue_snapshot()
    vectors = 0
    try:
        uid_dir = get_unlinked_index_dir("_global_probe")
        if index_exists(uid_dir):
            vectors = count_index_vectors(uid_dir)
    except Exception:
        pass
    emb_ready = est.get("state") == "READY"
    return {
        "embedding_model": "ready" if emb_ready else est.get("state", "loading").lower(),
        "embedding_state": est.get("state"),
        "query_ready": emb_ready,
        "active_vectors": vectors,
        "queue_size": queue.get("queue_size", 0),
        "failed_docs": queue.get("failed", 0),
        "error": est.get("error") or "",
        "model": est.get("model") or "",
    }


@app.on_event("startup")
async def _collab_realtime_worker():
    """Background WebSocket fan-out for Firm Chat."""
    try:
        import asyncio

        from backend.app.core.collab_realtime import start_broadcast_worker

        asyncio.create_task(start_broadcast_worker())
    except Exception:
        pass


@app.on_event("startup")
def _startup():
    import logging
    import threading
    import time

    try:
        from backend.app.core.production_guards import assert_production_guards

        assert_production_guards()
    except RuntimeError as exc:
        logging.getLogger("legalease.startup").critical("Production guards: %s", exc)
        if os.getenv("SAAS_PRODUCTION_STRICT", "1").lower() in ("1", "true", "yes"):
            raise

    logging.getLogger("legalease.startup").info(
        "Deferring heavy startup — API will be live while schemas/models load"
    )

    # Auth must use Postgres bridge before any login/register (not deferred).
    try:
        from backend.app.core.core_db import ensure_app_schemas

        ensure_app_schemas()
    except Exception as exc:
        logging.getLogger("legalease.startup").warning("Early app schemas: %s", exc)

    def _gpu_profile_background() -> None:
        try:
            from backend.app.core.gpu_runtime import apply_gpu_profile

            apply_gpu_profile()
        except Exception:
            pass

    threading.Thread(
        target=_gpu_profile_background,
        daemon=True,
        name="legalease-gpu-profile",
    ).start()

    def _light_then_heavy() -> None:
        try:
            from backend.app.core.schema_migrations import ensure_schema_at_startup

            ensure_schema_at_startup()
        except Exception:
            try:
                from legalease_auth import ensure_db

                ensure_db()
            except Exception:
                pass
        # Let /health/live and /auth/login respond before schema/RAG work contends for CPU.
        time.sleep(3)
        _run_startup_tasks()

    # Preload embeddings in background immediately (fast MiniLM ~10–40s) — API/login stay instant.
    try:
        from backend.app.core.embedding_manager import get_manager

        get_manager().start_background_load()
    except Exception:
        pass

    # Ollama legalease-tuned on GPU — auto-start if not running (OLLAMA_AUTO_START=1).
    try:
        from backend.app.core.ollama_manager import ensure_ollama_background

        ensure_ollama_background()
    except Exception:
        pass

    try:
        from backend.app.services.speech_service import preload_whisper_background

        preload_whisper_background()
    except Exception:
        pass

    threading.Thread(
        target=_light_then_heavy,
        daemon=True,
        name="legalease-startup",
    ).start()


def _heavy_startup_disabled(feature: str) -> bool:
    """Emergency / minimal boot — skip training, coach, auto-tuning at startup."""
    if os.getenv("LEGALEEASE_EMERGENCY_STARTUP", "0").lower() in {"1", "true", "yes"}:
        return True
    key = f"DISABLE_{feature.upper()}_STARTUP"
    return os.getenv(key, "0").lower() in {"1", "true", "yes"}


def _run_startup_tasks() -> None:
    try:
        from backend.app.core.production_config import (
            assert_production_config,
            production_mode,
            strict_production_startup,
            validate_production_config,
        )

        if production_mode():
            import logging

            errs = validate_production_config()
            if errs:
                logging.getLogger("legalease.startup").error(
                    "Production config errors: %s", "; ".join(errs)
                )
                if strict_production_startup():
                    assert_production_config()
    except RuntimeError:
        raise
    except Exception as exc:
        import logging

        logging.getLogger("legalease.startup").warning(
            "Production config check skipped: %s", exc
        )
    try:
        from backend.app.core.core_db import ensure_app_schemas

        ensure_app_schemas()
    except Exception as exc:
        import logging

        logging.getLogger("legalease.startup").warning("App DB schemas: %s", exc)
    try:
        from backend.app.core.legacy_db import check_legacy_db_split_brain

        split_brain = check_legacy_db_split_brain()
        if split_brain:
            import logging

            logging.getLogger("legalease.startup").warning("DB split-brain risk: %s", split_brain)
    except Exception:
        pass
    try:
        from backend.app.core.schema_migrations import ensure_schema_at_startup

        ensure_schema_at_startup()
    except Exception as exc:
        import logging

        logging.getLogger("legalease.schema").warning("Schema startup check failed: %s", exc)
    try:
        from backend.app.core.legal_conversion_engine import ensure_legal_conversion_schema

        ensure_legal_conversion_schema()
    except Exception as exc:
        import logging

        logging.getLogger("legalease.startup").warning("IPC-BNS mapping seed: %s", exc)

    minimal = os.getenv("LEGALEEASE_MINIMAL_STARTUP", "1").lower() in {"1", "true", "yes"}
    if minimal:
        import logging

        logging.getLogger("legalease.startup").info(
            "Minimal startup — schemas/coach/reindex deferred (LEGALEEASE_MINIMAL_STARTUP=1)"
        )
        try:
            from backend.app.core.embedding_manager import get_manager

            get_manager().start_background_load()
        except Exception:
            pass
        update_startup_snapshot(startup_complete=True)
        return

    try:
        from backend.app.core.chat_persistence import ensure_chat_schema
        ensure_chat_schema()
    except Exception:
        try:
            from app import init_db, _migrate_chat_thread_column
            init_db()
            _migrate_chat_thread_column()
        except Exception:
            pass
    try:
        from backend.app.core.adaptive_learning import ensure_learning_schema
        ensure_learning_schema()
    except Exception:
        pass
    try:
        from backend.app.core.enterprise_repo import ensure_enterprise_db
        ensure_enterprise_db()
    except Exception:
        pass
    try:
        from backend.app.core.enterprise_workspace import ensure_enterprise_workspace_schema
        ensure_enterprise_workspace_schema()
    except Exception:
        pass
    try:
        from backend.app.core.user_memory import ensure_user_memory_schema
        ensure_user_memory_schema()
    except Exception:
        pass
    try:
        from backend.app.core.practice_schema import (
            ensure_practice_schema,
            seed_builtin_templates_if_empty,
            seed_default_clauses_if_empty,
        )
        from backend.app.core.saas_schema import ensure_saas_schema

        ensure_practice_schema()
        ensure_saas_schema()
        from backend.app.core.crm_schema import ensure_crm_v2_schema

        ensure_crm_v2_schema()
        from backend.app.core.collab_schema import ensure_collab_schema

        ensure_collab_schema()
        seed_builtin_templates_if_empty()
        seed_default_clauses_if_empty()
        try:
            from backend.app.core.matter_intel_bootstrap import validate_matter_intel_modules

            intel_errs = validate_matter_intel_modules()
            if intel_errs:
                import logging

                logging.getLogger("legalease.startup").error(
                    "Matter intelligence validation failed: %s", "; ".join(intel_errs)
                )
                update_startup_snapshot(matter_intel_error="; ".join(intel_errs[:2]))
        except Exception as exc:
            import logging

            logging.getLogger("legalease.startup").warning("Matter intel bootstrap: %s", exc)
    except Exception:
        pass
    try:
        from backend.app.core.session_store import backend_name
        import logging
        logging.getLogger("legalease.startup").info(
            "Session store: %s", backend_name()
        )
    except Exception:
        pass
    try:
        from llms import clear_web_search_cache

        clear_web_search_cache()
    except Exception:
        pass
    if not _heavy_startup_disabled("neural_tuning"):
        try:
            from backend.app.core.neural_finetuning import ensure_neural_tuning_schema

            ensure_neural_tuning_schema()
        except Exception:
            pass
    if not _heavy_startup_disabled("learning_engine"):
        try:
            from backend.app.core.learning_engine import ensure_learning_engine_schema

            ensure_learning_engine_schema()
        except Exception:
            pass

    skip_warmup = os.getenv("LEGALEEASE_SKIP_RAG_WARMUP", "0").lower() in {"1", "true", "yes"}
    # When fast-startup skips full RAG warmup, embeddings still load via _warm_embeddings_background.
    if not skip_warmup:
        try:
            import logging
            from llms import warmup_rag_stack

            log = logging.getLogger("legalease.startup")
            rag_status = warmup_rag_stack()
            if not rag_status.get("embeddings_ok"):
                log.error(
                    "KB embeddings failed to load — retrieval will use keyword fallback only. %s",
                    rag_status.get("embeddings", {}),
                )
            else:
                log.info("RAG stack ready: %s", rag_status)
            emb = rag_status.get("embeddings") or {}
            update_startup_snapshot(
                embeddings_ok=bool(rag_status.get("embeddings_ok")),
                embeddings_error=str(emb.get("error") or ""),
                embeddings_model=str(emb.get("model") or ""),
                embeddings_device=str(emb.get("device") or "cpu"),
            )
        except Exception as exc:
            import logging

            logging.getLogger("legalease.startup").warning("RAG warmup skipped: %s", exc)
    if not _heavy_startup_disabled("auto_reindex"):
        try:
            from backend.app.core.reindex_scheduler import maybe_auto_reindex_on_startup

            maybe_auto_reindex_on_startup()
        except Exception:
            pass
    if not _heavy_startup_disabled("coach"):
        try:
            from backend.app.core.gemini_ollama_coach import ensure_coach_schema

            ensure_coach_schema()
        except Exception:
            pass
        try:
            from backend.app.core.coach_scheduler import start_coach_scheduler

            start_coach_scheduler()
        except Exception:
            pass

    update_startup_snapshot(startup_complete=True)


# ---------- Auth (v1 compatible paths) ----------

class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    confirm_password: str
    accept_terms: bool = False
    email: str = ""


class AuthResponse(BaseModel):
    token: str
    user: Dict[str, Any]


@app.post("/api/v1/auth/login", response_model=AuthResponse)
@app.post("/api/auth/login", response_model=AuthResponse)
def login(req: LoginRequest, request: Request):
    from auth_tokens import create_access_token
    from legalease_auth import authenticate_user

    user = authenticate_user(req.username.strip(), req.password)
    if not user:
        try:
            from backend.app.core.audit_service import log_audit

            ip = request.client.host if request.client else ""
            log_audit("login_failed", detail=req.username.strip()[:64], ip_address=ip)
        except Exception:
            pass
        raise HTTPException(401, "Invalid username or password")
    try:
        from backend.app.core.admin_auth import user_is_suspended

        if user_is_suspended(str(user["id"])):
            raise HTTPException(403, "Account suspended")
    except HTTPException:
        raise
    except Exception:
        pass
    try:
        from backend.app.core.audit_service import log_audit

        ip = request.client.host if request.client else ""
        log_audit("login_success", user_id=str(user["id"]), ip_address=ip)
    except Exception:
        pass
    return AuthResponse(token=create_access_token(user), user=user)


@app.post("/api/v1/auth/register", response_model=AuthResponse)
@app.post("/api/auth/register", response_model=AuthResponse)
def register(req: RegisterRequest):
    from legalease_auth import authenticate_user, create_user
    from auth_tokens import create_access_token
    if not req.accept_terms:
        raise HTTPException(400, "You must accept the Terms of Service and Privacy Policy")
    if req.password != req.confirm_password:
        raise HTTPException(400, "Passwords do not match")
    from backend.app.core.password_policy import validate_password

    ok_pw, pw_err = validate_password(req.password)
    if not ok_pw:
        raise HTTPException(400, pw_err)
    if not create_user(req.username.strip(), req.password):
        raise HTTPException(400, "Username invalid or already taken")
    user = authenticate_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(500, "Registration succeeded but login failed")
    email = (req.email or "").strip()
    if email and "@" in email:
        try:
            from backend.app.core.database import connect_data_db
            from backend.app.core.p2_saas_schema import ensure_p2_saas_schema

            ensure_p2_saas_schema()
            conn = connect_data_db()
            conn.execute(
                "UPDATE users SET email = ? WHERE id = ?",
                (email, str(user["id"])),
            )
            conn.commit()
            conn.close()
        except Exception:
            pass
    try:
        from datetime import datetime, timezone

        from backend.app.core.database import connect_data_db
        from backend.app.core.p2_saas_schema import ensure_p2_saas_schema

        ensure_p2_saas_schema()
        now = datetime.now(timezone.utc).isoformat()
        conn = connect_data_db()
        conn.execute(
            "UPDATE users SET accepted_terms_at = ? WHERE id = ?",
            (now, str(user["id"])),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    try:
        from backend.app.core.org_service import create_org_for_user

        create_org_for_user(user["id"], user.get("username", ""), user.get("membership", "Free"))
    except Exception:
        pass
    try:
        from backend.app.core.email_service import send_welcome_email

        send_welcome_email(str(user.get("username") or ""))
    except Exception:
        pass
    return AuthResponse(token=create_access_token(user), user=user)


@app.post("/api/v1/billing/stripe/webhook")
async def stripe_webhook(request: Request):
    """Stripe billing webhooks (no JWT — signature verified)."""
    from backend.app.core.stripe_billing import STRIPE_WEBHOOK_SECRET, handle_webhook_payload

    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Stripe webhooks not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        return handle_webhook_payload(payload, sig)
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/v1/auth/me")
@app.get("/api/auth/me")
def me(user: Dict[str, Any] = Depends(get_current_user)):
    return {"user": user}


@app.get("/api/settings/payments")
def legacy_settings_payments(user: Dict[str, Any] = Depends(get_current_user)):
    """Legacy alias — subscription payment history."""
    from backend.app.core.payment_service import list_payment_history

    return {"payments": list_payment_history(str(user["id"]))}


# ---------- Legacy route aliases + extended features ----------

app.include_router(api_router)
app.state.saas_practice_routes = True

# Legacy path aliases (older clients used /api/documents/*)
try:
    from backend.app.api.v1.endpoints.documents import (
        list_documents as v1_list_documents,
        upload_document as v1_upload_document,
    )

    app.add_api_route(
        "/api/documents",
        v1_list_documents,
        methods=["GET"],
        tags=["documents-legacy"],
    )
    app.add_api_route(
        "/api/documents/upload",
        v1_upload_document,
        methods=["POST"],
        tags=["documents-legacy"],
    )
except Exception:
    pass

try:
    from api_routes import router as legacy_features
    app.include_router(legacy_features)
except Exception:
    pass

# OCR
from fastapi import File, UploadFile


@app.post("/api/v1/ocr")
@app.post("/api/ocr")
async def ocr_image(file: UploadFile = File(...), user: Dict[str, Any] = Depends(get_current_user)):
    from ocr_engine import extract_text_from_image_bytes
    data = await file.read()
    text, _ = extract_text_from_image_bytes(data, file.filename or "upload.png")
    if not text.strip():
        raise HTTPException(400, "No text found in image")
    return {"filename": file.filename, "text": text, "chars": len(text)}


@app.get("/")
def root():
    return {
        "service": "LegalEase API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/api/v1/health/public",
    }
