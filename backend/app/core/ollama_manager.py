"""
Ollama lifecycle — auto-start on GPU when backend boots (like EmbeddingManager).

KB chat uses Ollama legalease-tuned only; Gemini stays retrieval-only (kb_gemini_safety).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_started = False
_state: Dict[str, Any] = {
    "state": "IDLE",
    "reachable": False,
    "auto_started": False,
    "model": "",
    "gpu_layers": "",
    "error": "",
    "warmup_ok": False,
}


def _ollama_base_url() -> str:
    return (
        os.getenv("OLLAMA_URL")
        or os.getenv("OLLAMA_BASE_URL")
        or "http://127.0.0.1:11434"
    ).strip().rstrip("/")


def _ollama_model() -> str:
    return (os.getenv("OLLAMA_MODEL") or "legalease-tuned").strip()


def _auto_start_enabled() -> bool:
    return os.getenv("OLLAMA_AUTO_START", "1").lower() in {"1", "true", "yes"}


def _auto_warmup_enabled() -> bool:
    return os.getenv("OLLAMA_AUTO_WARMUP", "1").lower() in {"1", "true", "yes"}


def _gpu_layers() -> str:
    return (os.getenv("OLLAMA_NUM_GPU") or "999").strip()


def _apply_gpu_env(env: Dict[str, str]) -> Dict[str, str]:
    """Ensure child process and API calls use GPU offload settings."""
    out = dict(env)
    out.setdefault("OLLAMA_NUM_GPU", _gpu_layers())
    out.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
    out.setdefault("CUDA_VISIBLE_DEVICES", os.getenv("CUDA_VISIBLE_DEVICES") or "0")
    if not out.get("OLLAMA_HOST"):
        parsed = urlparse(_ollama_base_url())
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or 11434
        out["OLLAMA_HOST"] = f"{host}:{port}"
    return out


def release_ollama_vram() -> None:
    """Unload Ollama models from RAM/VRAM before neural training (GPU-only mode)."""
    if not is_ollama_reachable(timeout=1.0):
        return
    model = _ollama_model()
    try:
        import requests

        requests.post(
            f"{_ollama_base_url()}/api/generate",
            json={"model": model, "prompt": "", "keep_alive": 0},
            timeout=8,
        )
        logger.info("[Ollama] Released VRAM for training (keep_alive=0)")
    except Exception as exc:
        logger.debug("[Ollama] VRAM release: %s", exc)


def ollama_gpu_subprocess_env() -> Dict[str, str]:
    """Env for `ollama create` / coach exports — GPU layers, not RAM."""
    return _apply_gpu_env(os.environ.copy())


def is_ollama_reachable(*, timeout: float = 2.5) -> bool:
    try:
        import requests

        r = requests.get(f"{_ollama_base_url()}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def get_ollama_status() -> Dict[str, Any]:
    with _lock:
        st = dict(_state)
    st["reachable"] = is_ollama_reachable(timeout=1.5)
    st["model"] = st.get("model") or _ollama_model()
    st["gpu_layers"] = st.get("gpu_layers") or _gpu_layers()
    st["base_url"] = _ollama_base_url()
    return st


def _set_state(**kwargs: Any) -> None:
    with _lock:
        _state.update(kwargs)


def _find_ollama_exe() -> Optional[str]:
    import shutil

    path = shutil.which("ollama")
    if path:
        return path
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
        os.path.expandvars(r"%ProgramFiles%\Ollama\ollama.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return None


def _spawn_ollama_serve() -> bool:
    if sys.platform != "win32":
        _set_state(
            state="IDLE",
            error="Use host Ollama on Linux (bash deploy/aws/setup-ollama-host.sh)",
        )
        return False
    exe = _find_ollama_exe()
    if not exe:
        _set_state(state="FAILED", error="ollama not found in PATH")
        logger.warning("[Ollama] ollama not found — install from https://ollama.com")
        return False
    env = _apply_gpu_env(os.environ.copy())
    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
    try:
        subprocess.Popen(
            [exe, "serve"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True,
        )
        _set_state(state="STARTING", auto_started=True, gpu_layers=_gpu_layers())
        logger.info(
            "[Ollama] Started ollama serve (OLLAMA_NUM_GPU=%s)",
            env.get("OLLAMA_NUM_GPU"),
        )
        return True
    except Exception as exc:
        _set_state(state="FAILED", error=str(exc)[:200])
        logger.warning("[Ollama] Failed to spawn serve: %s", exc)
        return False


def _wait_until_reachable(timeout_sec: float) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if is_ollama_reachable(timeout=2.0):
            return True
        time.sleep(1.5)
    return False


def _warmup_model() -> bool:
    if not _auto_warmup_enabled():
        return False
    model = _ollama_model()
    try:
        import requests

        opts: Dict[str, Any] = {"num_predict": 16, "temperature": 0.0}
        ng = _gpu_layers()
        if ng.isdigit():
            opts["num_gpu"] = int(ng)
        r = requests.post(
            f"{_ollama_base_url()}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": "ok"}],
                "stream": False,
                "options": opts,
            },
            timeout=float(os.getenv("OLLAMA_WARMUP_TIMEOUT_SEC", "180")),
        )
        if r.status_code == 200:
            _set_state(state="READY", warmup_ok=True, model=model)
            logger.info("[Ollama] Warmed model %s on GPU", model)
            return True
        err = (r.text or "")[:300]
        _set_state(state="READY", warmup_ok=False, error=err, model=model)
        if "system memory" in err.lower():
            logger.warning(
                "[Ollama] Warmup memory error — quit Ollama tray app, set OLLAMA_NUM_GPU=999 "
                "in Windows env vars, then restart backend."
            )
        return False
    except Exception as exc:
        _set_state(state="READY", warmup_ok=False, error=str(exc)[:200], model=model)
        logger.warning("[Ollama] Warmup failed: %s", exc)
        return False


def ensure_ollama_gpu(*, wait: bool = True) -> bool:
    """
    Ensure Ollama is listening; start serve with GPU env if configured and not running.
    Optional blocking wait + model warm-up (legalease-tuned).
    """
    global _started
    if os.getenv("LLM_BACKEND", "ollama").strip().lower() != "ollama":
        return False

    with _lock:
        if _started and _state.get("state") in ("READY", "STARTING"):
            if not wait:
                return _state.get("reachable", False) or is_ollama_reachable()
        _started = True

    if is_ollama_reachable():
        _set_state(state="READY", reachable=True, model=_ollama_model())
        if wait and _auto_warmup_enabled() and not _state.get("warmup_ok"):
            _warmup_model()
        return True

    if not _auto_start_enabled():
        _set_state(
            state="IDLE",
            reachable=False,
            error="Ollama not running; set OLLAMA_AUTO_START=1 or start ollama serve",
        )
        return False

    _set_state(state="STARTING", model=_ollama_model())
    if not _spawn_ollama_serve():
        return False

    wait_sec = float(os.getenv("OLLAMA_STARTUP_WAIT_SEC", "90"))
    if wait:
        if not _wait_until_reachable(wait_sec):
            _set_state(
                state="FAILED",
                error=f"Ollama did not respond within {wait_sec:.0f}s",
            )
            return False
        _set_state(reachable=True)
        _warmup_model()
        return True

    threading.Thread(
        target=_background_finish_start,
        kwargs={"wait_sec": wait_sec},
        daemon=True,
        name="ollama-startup",
    ).start()
    return True


def _background_finish_start(*, wait_sec: float) -> None:
    if _wait_until_reachable(wait_sec):
        _set_state(reachable=True, state="READY")
        _warmup_model()
    else:
        _set_state(state="FAILED", error=f"Ollama not ready after {wait_sec:.0f}s")


def ensure_ollama_background() -> bool:
    """Non-blocking — same pattern as ensure_embeddings_background."""
    if not _auto_start_enabled():
        return is_ollama_reachable()
    threading.Thread(
        target=lambda: ensure_ollama_gpu(wait=True),
        daemon=True,
        name="ollama-ensure",
    ).start()
    return True
