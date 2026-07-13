"""Unit tests for the pure deterministic metrics. No API."""

from __future__ import annotations

from arras_ai.evals.dataset import GroundTruth
from arras_ai.evals.metrics import agregar, precision_recall_f1, puntuar_caso
from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    Riesgo,
    Severidad,
    TipoArras,
)


def _riesgo(cat: CategoriaRiesgo, sev: Severidad = Severidad.alta) -> Riesgo:
    return Riesgo(categoria=cat, severidad=sev, descripcion="d", recomendacion="r", fuente="regla")


def _informe(**a: object) -> InformeArras:
    analisis = AnalisisArras(
        tipo_arras=TipoArras.penitenciales,
        confianza_tipo=0.9,
        justificacion_tipo="j",
        partes=[],
        inmueble=Inmueble(referencia_catastral="X"),
        importes=Importes(),
        fechas=Fechas(fecha_limite_escritura="2025-06-15"),
        referencias_codigo_civil=[],
        tiene_clausula_financiacion=True,
        resumen="r",
    ).model_copy(update=a.get("analisis", {}))  # type: ignore[arg-type]
    return InformeArras(
        analisis=analisis,
        riesgos=a.get("riesgos", []),  # type: ignore[arg-type]
        nivel_riesgo_global=a.get("nivel", NivelRiesgo.bajo),  # type: ignore[arg-type]
    )


def test_prf_perfect_and_empty() -> None:
    s = {CategoriaRiesgo.falta_financiacion}
    assert precision_recall_f1(s, s) == (1.0, 1.0, 1.0)
    # nothing expected, nothing detected -> all 1.0 (nothing wrong)
    assert precision_recall_f1(set(), set()) == (1.0, 1.0, 1.0)
    # detected a false positive
    p, r, f = precision_recall_f1({CategoriaRiesgo.fechas_mal_definidas}, s)
    assert p == 0.0 and r == 0.0 and f == 0.0


def test_otro_excluded_from_detected() -> None:
    informe = _informe(
        riesgos=[_riesgo(CategoriaRiesgo.falta_financiacion), _riesgo(CategoriaRiesgo.otro)],
        nivel=NivelRiesgo.alto,
    )
    gt = GroundTruth(
        tipo_arras=TipoArras.penitenciales,
        tiene_clausula_financiacion=True,
        fecha_limite_presente=True,
        referencia_catastral_presente=True,
        riesgos_esperados=[CategoriaRiesgo.falta_financiacion],
        nivel_riesgo_global=NivelRiesgo.alto,
    )
    res = puntuar_caso(informe, gt)
    # 'otro' must not count as a false positive
    assert res.riesgos_precision == 1.0
    assert CategoriaRiesgo.otro not in res.detectados


def test_puntuar_caso_fields_and_confidence() -> None:
    informe = _informe(analisis={"confianza_tipo": 0.5})
    gt = GroundTruth(
        tipo_arras=TipoArras.penitenciales,
        confianza_max=0.6,
        tiene_clausula_financiacion=True,
        fecha_limite_presente=True,
        referencia_catastral_presente=True,
        nivel_riesgo_global=NivelRiesgo.bajo,
    )
    res = puntuar_caso(informe, gt)
    assert res.tipo_ok is True
    assert res.confianza_ok is True  # 0.5 <= 0.6
    assert res.campos["tiene_clausula_financiacion"] is True
    assert res.campos["referencia_catastral_presente"] is True


def test_agregar_accuracy() -> None:
    gt_ok = GroundTruth(
        tipo_arras=TipoArras.penitenciales,
        tiene_clausula_financiacion=True,
        fecha_limite_presente=True,
        referencia_catastral_presente=True,
        nivel_riesgo_global=NivelRiesgo.bajo,
    )
    gt_wrong = gt_ok.model_copy(update={"tipo_arras": TipoArras.confirmatorias})
    res = [puntuar_caso(_informe(), gt_ok), puntuar_caso(_informe(), gt_wrong)]
    agg = agregar(res)
    assert agg.tipo_accuracy == 0.5
    assert agg.n == 2
