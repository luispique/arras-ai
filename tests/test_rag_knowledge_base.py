"""Tests for the deterministic side of KnowledgeBase (loading + lookups). No API/network."""

from __future__ import annotations

from pathlib import Path

import pytest

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


def test_retrieve_plumbing_with_fake_embeddings(tmp_path: Path, fake_embedding_model) -> None:  # type: ignore[no-untyped-def]
    from arras_ai.rag.store import LanceDBStore

    kb = KnowledgeBase.from_data_dir(
        DATA_DIR,
        index_dir=tmp_path / "idx",
        embedding_model=fake_embedding_model,
        store=LanceDBStore(index_dir=tmp_path / "idx", dim=fake_embedding_model.dim),
    )
    kb.ensure_index()
    # Query with a pattern's EXACT indexable text -> that pattern is top-1 (identity,
    # not semantic relevance: the fake embeds identical text to an identical vector).
    fin = kb.get_patron("financiacion")
    assert fin is not None
    hits = kb.retrieve(fin.texto_indexable(), k=3)
    assert hits and hits[0].patron.id == "financiacion"
    assert len(hits) <= 3


def test_index_model_mismatch_raises(tmp_path: Path, fake_embedding_model) -> None:  # type: ignore[no-untyped-def]
    from arras_ai.rag.store import LanceDBStore

    idx = tmp_path / "idx"
    kb = KnowledgeBase.from_data_dir(
        DATA_DIR,
        index_dir=idx,
        embedding_model=fake_embedding_model,
        store=LanceDBStore(index_dir=idx, dim=fake_embedding_model.dim),
    )
    kb.ensure_index()  # writes meta.json with model_id "fake:fake"

    class OtherModel(type(fake_embedding_model)):  # type: ignore[misc]
        @property
        def model_id(self) -> str:
            return "other:model"

    other = OtherModel()
    kb2 = KnowledgeBase.from_data_dir(
        DATA_DIR,
        index_dir=idx,
        embedding_model=other,
        store=LanceDBStore(index_dir=idx, dim=other.dim),
    )
    with pytest.raises(RuntimeError, match="build_kb"):
        kb2.ensure_index()
