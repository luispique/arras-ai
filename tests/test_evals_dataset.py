"""Tests for the eval dataset loader and the dataset's coverage. No API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arras_ai.evals.dataset import CasoEval, GroundTruth, load_casos
from arras_ai.models import CategoriaRiesgo, NivelRiesgo, TipoArras


def test_loads_all_cases() -> None:
    casos = load_casos()
    assert len(casos) >= 12
    assert all(isinstance(c, CasoEval) for c in casos)
    assert len({c.id for c in casos}) == len(casos)  # ids unique


def test_dataset_covers_all_types_and_risk_categories() -> None:
    casos = load_casos()
    tipos = {c.ground_truth.tipo_arras for c in casos}
    assert {
        TipoArras.penitenciales,
        TipoArras.confirmatorias,
        TipoArras.penales,
        TipoArras.no_especificado,
    } <= tipos
    esperados = {r for c in casos for r in c.ground_truth.riesgos_esperados}
    assert {
        CategoriaRiesgo.falta_financiacion,
        CategoriaRiesgo.fechas_mal_definidas,
        CategoriaRiesgo.inmueble_mal_identificado,
        CategoriaRiesgo.reparto_gastos_ambiguo,
        CategoriaRiesgo.tipo_ambiguo,
    } <= esperados
    # at least one clean contract (no expected risks)
    assert any(not c.ground_truth.riesgos_esperados for c in casos)


def test_ground_truth_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GroundTruth.model_validate(
            {
                "tipo_arras": "penitenciales",
                "tiene_clausula_financiacion": True,
                "fecha_limite_presente": True,
                "referencia_catastral_presente": True,
                "nivel_riesgo_global": "bajo",
                "unexpected": 1,
            }
        )


def test_nivel_is_bajo_when_no_risks() -> None:
    for c in load_casos():
        if not c.ground_truth.riesgos_esperados:
            assert c.ground_truth.nivel_riesgo_global is NivelRiesgo.bajo
