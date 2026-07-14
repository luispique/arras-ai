"""The legal knowledge base: deterministic Código Civil lookups + (Task 5) vector retrieval."""

from __future__ import annotations

import hashlib
import importlib.resources
import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml
from pydantic import BaseModel, ConfigDict

from arras_ai.models import CategoriaRiesgo, Fundamento

if TYPE_CHECKING:
    from arras_ai.config import Settings
    from arras_ai.rag.embeddings import EmbeddingModel
    from arras_ai.rag.store import VectorStore


class Articulo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    articulo: str
    titulo: str
    texto: str

    def como_fundamento(self) -> Fundamento:
        return Fundamento(
            tipo="codigo_civil", referencia=f"art. {self.articulo} CC", texto=self.texto
        )


class Patron(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    titulo: str
    categoria: CategoriaRiesgo
    tipo: Literal["doctrina", "jurisprudencia"]
    referencia: str
    texto: str

    def texto_indexable(self) -> str:
        return f"{self.titulo}. {self.texto}"

    def como_fundamento(self) -> Fundamento:
        return Fundamento(tipo=self.tipo, referencia=self.referencia, texto=self.texto)


class PatronHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patron: Patron
    score: float


def _default_kb_dir() -> Path:
    """The KB YAML ships inside the package (works from any install, no repo checkout)."""
    return Path(str(importlib.resources.files("arras_ai") / "kb_data"))


def _load_yaml_list(path: Path) -> list[dict[str, object]]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list in {path}")
    return data


class KnowledgeBase:
    """Loads the KB source data. Vector retrieval is wired in Task 5."""

    def __init__(
        self,
        articulos: dict[str, Articulo],
        patrones: dict[str, Patron],
        index_dir: Path,
        embedding_model: EmbeddingModel | None = None,
        store: VectorStore | None = None,
    ) -> None:
        self.articulos = articulos
        self.patrones = patrones
        self.index_dir = index_dir
        self._embedding_model = embedding_model
        self._store = store

    @classmethod
    def from_data_dir(
        cls,
        data_dir: Path,
        *,
        index_dir: Path,
        embedding_model: EmbeddingModel | None = None,
        store: VectorStore | None = None,
    ) -> KnowledgeBase:
        articulos = {
            str(a["id"]): Articulo.model_validate(a)
            for a in _load_yaml_list(data_dir / "codigo_civil.yaml")
        }
        patrones = {
            str(p["id"]): Patron.model_validate(p)
            for p in _load_yaml_list(data_dir / "patrones.yaml")
        }
        return cls(articulos, patrones, index_dir, embedding_model=embedding_model, store=store)

    @classmethod
    def build(
        cls, settings: Settings, data_dir: Path | None = None, *, force: bool = False
    ) -> KnowledgeBase:
        from arras_ai.rag.embeddings import make_embedding_model
        from arras_ai.rag.store import LanceDBStore

        data_dir = data_dir or _default_kb_dir()
        index_dir = Path(settings.kb_index_dir)
        embedding_model = make_embedding_model(settings)
        store = LanceDBStore(index_dir=index_dir, dim=embedding_model.dim)
        kb = cls.from_data_dir(
            data_dir, index_dir=index_dir, embedding_model=embedding_model, store=store
        )
        if force:
            kb.rebuild()
        else:
            kb.ensure_index()
        return kb

    def get_articulo(self, articulo_id: str) -> Articulo | None:
        return self.articulos.get(articulo_id)

    def get_patron(self, patron_id: str) -> Patron | None:
        return self.patrones.get(patron_id)

    def _meta_path(self) -> Path:
        return self.index_dir / "meta.json"

    def _patrones_hash(self) -> str:
        indexable = {pid: p.texto_indexable() for pid, p in sorted(self.patrones.items())}
        payload = json.dumps(indexable, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _expected_meta(self) -> dict[str, object]:
        assert self._embedding_model is not None
        return {
            "model_id": self._embedding_model.model_id,
            "dim": self._embedding_model.dim,
            "patrones_hash": self._patrones_hash(),
        }

    def ensure_index(self) -> None:
        if self._store is None or self._embedding_model is None:
            raise RuntimeError("KnowledgeBase has no embedding_model/store for indexing")
        expected = self._expected_meta()
        if self._store.count() == 0:
            from arras_ai.rag.ingest import build_index

            build_index(self, self._embedding_model, self._store)
            self.index_dir.mkdir(parents=True, exist_ok=True)
            self._meta_path().write_text(json.dumps(expected), encoding="utf-8")
            return
        # Index already built — verify it used the SAME embedding model AND the SAME
        # source patterns, else the query vectors will not match the stored ones (model
        # change) or the stored ones no longer reflect src/arras_ai/kb_data/patrones.yaml
        # (a source edit), and retrieval is garbage or stale either way.
        if not self._meta_path().is_file():
            raise RuntimeError(
                "KB index has no metadata; rebuild it with `uv run python scripts/build_kb.py`."
            )
        actual = json.loads(self._meta_path().read_text(encoding="utf-8"))
        if actual != expected:
            raise RuntimeError(
                f"KB index was built with {actual} but the current config/patterns expect "
                f"{expected}. Rebuild it with `uv run python scripts/build_kb.py`."
            )

    def rebuild(self) -> None:
        """Unconditionally re-embed all patterns and overwrite the index + metadata."""
        if self._store is None or self._embedding_model is None:
            raise RuntimeError("KnowledgeBase has no embedding_model/store for indexing")
        from arras_ai.rag.ingest import build_index

        build_index(self, self._embedding_model, self._store)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self._meta_path().write_text(json.dumps(self._expected_meta()), encoding="utf-8")

    def retrieve(self, query: str, k: int = 4) -> list[PatronHit]:
        if self._store is None or self._embedding_model is None:
            raise RuntimeError("KnowledgeBase has no embedding_model/store for retrieval")
        vector = self._embedding_model.embed_query(query)
        hits: list[PatronHit] = []
        for patron_id, score in self._store.query(vector, k):
            patron = self.patrones.get(patron_id)
            if patron is not None:
                hits.append(PatronHit(patron=patron, score=score))
        return hits
