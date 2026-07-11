"""PDF text extraction.

Uses pdfplumber (MIT-licensed, built on pdfminer.six) rather than PyMuPDF (AGPL),
so the whole dependency tree stays MIT-compatible for an open-source project.
See ARCHITECTURE.md for the trade-off.
"""

from __future__ import annotations

from pathlib import Path

import pdfplumber


class PdfExtractionError(RuntimeError):
    """Raised when a PDF cannot be read or contains no extractable text."""


def extract_text(path: str | Path) -> str:
    """Extract the full text of a PDF as a single newline-joined string.

    Args:
        path: Path to a PDF file.

    Returns:
        The concatenated text of every page.

    Raises:
        PdfExtractionError: if the file is missing, unreadable, or has no text
            layer (e.g. a scanned image with no OCR).
    """
    pdf_path = Path(path)
    if not pdf_path.is_file():
        raise PdfExtractionError(f"File not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise PdfExtractionError(f"Not a PDF file: {pdf_path}")

    pages: list[str] = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(text)
    except PdfExtractionError:
        raise
    except Exception as exc:  # pdfminer raises a variety of low-level errors
        raise PdfExtractionError(f"Could not read PDF {pdf_path}: {exc}") from exc

    full_text = "\n\n".join(pages).strip()
    if not full_text:
        raise PdfExtractionError(
            f"No extractable text in {pdf_path}. "
            "It may be a scanned document without an OCR text layer."
        )
    return full_text
