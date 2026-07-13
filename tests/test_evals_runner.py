"""Unit tests for the eval runner with analyzer + judge mocked. No API."""

from __future__ import annotations

import pytest

from arras_ai.evals import runner
from arras_ai.evals.dataset import CasoEval, GroundTruth
from arras_ai.evals.judge import VeredictoFidelidad, VeredictoRecomendacion
from arras_ai.evals.runner import metricas_cabecera, run_evals
from arras_ai.models import (
    AnalisisArras,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    TipoArras,
)


def _caso(cid: str, tipo: TipoArras) -> CasoEval:
    return CasoEval(
        id=cid,
        texto="texto",
        ground_truth=GroundTruth(
            tipo_arras=tipo,
            tiene_clausula_financiacion=True,
            fecha_limite_presente=True,
            referencia_catastral_presente=True,
            nivel_riesgo_global=NivelRiesgo.bajo,
        ),
    )


def _informe(tipo: TipoArras) -> InformeArras:
    return InformeArras(
        analisis=AnalisisArras(
            tipo_arras=tipo,
            confianza_tipo=0.9,
            justificacion_tipo="j",
            partes=[],
            inmueble=Inmueble(referencia_catastral="X"),
            importes=Importes(),
            fechas=Fechas(fecha_limite_escritura="2025-06-15"),
            referencias_codigo_civil=[],
            tiene_clausula_financiacion=True,
            resumen="r",
        ),
        riesgos=[],
        nivel_riesgo_global=NivelRiesgo.bajo,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, *, fail_id: str | None = None) -> None:
    def fake_analizar(texto: str, **kw: object) -> InformeArras:
        return _informe(TipoArras.penitenciales)

    monkeypatch.setattr(runner, "analizar_texto", fake_analizar)
    monkeypatch.setattr(
        runner,
        "juzgar_fidelidad",
        lambda *a, **k: VeredictoFidelidad(
            veredicto="fiel", score=4, evidencia="e", razonamiento="r"
        ),
    )
    monkeypatch.setattr(
        runner,
        "juzgar_recomendaciones",
        lambda *a, **k: VeredictoRecomendacion(score=4, razonamiento="r"),
    )


def test_run_evals_produces_report(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch)
    casos = [_caso("a", TipoArras.penitenciales), _caso("b", TipoArras.confirmatorias)]
    report = run_evals(casos, analyzer_client=object(), judge_client=object())  # type: ignore[arg-type]
    assert report.agregado.n == 2
    assert report.agregado.tipo_accuracy == 0.5  # 'b' expected confirmatorias, got penitenciales
    assert report.fidelidad_media == 4.0
    assert report.n_errores == 0
    head = metricas_cabecera(report)
    assert head["juez_fidelidad_media"] == pytest.approx(0.8)  # 4/5


def test_run_evals_records_case_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(texto: str, **kw: object) -> InformeArras:
        raise RuntimeError("analyzer down")

    monkeypatch.setattr(runner, "analizar_texto", boom)
    report = run_evals(
        [_caso("a", TipoArras.penitenciales)],
        analyzer_client=object(),  # type: ignore[arg-type]
        judge_client=object(),  # type: ignore[arg-type]
    )
    assert report.n_errores == 1
    assert report.registros[0].error is not None
    assert report.agregado.n == 0 or report.registros[0].determinista is None


def test_warns_when_judge_equals_analyzer(monkeypatch: pytest.MonkeyPatch, caplog) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)
    import logging

    with caplog.at_level(logging.WARNING):
        run_evals(
            [_caso("a", TipoArras.penitenciales)],
            analyzer_client=object(),  # type: ignore[arg-type]
            judge_client=object(),  # type: ignore[arg-type]
            analyzer_model="m",
            judge_model="m",
        )
    assert any("judge" in r.message.lower() for r in caplog.records)
