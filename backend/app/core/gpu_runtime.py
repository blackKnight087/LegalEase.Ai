"""GPU detection, VRAM stats, and GPU_PROFILE presets for 6GB laptop VRAM."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_CUDA_CACHE: Optional[bool] = None
_CUDA_CACHE_LOCK = threading.Lock()

_PROFILES = frozenset({"balanced", "max_stt", "max_chat", "legal_gpu"})


def gpu_only_mode() -> bool:
    """Prefer VRAM for Ollama + local training; keep embeddings on CPU during KB chat."""
    return os.getenv("LEGALEEASE_GPU_ONLY", "0").lower() in {"1", "true", "yes"}


def apply_gpu_only_overrides() -> None:
    """
    LEGALEEASE_GPU_ONLY=1 — Ollama legalease-tuned + neural/Gemini-coach training paths use GPU,
    not system RAM. Gemini API calls are cloud-side; local Ollama create/train uses CUDA.
    """
    if not gpu_only_mode():
        return
    if not cuda_available() and not _trust_gpu_env_without_probe():
        logger.warning("[GPU] LEGALEEASE_GPU_ONLY=1 but CUDA unavailable — using CPU fallbacks")
        return
    os.environ["GPU_PROFILE"] = "legal_gpu"
    os.environ["OLLAMA_NUM_GPU"] = os.getenv("OLLAMA_NUM_GPU") or "999"
    os.environ.setdefault("OLLAMA_AUTO_START", "1")
    os.environ.setdefault("OLLAMA_AUTO_WARMUP", "1")
    os.environ.setdefault("RAG_EMBEDDING_DEVICE", "cpu")
    os.environ.setdefault("NEURAL_FINETUNE_DEVICE", "cuda")
    os.environ.setdefault("STT_DEVICE", "cpu")
    os.environ.setdefault("STT_PRELOAD", "0")
    os.environ.setdefault("OCR_GPU", "0")
    os.environ.setdefault("LLM_USE_TRAINED_ADAPTER", "0")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", os.getenv("CUDA_VISIBLE_DEVICES") or "0")
    os.environ.setdefault("OLLAMA_MAX_LOADED_MODELS", "1")
    logger.info(
        "[GPU] LEGALEEASE_GPU_ONLY: Ollama layers=%s, neural_train=cuda, KB embeddings=cpu",
        os.getenv("OLLAMA_NUM_GPU"),
    )


def release_ollama_vram_for_training() -> None:
    """Free GPU VRAM before embedding neural train when GPU-only mode is on."""
    if not gpu_only_mode():
        return
    try:
        from backend.app.core.ollama_manager import release_ollama_vram

        release_ollama_vram()
    except Exception:
        pass


def resolve_neural_train_device() -> str:
    """Embedding fine-tune / learning — use GPU when LEGALEEASE_GPU_ONLY or NEURAL_FINETUNE_DEVICE."""
    explicit = (os.getenv("NEURAL_FINETUNE_DEVICE") or "").strip().lower()
    if explicit in {"cuda", "gpu"} and cuda_available():
        return "cuda"
    if gpu_only_mode() and cuda_available():
        return "cuda"
    return (os.getenv("RAG_EMBEDDING_DEVICE") or "cpu").strip().lower() or "cpu"


def _cuda_probe_timeout_sec() -> float:
    try:
        return max(1.0, float(os.getenv("LEGALEEASE_CUDA_PROBE_TIMEOUT_SEC", "4")))
    except ValueError:
        return 4.0


def _skip_cuda_probe() -> bool:
    return os.getenv("LEGALEEASE_SKIP_CUDA_PROBE", "0").lower() in {"1", "true", "yes"}


def _trust_gpu_env_without_probe() -> bool:
    """When Ollama holds the GPU, torch.cuda.is_available() can block for minutes at import."""
    return _skip_cuda_probe() or os.getenv("LEGALEEASE_GPU_ONLY_TRUST_ENV", "1").lower() in {
        "1",
        "true",
        "yes",
    }


def cuda_available(*, force_refresh: bool = False) -> bool:
    global _CUDA_CACHE
    if not force_refresh and _CUDA_CACHE is not None:
        return _CUDA_CACHE
    if _skip_cuda_probe():
        _CUDA_CACHE = False
        return False

    with _CUDA_CACHE_LOCK:
        if not force_refresh and _CUDA_CACHE is not None:
            return _CUDA_CACHE

        result: Dict[str, bool] = {"ok": False}

        def _probe() -> None:
            try:
                import torch

                result["ok"] = bool(torch.cuda.is_available())
            except Exception:
                result["ok"] = False

        probe = threading.Thread(target=_probe, daemon=True, name="cuda-probe")
        probe.start()
        probe.join(timeout=_cuda_probe_timeout_sec())
        if probe.is_alive():
            logger.warning(
                "[GPU] CUDA probe timed out after %.0fs (Ollama may hold VRAM) — skipping torch at boot",
                _cuda_probe_timeout_sec(),
            )
            _CUDA_CACHE = False
            return False

        _CUDA_CACHE = bool(result["ok"])
        return _CUDA_CACHE


def resolve_embedding_device() -> str:
    """Honor RAG_EMBEDDING_DEVICE when CUDA is available."""
    requested = (os.getenv("RAG_EMBEDDING_DEVICE") or "cpu").strip().lower()
    if requested in {"cuda", "gpu"} and cuda_available():
        return "cuda"
    return "cpu"


def get_gpu_diagnostics() -> Dict[str, Any]:
    """VRAM and device info for health endpoints."""
    out: Dict[str, Any] = {
        "cuda_available": False,
        "gpu_name": "",
        "vram_total_mb": 0,
        "vram_used_mb": 0,
        "gpu_profile": (os.getenv("GPU_PROFILE") or "balanced").strip().lower(),
        "torch_cuda_version": "",
    }
    try:
        import torch

        out["cuda_available"] = bool(torch.cuda.is_available())
        if out["cuda_available"]:
            out["gpu_name"] = torch.cuda.get_device_name(0) or ""
            out["torch_cuda_version"] = getattr(torch.version, "cuda", "") or ""
            props = torch.cuda.get_device_properties(0)
            total = int(getattr(props, "total_memory", 0) or 0)
            out["vram_total_mb"] = round(total / (1024 * 1024))
            try:
                free_b, total_b = torch.cuda.mem_get_info(0)
                out["vram_used_mb"] = round((total_b - free_b) / (1024 * 1024))
                if not out["vram_total_mb"]:
                    out["vram_total_mb"] = round(total_b / (1024 * 1024))
            except Exception:
                try:
                    alloc = torch.cuda.memory_allocated(0)
                    out["vram_used_mb"] = round(alloc / (1024 * 1024))
                except Exception:
                    pass
    except Exception as exc:
        out["error"] = str(exc)[:200]
    return out


def apply_gpu_profile() -> str:
    """
    Apply GPU_PROFILE presets when CUDA is available.
    User .env values take precedence (setdefault for balanced; explicit for max_*).
    """
    apply_gpu_only_overrides()
    profile = (os.getenv("GPU_PROFILE") or "balanced").strip().lower()
    if profile not in _PROFILES:
        profile = "balanced"

    if not cuda_available() and not _trust_gpu_env_without_probe():
        logger.info("[GPU] CUDA not available — GPU_PROFILE=%s ignored", profile)
        return profile

    if profile == "balanced":
        os.environ.setdefault("STT_DEVICE", "cuda")
        os.environ.setdefault("STT_COMPUTE_TYPE", "float16")
        os.environ.setdefault("RAG_EMBEDDING_DEVICE", "cpu")
        os.environ.setdefault("OLLAMA_NUM_GPU", "999")
        os.environ.setdefault("OLLAMA_AUTO_START", "1")
    elif profile == "max_stt":
        os.environ["STT_DEVICE"] = "cuda"
        os.environ.setdefault("STT_COMPUTE_TYPE", "float16")
        os.environ["RAG_EMBEDDING_DEVICE"] = "cpu"
        os.environ.setdefault("OCR_GPU", "0")
    elif profile == "max_chat":
        os.environ["STT_DEVICE"] = "cpu"
        os.environ.setdefault("STT_COMPUTE_TYPE", "int8")
        os.environ["RAG_EMBEDDING_DEVICE"] = "cpu"
        os.environ.setdefault("OLLAMA_NUM_GPU", "999")
        os.environ.setdefault("OLLAMA_AUTO_START", "1")
    elif profile == "legal_gpu":
        os.environ["STT_DEVICE"] = "cpu"
        os.environ.setdefault("STT_COMPUTE_TYPE", "int8")
        os.environ["RAG_EMBEDDING_DEVICE"] = "cpu"
        os.environ["OLLAMA_NUM_GPU"] = os.getenv("OLLAMA_NUM_GPU") or "999"
        os.environ.setdefault("OLLAMA_AUTO_START", "1")
        os.environ.setdefault("NEURAL_FINETUNE_DEVICE", "cuda")
        os.environ.setdefault("OCR_GPU", "0")
        os.environ.setdefault("STT_PRELOAD", "0")

    logger.info(
        "[GPU] profile=%s stt=%s embed=%s",
        profile,
        os.getenv("STT_DEVICE"),
        os.getenv("RAG_EMBEDDING_DEVICE"),
    )
    return profile


def get_runtime_accelerator_status() -> Dict[str, Any]:
    """Combined GPU + STT + OCR + embedding device snapshot."""
    gpu = get_gpu_diagnostics()
    try:
        from ocr_engine import ocr_status

        ocr = ocr_status()
    except Exception:
        ocr = {"gpu": os.getenv("OCR_GPU", "0") == "1"}
    try:
        from backend.app.services.speech_service import stt_status

        stt = stt_status()
    except Exception:
        stt = {}
    try:
        from backend.app.core.embedding_manager import get_manager

        emb = get_manager().get_status()
        embeddings_device = emb.get("device") or resolve_embedding_device()
    except Exception:
        embeddings_device = resolve_embedding_device()

    try:
        from backend.app.core.ollama_manager import get_ollama_status

        ollama_st = get_ollama_status()
    except Exception:
        ollama_st = {}

    return {
        **gpu,
        "stt_device": stt.get("device", os.getenv("STT_DEVICE", "cpu")),
        "stt_compute_type": stt.get("compute_type", ""),
        "stt_model": stt.get("model", ""),
        "embeddings_device": embeddings_device,
        "ocr_gpu": bool(ocr.get("gpu")),
        "low_resource_mode": os.getenv("LOW_RESOURCE_MODE", "1").lower() in {"1", "true", "yes"},
        "ollama_auto_start": os.getenv("OLLAMA_AUTO_START", "1"),
        "ollama_num_gpu": os.getenv("OLLAMA_NUM_GPU", ""),
        "ollama_runtime": ollama_st,
        "gpu_only_mode": gpu_only_mode(),
        "neural_train_device": resolve_neural_train_device(),
        "gemini_note": "Gemini API runs in Google cloud; local GPU is used for Ollama + neural training",
    }
