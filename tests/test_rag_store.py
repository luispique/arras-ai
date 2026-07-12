"""PLUMBING tests for the vector store using controlled vectors (no semantics)."""

from __future__ import annotations

from pathlib import Path

from arras_ai.rag.store import LanceDBStore


def test_store_roundtrip_and_topk(tmp_path: Path) -> None:
    store = LanceDBStore(index_dir=tmp_path / "idx", dim=3)
    store.add(
        ids=["a", "b", "c"],
        vectors=[[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        metadatas=[{"titulo": "A"}, {"titulo": "B"}, {"titulo": "C"}],
    )
    assert store.count() == 3
    # Query with a vector equal to 'b' -> 'b' is its own nearest neighbour.
    hits = store.query([0.0, 1.0, 0.0], k=2)
    assert hits[0][0] == "b"
    assert len(hits) == 2
