"""Vercel Python function: POST /api/analyze.

Thin HTTP wrapper over a pure `procesar()` (validation + caps + error mapping) that
calls the unchanged Python core. The demo configures hosted Voyage embeddings and a
/tmp index via environment variables; the core is otherwise untouched.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler
from typing import Any

# The repo `src/` is bundled with the function; make `arras_ai` importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from arras_ai.analyzer import AnalysisError  # noqa: E402
from arras_ai.models import InformeArras  # noqa: E402
from arras_ai.pdf import PdfExtractionError  # noqa: E402

MAX_TEXTO = 30_000
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGINAS = 15


def extraer_texto_pdf(data: bytes) -> str:
    """Extract text from PDF bytes with the same engine/limits as the core CLI."""
    import pdfplumber

    paginas: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > MAX_PDF_PAGINAS:
                raise PdfExtractionError(
                    f"El PDF tiene demasiadas páginas (máximo {MAX_PDF_PAGINAS})."
                )
            for page in pdf.pages:
                texto = page.extract_text() or ""
                if texto.strip():
                    paginas.append(texto)
    except PdfExtractionError:
        raise
    except Exception as exc:  # pdfminer raises a variety of low-level errors
        raise PdfExtractionError(
            "No se pudo leer el PDF (¿archivo dañado o no es un PDF?)."
        ) from exc
    full = "\n\n".join(paginas).strip()
    if not full:
        raise PdfExtractionError("No se pudo extraer texto del PDF (¿es un escaneo sin OCR?).")
    return full


def _analizar_real(texto: str) -> InformeArras:
    # The core resolves the Voyage provider + /tmp index from the environment.
    from arras_ai.agent import analizar_texto

    return analizar_texto(texto)


def procesar(
    payload: dict[str, Any], *, analizar: Callable[[str], InformeArras]
) -> tuple[int, dict[str, Any]]:
    """Validate, cap, and run one analysis request. Pure except for `analizar`."""
    texto_in = payload.get("texto")
    pdf_in = payload.get("pdf_base64")

    if (texto_in is None) == (pdf_in is None):
        return 400, {"error": "Envía exactamente uno: 'texto' o 'pdf_base64'."}

    if texto_in is not None:
        if not isinstance(texto_in, str) or not texto_in.strip():
            return 400, {"error": "El campo 'texto' está vacío."}
        if len(texto_in) > MAX_TEXTO:
            return 413, {"error": f"El texto supera el máximo de {MAX_TEXTO} caracteres."}
        texto = texto_in
    else:
        if not isinstance(pdf_in, str):
            return 400, {"error": "El campo 'pdf_base64' no es válido."}
        try:
            data = base64.b64decode(pdf_in, validate=True)
        except (binascii.Error, ValueError):
            return 400, {"error": "El PDF no está correctamente codificado en base64."}
        if len(data) > MAX_PDF_BYTES:
            return 413, {"error": "El PDF supera el máximo de 5 MB."}
        try:
            texto = extraer_texto_pdf(data)
        except PdfExtractionError as exc:
            return 422, {"error": str(exc)}

    try:
        informe = analizar(texto)
    except (AnalysisError, PdfExtractionError) as exc:
        return 422, {"error": str(exc)}
    except Exception:  # upstream model/API failure
        return 502, {"error": "Error del servicio de análisis. Inténtalo de nuevo más tarde."}

    return 200, json.loads(informe.model_dump_json())


class handler(BaseHTTPRequestHandler):  # noqa: N801 (Vercel Python function entry point)
    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._send(400, {"error": "Content-Type debe ser application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_PDF_BYTES * 2:
            self._send(413, {"error": "Cuerpo de la petición ausente o demasiado grande."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._send(400, {"error": "JSON inválido."})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "El cuerpo debe ser un objeto JSON."})
            return
        status, body = procesar(payload, analizar=_analizar_real)
        self._send(status, body)

    def do_GET(self) -> None:  # noqa: N802
        self._send(405, {"error": "Usa POST para analizar."})
