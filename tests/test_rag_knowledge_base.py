"""Tests for the deterministic side of KnowledgeBase (loading + lookups). No API/network."""

from __future__ import annotations

from pathlib import Path

from arras_ai.models import CategoriaRiesgo
from arras_ai.rag.knowledge_base import KnowledgeBase

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "kb"


def _kb() -> KnowledgeBase:
    return KnowledgeBase.from_data_dir(DATA_DIR, index_dir=Path("/tmp/unused-index"))


def test_loads_articulos_and_patrones() -> None:
    kb = _kb()
    articulo = kb.get_articulo("1454")
    assert articulo is not None
    assert articulo.articulo == "1454"
    patron = kb.get_patron("financiacion")
    assert patron is not None
    assert patron.categoria is CategoriaRiesgo.falta_financiacion


def test_missing_lookup_returns_none() -> None:
    kb = _kb()
    assert kb.get_articulo("9999") is None
    assert kb.get_patron("nope") is None


def test_articulo_como_fundamento() -> None:
    articulo = _kb().get_articulo("1454")
    assert articulo is not None
    f = articulo.como_fundamento()
    assert f.tipo == "codigo_civil"
    assert f.referencia == "art. 1454 CC"
    assert "arras" in f.texto.lower()


def test_patron_como_fundamento() -> None:
    patron = _kb().get_patron("financiacion")
    assert patron is not None
    f = patron.como_fundamento()
    assert f.tipo == "doctrina"
    assert f.texto
