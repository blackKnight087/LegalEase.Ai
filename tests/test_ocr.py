import ocr_engine
from document_processing import extract_text_from_pdf


def test_should_run_ocr_low_text():
    assert ocr_engine.should_run_ocr("", page_count=3) is True
    assert ocr_engine.should_run_ocr("tiny", page_count=5) is True


def test_should_not_run_ocr_rich_text():
    rich = "Section 66C identity theft. " * 40
    assert ocr_engine.should_run_ocr(rich, page_count=2) is False


def test_ocr_cache_roundtrip(tmp_path, monkeypatch):
    pdf = tmp_path / "sample.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%EOF")
    monkeypatch.setattr(ocr_engine, "OCR_CACHE_DIR", tmp_path / "cache")
    ocr_engine.OCR_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    ocr_engine.write_ocr_cache(pdf, "[Page 1]\nCached OCR text for legal section.")
    cached = ocr_engine.read_ocr_cache(pdf)
    assert cached
    assert "Cached OCR text" in cached


def test_extract_text_from_pdf_native_only(monkeypatch, tmp_path):
    def fake_routed(path, progress_callback=None):
        return "[Page 1]\nSection 420 IPC cheating and dishonesty.", "native_pdf"

    monkeypatch.setattr(
        "backend.app.core.ocr_router.extract_text_routed",
        fake_routed,
    )

    pdf_path = tmp_path / "x.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    text, method = extract_text_from_pdf(pdf_path)
    assert "Section 420" in text
    assert method == "native_pdf"


def test_extract_text_from_pdf_uses_ocr_when_needed(monkeypatch, tmp_path):
    def fake_routed(path, progress_callback=None):
        return "[Page 1]\nSection 57 CrPC procedure.", "ocr_easyocr"

    import document_processing as dp

    monkeypatch.setattr(
        "backend.app.core.ocr_router.extract_text_routed",
        fake_routed,
    )

    pdf_path = tmp_path / "scan.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%EOF")
    text, method = extract_text_from_pdf(pdf_path)
    assert "Section 57" in text
    assert method == "ocr_easyocr"
