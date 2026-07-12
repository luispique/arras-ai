"""End-to-end integration test: real Claude API call over a fixture PDF.

Marked `integration` and skipped unless ANTHROPIC_API_KEY is set, so the default
`pytest` run stays offline. Run it explicitly with:

    uv run pytest -m integration
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from arras_ai.agent import analizar_pdf
from arras_ai.analyzer import analyze_pdf
from arras_ai.config import load_settings
from arras_ai.models import CategoriaRiesgo, NivelRiesgo, Severidad, TipoArras
from arras_ai.rag.knowledge_base import KnowledgeBase

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not os.getenv("ANTHROPIC_API_KEY"),
        reason="ANTHROPIC_API_KEY not set; skipping real API call.",
    ),
]


def test_penitenciales_contract_end_to_end(penitenciales_pdf: Path) -> None:
    analisis = analyze_pdf(penitenciales_pdf)

    # Modality: the contract states penitenciales and cites art. 1454.
    assert analisis.tipo_arras is TipoArras.penitenciales
    assert analisis.confianza_tipo >= 0.7
    assert any(ref.articulo == "1454" for ref in analisis.referencias_codigo_civil)

    # Amounts.
    assert analisis.importes.precio_total == pytest.approx(280000, rel=0.01)
    assert analisis.importes.importe_arras == pytest.approx(28000, rel=0.01)

    # This contract DOES have a financing-contingency clause.
    assert analisis.tiene_clausula_financiacion is True

    # Both parties were extracted.
    assert len(analisis.partes) == 2


def test_agente_confirmatorias_flags_financing(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_confirmatorias_problematic.pdf")
    cats = {r.categoria for r in informe.riesgos}
    assert CategoriaRiesgo.falta_financiacion in cats
    assert informe.nivel_riesgo_global is NivelRiesgo.alto


def test_agente_penitenciales_no_high_risk(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_penitenciales_clean.pdf")
    # A well-drafted contract may still carry minor drafting notes, but nothing
    # high-severity — that (not "zero risks") is the signal of a clean contract.
    assert all(r.severidad is not Severidad.alta for r in informe.riesgos)
    assert informe.nivel_riesgo_global is not NivelRiesgo.alto


def test_agente_ambiguo_flags_type_and_financing(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_ambiguas.pdf")
    cats = {r.categoria for r in informe.riesgos}
    assert CategoriaRiesgo.tipo_ambiguo in cats
    assert CategoriaRiesgo.falta_financiacion in cats


def test_retrieval_relevance_real_embeddings(tmp_path: Path) -> None:
    # The ONLY test that asserts semantic relevance (real fastembed).
    settings = load_settings().model_copy(update={"kb_index_dir": str(tmp_path / "idx")})
    kb = KnowledgeBase.build(settings)
    hits = kb.retrieve("El contrato no incluye condición suspensiva de financiación", k=3)
    assert hits and hits[0].patron.id == "financiacion"


def test_agente_risks_carry_citations(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_confirmatorias_problematic.pdf")
    fin = next(r for r in informe.riesgos if r.categoria is CategoriaRiesgo.falta_financiacion)
    assert fin.referencias  # at least one Fundamento attached
