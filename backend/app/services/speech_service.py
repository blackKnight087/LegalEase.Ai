"""Server-side speech-to-text via faster-whisper (lazy-loaded)."""
from __future__ import annotations

import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_MODEL_LOCK = threading.Lock()
_MODEL: Any = None
_MODEL_LOAD_ERROR: Optional[str] = None
_PRELOAD_STARTED = False

SUPPORTED_LANGS = frozenset({"en", "hi", "ta", "mr", "bn", "gu"})

LANG_NAME_TO_CODE: Dict[str, str] = {
    "english": "en",
    "hindi": "hi",
    "tamil": "ta",
    "marathi": "mr",
    "bengali": "bn",
    "gujarati": "gu",
}

STT_ENABLED = os.getenv("STT_ENABLED", "1").strip().lower() in {"1", "true", "yes", "on"}
STT_MAX_BYTES = int(os.getenv("STT_MAX_UPLOAD_MB", "12")) * 1024 * 1024


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.getenv(key, "1" if default else "0").strip().lower()
    return v in {"1", "true", "yes", "on"}


def stt_status() -> Dict[str, Any]:
    return {
        "enabled": STT_ENABLED,
        "engine": (os.getenv("STT_ENGINE") or "faster_whisper").strip(),
        "model": (os.getenv("STT_MODEL") or "small").strip(),
        "device": (os.getenv("STT_DEVICE") or "cpu").strip(),
        "compute_type": (os.getenv("STT_COMPUTE_TYPE") or "int8").strip(),
        "max_seconds": int(os.getenv("STT_MAX_SECONDS") or "90"),
        "max_upload_mb": int(os.getenv("STT_MAX_UPLOAD_MB") or "12"),
        "fallback_browser": _env_bool("STT_FALLBACK_BROWSER", True),
        "polish_default": _env_bool("STT_POLISH_DEFAULT", False),
        "preload": _env_bool("STT_PRELOAD", False),
    }


def stt_config() -> Dict[str, Any]:
    return stt_status()


def normalize_language_code(language: str) -> str:
    raw = (language or "en").strip().lower()
    if raw in SUPPORTED_LANGS:
        return raw
    mapped = LANG_NAME_TO_CODE.get(raw)
    if mapped:
        return mapped
    if len(raw) == 2 and raw.isalpha():
        return raw
    return "en"


normalize_language = normalize_language_code


def browser_fallback_allowed(language: str) -> bool:
    cfg = stt_status()
    return cfg["fallback_browser"] and normalize_language_code(language) == "en"


class SpeechTranscriptionError(Exception):
    def __init__(self, message: str, *, fallback_browser: bool = False):
        super().__init__(message)
        self.fallback_browser = fallback_browser


def _resolve_stt_device(requested: str) -> str:
    dev = (requested or "cpu").strip().lower()
    if dev not in {"cuda", "gpu"}:
        return dev if dev else "cpu"
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    logger.warning("STT_DEVICE=%s unavailable — using CPU", requested)
    return "cpu"


def _get_whisper_model():
    global _MODEL, _MODEL_LOAD_ERROR
    if _MODEL is not None:
        return _MODEL
    if _MODEL_LOAD_ERROR:
        raise SpeechTranscriptionError(_MODEL_LOAD_ERROR, fallback_browser=True)

    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL
        if _MODEL_LOAD_ERROR:
            raise SpeechTranscriptionError(_MODEL_LOAD_ERROR, fallback_browser=True)
        cfg = stt_status()
        device = _resolve_stt_device(str(cfg["device"]))
        compute = str(cfg["compute_type"])
        if device == "cpu" and compute in {"float16", "float32"}:
            compute = "int8"
        load_t0 = time.perf_counter()
        try:
            from faster_whisper import WhisperModel

            logger.info(
                "Loading Whisper model=%s device=%s compute=%s",
                cfg["model"],
                device,
                compute,
            )
            _MODEL = WhisperModel(
                cfg["model"],
                device=device,
                compute_type=compute,
            )
            logger.info(
                "Whisper ready in %.1fs (device=%s)",
                time.perf_counter() - load_t0,
                device,
            )
            return _MODEL
        except Exception as exc:
            _MODEL_LOAD_ERROR = str(exc)
            logger.exception("Failed to load faster-whisper model")
            raise SpeechTranscriptionError(
                f"Speech model unavailable: {exc}",
                fallback_browser=browser_fallback_allowed("en"),
            ) from exc


