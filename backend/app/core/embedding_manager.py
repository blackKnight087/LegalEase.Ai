"""
Production embedding manager — singleton model, state machine, timeouts, auto-retry.

Never blocks API startup. All document embedding goes through get_model() / get_langchain_embeddings().
"""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("legalease.embedding")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

FALLBACK_MODELS_DEFAULT = [
    "BAAI/bge-small-en-v1.5",
    "sentence-transformers/all-MiniLM-L6-v2",
    "sentence-transformers/paraphrase-MiniLM-L3-v2",
]
FALLBACK_MODELS_LOW_RESOURCE = [
    "sentence-transformers/all-MiniLM-L6-v2",
    "BAAI/bge-small-en-v1.5",
    "sentence-transformers/paraphrase-MiniLM-L3-v2",
]


def _is_low_resource_mode() -> bool:
    return os.getenv("LOW_RESOURCE_MODE", "1").lower() in {"1", "true", "yes"}


def _resolve_embedding_device() -> str:
    from backend.app.core.gpu_runtime import resolve_embedding_device

    return resolve_embedding_device()


def _configure_hf_cache() -> None:
    """Stable local cache — avoid re-downloading weights every boot."""
    cache_root = Path(
        os.getenv("LEGALEEASE_HF_CACHE", str(_PROJECT_ROOT / "Data" / "hf_cache"))
    )
    cache_root.mkdir(parents=True, exist_ok=True)
    # HF_HOME is the supported cache root (Transformers v5 drops TRANSFORMERS_CACHE).
    os.environ.setdefault("HF_HOME", str(cache_root))
    os.environ.pop("TRANSFORMERS_CACHE", None)
    os.environ.setdefault("SENTENCE_TRANSFORMERS_HOME", str(cache_root / "sentence_transformers"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    # Windows without Developer Mode cannot create symlinks in the HF cache (WinError 1314).
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")


_configure_hf_cache()

MODEL_LOAD_TIMEOUT_SEC = float(
    os.getenv(
        "EMBEDDING_MODEL_LOAD_TIMEOUT_SEC",
        "120" if _is_low_resource_mode() else "90",
    )
)
CHUNK_EMBED_TIMEOUT_SEC = float(os.getenv("EMBEDDING_CHUNK_TIMEOUT_SEC", "10"))
DOC_EMBED_TIMEOUT_SEC = float(os.getenv("EMBEDDING_DOC_TIMEOUT_SEC", "300"))
LOAD_RETRY_DELAYS = [1.0, 3.0, 5.0, 10.0, 30.0]
MAX_LOAD_RETRIES = int(
    os.getenv(
        "EMBEDDING_MAX_LOAD_RETRIES",
        "3" if _is_low_resource_mode() else "5",
    )
)


class EmbeddingState(str, Enum):
    IDLE = "IDLE"
    LOADING_MODEL = "LOADING_MODEL"
    READY = "READY"
    EMBEDDING_DOCS = "EMBEDDING_DOCS"
    INDEXING = "INDEXING"
    FAILED = "FAILED"
    RECOVERING = "RECOVERING"


class EmbeddingManager:
    """Process-wide singleton for embedding model lifecycle."""

    _instance: Optional["EmbeddingManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._state = EmbeddingState.IDLE
        self._error = ""
        self._model_name = ""
        self._device = "cpu"
        self._model: Any = None
        self._lc_embeddings: Any = None
        self._lock = threading.RLock()
        self._load_lock = threading.Lock()
        self._load_started_at = 0.0
        self._load_attempts = 0
        self._ready_at = 0.0
        self._loader_future: Any = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="emb-load")
        self._watchdog_started = False
        self._active_doc_jobs = 0
        self._active_index_jobs = 0
        self._loader_thread_active = False
        self._last_load_error = ""

    @classmethod
    def instance(cls) -> "EmbeddingManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _set_state(self, state: EmbeddingState, error: str = "") -> None:
        with self._lock:
            prev = self._state
            self._state = state
            if error:
                self._error = error[:2000]
            elif state == EmbeddingState.READY:
                self._error = ""
            logger.info(
                "[EMBEDDING] state %s -> %s%s",
                prev.value,
                state.value,
                f" ({self._error[:120]})" if self._error and state == EmbeddingState.FAILED else "",
            )

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            loading = self._state == EmbeddingState.LOADING_MODEL
            ready = self._state == EmbeddingState.READY
            if self._state == EmbeddingState.LOADING_MODEL and self._load_started_at:
                elapsed = time.time() - self._load_started_at
                if elapsed > MODEL_LOAD_TIMEOUT_SEC:
                    loading = True
            return {
                "state": self._state.value,
                "ready": ready,
                "loading": loading,
                "loaded": ready,
                "error": self._error or self._last_load_error,
                "last_error": self._last_load_error or self._error,
                "model": self._model_name,
                "model_name": self._model_name,
                "device": self._device,
                "load_attempts": self._load_attempts,
                "retry_count": self._load_attempts,
                "ready_at": self._ready_at,
                "active_doc_jobs": self._active_doc_jobs,
                "active_index_jobs": self._active_index_jobs,
                "low_resource_mode": _is_low_resource_mode(),
            }

    def _embedding_fallback_models(self, user_id: str = "") -> List[str]:
        """Ordered candidates — smallest-first when LOW_RESOURCE_MODE."""
        chain = (
            FALLBACK_MODELS_LOW_RESOURCE
            if _is_low_resource_mode()
            else FALLBACK_MODELS_DEFAULT
        )
        out: List[str] = list(chain)
        prefer_base = os.getenv("RAG_PREFER_BASE_EMBEDDINGS", "1").lower() in {"1", "true", "yes"}
        if prefer_base:
            explicit = (os.getenv("HF_EMBEDDING_MODEL") or "").strip()
            # Always honor HF_EMBEDDING_MODEL from .env (move to front if already in fallback list).
            if explicit:
                if explicit in out:
                    out.remove(explicit)
                out.insert(0, explicit)
        else:
            try:
                from backend.app.core.neural_finetuning import resolve_embedding_model_name

                tuned = (resolve_embedding_model_name(user_id) or "").strip()
                if tuned and tuned not in out:
                    out.insert(0, tuned)
            except Exception:
                pass
        seen: set[str] = set()
        deduped: List[str] = []
        for name in out:
            if name and name not in seen:
                seen.add(name)
                deduped.append(name)
        return deduped or list(FALLBACK_MODELS_LOW_RESOURCE)

    def _resolve_model_name(self, user_id: str = "") -> str:
        models = self._embedding_fallback_models(user_id)
        return models[0]

    def _hf_local_snapshot(self, model_name: str) -> Optional[str]:
        p = Path(model_name)
        if p.exists() and ((p / "config.json").exists() or (p / "modules.json").exists()):
            return str(p.resolve())
        slug = "models--" + model_name.replace("/", "--")
        cache_roots: List[Path] = []
        for key in ("LEGALEEASE_HF_CACHE", "HF_HOME", "SENTENCE_TRANSFORMERS_HOME"):
            raw = (os.getenv(key) or "").strip()
            if raw:
                cache_roots.append(Path(raw))
        cache_roots.append(Path.home() / ".cache" / "huggingface")
        seen_roots: set[str] = set()
        for root in cache_roots:
            rkey = str(root.resolve()) if root.exists() else str(root)
            if rkey in seen_roots:
                continue
            seen_roots.add(rkey)
            # huggingface_hub may use HF_HOME/hub/... or cache_dir/models--... at root
            for base in (root / "hub", root):
                snap_root = base / slug / "snapshots"
                if not snap_root.is_dir():
                    continue
                try:
                    snaps = sorted(
                        snap_root.iterdir(),
                        key=lambda x: x.stat().st_mtime,
                        reverse=True,
                    )
                except OSError:
                    snaps = list(snap_root.iterdir())
                for s in snaps:
                    if (s / "config.json").exists() or (s / "modules.json").exists():
                        return str(s.resolve())
        return None

    def _load_model_impl(self, model_name: str) -> Any:
        from sentence_transformers import SentenceTransformer

        import torch

        t0 = time.perf_counter()
        local = self._hf_local_snapshot(model_name)
        path = local or model_name
        if local:
            logger.info("[EMBEDDING] Loading local snapshot: %s", path)
        else:
            logger.info("[EMBEDDING] Loading model: %s", model_name)

        try:
            torch.set_grad_enabled(False)
        except Exception:
            pass

        device = _resolve_embedding_device()
        if device == "cpu":
            st = SentenceTransformer(
                path,
                device=device,
                trust_remote_code=False,
                model_kwargs={"low_cpu_mem_usage": True},
            )
        else:
            st = SentenceTransformer(
                path,
                device=device,
                trust_remote_code=False,
            )
        if device == "cpu" and not _is_low_resource_mode():
            st.encode(["warmup"], convert_to_numpy=True, show_progress_bar=False)
        elapsed = round(time.perf_counter() - t0, 2)
        logger.info("[EMBEDDING] Ready in %ss on %s (%s)", elapsed, device, path)
        st._legalease_device = device  # noqa: SLF001 — track for get_status
        return st

    def _do_load(self) -> bool:
        candidates = self._embedding_fallback_models()
        last_err = ""
        with self._load_lock:
            for idx, model_name in enumerate(candidates):
                timeout = MODEL_LOAD_TIMEOUT_SEC if idx == 0 else min(
                    75.0, MODEL_LOAD_TIMEOUT_SEC
                )
                self._model_name = model_name
                logger.info(
                    "[EMBEDDING] Startup attempt %s/%s: %s (timeout=%ss, low_resource=%s)",
                    idx + 1,
                    len(candidates),
                    model_name,
                    int(timeout),
                    _is_low_resource_mode(),
                )
                try:
                    fut = self._executor.submit(self._load_model_impl, model_name)
                    model = fut.result(timeout=timeout)
                except FuturesTimeout:
                    last_err = (
                        f"Timed out after {int(timeout)}s loading {model_name} "
                        "(try LOW_RESOURCE_MODE=1 or free RAM)"
                    )
                    self._last_load_error = last_err
                    logger.error("[EMBEDDING] %s", last_err)
                    continue
                except Exception as exc:
                    last_err = f"{type(exc).__name__}: {exc}"
                    self._last_load_error = last_err
                    logger.exception(
                        "[EMBEDDING] Embedding startup failed for %s — trying next model",
                        model_name,
                    )
                    continue

                self._model = model
                self._lc_embeddings = None
                self._device = getattr(model, "_legalease_device", None) or _resolve_embedding_device()
                self._ready_at = time.time()
                self._last_load_error = ""
                self._set_state(EmbeddingState.READY)
                logger.info("[EMBEDDING] QUERY_READY using model %s", model_name)
                try:
                    from backend.app.core.startup_state import update_startup_snapshot

                    update_startup_snapshot(
                        embeddings_ok=True,
                        embeddings_error="",
                        embeddings_model=self._model_name,
                        embeddings_device=self._device,
                    )
                except Exception:
                    pass
                return True

            msg = (
                f"All {len(candidates)} embedding model(s) failed. Last: {last_err[:800]}"
            )
            self._last_load_error = msg
            self._set_state(EmbeddingState.FAILED, msg)
            return False

    def _load_worker(self) -> None:
        with self._lock:
            self._load_attempts += 1
            attempt = self._load_attempts
        self._set_state(EmbeddingState.LOADING_MODEL)
        self._load_started_at = time.time()
        ok = self._do_load()
        if ok:
            if self._state != EmbeddingState.READY:
                self._set_state(EmbeddingState.READY)
        elif self._state != EmbeddingState.FAILED:
            self._set_state(EmbeddingState.FAILED, self._error or "Embedding model load failed")
        max_retries = MAX_LOAD_RETRIES
        if not ok and attempt < max_retries:
            delay = LOAD_RETRY_DELAYS[min(attempt - 1, len(LOAD_RETRY_DELAYS) - 1)]
            logger.error(
                "[EMBEDDING] All fallbacks failed (round %s/%s). Last error: %s — retry in %ss",
                attempt,
                max_retries,
                (self._last_load_error or self._error or "unknown")[:500],
                int(delay),
            )
            self._error = (self._last_load_error or self._error or "Load failed") + (
                f" — retry in {int(delay)}s"
            )
            threading.Timer(delay, self.start_background_load).start()

    def start_background_load(self) -> None:
        """Non-blocking: start model load in background if needed (single loader thread)."""
        with self._lock:
            if self._state == EmbeddingState.READY and self._model is not None:
                return
            if self._loader_thread_active:
                return
            if self._state == EmbeddingState.LOADING_MODEL:
                if self._load_started_at and (
                    time.time() - self._load_started_at
                ) > MODEL_LOAD_TIMEOUT_SEC + 15:
                    logger.warning(
                        "[EMBEDDING] Load watchdog: stuck > timeout, forcing retry"
                    )
                    self._state = EmbeddingState.FAILED
                else:
                    return
            if self._state == EmbeddingState.IDLE:
                self._set_state(EmbeddingState.LOADING_MODEL)
            self._loader_thread_active = True

        if not self._watchdog_started:
            self._watchdog_started = True
            threading.Thread(
                target=self._watchdog_loop, daemon=True, name="emb-watchdog"
            ).start()

        def _runner() -> None:
            try:
                self._load_worker()
            finally:
                with self._lock:
                    self._loader_thread_active = False

        threading.Thread(target=_runner, daemon=True, name="emb-loader").start()

    def _watchdog_loop(self) -> None:
        while True:
            sleep_sec = 15
            try:
                from backend.app.core.memory_efficiency import pressure_level

                if pressure_level() in ("high", "critical"):
                    sleep_sec = 45
            except Exception:
                pass
            time.sleep(sleep_sec)
            with self._lock:
                st = self._state
                started = self._load_started_at
            if st == EmbeddingState.LOADING_MODEL and started:
                if time.time() - started > MODEL_LOAD_TIMEOUT_SEC + 30:
                    logger.error("[EMBEDDING] Watchdog: load stuck, scheduling recovery")
                    with self._lock:
                        self._state = EmbeddingState.FAILED
                        self._error = "Embedding model load stuck — auto-retrying"
                    self.start_background_load()
            elif st == EmbeddingState.FAILED:
                try:
                    from backend.app.core.memory_efficiency import pressure_level

                    if pressure_level() == "critical":
                        continue
                except Exception:
                    pass
                self.start_background_load()

    def wait_until_ready(self, timeout_sec: float = 120.0) -> bool:
        """Block up to timeout_sec for READY (index worker only — not HTTP handlers)."""
        deadline = time.time() + timeout_sec
        self.start_background_load()
        while time.time() < deadline:
            with self._lock:
                if self._state == EmbeddingState.READY and self._model is not None:
                    return True
                if self._state == EmbeddingState.FAILED:
                    self.start_background_load()
            time.sleep(0.5)
        return False

    def get_model(self, user_id: str = "", wait_timeout: float = 0) -> Any:
        if wait_timeout > 0:
            if not self.wait_until_ready(wait_timeout):
                raise RuntimeError(self._error or "Embedding model not ready")
        with self._lock:
            if self._model is not None and self._state == EmbeddingState.READY:
                return self._model
        self.start_background_load()
        raise RuntimeError(
            self._error or "Embedding model loading in background — retry shortly"
        )

    def get_langchain_embeddings(self, user_id: str = ""):
        """LangChain-compatible wrapper; cached singleton."""
        with self._lock:
            if self._lc_embeddings is not None and self._state == EmbeddingState.READY:
                return self._lc_embeddings
        model = self.get_model(user_id=user_id, wait_timeout=MODEL_LOAD_TIMEOUT_SEC)
        from rag import HuggingFaceEmbeddingsWrapper

        with self._lock:
            if self._lc_embeddings is None:
                self._lc_embeddings = HuggingFaceEmbeddingsWrapper(
                    self._model_name,
                    st_model=model,
                )
            return self._lc_embeddings

    def embed_texts_batched(
        self,
        texts: List[str],
        *,
        batch_size: int = 50,
        progress_callback: Optional[Callable[[str], None]] = None,
        doc_timeout_sec: float = DOC_EMBED_TIMEOUT_SEC,
    ) -> Any:
        """Embed texts in batches with per-batch timeout; returns numpy array."""
        import numpy as np

        if not texts:
            return np.array([])

        model = self.get_model(wait_timeout=MODEL_LOAD_TIMEOUT_SEC)
        t0 = time.time()
        batches = max(1, (len(texts) + batch_size - 1) // batch_size)
        parts: List[Any] = []

        for i in range(0, len(texts), batch_size):
            if time.time() - t0 > doc_timeout_sec:
                raise TimeoutError(
                    f"Document embedding timed out after {int(doc_timeout_sec)}s at batch {i // batch_size + 1}/{batches}"
                )
            batch = texts[i : i + batch_size]
            bn = i // batch_size + 1
            if progress_callback:
                progress_callback(f"Embedding batch {bn}/{batches} ({len(batch)} chunks)")

            def _encode():
                return model.encode(batch, convert_to_numpy=True, show_progress_bar=False)

            with ThreadPoolExecutor(max_workers=1) as ex:
                fut = ex.submit(_encode)
                try:
                    vec = fut.result(timeout=CHUNK_EMBED_TIMEOUT_SEC * max(1, len(batch) // 8))
                except FuturesTimeout:
                    logger.error("[EMBEDDING] Chunk batch %s timeout — skipping batch", bn)
                    continue
            parts.append(vec)

        if not parts:
            raise RuntimeError("All embedding batches failed or timed out")
        return np.vstack(parts)

    def set_doc_jobs(self, delta: int) -> None:
        with self._lock:
            self._active_doc_jobs = max(0, self._active_doc_jobs + delta)
            if self._active_doc_jobs > 0 and self._state == EmbeddingState.READY:
                self._set_state(EmbeddingState.EMBEDDING_DOCS)
            elif self._active_doc_jobs == 0 and self._active_index_jobs == 0 and self._model:
                self._set_state(EmbeddingState.READY)

    def set_index_jobs(self, delta: int) -> None:
        with self._lock:
            self._active_index_jobs = max(0, self._active_index_jobs + delta)
            if self._active_index_jobs > 0:
                self._set_state(EmbeddingState.INDEXING)
            elif self._active_doc_jobs == 0 and self._model:
                self._set_state(EmbeddingState.READY)

    def clear_embeddings_cache(self, user_id: str = "", *, mark_offline: bool = False) -> None:
        with self._lock:
            if mark_offline:
                self._model = None
                self._lc_embeddings = None
                self._set_state(EmbeddingState.IDLE)
                self.start_background_load()


def get_manager() -> EmbeddingManager:
    return EmbeddingManager.instance()


def get_embeddings_status() -> Dict[str, Any]:
    st = get_manager().get_status()
    state = st.get("state", "IDLE")
    return {
        "ready": st["ready"],
        "loaded": st.get("loaded", st["ready"]),
        "loading": st["loading"],
        "error": st.get("last_error") or st["error"],
        "last_error": st.get("last_error") or st["error"],
        "model": st["model"],
        "model_name": st.get("model_name") or st["model"],
        "device": st["device"],
        "state": state,
        "retry_count": st.get("retry_count", st.get("load_attempts", 0)),
        "query_ready": state == EmbeddingState.READY.value,
    }


def ensure_embeddings_background() -> bool:
    get_manager().start_background_load()
    return True


def warmup_embeddings(model: str | None = None) -> bool:
    mgr = get_manager()
    mgr.start_background_load()
    return mgr.wait_until_ready(timeout_sec=MODEL_LOAD_TIMEOUT_SEC + 30)


def get_embeddings(model: str = "", user_id: str = "") -> Any:
    return get_manager().get_model(user_id=user_id, wait_timeout=0)


def clear_embeddings_cache(user_id: str = "", *, mark_offline: bool = False) -> None:
    mgr = get_manager()
    with mgr._lock:
        if mark_offline:
            mgr._model = None
            mgr._lc_embeddings = None
            mgr._set_state(EmbeddingState.IDLE)


# Attach to class for llms.py shim
def _manager_clear(mark_offline: bool = False) -> None:
    clear_embeddings_cache(mark_offline=mark_offline)


EmbeddingManager.clear_embeddings_cache = lambda self, user_id="", mark_offline=False: clear_embeddings_cache(  # type: ignore
    user_id, mark_offline=mark_offline
)
