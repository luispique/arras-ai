"""Unit tests for the deterministic risk detectors (pure, no API)."""

from __future__ import annotations

from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    Fechas,
    Importes,
    Inmueble,
    NivelRiesgo,
    Riesgo,
    Severidad,
    TipoArras,
)
from arras_ai.riesgos import componer_informe, detectar_por_reglas, nivel_global


def _analisis(**overrides: object) -> AnalisisArras:
    base = AnalisisArras(
        tipo_arras=TipoArras.penitenciales,
        confianza_tipo=0.95,
        justificacion_tipo="cita art. 1454",
        partes=[],
        inmueble=Inmueble(referencia_catastral="9872023VH5797S0001WX", cargas="libre de cargas"),
        importes=Importes(),
        fechas=Fechas(fecha_limite_escritura="2025-06-15"),
        referencias_codigo_civil=[],
        tiene_clausula_financiacion=True,
        resumen="ok",
    )
    return base.model_copy(update=overrides)


def _cats(riesgos: list[Riesgo]) -> set[CategoriaRiesgo]:
    return {r.categoria for r in riesgos}


def test_clean_contract_has_no_rule_risks() -> None:
    assert detectar_por_reglas(_analisis()) == []


def test_tipo_no_especificado_is_high_risk() -> None:
    riesgos = detectar_por_reglas(_analisis(tipo_arras=TipoArras.no_especificado))
    tipo = next(r for r in riesgos if r.categoria is CategoriaRiesgo.tipo_ambiguo)
    assert tipo.severidad is Severidad.alta
    assert tipo.fuente == "regla"


def test_low_confidence_type_is_medium_risk() -> None:
    riesgos = detectar_por_reglas(_analisis(confianza_tipo=0.4))
    tipo = next(r for r in riesgos if r.categoria is CategoriaRiesgo.tipo_ambiguo)
    assert tipo.severidad is Severidad.media


def test_missing_financing_clause_detected() -> None:
    riesgos = detectar_por_reglas(_analisis(tiene_clausula_financiacion=False))
    assert CategoriaRiesgo.falta_financiacion in _cats(riesgos)


def test_missing_dates_detected() -> None:
    riesgos = detectar_por_reglas(_analisis(fechas=Fechas()))
    assert CategoriaRiesgo.fechas_mal_definidas in _cats(riesgos)


def test_missing_cadastral_reference_detected() -> None:
    riesgos = detectar_por_reglas(_analisis(inmueble=Inmueble()))
    assert CategoriaRiesgo.inmueble_mal_identificado in _cats(riesgos)


def test_nivel_global_takes_max_severity() -> None:
    def r(sev: Severidad) -> Riesgo:
        return Riesgo(categoria=CategoriaRiesgo.otro, severidad=sev,
                      descripcion="d", recomendacion="r", fuente="regla")

    assert nivel_global([]) is NivelRiesgo.bajo
    assert nivel_global([r(Severidad.baja), r(Severidad.media)]) is NivelRiesgo.medio
    assert nivel_global([r(Severidad.media), r(Severidad.alta)]) is NivelRiesgo.alto


def test_componer_dedups_rule_categories_but_keeps_otro() -> None:
    analisis = _analisis(tiene_clausula_financiacion=False)
    reglas = detectar_por_reglas(analisis)  # includes falta_financiacion (regla)
    llm = [
        Riesgo(categoria=CategoriaRiesgo.falta_financiacion, severidad=Severidad.media,
               descripcion="dup", recomendacion="r", fuente="llm"),
        Riesgo(categoria=CategoriaRiesgo.otro, severidad=Severidad.baja,
               descripcion="extra1", recomendacion="r", fuente="llm"),
        Riesgo(categoria=CategoriaRiesgo.otro, severidad=Severidad.baja,
               descripcion="extra2", recomendacion="r", fuente="llm"),
    ]
    informe = componer_informe(analisis, reglas, llm)
    # the LLM's duplicate falta_financiacion is dropped (rule wins)...
    fin = [r for r in informe.riesgos if r.categoria is CategoriaRiesgo.falta_financiacion]
    assert len(fin) == 1 and fin[0].fuente == "regla"
    # ...but both 'otro' findings survive
    otros = [r for r in informe.riesgos if r.categoria is CategoriaRiesgo.otro]
    assert len(otros) == 2
    assert informe.nivel_riesgo_global is NivelRiesgo.alto
