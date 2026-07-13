"""Unit tests for the LLM-as-judge with the client mocked. No network."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic

from arras_ai.evals.judge import VeredictoFidelidad, VeredictoRecomendacion, juzgar_fidelidad
from arras_ai.models import (
    AnalisisArras,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    TipoArras,
)


class _FakeMessages:
    def __init__(self, parsed: object) -> None:
        self._parsed = parsed
        self.last_kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return SimpleNamespace(parsed_output=self._parsed, stop_reason="end_turn")


class _FakeClient:
    def __init__(self, parsed: object) -> None:
        self.messages = _FakeMessages(parsed)


def _informe() -> InformeArras:
    return InformeArras(
        analisis=AnalisisArras(
            tipo_arras=TipoArras.penitenciales,
            confianza_tipo=0.9,
            justificacion_tipo="Cita el art. 1454 y el derecho de desistimiento.",
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


def test_juzgar_fidelidad_parses_and_passes_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    veredicto = VeredictoFidelidad(
        veredicto="fiel", score=5, evidencia="art. 1454", razonamiento="coherente"
    )
    client = _FakeClient(veredicto)
    out = juzgar_fidelidad(
        "texto del contrato",
        _informe(),
        client=cast(anthropic.Anthropic, client),
        model="claude-sonnet-5",
    )
    assert out.veredicto == "fiel" and out.score == 5
    assert client.messages.last_kwargs["model"] == "claude-sonnet-5"
    assert client.messages.last_kwargs["output_format"] is VeredictoFidelidad


def test_recomendacion_schema_bounds() -> None:
    import pytest
    from pydantic import ValidationError

    VeredictoRecomendacion(score=3, razonamiento="ok")
    with pytest.raises(ValidationError):
        VeredictoRecomendacion(score=9, razonamiento="fuera de rango")
