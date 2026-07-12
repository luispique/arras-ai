"""CLI tests with the agent mocked (no API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arras_ai import cli
from arras_ai.models import InformeArras

runner = CliRunner()


def test_analyze_human_output(
    monkeypatch: pytest.MonkeyPatch, penitenciales_pdf: Path, fake_informe: InformeArras
) -> None:
    monkeypatch.setattr(cli, "analizar_pdf", lambda *a, **k: fake_informe)
    result = runner.invoke(cli.app, ["analyze", str(penitenciales_pdf)])
    assert result.exit_code == 0
    assert "Nivel de riesgo" in result.stdout
    assert "ALTO" in result.stdout


def test_analyze_json_output(
    monkeypatch: pytest.MonkeyPatch, penitenciales_pdf: Path, fake_informe: InformeArras
) -> None:
    monkeypatch.setattr(cli, "analizar_pdf", lambda *a, **k: fake_informe)
    result = runner.invoke(cli.app, ["analyze", str(penitenciales_pdf), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    InformeArras.model_validate(payload)  # round-trips
    assert "nivel_riesgo_global" in payload


def test_analyze_renders_citations(
    monkeypatch: pytest.MonkeyPatch, penitenciales_pdf: Path, fake_informe: InformeArras
) -> None:
    monkeypatch.setattr(cli, "analizar_pdf", lambda *a, **k: fake_informe)
    result = runner.invoke(cli.app, ["analyze", str(penitenciales_pdf)])
    assert result.exit_code == 0
    assert "Cf." in result.stdout  # flattened citation line
    assert "Doctrina:" in result.stdout  # legal-nature label for the doctrina fundamento
    assert "financiación" in result.stdout.lower()
