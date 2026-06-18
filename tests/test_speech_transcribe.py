"""Tests for speech_service language mapping and guards."""
from __future__ import annotations

import pytest

from backend.app.services import speech_service as svc


def test_normalize_language_names():
    assert svc.normalize_language_code("English") == "en"
    assert svc.normalize_language_code("Hindi") == "hi"
    assert svc.normalize_language_code("Tamil") == "ta"
    assert svc.normalize_language_code("Marathi") == "mr"
    assert svc.normalize_language_code("Bengali") == "bn"
    assert svc.normalize_language_code("Gujarati") == "gu"


def test_normalize_language_codes():
    assert svc.normalize_language_code("hi") == "hi"
    assert svc.normalize_language_code("EN") == "en"


def test_normalize_unknown_defaults_en():
    assert svc.normalize_language_code("Klingon") == "en"


def test_stt_status_keys():
    s = svc.stt_status()
    assert "enabled" in s
    assert s["engine"] == "faster_whisper"


def test_empty_audio_raises():
    with pytest.raises(ValueError, match="Empty audio"):
        svc.transcribe_audio_bytes(b"", language="en")


def test_oversized_audio_raises(monkeypatch):
    monkeypatch.setattr(svc, "STT_MAX_BYTES", 10)
    with pytest.raises(ValueError, match="exceeds"):
        svc.transcribe_audio_bytes(b"x" * 20, language="en")


def test_transcribe_mock_whisper(monkeypatch):
    class FakeSeg:
        def __init__(self, t):
            self.text = t

    class FakeInfo:
        language = "hi"

    class FakeModel:
        def transcribe(self, path, **kwargs):
            assert path
            assert kwargs.get("language") == "hi"
            return ([FakeSeg("नमस्ते"), FakeSeg("दुनिया")], FakeInfo())

    monkeypatch.setattr(svc, "_MODEL", FakeModel(), raising=False)
    monkeypatch.setattr(svc, "_MODEL_LOAD_ERROR", None, raising=False)
    monkeypatch.setattr(svc, "STT_ENABLED", True)
    out = svc.transcribe_audio_bytes(b"fake", language="Hindi", filename="x.webm")
    assert "नमस्ते" in out["text"]
    assert out["engine"] == "faster_whisper"
    assert out["language_requested"] == "hi"


def test_polish_fallback_on_error(monkeypatch):
    def boom(_):
        raise RuntimeError("no llm")

    monkeypatch.setattr(
        "llms.process_voice_to_legal_text",
        boom,
        raising=False,
    )
    assert svc.polish_legal_text("hello world") == "hello world"
