"""Benchmark STT pipeline (model load + transcribe)."""
from __future__ import annotations

import logging
import shutil
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("stt_benchmark")

from backend.app.core.gpu_runtime import apply_gpu_profile, get_gpu_diagnostics
from backend.app.services import speech_service as svc


def make_silent_wav(seconds: float = 2.0, rate: int = 16000) -> bytes:
    import io

    buf = io.BytesIO()
    n = int(rate * seconds)
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)
    return buf.getvalue()


def main() -> int:
    apply_gpu_profile()
    gpu = get_gpu_diagnostics()
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    logger.info("GPU: %s", gpu)
    logger.info("STT config: %s", svc.stt_status())
    logger.info("ffmpeg: %s", ffmpeg or "MISSING")
    logger.info("ffprobe: %s", ffprobe or "MISSING")

    wav = make_silent_wav(2.0)
    logger.info("Running transcribe on %s byte silent WAV…", len(wav))

    t0 = time.perf_counter()
    try:
        out = svc.transcribe_audio_bytes(wav, language="en", filename="bench.wav")
        logger.info("Result: %s", out)
    except Exception as exc:
        logger.error("FAILED: %s", exc)
        return 1

    elapsed = time.perf_counter() - t0
    logger.info("Total wall time: %.2fs", elapsed)

    t1 = time.perf_counter()
    out2 = svc.transcribe_audio_bytes(wav, language="en", filename="bench2.wav")
    warm = time.perf_counter() - t1
    logger.info("Warm pass: %.2fs, text_len=%s", warm, len(out2.get("text") or ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
