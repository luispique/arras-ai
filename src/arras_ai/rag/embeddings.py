"""Embedding models behind a provider-agnostic interface.

Local `fastembed` is the default (no API key, offline). OpenAI and Voyage adapters
lazy-import their SDKs so they are optional extras, never hard dependencies.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import cast

from arras_ai.config import Settings

# NOTE: the installed fastembed version only ships the "large" multilingual e5
# checkpoint ("small" is not in `TextEmbedding.list_supported_models()`), so we
# default to it here. Its embedding dimension is 1024, not the 384 of "small".
DEFAULT_LOCAL_MODEL = "intfloat/multilingual-e5-large"
_E5_DIM = 1024


class EmbeddingModel(ABC):
    @property
    @abstractmethod
    def dim(self) -> int: ...

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identity (e.g. 'local:intfloat/multilingual-e5-large') stored in
        the index metadata to detect a provider/model change on load."""

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedModel(EmbeddingModel):
    """Local ONNX embeddings via fastembed. Applies e5 query/passage prefixes."""

    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL) -> None:
        from fastembed import TextEmbedding

        self._model_name = model_name
        self._model = TextEmbedding(model_name=model_name)
        self._is_e5 = "e5" in model_name.lower()

    @property
    def dim(self) -> int:
        return _E5_DIM if self._is_e5 else len(self.embed_query("dim probe"))

    @property
    def model_id(self) -> str:
        return f"local:{self._model_name}"

    def _prefix(self, text: str, kind: str) -> str:
        return f"{kind}: {text}" if self._is_e5 else text

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        prefixed = [self._prefix(t, "passage") for t in texts]
        return [vec.tolist() for vec in self._model.embed(prefixed)]

    def embed_query(self, text: str) -> list[float]:
        vec = next(iter(self._model.embed([self._prefix(text, "query")])))
        return cast("list[float]", vec.tolist())


class OpenAIEmbeddingModel(EmbeddingModel):
    def __init__(self, api_key: str, model: str = "text-embedding-3-large") -> None:
        try:
            from openai import OpenAI
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised via message only
            raise RuntimeError(
                "OpenAI embeddings need the 'openai' extra: uv sync --extra openai"
            ) from exc
        self._client = OpenAI(api_key=api_key)
        self._model = model

    @property
    def dim(self) -> int:
        return 3072

    @property
    def model_id(self) -> str:
        return f"openai:{self._model}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(model=self._model, input=texts)
        return [d.embedding for d in resp.data]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


class VoyageEmbeddingModel(EmbeddingModel):
    def __init__(self, api_key: str, model: str = "voyage-law-2") -> None:
        try:
            import voyageai
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError(
                "Voyage embeddings need the 'voyage' extra: uv sync --extra voyage"
            ) from exc
        self._client = voyageai.Client(api_key=api_key)
        self._model = model

    @property
    def dim(self) -> int:
        return 1024

    @property
    def model_id(self) -> str:
        return f"voyage:{self._model}"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._client.embed(texts, model=self._model, input_type="document").embeddings
        return cast("list[list[float]]", embeddings)

    def embed_query(self, text: str) -> list[float]:
        embeddings = self._client.embed([text], model=self._model, input_type="query").embeddings
        return cast("list[float]", embeddings[0])


def make_embedding_model(settings: Settings) -> EmbeddingModel:
    provider = settings.embedding_provider
    if provider == "local":
        return FastEmbedModel()
    if provider == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY required for embedding_provider=openai")
        return OpenAIEmbeddingModel(settings.openai_api_key)
    if provider == "voyage":
        if not settings.voyage_api_key:
            raise ValueError("VOYAGE_API_KEY required for embedding_provider=voyage")
        return VoyageEmbeddingModel(settings.voyage_api_key)
    raise ValueError(f"Unknown embedding provider: {provider!r}")
