"""Unit tests for the agent (LangGraph nodes + LLM pass) with Claude mocked."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic

from arras_ai import agent
from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    RiesgoBase,
    RiesgosDetectadosLLM,
    Severidad,
)


class _FakeMessages:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.messages = _FakeMessages(response)


def test_detectar_riesgos_llm_marks_fuente_llm(fake_analisis: AnalisisArras) -> None:
    parsed = RiesgosDetectadosLLM(
        riesgos=[
            RiesgoBase(
                categoria=CategoriaRiesgo.reparto_gastos_ambiguo,
                severidad=Severidad.baja,
                descripcion="El reparto de gastos no está claro.",
                recomendacion="Detalla qué gastos asume cada parte.",
            )
        ]
    )
    client = _FakeClient(SimpleNamespace(parsed_output=parsed, stop_reason="end_turn"))
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, client=cast(anthropic.Anthropic, client)
    )
    assert len(riesgos) == 1
    assert riesgos[0].fuente == "llm"
    assert riesgos[0].categoria is CategoriaRiesgo.reparto_gastos_ambiguo


def test_detectar_riesgos_llm_returns_empty_when_unparsed(fake_analisis: AnalisisArras) -> None:
    client = _FakeClient(SimpleNamespace(parsed_output=None, stop_reason="max_tokens"))
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, client=cast(anthropic.Anthropic, client)
    )
    assert riesgos == []
