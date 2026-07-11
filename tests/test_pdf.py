"""Unit tests for PDF text extraction (no API)."""

from __future__ import annotations

from pathlib import Path

import pytest

from arras_ai.pdf import PdfExtractionError, extract_text


def test_extract_text_from_fixture(penitenciales_pdf: Path) -> None:
    text = extract_text(penitenciales_pdf)
    assert "ARRAS PENITENCIALES" in text
    assert "1454" in text
    assert "280.000" in text


def test_missing_file_raises() -> None:
    with pytest.raises(PdfExtractionError, match="File not found"):
        extract_text("does/not/exist.pdf")


def test_non_pdf_extension_raises(tmp_path: Path) -> None:
    txt = tmp_path / "note.txt"
    txt.write_text("not a pdf")
    with pytest.raises(PdfExtractionError, match="Not a PDF"):
        extract_text(txt)


def test_corrupt_pdf_raises(tmp_path: Path) -> None:
    fake = tmp_path / "broken.pdf"
    fake.write_bytes(b"%PDF-1.4 this is not really a pdf")
    with pytest.raises(PdfExtractionError):
        extract_text(fake)
