"""The agent must anonymize contract text before it reaches the LLM (fail-closed)."""

from __future__ import annotations

import pytest

from arras_ai.agent import _anonimizar_o_fallar
from arras_ai.analyzer import AnalysisError
from arras_ai.anonimizacion import Anonimizador, ResultadoAnonimizacion
from arras_ai.config import Settings


def test_pii_masked_amounts_kept() -> None:
    settings = Settings(anonimizar=True, anonimizador_provider="regex")
    out = _anonimizar_o_fallar("D. Juan, NIF 12345678Z, precio 280.000 €", settings)
    assert "12345678Z" not in out
    assert "«NIF_1»" in out
    assert "280.000" in out  # amounts are never masked


def test_disabled_is_passthrough() -> None:
    settings = Settings(anonimizar=False)
    texto = "D. Juan, NIF 12345678Z"
    assert _anonimizar_o_fallar(texto, settings) == texto


def test_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    class Explota(Anonimizador):
        def anonimizar(self, texto: str) -> ResultadoAnonimizacion:
            raise RuntimeError("boom")

    monkeypatch.setattr("arras_ai.agent.make_anonimizador", lambda _s: Explota())
    with pytest.raises(AnalysisError):
        _anonimizar_o_fallar("cualquier texto", Settings())
