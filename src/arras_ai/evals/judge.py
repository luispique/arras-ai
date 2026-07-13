"""LLM-as-judge for the subjective outputs, run on an independent model.

The judge checks FAITHFULNESS (is what the model said grounded in the contract?)
and pertinence — not absolute legal correctness, which the deterministic metrics
cover. It must cite the contract span backing each verdict.
"""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, ConfigDict, Field

from arras_ai.config import DEFAULT_JUDGE_MODEL
from arras_ai.models import InformeArras

JUDGE_MAX_TOKENS = 2000

SYSTEM_FIDELIDAD = """\
You are an impartial evaluator of a Spanish earnest-money contract analysis. You are \
NOT re-deciding the law; you check whether the analysis's stated justification for the \
arras type is FAITHFUL to the contract text — i.e. supported by what the document \
actually says, with no invented facts. Base your verdict on evidence: quote the exact \
contract span that supports or contradicts the justification. Score 1 (unfaithful / \
hallucinated) to 5 (fully supported). All output fields in Spanish.
"""

SYSTEM_RECOMENDACIONES = """\
You are an impartial evaluator of the risk recommendations in a Spanish earnest-money \
contract analysis. Judge whether each recommendation is correct, actionable, and \
pertinent to the problem it addresses, given the contract. Do not reward generic or \
irrelevant advice. Score 1 (poor) to 5 (excellent). All output fields in Spanish.
"""


class VeredictoFidelidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    veredicto: Literal["fiel", "parcial", "no_fiel"] = Field(
        description="Si la justificación está sustentada en el contrato"
    )
    score: int = Field(ge=1, le=5, description="1 (no fiel) a 5 (totalmente sustentada)")
    evidencia: str = Field(description="Fragmento del contrato que sustenta o contradice")
    razonamiento: str = Field(description="Explicación breve en español")


class VeredictoRecomendacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5, description="1 (pobre) a 5 (excelente)")
    razonamiento: str = Field(description="Explicación breve en español")


def _user_fidelidad(texto: str, informe: InformeArras) -> str:
    a = informe.analisis
    return (
        f"Contrato:\n--- INICIO ---\n{texto.strip()}\n--- FIN ---\n\n"
        f"Tipo de arras detectado: {a.tipo_arras.value}\n"
        f"Justificación a evaluar:\n{a.justificacion_tipo}"
    )


def _user_recomendaciones(texto: str, informe: InformeArras) -> str:
    riesgos = (
        "\n".join(
            f"- [{r.severidad.value}] {r.categoria.value}: {r.descripcion} -> {r.recomendacion}"
            for r in informe.riesgos
        )
        or "(sin riesgos detectados)"
    )
    return (
        f"Contrato:\n--- INICIO ---\n{texto.strip()}\n--- FIN ---\n\n"
        f"Riesgos y recomendaciones a evaluar:\n{riesgos}"
    )


def juzgar_fidelidad(
    texto: str,
    informe: InformeArras,
    *,
    client: anthropic.Anthropic,
    model: str = DEFAULT_JUDGE_MODEL,
) -> VeredictoFidelidad:
    response = client.messages.parse(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=SYSTEM_FIDELIDAD,
        messages=[{"role": "user", "content": _user_fidelidad(texto, informe)}],
        output_format=VeredictoFidelidad,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"Judge returned no verdict (stop_reason={response.stop_reason})")
    return parsed


def juzgar_recomendaciones(
    texto: str,
    informe: InformeArras,
    *,
    client: anthropic.Anthropic,
    model: str = DEFAULT_JUDGE_MODEL,
) -> VeredictoRecomendacion:
    response = client.messages.parse(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=SYSTEM_RECOMENDACIONES,
        messages=[{"role": "user", "content": _user_recomendaciones(texto, informe)}],
        output_format=VeredictoRecomendacion,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"Judge returned no verdict (stop_reason={response.stop_reason})")
    return parsed
