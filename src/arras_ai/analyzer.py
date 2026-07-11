"""Orchestrates the analysis: PDF text -> Claude structured output -> typed result."""

from __future__ import annotations

from pathlib import Path

import anthropic

from arras_ai.config import DEFAULT_MODEL, load_settings
from arras_ai.models import AnalisisArras
from arras_ai.pdf import extract_text
from arras_ai.prompts import SYSTEM_PROMPT, build_user_message

# max_tokens stays under the ~16k non-streaming SDK timeout guard; the schema is small.
MAX_TOKENS = 8000


class AnalysisError(RuntimeError):
    """Raised when Claude does not return a valid structured analysis."""


def _build_client(api_key: str | None) -> anthropic.Anthropic:
    # A None api_key lets the SDK resolve credentials from the environment itself.
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def analyze_text(
    contract_text: str,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> AnalisisArras:
    """Analyze the already-extracted text of a contrato de arras.

    Args:
        contract_text: Plain text of the contract.
        client: An Anthropic client. If omitted, one is built from settings/env.
        model: Model id to use.
        max_tokens: Output token cap.

    Returns:
        A validated :class:`AnalisisArras`.

    Raises:
        AnalysisError: if the model refuses or returns output that does not
            validate against the schema.
    """
    if not contract_text.strip():
        raise AnalysisError("Empty contract text.")

    if client is None:
        settings = load_settings()
        client = _build_client(settings.anthropic_api_key)

    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": build_user_message(contract_text)}],
        output_format=AnalisisArras,
    )

    if response.stop_reason == "refusal":
        raise AnalysisError("The model declined to analyze this document.")

    result = response.parsed_output
    if result is None:
        raise AnalysisError(
            f"The model did not return a parseable analysis (stop_reason={response.stop_reason})."
        )
    return result


def analyze_pdf(
    path: str | Path,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    max_tokens: int = MAX_TOKENS,
) -> AnalisisArras:
    """Extract text from a PDF and analyze it. See :func:`analyze_text`."""
    text = extract_text(path)
    return analyze_text(text, client=client, model=model, max_tokens=max_tokens)
