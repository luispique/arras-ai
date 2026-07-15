"""Offline tests for the /api/analyze request logic. Analysis is mocked; no network."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import pytest

from arras_ai.analyzer import AnalysisError
from arras_ai.models import (
    AnalisisArras,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    TipoArras,
)
from arras_ai.pdf import PdfExtractionError

# The FastAPI entrypoint is a root-level module; load it by path.
_ANALYZE = Path(__file__).resolve().parent.parent / "main.py"
_spec = importlib.util.spec_from_file_location("arras_api_main", _ANALYZE)
assert _spec and _spec.loader
analyze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze)


def _informe() -> InformeArras:
    return InformeArras(
        analisis=AnalisisArras(
            tipo_arras=TipoArras.penitenciales,
            confianza_tipo=0.9,
            justificacion_tipo="j",
            partes=[],
            inmueble=Inmueble(),
            importes=Importes(),
            fechas=Fechas(),
            referencias_codigo_civil=[],
            tiene_clausula_financiacion=True,
            resumen="r",
        ),
        riesgos=[],
        nivel_riesgo_global=NivelRiesgo.bajo,
    )


def _ok(_texto: str) -> InformeArras:
    return _informe()


def test_texto_ok() -> None:
    status, body = analyze.procesar({"texto": "un contrato de arras"}, analizar=_ok)
    assert status == 200
    assert body["nivel_riesgo_global"] == "bajo"
    assert body["analisis"]["tipo_arras"] == "penitenciales"


def test_empty_input() -> None:
    status, body = analyze.procesar({}, analizar=_ok)
    assert status == 400 and "error" in body


def test_multiple_inputs() -> None:
    status, body = analyze.procesar({"texto": "x", "pdf_base64": "y"}, analizar=_ok)
    assert status == 400


def test_texto_too_long() -> None:
    status, body = analyze.procesar({"texto": "x" * (analyze.MAX_TEXTO + 1)}, analizar=_ok)
    assert status == 413


def test_analysis_error_maps_422() -> None:
    def boom(_t: str) -> InformeArras:
        raise AnalysisError("no se pudo analizar")

    status, body = analyze.procesar({"texto": "contrato"}, analizar=boom)
    assert status == 422


def test_pdf_too_big() -> None:
    big = base64.b64encode(b"%PDF-1.4" + b"0" * (analyze.MAX_PDF_BYTES + 1)).decode()
    status, body = analyze.procesar({"pdf_base64": big}, analizar=_ok)
    assert status == 413


def test_pdf_extraction_error_maps_422(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_extract(_b: bytes) -> str:
        raise PdfExtractionError("sin texto")

    monkeypatch.setattr(analyze, "extraer_texto_pdf", bad_extract)
    payload = {"pdf_base64": base64.b64encode(b"%PDF-1.4 mini").decode()}
    status, body = analyze.procesar(payload, analizar=_ok)
    assert status == 422


def test_corrupt_pdf_maps_422() -> None:
    import base64 as _b64

    corrupt = _b64.b64encode(b"%PDF-1.4 esto no es un PDF de verdad").decode()
    status, body = analyze.procesar({"pdf_base64": corrupt}, analizar=_ok)
    assert status == 422
    assert "error" in body


def test_fastapi_route(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setattr(analyze, "_analizar_real", _ok)
    client = TestClient(analyze.app)

    ok = client.post("/api/analyze", json={"texto": "un contrato de arras"})
    assert ok.status_code == 200
    assert ok.json()["analisis"]["tipo_arras"] == "penitenciales"

    # The bare path is also registered (service rewrite may drop the /api prefix).
    bare = client.post("/analyze", json={"texto": "un contrato de arras"})
    assert bare.status_code == 200

    bad = client.post("/api/analyze", json={})
    assert bad.status_code == 400
