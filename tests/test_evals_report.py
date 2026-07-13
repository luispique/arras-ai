"""Unit tests for eval report rendering. No API."""

from __future__ import annotations

import json

from rich.console import Console

from arras_ai.evals.metrics import AgregadoDeterminista
from arras_ai.evals.report import render_human, to_json
from arras_ai.evals.runner import CasoRegistro, EvalReport


def _report() -> EvalReport:
    return EvalReport(
        agregado=AgregadoDeterminista(
            tipo_accuracy=0.9,
            confianza_band_rate=0.8,
            campos_accuracy={"precio_total": 1.0},
            riesgos_precision_micro=0.85,
            riesgos_recall_micro=0.8,
            riesgos_f1_micro=0.82,
            riesgos_f1_macro=0.8,
            nivel_accuracy=0.9,
            n=10,
        ),
        fidelidad_media=4.2,
        recomendacion_media=4.0,
        distribucion_veredictos={"fiel": 8, "parcial": 2},
        registros=[CasoRegistro(id="a")],
        analyzer_model="claude-opus-4-8",
        judge_model="claude-sonnet-5",
        n_errores=0,
    )


def test_to_json_roundtrips() -> None:
    payload = json.loads(to_json(_report()))
    assert payload["agregado"]["tipo_accuracy"] == 0.9
    assert payload["judge_model"] == "claude-sonnet-5"


def test_render_human_writes_summary() -> None:
    console = Console(record=True, width=100)
    render_human(_report(), console=console)
    text = console.export_text()
    assert "tipo_accuracy" in text or "Tipo" in text
    assert "claude-sonnet-5" in text
