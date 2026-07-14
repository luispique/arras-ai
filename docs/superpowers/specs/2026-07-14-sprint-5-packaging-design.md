# Sprint 5 (part 2) — CLI/Docker packaging (self-host)

**Status:** approved (design, revised after a packaging discovery)
**Date:** 2026-07-14
**Depends on:** the existing `arras` CLI entry point (`pyproject.toml`, Sprint 1) and
the `KnowledgeBase`/RAG layer (Sprint 3).

## Goal

Package the **self-host core layer** so a technical user can run `arras` without a
dev checkout: make the package **self-contained**, add a `Dockerfile` (fastembed
model cached in a mounted volume), and document pipx + Docker self-host.

## Packaging discovery (drives the one core change)

The knowledge-base YAML lives at repo-root `data/kb/`, **outside** the package
`src/arras_ai/`. Every run so far was `uv run arras` *from the repo*, so
`KnowledgeBase.build()` found it via `parents[3]/data/kb`. A real pip/pipx/wheel
install puts `arras_ai` in `site-packages` and does **not** ship `data/kb` → the
full `arras analyze` path would fail with `FileNotFoundError`. Packaging can't work
until the KB ships inside the package. This is a latent bug the packaging surfaces.

## Deliverables

### 0. Make the package self-contained (the one scoped, behavior-preserving core change)

- Move `data/kb/codigo_civil.yaml` + `data/kb/patrones.yaml` → **`src/arras_ai/kb_data/`**
  (inside the package). (`data/evals/casos.yaml` is a dev-only eval fixture and
  **stays** at repo root — it is not part of the installed package.)
- `src/arras_ai/rag/knowledge_base.py`: change the default KB directory from
  `parents[3]/data/kb` to the packaged location, resolved via
  `importlib.resources.files("arras_ai") / "kb_data"` (as a `Path` — `arras_ai` is a
  regular filesystem package). Same YAML, same schema, same behavior; only the source
  location + resolution changes. `from_data_dir(path)` is unchanged.
- `pyproject.toml`: ensure the `*.yaml` under `src/arras_ai/kb_data/` are included in
  the built wheel (hatchling includes files under the package by default; verify by
  inspecting the wheel).
- Update the references that hard-coded `data/kb`: the tests that build a KB from an
  explicit `data/kb` path (`tests/test_rag_knowledge_base.py`, the `citar` test in
  `tests/test_riesgos.py`) switch to the new packaged location (or the default), and
  `vercel.json` `includeFiles` simplifies from `{src,data}/**` to `src/**` (the demo's
  KB now resolves inside the package; `data/` is no longer needed at runtime).
- Verify: full `uv run pytest` green; `uv run python scripts/build_kb.py` still builds;
  `uv build` produces a wheel that **contains** `arras_ai/kb_data/*.yaml`.

### 1. Dockerfile + `.dockerignore`

- Base `python:3.12-slim`; `pip install .` (now self-contained — installs the `arras`
  console script + deps incl. local `fastembed`). `WORKDIR /data`; `ENTRYPOINT ["arras"]`.
- Route large caches into a mountable volume: `HOME=/cache`, `HF_HOME=/cache/hf`
  (fastembed pulls weights via the HF hub), `ARRAS_KB_INDEX_DIR=/cache/kb_index`
  (existing env seam). First run downloads the model + builds the index into the volume.
  (The implementer confirms the exact cache env fastembed honors; the first real run —
  user-side — validates it.)
- `.dockerignore`: exclude `web/`, `node_modules`, `.git`, `tests/`, `docs/`,
  `.superpowers/`, `data/evals/`, `.arras_kb_index/`, `dist/`, `__pycache__`, `.venv`, `.vercel`.

### 2. CI `docker` job

`docker build` the image (no run, no push) as a Dockerfile regression guard; the
existing `check` and `web` jobs unchanged.

### 3. Docs (`README.md`, `ARCHITECTURE.md`)

- README "Install / self-host": pipx (`pipx install git+https://github.com/luispique/arras-ai`,
  then `export ANTHROPIC_API_KEY=... && arras analyze contrato.pdf`); Docker
  (`docker run --rm -e ANTHROPIC_API_KEY=... -v "$PWD:/data" -v arras-cache:/cache <image> analyze /data/contrato.pdf`,
  noting the slow first run); PyPI "planned; not yet published"; tick Sprint 5 complete
  in the roadmap (web demo + packaging), leaving Sprint 6.
- ARCHITECTURE: a short note — the KB now ships as package data (self-contained
  install), and this is the self-host packaging of the two-layer split (local
  fastembed), distinct from the Vercel demo (hosted Voyage).

## Usage (documented)

```bash
docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... \
  -v "$PWD:/data" -v arras-cache:/cache \
  ghcr.io/luispique/arras-ai analyze /data/contrato.pdf
```

## Verification

- **Local:** full `uv run pytest` green; `uv build` wheel contains `arras_ai/kb_data/*.yaml`;
  install the wheel into a throwaway venv and confirm `arras --version`/`--help` work
  from the installed console script (validates the self-contained entry point).
  ruff/mypy clean.
- **CI:** the new `docker` job validates the `Dockerfile` **builds**.
- **User-gated (documented):** a real `docker run ... analyze` (Anthropic key + ~2 GB
  model download) and the GHCR image publish are maintainer steps; Docker is unavailable
  in the dev environment, so the build is validated by CI, not locally.

## Success criteria

- The package is self-contained: a wheel install exposes a working `arras` whose
  `analyze` path can locate the KB (no repo checkout needed). Verified via wheel-contents
  + venv install locally; full analyze is user-gated (needs a key + model).
- CI `docker build` succeeds. `src/arras_ai/` change is limited to the KB relocation +
  path resolution (behavior-preserving). README documents pipx + Docker; roadmap shows
  Sprint 5 complete.

## Non-goals / future

- PyPI publish (`pip install arras-ai`) — needs the maintainer's PyPI account/token.
- Sprint 6: MCP server + polish + public launch.
