"""Build the LanceDB knowledge-base index from data/kb/*.yaml.

uv run python scripts/build_kb.py
"""

from __future__ import annotations

from arras_ai.config import load_settings
from arras_ai.rag.knowledge_base import KnowledgeBase


def main() -> None:
    kb = KnowledgeBase.build(load_settings())
    print(f"index ready at {kb.index_dir} ({len(kb.patrones)} patterns)")


if __name__ == "__main__":
    main()
