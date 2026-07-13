"""Orchestrate an eval run: analyze each case, score it, judge it, aggregate."""

from __future__ import annotations

import logging

import anthropic
from pydantic import BaseModel, ConfigDict

from arras_ai.agent import analizar_texto
from arras_ai.analyzer import _build_client
from arras_ai.config import DEFAULT_JUDGE_MODEL, DEFAULT_MODEL, load_settings
from arras_ai.evals.dataset import CasoEval
from arras_ai.evals.judge import (
    VeredictoFidelidad,
    VeredictoRecomendacion,
    juzgar_fidelidad,
    juzgar_recomendaciones,
)
from arras_ai.evals.metrics import (
    AgregadoDeterminista,
    ResultadoDeterminista,
    agregar,
    puntuar_caso,
)
from arras_ai.rag.knowledge_base import KnowledgeBase

logger = logging.getLogger("arras_ai.evals")


class CasoRegistro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    determinista: ResultadoDeterminista | None = None
    fidelidad: VeredictoFidelidad | None = None
    recomendacion: VeredictoRecomendacion | None = None
    error: str | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agregado: AgregadoDeterminista
    fidelidad_media: float | None
    recomendacion_media: float | None
    distribucion_veredictos: dict[str, int]
    registros: list[CasoRegistro]
    analyzer_model: str
    judge_model: str
    n_errores: int


def run_evals(
    casos: list[CasoEval],
    *,
    analyzer_client: anthropic.Anthropic | None = None,
    judge_client: anthropic.Anthropic | None = None,
    analyzer_model: str = DEFAULT_MODEL,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    kb: KnowledgeBase | None = None,
) -> EvalReport:
    if judge_model == analyzer_model:
        logger.warning(
            "judge_model == analyzer_model (%s): self-evaluation bias; "
            "set ARRAS_JUDGE_MODEL to a different model",
            judge_model,
        )

    if judge_client is None:
        judge_client = _build_client(load_settings().anthropic_api_key)

    registros: list[CasoRegistro] = []
    for caso in casos:
        try:
            informe = analizar_texto(
                caso.texto, client=analyzer_client, model=analyzer_model, kb=kb
            )
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            logger.warning("case %s analysis failed: %s", caso.id, exc)
            registros.append(CasoRegistro(id=caso.id, error=f"analysis: {exc}"))
            continue

        determinista = puntuar_caso(informe, caso.ground_truth)
        fidelidad: VeredictoFidelidad | None = None
        recomendacion: VeredictoRecomendacion | None = None
        error: str | None = None
        try:
            fidelidad = juzgar_fidelidad(
                caso.texto, informe, client=judge_client, model=judge_model
            )
            if informe.riesgos:
                recomendacion = juzgar_recomendaciones(
                    caso.texto, informe, client=judge_client, model=judge_model
                )
        except Exception as exc:  # noqa: BLE001 - a judge failure must not discard determinista
            logger.warning("case %s judge failed: %s", caso.id, exc)
            fidelidad = None
            recomendacion = None
            error = f"judge: {exc}"

        registros.append(
            CasoRegistro(
                id=caso.id,
                determinista=determinista,
                fidelidad=fidelidad,
                recomendacion=recomendacion,
                error=error,
            )
        )

    deterministas = [r.determinista for r in registros if r.determinista is not None]
    agregado = (
        agregar(deterministas)
        if deterministas
        else AgregadoDeterminista(
            tipo_accuracy=0.0,
            confianza_band_rate=None,
            campos_accuracy={},
            riesgos_precision_micro=0.0,
            riesgos_recall_micro=0.0,
            riesgos_f1_micro=0.0,
            riesgos_f1_macro=0.0,
            nivel_accuracy=0.0,
            n=0,
        )
    )

    fidelidades = [r.fidelidad for r in registros if r.fidelidad is not None]
    recomendaciones = [r.recomendacion for r in registros if r.recomendacion is not None]
    fidelidad_media = sum(f.score for f in fidelidades) / len(fidelidades) if fidelidades else None
    recomendacion_media = (
        sum(r.score for r in recomendaciones) / len(recomendaciones) if recomendaciones else None
    )
    distribucion: dict[str, int] = {}
    for f in fidelidades:
        distribucion[f.veredicto] = distribucion.get(f.veredicto, 0) + 1

    return EvalReport(
        agregado=agregado,
        fidelidad_media=fidelidad_media,
        recomendacion_media=recomendacion_media,
        distribucion_veredictos=distribucion,
        registros=registros,
        analyzer_model=analyzer_model,
        judge_model=judge_model,
        n_errores=sum(1 for r in registros if r.error is not None),
    )


def metricas_cabecera(report: EvalReport) -> dict[str, float]:
    return {
        "tipo_accuracy": report.agregado.tipo_accuracy,
        "riesgos_f1_micro": report.agregado.riesgos_f1_micro,
        "juez_fidelidad_media": (
            report.fidelidad_media / 5.0 if report.fidelidad_media is not None else 0.0
        ),
    }
