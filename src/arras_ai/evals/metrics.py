"""Pure deterministic scoring of an InformeArras against ground truth. No API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arras_ai.evals.dataset import GroundTruth
from arras_ai.models import CategoriaRiesgo, InformeArras

TOLERANCIA_IMPORTE = 0.01


def precision_recall_f1(
    detectados: set[CategoriaRiesgo], esperados: set[CategoriaRiesgo]
) -> tuple[float, float, float]:
    tp = len(detectados & esperados)
    fp = len(detectados - esperados)
    fn = len(esperados - detectados)
    precision = 1.0 if tp + fp == 0 else tp / (tp + fp)
    recall = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


class ResultadoDeterminista(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_ok: bool
    confianza_ok: bool | None
    campos: dict[str, bool]
    riesgos_precision: float
    riesgos_recall: float
    riesgos_f1: float
    nivel_ok: bool
    detectados: list[CategoriaRiesgo]
    esperados: list[CategoriaRiesgo]


def _num_ok(actual: float | None, esperado: float | None) -> bool:
    if esperado is None:
        return True
    if actual is None:
        return False
    return abs(actual - esperado) <= abs(esperado) * TOLERANCIA_IMPORTE


def puntuar_caso(informe: InformeArras, gt: GroundTruth) -> ResultadoDeterminista:
    a = informe.analisis
    confianza_ok: bool | None = None
    if gt.confianza_min is not None or gt.confianza_max is not None:
        lo = gt.confianza_min if gt.confianza_min is not None else 0.0
        hi = gt.confianza_max if gt.confianza_max is not None else 1.0
        confianza_ok = lo <= a.confianza_tipo <= hi

    campos = {
        "precio_total": _num_ok(a.importes.precio_total, gt.precio_total),
        "importe_arras": _num_ok(a.importes.importe_arras, gt.importe_arras),
        "tiene_clausula_financiacion": a.tiene_clausula_financiacion
        == gt.tiene_clausula_financiacion,
        "referencia_catastral_presente": (a.inmueble.referencia_catastral is not None)
        == gt.referencia_catastral_presente,
        "fecha_limite_presente": (
            a.fechas.fecha_limite_escritura is not None or a.fechas.plazo_dias is not None
        )
        == gt.fecha_limite_presente,
    }

    detectados: set[CategoriaRiesgo] = {
        r.categoria for r in informe.riesgos if r.categoria is not CategoriaRiesgo.otro
    }
    esperados = set(gt.riesgos_esperados)
    p, r, f = precision_recall_f1(detectados, esperados)

    return ResultadoDeterminista(
        tipo_ok=a.tipo_arras == gt.tipo_arras,
        confianza_ok=confianza_ok,
        campos=campos,
        riesgos_precision=p,
        riesgos_recall=r,
        riesgos_f1=f,
        nivel_ok=informe.nivel_riesgo_global == gt.nivel_riesgo_global,
        detectados=sorted(detectados, key=lambda c: c.value),
        esperados=sorted(esperados, key=lambda c: c.value),
    )


class AgregadoDeterminista(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_accuracy: float
    confianza_band_rate: float | None
    campos_accuracy: dict[str, float]
    riesgos_precision_micro: float
    riesgos_recall_micro: float
    riesgos_f1_micro: float
    riesgos_f1_macro: float
    nivel_accuracy: float
    n: int


def agregar(resultados: list[ResultadoDeterminista]) -> AgregadoDeterminista:
    n = len(resultados)
    if n == 0:
        raise ValueError("No results to aggregate")

    tipo_accuracy = sum(r.tipo_ok for r in resultados) / n
    nivel_accuracy = sum(r.nivel_ok for r in resultados) / n

    conf = [r.confianza_ok for r in resultados if r.confianza_ok is not None]
    confianza_band_rate = (sum(conf) / len(conf)) if conf else None

    campos_keys = resultados[0].campos.keys()
    campos_accuracy = {k: sum(r.campos[k] for r in resultados) / n for k in campos_keys}

    tp = fp = fn = 0
    for r in resultados:
        det, esp = set(r.detectados), set(r.esperados)
        tp += len(det & esp)
        fp += len(det - esp)
        fn += len(esp - det)
    p_micro = 1.0 if tp + fp == 0 else tp / (tp + fp)
    r_micro = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f_micro = 0.0 if p_micro + r_micro == 0 else 2 * p_micro * r_micro / (p_micro + r_micro)
    f_macro = sum(r.riesgos_f1 for r in resultados) / n

    return AgregadoDeterminista(
        tipo_accuracy=tipo_accuracy,
        confianza_band_rate=confianza_band_rate,
        campos_accuracy=campos_accuracy,
        riesgos_precision_micro=p_micro,
        riesgos_recall_micro=r_micro,
        riesgos_f1_micro=f_micro,
        riesgos_f1_macro=f_macro,
        nivel_accuracy=nivel_accuracy,
        n=n,
    )