def preload_whisper_background() -> None:
    """Optional background load when STT_PRELOAD=1 and STT_DEVICE is CUDA."""
    global _PRELOAD_STARTED
    if _PRELOAD_STARTED or not STT_ENABLED:
        return
    if not _env_bool("STT_PRELOAD", False):
        return
    cfg = stt_status()
    dev = (cfg.get("device") or "cpu").lower()
    if dev not in {"cuda", "gpu"}:
        return
    _PRELOAD_STARTED = True

    def _worker() -> None:
        try:
            _get_whisper_model()
            logger.info("STT preload complete (device=%s)", dev)
        except Exception as exc:
            logger.warning("STT preload failed: %s", exc)

    threading.Thread(target=_worker, name="stt-preload", daemon=True).start()


def _estimate_duration_sec(path: Path) -> Optional[float]:
    try:
        import subprocess

        proc = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception:
        pass
    return None


def transcribe_audio_bytes(
    audio_bytes: bytes,
    *,
    language: str,
    filename: str = "audio.webm",
) -> Dict[str, Any]:
    if not STT_ENABLED:
        raise ValueError("Speech-to-text is disabled")

    lang = normalize_language_code(language)
    if lang not in SUPPORTED_LANGS:
        raise ValueError(f"Unsupported language: {language}")

    if not audio_bytes:
        raise ValueError("Empty audio upload")

    if len(audio_bytes) > STT_MAX_BYTES:
        mb = max(1, STT_MAX_BYTES // (1024 * 1024))
        raise ValueError(f"Audio exceeds {mb} MB limit")

    suffix = Path(filename or "audio.webm").suffix or ".webm"
    if suffix.lower() not in {".webm", ".wav", ".ogg", ".mp3", ".m4a", ".mp4"}:
        suffix = ".webm"

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)

        cfg = stt_status()
        duration = _estimate_duration_sec(tmp_path)
        max_sec = int(cfg["max_seconds"])
        if duration is not None and duration > max_sec + 1:
            raise ValueError(f"Recording too long (max {max_sec}s)")

        model = _get_whisper_model()
        segments, info = model.transcribe(
            str(tmp_path),
            language=lang,
            beam_size=5,
            vad_filter=True,
        )
        parts = [seg.text.strip() for seg in segments if seg.text and seg.text.strip()]
        text = " ".join(parts).strip()
        detected = getattr(info, "language", None) or lang
        return {
            "text": text,
            "language_detected": str(detected),
            "language_requested": lang,
            "engine": "faster_whisper",
            "duration_sec": duration,
        }
    except (ValueError, SpeechTranscriptionError):
        raise
    except Exception as exc:
        logger.exception("Transcription failed")
        raise SpeechTranscriptionError(
            f"Transcription failed: {exc}",
            fallback_browser=browser_fallback_allowed(lang),
        ) from exc
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def transcribe_audio(
    audio_bytes: bytes,
    *,
    language: str,
    filename: str = "audio.webm",
) -> Dict[str, Any]:
    try:
        return transcribe_audio_bytes(
            audio_bytes, language=language, filename=filename
        )
    except ValueError as exc:
        raise SpeechTranscriptionError(
            str(exc),
            fallback_browser=browser_fallback_allowed(language),
        ) from exc


def polish_legal_text(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return ""
    try:
        from llms import process_voice_to_legal_text

        return process_voice_to_legal_text(cleaned)
    except Exception as exc:
        logger.warning("Speech polish unavailable: %s", exc)
        return cleaned
