"""Unit tests for embedding selection/plumbing. Does NOT download models or hit the network."""

from __future__ import annotations

import pytest

from arras_ai.config import Settings
from arras_ai.rag.embeddings import make_embedding_model


def test_fake_embedding_is_deterministic(fake_embedding_model) -> None:  # type: ignore[no-untyped-def]
    a = fake_embedding_model.embed_documents(["hola"])[0]
    b = fake_embedding_model.embed_query("hola")
    assert a == b
    assert len(a) == fake_embedding_model.dim


def test_make_embedding_model_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="Unknown embedding provider"):
        make_embedding_model(Settings(embedding_provider="nope"))
