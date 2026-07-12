"""Command-line interface: `arras analyze contract.pdf`."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from arras_ai import __version__
from arras_ai.agent import analizar_pdf
from arras_ai.analyzer import AnalysisError
from arras_ai.config import load_settings
from arras_ai.models import AnalisisArras, InformeArras, NivelRiesgo, Severidad, TipoArras
from arras_ai.pdf import PdfExtractionError

app = typer.Typer(
    name="arras",
    help="Analyze Spanish earnest-money contracts (contratos de arras).",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)

_TIPO_STYLE = {
    TipoArras.penitenciales: "cyan",
    TipoArras.confirmatorias: "yellow",
    TipoArras.penales: "magenta",
    TipoArras.no_especificado: "bold red",
}
_NIVEL_STYLE = {
    NivelRiesgo.alto: "bold red",
    NivelRiesgo.medio: "yellow",
    NivelRiesgo.bajo: "green",
}
_SEV_STYLE = {
    Severidad.alta: "red",
    Severidad.media: "yellow",
    Severidad.baja: "dim",
}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"arras-ai {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """arras-ai command-line interface."""


def _render_human(analisis: AnalisisArras) -> None:
    tipo = analisis.tipo_arras
    style = _TIPO_STYLE.get(tipo, "white")
    header = Table.grid(padding=(0, 1))
    header.add_column(justify="left")
    header.add_row(
        f"[{style}]Tipo de arras: {tipo.value}[/{style}]  (confianza {analisis.confianza_tipo:.0%})"
    )
    console.print(Panel(header, title="arras-ai", border_style=style))

    console.print(f"[bold]Justificación:[/bold] {analisis.justificacion_tipo}\n")

    partes = Table(title="Partes", show_header=True, header_style="bold")
    partes.add_column("Rol")
    partes.add_column("Nombre")
    partes.add_column("NIF")
    for parte in analisis.partes:
        partes.add_row(parte.rol.value, parte.nombre or "—", parte.nif or "—")
    if analisis.partes:
        console.print(partes)

    datos = Table(title="Datos clave", show_header=False)
    datos.add_column(style="bold")
    datos.add_column()
    imp = analisis.importes
    datos.add_row("Precio total", _money(imp.precio_total, imp.moneda))
    datos.add_row("Importe arras", _money(imp.importe_arras, imp.moneda))
    if imp.porcentaje_arras is not None:
        datos.add_row("% arras", f"{imp.porcentaje_arras:.1f}%")
    datos.add_row("Dirección", analisis.inmueble.direccion or "—")
    datos.add_row("Ref. catastral", analisis.inmueble.referencia_catastral or "—")
    datos.add_row("Fecha contrato", analisis.fechas.fecha_contrato or "—")
    datos.add_row("Límite escritura", analisis.fechas.fecha_limite_escritura or "—")
    if analisis.fechas.plazo_dias is not None:
        datos.add_row("Plazo (días)", str(analisis.fechas.plazo_dias))
    fin = "sí" if analisis.tiene_clausula_financiacion else "[red]no[/red]"
    datos.add_row("Cláusula financiación", fin)
    console.print(datos)

    if analisis.referencias_codigo_civil:
        refs = ", ".join(f"art. {r.articulo}" for r in analisis.referencias_codigo_civil)
        console.print(f"\n[bold]Código Civil:[/bold] {refs}")

    console.print(Panel(analisis.resumen, title="Resumen", border_style="dim"))


def _money(value: float | None, currency: str) -> str:
    if value is None:
        return "—"
    return f"{value:,.2f} {currency}"


def _render_informe(informe: InformeArras) -> None:
    _render_human(informe.analisis)

    nivel = informe.nivel_riesgo_global
    style = _NIVEL_STYLE.get(nivel, "white")
    console.print(
        Panel(
            f"[{style}]Nivel de riesgo global: {nivel.value.upper()}[/{style}]",
            border_style=style,
        )
    )

    if not informe.riesgos:
        console.print("Sin riesgos detectados.")
        return

    tabla = Table(title="Riesgos detectados", show_header=True, header_style="bold")
    tabla.add_column("Sev.")
    tabla.add_column("Categoría")
    tabla.add_column("Descripción")
    tabla.add_column("Recomendación")
    for r in informe.riesgos:
        sev_style = _SEV_STYLE.get(r.severidad, "white")
        recomendacion = r.recomendacion
        if r.referencias:
            citas = " · ".join(f"{f.referencia}" for f in r.referencias)
            recomendacion = f"{recomendacion}\n[dim]Cf. {citas}[/dim]"
        tabla.add_row(
            f"[{sev_style}]{r.severidad.value}[/{sev_style}]",
            r.categoria.value,
            r.descripcion,
            recomendacion,
        )
    console.print(tabla)


@app.command()
def analyze(
    pdf: Annotated[Path, typer.Argument(help="Path to the arras contract PDF.")],
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print the raw JSON analysis instead of a table."),
    ] = False,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Override the model (default: from config)."),
    ] = None,
) -> None:
    """Analyze a contrato de arras PDF and print the extracted information."""
    settings = load_settings()
    chosen_model = model or settings.model

    try:
        informe = analizar_pdf(pdf, model=chosen_model)
    except PdfExtractionError as exc:
        err_console.print(f"[red]PDF error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    except AnalysisError as exc:
        err_console.print(f"[red]Analysis error:[/red] {exc}")
        raise typer.Exit(code=3) from exc
    except Exception as exc:  # network / auth / API errors from the SDK
        err_console.print(f"[red]Unexpected error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        # stdout stays clean JSON so the CLI is pipeable.
        sys.stdout.write(informe.model_dump_json(indent=2))
        sys.stdout.write("\n")
    else:
        _render_informe(informe)


if __name__ == "__main__":
    app()
