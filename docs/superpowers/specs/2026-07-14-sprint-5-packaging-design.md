# Sprint 5 (part 2) — CLI/Docker packaging (self-host)

**Status:** approved (design)
**Date:** 2026-07-14
**Depends on:** the existing core (`arras` CLI entry point in `pyproject.toml`, `[project.scripts] arras = "arras_ai.cli:app"`, from Sprint 1) and the `ARRAS_KB_INDEX_DIR` env seam (Sprint 3).

## Goal

Package the **self-host core layer** so a technical user can run `arras` without a
dev checkout: a `Dockerfile` (with the fastembed model cached in a mounted volume)
plus install/self-host docs. The CLI is already pip/pipx-installable via the
existing entry point, so this sprint adds Docker + documentation and validates the
packaged install.

### Non-goals

- Publishing to PyPI (documented as an optional future; needs the maintainer's PyPI
  account/token — not done here).
- Any change to the core behavior or the web demo.
- Baking the 2 GB model into the image (rejected: runtime download + cache volume).

## Deliverables

1. **`Dockerfile`** (self-host core):
   - Base `python:3.12-slim`; install the project so the `arras` console script is on
     PATH with its runtime deps **including local `fastembed`** (self-host default).
   - `ENTRYPOINT ["arras"]`, `WORKDIR /data` (mount the user's contracts there).
   - Route large caches into a **mountable volume**: set `HOME=/cache` and
     `HF_HOME=/cache/hf` (fastembed pulls model weights via the Hugging Face hub) and
     `ARRAS_KB_INDEX_DIR=/cache/kb_index` (existing env seam) so the model download +
     KB index persist across runs in a `-v` volume. (The implementer confirms the exact
     cache env fastembed honors; the first real run — user-side — validates it.)
2. **`.dockerignore`**: exclude `web/`, `node_modules`, `.git`, `tests/`, `docs/`,
   `.superpowers/`, `.arras_kb_index/`, `dist/`, `__pycache__`, `.venv`, `.vercel`.
3. **CI `docker` job**: `docker build` the image (no run, no push) as a Dockerfile
   regression guard. The existing `check` and `web` jobs are unchanged.
4. **Docs** (`README.md`): an "Install / self-host" section —
   - pipx: `pipx install git+https://github.com/luispique/arras-ai`, then
     `export ANTHROPIC_API_KEY=... && arras analyze contrato.pdf`.
   - Docker: `docker run --rm -e ANTHROPIC_API_KEY=... -v "$PWD:/data" -v arras-cache:/cache <image> analyze /data/contrato.pdf`, noting the slow first run (model download).
   - PyPI: "planned; not yet published."
   - Tick Sprint 5 fully done in the roadmap (web demo + packaging), leaving Sprint 6.
   - `ARCHITECTURE.md`: a short note that this is the self-host packaging of the
     two-layer split (local fastembed), distinct from the Vercel demo (hosted Voyage).

## Usage (documented)

```bash
docker run --rm \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -v "$PWD:/data" -v arras-cache:/cache \
  ghcr.io/luispique/arras-ai analyze /data/contrato.pdf
```
First run downloads the fastembed model into the `arras-cache` volume and builds the
KB index there; later runs reuse both.

## Verification

- **Local (this sprint):** `uv build` produces a wheel; install it into a throwaway
  venv and confirm `arras --version` / `arras --help` work from the installed console
  script (validates the packaged entry point + that deps resolve). Python suite stays
  green; ruff/mypy unaffected (no core changes).
- **CI:** the new `docker` job validates that the `Dockerfile` **builds** on the
  runner.
- **User-gated (documented):** a real `docker run ... analyze` (needs an Anthropic key
  + the ~2 GB model download) and the actual GHCR image publish are maintainer steps;
  Docker is not available in the dev environment, so the build is validated by CI, not
  locally.

## Success criteria

- `uv build` + wheel install exposes a working `arras` console script (local check).
- CI `docker build` succeeds (Dockerfile validated on the runner).
- The core (`src/arras_ai/`) is unchanged; only new files (`Dockerfile`,
  `.dockerignore`) + CI + docs.
- README documents pipx + Docker self-host clearly; roadmap shows Sprint 5 complete.

## Future (recorded)

- PyPI publish (`pip install arras-ai`) via a release workflow — needs the maintainer's
  PyPI account/token.
- Sprint 6: MCP server + polish + public launch.
