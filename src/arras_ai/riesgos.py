"""Deterministic risk detectors and report composition.

Pure functions, no API calls — the reliable, free, testable half of the hybrid
risk detection (the other half is the LLM pass in agent.py). Kept pure so it is
trivially unit-tested and reusable by the Sprint 4 eval harness.
"""

from __future__ import annotations

from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    InformeArras,
    NivelRiesgo,
    Riesgo,
    Severidad,
    TipoArras,
)

UMBRAL_CONFIANZA_TIPO = 0.6


def detectar_por_reglas(analisis: AnalisisArras) -> list[Riesgo]:
    """Derive the 'obvious' risks directly from the structured extraction."""
    riesgos: list[Riesgo] = []

    if analisis.tipo_arras is TipoArras.no_especificado:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.tipo_ambiguo,
                severidad=Severidad.alta,
                descripcion=(
                    "El contrato no especifica la modalidad de arras. Por defecto, los "
                    "tribunales las interpretan como confirmatorias, la modalidad más vinculante."
                ),
                recomendacion=(
                    "Exige que el contrato indique expresamente el tipo de arras y cite el "
                    "artículo del Código Civil correspondiente."
                ),
                fuente="regla",
            )
        )
    elif analisis.confianza_tipo < UMBRAL_CONFIANZA_TIPO:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.tipo_ambiguo,
                severidad=Severidad.media,
                descripcion=(
                    f"La modalidad detectada ({analisis.tipo_arras.value}) no aparece de forma "
                    f"inequívoca (confianza {analisis.confianza_tipo:.0%})."
                ),
                recomendacion="Aclara en el contrato la modalidad de arras para evitar dudas.",
                fuente="regla",
            )
        )

    if analisis.tiene_clausula_financiacion is False:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.falta_financiacion,
                severidad=Severidad.alta,
                descripcion=(
                    "No consta cláusula suspensiva de financiación. Si el banco deniega la "
                    "hipoteca, el comprador puede perder la señal entregada."
                ),
                recomendacion=(
                    "Incluye una condición suspensiva de financiación que permita recuperar la "
                    "señal si no se concede el préstamo."
                ),
                fuente="regla",
            )
        )

    if analisis.fechas.fecha_limite_escritura is None and analisis.fechas.plazo_dias is None:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.fechas_mal_definidas,
                severidad=Severidad.media,
                descripcion="No se fija fecha límite ni plazo para otorgar la escritura pública.",
                recomendacion=(
                    "Fija una fecha límite concreta (o un plazo en días) para elevar a público "
                    "la compraventa."
                ),
                fuente="regla",
            )
        )

    if analisis.inmueble.referencia_catastral is None:
        descripcion = "El contrato no incluye la referencia catastral del inmueble."
        if analisis.inmueble.cargas is None:
            descripcion += " Tampoco indica si el inmueble está libre de cargas."
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.inmueble_mal_identificado,
                severidad=Severidad.media,
                descripcion=descripcion,
                recomendacion=(
                    "Añade la referencia catastral y el estado de cargas (nota simple registral) "
                    "para identificar el inmueble sin ambigüedad."
                ),
                fuente="regla",
            )
        )

    return riesgos


def nivel_global(riesgos: list[Riesgo]) -> NivelRiesgo:
    """Aggregate to a global level by maximum severity (no accumulation)."""
    severidades = {r.severidad for r in riesgos}
    if Severidad.alta in severidades:
        return NivelRiesgo.alto
    if Severidad.media in severidades:
        return NivelRiesgo.medio
    return NivelRiesgo.bajo


def componer_informe(
    analisis: AnalisisArras,
    riesgos_regla: list[Riesgo],
    riesgos_llm: list[Riesgo],
) -> InformeArras:
    """Merge rule + LLM risks, deduping only rule categories a rule already covered."""
    categorias_cubiertas = {r.categoria for r in riesgos_regla}
    llm_filtrados = [
        r
        for r in riesgos_llm
        if r.categoria is CategoriaRiesgo.otro or r.categoria not in categorias_cubiertas
    ]
    riesgos = [*riesgos_regla, *llm_filtrados]
    return InformeArras(
        analisis=analisis,
        riesgos=riesgos,
        nivel_riesgo_global=nivel_global(riesgos),
    )
