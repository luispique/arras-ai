"""Tests for the MCP server. Pure tool tests run offline (no `mcp`, core mocked);
the registration test is gated on the `mcp` extra being installed."""

from __future__ import annotations

import pytest

from arras_ai import mcp_server
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


def test_analizar_contrato_arras_returns_json_dict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "analizar_texto", lambda texto: _informe())
    out = mcp_server.analizar_contrato_arras("un contrato de arras")
    assert isinstance(out, dict)
    assert out["nivel_riesgo_global"] == "bajo"
    assert out["analisis"]["tipo_arras"] == "penitenciales"


def test_analizar_contrato_arras_maps_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_t: str) -> InformeArras:
        raise AnalysisError("no se pudo")

    monkeypatch.setattr(mcp_server, "analizar_texto", boom)
    with pytest.raises(ValueError, match="No se pudo analizar"):
        mcp_server.analizar_contrato_arras("x")


def test_analizar_contrato_pdf_reads_then_analyzes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_server, "extract_text", lambda ruta: "texto del pdf")
    monkeypatch.setattr(mcp_server, "analizar_texto", lambda texto: _informe())
    out = mcp_server.analizar_contrato_pdf("/tmp/contrato.pdf")
    assert out["analisis"]["tipo_arras"] == "penitenciales"


def test_analizar_contrato_pdf_maps_pdf_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_r: str) -> str:
        raise PdfExtractionError("sin texto")

    monkeypatch.setattr(mcp_server, "extract_text", boom)
    with pytest.raises(ValueError, match="No se pudo leer el PDF"):
        mcp_server.analizar_contrato_pdf("/tmp/bad.pdf")


def test_build_server_registers_two_tools() -> None:
    pytest.importorskip("mcp")
    server = mcp_server.build_server()
    # The tool-listing accessor may differ across mcp versions — confirm against the
    # installed FastMCP API and adjust if needed (see Step 4 note).
    names = {t.name for t in server._tool_manager.list_tools()}  # noqa: SLF001
    assert {"analizar_contrato_arras", "analizar_contrato_pdf"} <= names
