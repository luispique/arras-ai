"""The legal knowledge base: deterministic Código Civil lookups + (Task 5) vector retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from arras_ai.models import CategoriaRiesgo, Fundamento


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
    ) -> None:
        self.articulos = articulos
        self.patrones = patrones
        self.index_dir = index_dir

    @classmethod
    def from_data_dir(cls, data_dir: Path, *, index_dir: Path) -> KnowledgeBase:
        articulos = {
            str(a["id"]): Articulo.model_validate(a)
            for a in _load_yaml_list(data_dir / "codigo_civil.yaml")
        }
        patrones = {
            str(p["id"]): Patron.model_validate(p)
            for p in _load_yaml_list(data_dir / "patrones.yaml")
        }
        return cls(articulos, patrones, index_dir)

    def get_articulo(self, articulo_id: str) -> Articulo | None:
        return self.articulos.get(articulo_id)

    def get_patron(self, patron_id: str) -> Patron | None:
        return self.patrones.get(patron_id)
