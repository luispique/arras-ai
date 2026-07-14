"""MCP server exposing the arras analysis as tools over stdio.

Optional: needs the `mcp` extra (`pipx install 'arras-ai[mcp]'`). The tool functions
are pure wrappers over the unchanged core and are importable/testable without `mcp`;
`build_server()` imports the SDK lazily so the base install stays lean.
"""

from __future__ import annotations

from typing import Any

from arras_ai.agent import analizar_texto
from arras_ai.analyzer import AnalysisError
from arras_ai.pdf import PdfExtractionError, extract_text


def analizar_contrato_arras(texto: str) -> dict[str, Any]:
    """Analiza el texto de un contrato de arras español.

    Devuelve la modalidad de arras detectada (con confianza y justificación), los datos
    clave (partes, importes, fechas, inmueble), y un informe de riesgos con su nivel
    global y citas al Código Civil / doctrina. No es asesoramiento legal.
    """
    try:
        informe = analizar_texto(texto)
    except AnalysisError as exc:
        raise ValueError(f"No se pudo analizar el contrato: {exc}") from exc
    return informe.model_dump(mode="json")


def analizar_contrato_pdf(ruta: str) -> dict[str, Any]:
    """Analiza un contrato de arras desde un PDF local (ruta de fichero en el equipo).

    Extrae el texto del PDF y devuelve el mismo informe que `analizar_contrato_arras`.
    """
    try:
        texto = extract_text(ruta)
    except PdfExtractionError as exc:
        raise ValueError(f"No se pudo leer el PDF: {exc}") from exc
    return analizar_contrato_arras(texto)


def build_server() -> Any:
    """Build the FastMCP server with the two tools registered. Needs the `mcp` extra."""
    try:
        from mcp.server.fastmcp import FastMCP
    except ModuleNotFoundError as exc:  # pragma: no cover - exercised via message
        raise RuntimeError(
            "El servidor MCP necesita el extra 'mcp'. Instala: pipx install 'arras-ai[mcp]'"
        ) from exc
    server = FastMCP("arras-ai")
    server.tool()(analizar_contrato_arras)
    server.tool()(analizar_contrato_pdf)
    return server


def main() -> None:
    """Entry point for `arras-mcp`: run the stdio MCP server."""
    build_server().run()


if __name__ == "__main__":
    main()
