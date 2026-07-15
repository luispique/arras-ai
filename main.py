"""Vercel Python API: a FastAPI app exposing POST /api/analyze.

Deployed as its own Vercel project (Root Directory = repo root); the entrypoint is
`main:app` (see `[tool.vercel]` in pyproject.toml). The file lives at the repo root
(not under `api/`) on purpose: Vercel treats `api/*.py` as individual serverless
functions mounted at their own path, whereas a root-level entrypoint deploys the
FastAPI app as a single catch-all function that receives the full request path — so
its `/api/analyze` route is reachable. The Astro frontend is a separate Vercel project
(Root Directory = web) that proxies `/api/*` here via a rewrite, so the browser stays
same-origin (no CORS). `app` is a thin FastAPI wrapper over a pure `procesar()`
(validation + caps + error mapping) that calls the unchanged Python core. The demo
configures a hosted embedding provider + a /tmp index via env vars; the core is
otherwise untouched.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

# The repo `src/` is bundled with the function; make `arras_ai` importable.
# This file lives at the repo root, so `src/` is a direct child.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

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
    # The core resolves the embedding provider (ARRAS_EMBEDDING_PROVIDER) + the
    # /tmp index dir (ARRAS_KB_INDEX_DIR) from the environment set on the deploy.
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


app = FastAPI(title="arras-ai")


async def _handle(request: Request) -> JSONResponse:
    body_bytes = await request.body()
    if len(body_bytes) > MAX_PDF_BYTES * 2:
        return JSONResponse(status_code=413, content={"error": "Cuerpo demasiado grande."})
    try:
        payload = json.loads(body_bytes)
    except (json.JSONDecodeError, ValueError):
        return JSONResponse(status_code=400, content={"error": "JSON inválido."})
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400, content={"error": "El cuerpo debe ser un objeto JSON."}
        )
    status, result = procesar(payload, analizar=_analizar_real)
    return JSONResponse(status_code=status, content=result)


# The frontend rewrite forwards `/api/*` here preserving the prefix, so the app
# is reached at `/api/analyze`. The bare `/analyze` is also registered for direct
# calls to the API deployment (curl, health checks) without the prefix.
@app.post("/api/analyze")
async def analyze_api(request: Request) -> JSONResponse:
    return await _handle(request)


@app.post("/analyze")
async def analyze_bare(request: Request) -> JSONResponse:
    return await _handle(request)
