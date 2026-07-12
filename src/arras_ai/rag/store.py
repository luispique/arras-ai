"""Vector store behind an interface. LanceDB is the embedded, file-based implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class VectorStore(ABC):
    @abstractmethod
    def add(
        self, ids: list[str], vectors: list[list[float]], metadatas: list[dict[str, str]]
    ) -> None: ...

    @abstractmethod
    def query(self, vector: list[float], k: int) -> list[tuple[str, float]]: ...

    @abstractmethod
    def count(self) -> int: ...


class LanceDBStore(VectorStore):
    def __init__(self, index_dir: Path, dim: int, table: str = "patrones") -> None:
        import lancedb

        self._dim = dim
        self._table_name = table
        index_dir.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(index_dir))

    def add(
        self, ids: list[str], vectors: list[list[float]], metadatas: list[dict[str, str]]
    ) -> None:
        rows = [
            {"id": i, "vector": v, **m} for i, v, m in zip(ids, vectors, metadatas, strict=True)
        ]
        self._db.create_table(self._table_name, data=rows, mode="overwrite")

    def query(self, vector: list[float], k: int) -> list[tuple[str, float]]:
        tbl = self._db.open_table(self._table_name)
        results = tbl.search(vector).limit(k).to_list()
        # LanceDB returns L2 `_distance` (lower is closer); convert to higher-is-closer.
        return [(r["id"], -float(r["_distance"])) for r in results]

    def count(self) -> int:
        if self._table_name not in self._db.list_tables().tables:
            return 0
        return int(self._db.open_table(self._table_name).count_rows())
