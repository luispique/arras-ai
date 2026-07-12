"""LangGraph agent: extraction -> risk detection -> report.

Nodes call Claude directly through the anthropic SDK (no LangChain models). The
graph is a simple linear StateGraph; the sophistication is in the typed state and
the hybrid (rules + LLM) risk detection, not in control flow.
"""

from __future__ import annotations

import logging
from pathlib import Path  # noqa: F401  (used by the graph nodes added in Task 4)

import anthropic

# The following are unused until Task 4 wires the StateGraph nodes together; kept
# here now so this import block does not need to be revisited.
from arras_ai.analyzer import AnalysisError, _build_client, analyze_text  # noqa: F401
from arras_ai.config import DEFAULT_MODEL, load_settings  # noqa: F401
from arras_ai.models import AnalisisArras, InformeArras, Riesgo, RiesgosDetectadosLLM  # noqa: F401
from arras_ai.pdf import extract_text  # noqa: F401
from arras_ai.prompts import SYSTEM_PROMPT_RIESGOS, build_user_message_riesgos
from arras_ai.riesgos import componer_informe, detectar_por_reglas  # noqa: F401

logger = logging.getLogger("arras_ai.agent")

RIESGOS_MAX_TOKENS = 4000


def detectar_riesgos_llm(
    texto: str,
    analisis: AnalisisArras,
    *,
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
    max_tokens: int = RIESGOS_MAX_TOKENS,
) -> list[Riesgo]:
    """Run the focused LLM risk pass; tag results with fuente='llm'.

    Returns an empty list if the model returns nothing parseable.
    """
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT_RIESGOS,
        messages=[{"role": "user", "content": build_user_message_riesgos(texto, analisis)}],
        output_format=RiesgosDetectadosLLM,
    )
    parsed = response.parsed_output
    if parsed is None:
        return []
    return [Riesgo(**base.model_dump(), fuente="llm") for base in parsed.riesgos]
