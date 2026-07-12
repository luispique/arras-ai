"""Build the vector index from the knowledge base's patterns."""

from __future__ import annotations

from arras_ai.rag.embeddings import EmbeddingModel
from arras_ai.rag.knowledge_base import KnowledgeBase
from arras_ai.rag.store import VectorStore


def build_index(kb: KnowledgeBase, embedding_model: EmbeddingModel, store: VectorStore) -> None:
    patrones = list(kb.patrones.values())
    if not patrones:
        return
    ids = [p.id for p in patrones]
    vectors = embedding_model.embed_documents([p.texto_indexable() for p in patrones])
    metadatas = [{"titulo": p.titulo} for p in patrones]
    store.add(ids, vectors, metadatas)
