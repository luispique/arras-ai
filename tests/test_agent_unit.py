"""Unit tests for the agent (LangGraph nodes + LLM pass) with Claude mocked."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest

from arras_ai import agent
from arras_ai.analyzer import AnalysisError
from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    InformeArras,
    NivelRiesgo,
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


def _stub_extract(monkeypatch: pytest.MonkeyPatch, analisis: AnalisisArras) -> None:
    monkeypatch.setattr(agent, "analyze_text", lambda *a, **k: analisis)


def test_analizar_texto_builds_informe(
    monkeypatch: pytest.MonkeyPatch, fake_analisis: AnalisisArras
) -> None:
    # extraction returns a contract missing the financing clause -> rule risk
    analisis = fake_analisis.model_copy(update={"tiene_clausula_financiacion": False})
    _stub_extract(monkeypatch, analisis)
    monkeypatch.setattr(agent, "detectar_riesgos_llm", lambda *a, **k: [])

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
    )
    assert isinstance(informe, InformeArras)
    assert any(r.categoria is CategoriaRiesgo.falta_financiacion for r in informe.riesgos)
    assert informe.nivel_riesgo_global is NivelRiesgo.alto


def test_analizar_texto_degrades_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch, fake_analisis: AnalisisArras
) -> None:
    analisis = fake_analisis.model_copy(update={"tiene_clausula_financiacion": False})
    _stub_extract(monkeypatch, analisis)

    def _boom(*a: Any, **k: Any) -> list[Any]:
        raise RuntimeError("network down")

    monkeypatch.setattr(agent, "detectar_riesgos_llm", _boom)

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
    )
    # still produced from rule risks
    assert any(r.fuente == "regla" for r in informe.riesgos)
    assert all(r.fuente == "regla" for r in informe.riesgos)


def test_analizar_texto_rejects_empty() -> None:
    with pytest.raises(AnalysisError):
        agent.analizar_texto(
            "   ", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
        )
