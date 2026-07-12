"""Unit tests for the agent (LangGraph nodes + LLM pass) with Claude mocked."""

from __future__ import annotations

from pathlib import Path
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
    RiesgoLLM,
    RiesgosDetectadosLLM,
    Severidad,
)
from arras_ai.rag.knowledge_base import KnowledgeBase

_KB_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kb"


def _load_kb() -> KnowledgeBase:
    return KnowledgeBase.from_data_dir(_KB_DATA_DIR, index_dir=Path("/tmp/unused"))


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
            RiesgoLLM(
                categoria=CategoriaRiesgo.reparto_gastos_ambiguo,
                severidad=Severidad.baja,
                descripcion="El reparto de gastos no está claro.",
                recomendacion="Detalla qué gastos asume cada parte.",
            )
        ]
    )
    client = _FakeClient(SimpleNamespace(parsed_output=parsed, stop_reason="end_turn"))
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, [], client=cast(anthropic.Anthropic, client), kb=_load_kb()
    )
    assert len(riesgos) == 1
    assert riesgos[0].fuente == "llm"
    assert riesgos[0].categoria is CategoriaRiesgo.reparto_gastos_ambiguo


def test_detectar_riesgos_llm_returns_empty_when_unparsed(fake_analisis: AnalisisArras) -> None:
    client = _FakeClient(SimpleNamespace(parsed_output=None, stop_reason="max_tokens"))
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, [], client=cast(anthropic.Anthropic, client), kb=_load_kb()
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
    # retrieval is stubbed so no index/model is needed
    monkeypatch.setattr(KnowledgeBase, "retrieve", lambda self, q, k=4: [])

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace())), kb=_load_kb()
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
    # retrieval is stubbed so no index/model is needed
    monkeypatch.setattr(KnowledgeBase, "retrieve", lambda self, q, k=4: [])

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace())), kb=_load_kb()
    )
    # still produced from rule risks
    assert any(r.fuente == "regla" for r in informe.riesgos)
    assert all(r.fuente == "regla" for r in informe.riesgos)


def test_analizar_texto_rejects_empty() -> None:
    with pytest.raises(AnalysisError):
        agent.analizar_texto(
            "   ", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
        )


def test_detectar_riesgos_llm_maps_patron_ids_to_fundamentos(fake_analisis: AnalisisArras) -> None:
    from pathlib import Path

    from arras_ai.models import RiesgoLLM, RiesgosDetectadosLLM
    from arras_ai.rag.knowledge_base import KnowledgeBase, PatronHit

    data_dir = Path(__file__).resolve().parent.parent / "data" / "kb"
    kb = KnowledgeBase.from_data_dir(data_dir, index_dir=Path("/tmp/unused"))
    parsed = RiesgosDetectadosLLM(
        riesgos=[
            RiesgoLLM(
                categoria=CategoriaRiesgo.reparto_gastos_ambiguo,
                severidad=Severidad.baja,
                descripcion="d",
                recomendacion="r",
                patron_ids=["gastos", "ghost"],
            ),
            RiesgoLLM(
                categoria=CategoriaRiesgo.otro,
                severidad=Severidad.baja,
                descripcion="sin cita",
                recomendacion="r",
                patron_ids=[],
            ),
        ]
    )
    client = _FakeClient(SimpleNamespace(parsed_output=parsed, stop_reason="end_turn"))
    gastos = kb.get_patron("gastos")
    assert gastos is not None
    patrones = [PatronHit(patron=gastos, score=0.9)]
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, patrones, client=cast(anthropic.Anthropic, client), kb=kb
    )
    assert riesgos[0].fuente == "llm"
    refs = riesgos[0].referencias
    assert [f.referencia for f in refs] == [gastos.como_fundamento().referencia]
    # 'ghost' (unknown id) dropped.
    # A finding that names NO patron_ids gets NO citation, even though a pattern was
    # retrieved — we never fabricate a citation by association.
    assert riesgos[1].referencias == []


def test_analizar_texto_attaches_rule_citations(
    monkeypatch: pytest.MonkeyPatch, fake_analisis: AnalisisArras
) -> None:
    from pathlib import Path

    from arras_ai.models import CategoriaRiesgo, NivelRiesgo
    from arras_ai.rag.knowledge_base import KnowledgeBase

    data_dir = Path(__file__).resolve().parent.parent / "data" / "kb"
    kb = KnowledgeBase.from_data_dir(data_dir, index_dir=Path("/tmp/unused"))

    analisis = fake_analisis.model_copy(update={"tiene_clausula_financiacion": False})
    monkeypatch.setattr(agent, "analyze_text", lambda *a, **k: analisis)
    monkeypatch.setattr(agent, "detectar_riesgos_llm", lambda *a, **k: [])
    # retrieval is stubbed so no index/model is needed
    monkeypatch.setattr(KnowledgeBase, "retrieve", lambda self, q, k=4: [])

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace())), kb=kb
    )
    fin = next(r for r in informe.riesgos if r.categoria is CategoriaRiesgo.falta_financiacion)
    assert fin.referencias and fin.referencias[0].tipo == "doctrina"
    assert informe.nivel_riesgo_global is NivelRiesgo.alto


def test_construir_query_uses_facts_not_raw_text(fake_analisis: AnalisisArras) -> None:
    analisis = fake_analisis.model_copy(update={"tiene_clausula_financiacion": False})
    q = agent.construir_query_recuperacion(analisis)
    assert analisis.tipo_arras.value in q
    assert "financiación" in q.lower()  # the detected absence is in the query
    assert "INICIO DEL CONTRATO" not in q  # NOT a raw contract-text dump
    assert len(q) < 1000  # focused, within the embedder's token budget
