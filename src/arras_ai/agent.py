"""LangGraph agent: extraction -> risk detection -> report.

Nodes call Claude directly through the anthropic SDK (no LangChain models). The
graph is a simple linear StateGraph; the sophistication is in the typed state and
the hybrid (rules + LLM) risk detection, not in control flow.
"""

from __future__ import annotations

import logging
from functools import partial
from pathlib import Path
from typing import Any

import anthropic
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from arras_ai.analyzer import AnalysisError, _build_client, analyze_text
from arras_ai.config import DEFAULT_MODEL, load_settings
from arras_ai.models import AnalisisArras, InformeArras, Riesgo, RiesgosDetectadosLLM
from arras_ai.pdf import extract_text
from arras_ai.prompts import SYSTEM_PROMPT_RIESGOS, build_user_message_riesgos
from arras_ai.rag.knowledge_base import KnowledgeBase, PatronHit
from arras_ai.riesgos import citar, componer_informe, detectar_por_reglas

logger = logging.getLogger("arras_ai.agent")

RIESGOS_MAX_TOKENS = 8000


def detectar_riesgos_llm(
    texto: str,
    analisis: AnalisisArras,
    patrones: list[PatronHit],
    *,
    client: anthropic.Anthropic,
    kb: KnowledgeBase,
    model: str = DEFAULT_MODEL,
    max_tokens: int = RIESGOS_MAX_TOKENS,
) -> list[Riesgo]:
    """Run the focused LLM risk pass; tag results with fuente='llm'.

    Grounds each finding in the retrieved `patrones`: the model is asked to cite
    supporting `patron_ids`, which are mapped here to `Fundamento`s via `kb`.

    Returns an empty list if the model returns nothing parseable.
    """
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT_RIESGOS,
        messages=[
            {"role": "user", "content": build_user_message_riesgos(texto, analisis, patrones)}
        ],
        output_format=RiesgosDetectadosLLM,
    )
    parsed = response.parsed_output
    if parsed is None:
        logger.warning(
            "risk LLM pass returned no parseable output (stop_reason=%s)", response.stop_reason
        )
        return []
    riesgos: list[Riesgo] = []
    for r in parsed.riesgos:
        # Cite ONLY patterns the model explicitly named and that exist. If it named
        # none (or only unknown ids), attach NO citation — never associate the
        # top-k retrieved pattern with a finding it may not support. In a legal tool
        # a wrong citation is worse than none.
        referencias = [
            p.como_fundamento() for pid in r.patron_ids if (p := kb.get_patron(pid)) is not None
        ]
        riesgos.append(
            Riesgo(
                categoria=r.categoria,
                severidad=r.severidad,
                descripcion=r.descripcion,
                recomendacion=r.recomendacion,
                fuente="llm",
                referencias=referencias,
            )
        )
    return riesgos


class EstadoAnalisis(BaseModel):
    """Typed state passed between graph nodes."""

    texto_contrato: str
    analisis: AnalisisArras | None = None
    patrones_recuperados: list[PatronHit] = Field(default_factory=list)
    riesgos_regla: list[Riesgo] = Field(default_factory=list)
    riesgos_llm: list[Riesgo] = Field(default_factory=list)
    informe: InformeArras | None = None


def construir_query_recuperacion(analisis: AnalisisArras) -> str:
    """Build a focused retrieval query from EXTRACTED FACTS — never the raw PDF text.

    Embedding the whole contract dilutes the signal (the problem is ~10% of the text,
    lost in boilerplate) and exceeds the embedder's ~512-token limit. We synthesize
    the type, the detected absences, and captured fragments instead.
    """
    partes = [f"Contrato de arras {analisis.tipo_arras.value}."]
    if not analisis.tiene_clausula_financiacion:
        partes.append("No consta cláusula suspensiva de financiación.")
    if analisis.fechas.fecha_limite_escritura is None and analisis.fechas.plazo_dias is None:
        partes.append("No se fija fecha límite ni plazo para la escritura.")
    if analisis.inmueble.referencia_catastral is None:
        partes.append("Falta la referencia catastral del inmueble.")
    if analisis.inmueble.cargas is None:
        partes.append("No se mencionan cargas registrales.")
    partes.append(analisis.justificacion_tipo)
    return " ".join(p for p in partes if p)


