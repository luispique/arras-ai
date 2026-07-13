"""Render an EvalReport as a human summary (Rich) or JSON."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from arras_ai.evals.runner import EvalReport


def to_json(report: EvalReport) -> str:
    return report.model_dump_json(indent=2)


def render_human(report: EvalReport, *, console: Console | None = None) -> None:
    console = console or Console()
    agg = report.agregado

    tabla = Table(title="Evals — métricas deterministas", show_header=True, header_style="bold")
    tabla.add_column("Métrica")
    tabla.add_column("Valor", justify="right")
    tabla.add_row("tipo_accuracy", f"{agg.tipo_accuracy:.2%}")
    if agg.confianza_band_rate is not None:
        tabla.add_row("confianza_band_rate", f"{agg.confianza_band_rate:.2%}")
    tabla.add_row("riesgos_precision_micro", f"{agg.riesgos_precision_micro:.2%}")
    tabla.add_row("riesgos_recall_micro", f"{agg.riesgos_recall_micro:.2%}")
    tabla.add_row("riesgos_f1_micro", f"{agg.riesgos_f1_micro:.2%}")
    tabla.add_row("riesgos_f1_macro", f"{agg.riesgos_f1_macro:.2%}")
    tabla.add_row("nivel_accuracy", f"{agg.nivel_accuracy:.2%}")
    for campo, acc in agg.campos_accuracy.items():
        tabla.add_row(f"campo:{campo}", f"{acc:.2%}")
    console.print(tabla)

    juez = Table(title="Evals — LLM-as-judge", show_header=True, header_style="bold")
    juez.add_column("Métrica")
    juez.add_column("Valor", justify="right")
    fidelidad_val = "—" if report.fidelidad_media is None else f"{report.fidelidad_media:.2f}"
    juez.add_row("fidelidad_media (1-5)", fidelidad_val)
    recomendacion_val = (
        "—" if report.recomendacion_media is None else f"{report.recomendacion_media:.2f}"
    )
    juez.add_row("recomendacion_media (1-5)", recomendacion_val)
    juez.add_row("veredictos", str(report.distribucion_veredictos))
    console.print(juez)

    console.print(
        f"[dim]casos: {agg.n} · errores: {report.n_errores} · "
        f"analizador: {report.analyzer_model} · juez: {report.judge_model}[/dim]"
    )
