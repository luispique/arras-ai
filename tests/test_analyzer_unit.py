"""Unit tests for the analyzer with Claude mocked out (no network)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic
import pytest

from arras_ai.analyzer import AnalysisError, analyze_text
from arras_ai.models import AnalisisArras


class FakeMessages:
    """Stand-in for `client.messages` that records the call and returns a stub."""

    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return self._response


class FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.messages = FakeMessages(response)


def _response(parsed: AnalisisArras | None, stop_reason: str = "end_turn") -> SimpleNamespace:
    return SimpleNamespace(parsed_output=parsed, stop_reason=stop_reason)


def _fake_client(response: SimpleNamespace) -> FakeClient:
    """Build a FakeClient; cast at the call site to satisfy the typed signature."""
    return FakeClient(response)


def test_analyze_text_returns_parsed_output(fake_analisis: AnalisisArras) -> None:
    client = _fake_client(_response(fake_analisis))
    result = analyze_text(
        "some contract text",
        client=cast(anthropic.Anthropic, client),
        model="test-model",
    )

    assert result is fake_analisis
    # The system prompt and schema are wired through to the API call.
    assert client.messages.last_kwargs["output_format"] is AnalisisArras
    assert client.messages.last_kwargs["model"] == "test-model"
    assert "Código Civil" in client.messages.last_kwargs["system"]


def test_empty_text_raises() -> None:
    client = _fake_client(_response(None))
    with pytest.raises(AnalysisError, match="Empty contract text"):
        analyze_text("   ", client=cast(anthropic.Anthropic, client))


def test_refusal_raises(fake_analisis: AnalisisArras) -> None:
    client = _fake_client(_response(fake_analisis, stop_reason="refusal"))
    with pytest.raises(AnalysisError, match="declined"):
        analyze_text("text", client=cast(anthropic.Anthropic, client))


def test_unparseable_response_raises() -> None:
    client = _fake_client(_response(None, stop_reason="max_tokens"))
    with pytest.raises(AnalysisError, match="parseable"):
        analyze_text("text", client=cast(anthropic.Anthropic, client))