def _nodo_extraer(
    estado: EstadoAnalisis, *, client: anthropic.Anthropic, model: str
) -> dict[str, Any]:
    analisis = analyze_text(estado.texto_contrato, client=client, model=model)
    return {"analisis": analisis}


def _nodo_recuperar(estado: EstadoAnalisis, *, kb: KnowledgeBase) -> dict[str, Any]:
    assert estado.analisis is not None  # extraer ran first
    query = construir_query_recuperacion(estado.analisis)
    try:
        patrones = kb.retrieve(query, k=4)
    except Exception:
        logger.warning("pattern retrieval failed; continuing without patterns", exc_info=True)
        patrones = []
    return {"patrones_recuperados": patrones}


def _nodo_detectar(
    estado: EstadoAnalisis, *, client: anthropic.Anthropic, model: str, kb: KnowledgeBase
) -> dict[str, Any]:
    assert estado.analisis is not None  # extraer ran first
    riesgos_regla = detectar_por_reglas(estado.analisis)
    for r in riesgos_regla:
        r.referencias = citar(r.categoria, kb.articulos, kb.patrones)
    try:
        riesgos_llm = detectar_riesgos_llm(
            estado.texto_contrato,
            estado.analisis,
            estado.patrones_recuperados,
            client=client,
            kb=kb,
            model=model,
        )
    except Exception:
        logger.warning("risk LLM pass failed; using rule-based risks only", exc_info=True)
        riesgos_llm = []
    return {"riesgos_regla": riesgos_regla, "riesgos_llm": riesgos_llm}


def _nodo_componer(estado: EstadoAnalisis) -> dict[str, Any]:
    assert estado.analisis is not None
    informe = componer_informe(estado.analisis, estado.riesgos_regla, estado.riesgos_llm)
    return {"informe": informe}


def build_graph(client: anthropic.Anthropic, model: str, kb: KnowledgeBase) -> Any:
    """Compile the extraction -> retrieval -> risk-detection -> report graph."""
    builder = StateGraph(EstadoAnalisis)
    builder.add_node("extraer", partial(_nodo_extraer, client=client, model=model))
    builder.add_node("recuperar_contexto", partial(_nodo_recuperar, kb=kb))
    builder.add_node("detectar_riesgos", partial(_nodo_detectar, client=client, model=model, kb=kb))
    builder.add_node("componer_informe", partial(_nodo_componer))
    builder.add_edge(START, "extraer")
    builder.add_edge("extraer", "recuperar_contexto")
    builder.add_edge("recuperar_contexto", "detectar_riesgos")
    builder.add_edge("detectar_riesgos", "componer_informe")
    builder.add_edge("componer_informe", END)
    return builder.compile()


def analizar_texto(
    texto: str,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    kb: KnowledgeBase | None = None,
) -> InformeArras:
    """Analyze already-extracted contract text end to end."""
    if not texto.strip():
        raise AnalysisError("Empty contract text.")
    settings = load_settings()
    if client is None:
        client = _build_client(settings.anthropic_api_key)
    if kb is None:
        kb = KnowledgeBase.build(settings)
    graph = build_graph(client, model, kb)
    final = graph.invoke(EstadoAnalisis(texto_contrato=texto))
    estado = EstadoAnalisis.model_validate(final)
    if estado.informe is None:
        raise AnalysisError("The agent did not produce a report.")
    return estado.informe


def analizar_pdf(
    path: str | Path,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    kb: KnowledgeBase | None = None,
) -> InformeArras:
    """Extract text from a PDF and analyze it. See :func:`analizar_texto`."""
    return analizar_texto(extract_text(path), client=client, model=model, kb=kb)
