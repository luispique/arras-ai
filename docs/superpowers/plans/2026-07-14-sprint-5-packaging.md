# Sprint 5 (part 2) — CLI/Docker Packaging — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the package self-contained (ship the KB as package data), then add a Dockerfile + a CI build guard + install/self-host docs, so `arras` runs from a real install (pipx/Docker/wheel) without a repo checkout.

**Architecture:** One scoped, behavior-preserving core change — relocate `data/kb/*.yaml` into `src/arras_ai/kb_data/` and resolve the default KB dir via `importlib.resources` — makes pip/pipx/Docker installs work. Then a `python:3.12-slim` Dockerfile that pip-installs the package (local fastembed), routing the model + index cache into a mounted volume; a CI `docker build` job; and README/ARCHITECTURE docs.

**Tech Stack:** Python 3.11+ (`importlib.resources`), hatchling wheel build, Docker, existing tooling (uv/ruff/mypy/pytest), GitHub Actions.

## Global Constraints

- Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest` stay green; line 100.
- The ONLY core change is the KB relocation + default-path resolution (behavior-preserving). No other `src/arras_ai/` behavior changes.
- `data/evals/casos.yaml` stays at repo root (dev-only eval fixture, not shipped). Only `data/kb/` moves into the package.
- The built wheel MUST contain `arras_ai/kb_data/codigo_civil.yaml` and `patrones.yaml`.
- Docker is NOT available in the dev environment — the Dockerfile is validated by a CI `docker build` job, not locally. Do not attempt to run Docker locally.
- Conventional Commits; every commit ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Work on branch `feat/sprint-5-packaging` (already checked out).

## File Structure

- `src/arras_ai/kb_data/codigo_civil.yaml`, `.../patrones.yaml` — **move** from `data/kb/`.
- `src/arras_ai/rag/knowledge_base.py` — **modify**: default KB dir via `importlib.resources`.
- `pyproject.toml` — **modify** if needed: ensure `kb_data/*.yaml` ships in the wheel.
- `tests/test_rag_knowledge_base.py`, `tests/test_riesgos.py` — **modify**: point at the packaged KB location.
- `vercel.json` — **modify**: `includeFiles` `{src,data}/**` → `src/**`.
- `Dockerfile`, `.dockerignore` — **create**.
- `.github/workflows/ci.yml` — **modify**: add a `docker` build job.
- `README.md`, `ARCHITECTURE.md` — **modify**: install/self-host docs + roadmap.

---

## Task 1: Ship the KB as package data (self-contained install)

**Files:** Move `data/kb/*.yaml` → `src/arras_ai/kb_data/`; modify `src/arras_ai/rag/knowledge_base.py`, `pyproject.toml`, `tests/test_rag_knowledge_base.py`, `tests/test_riesgos.py`, `vercel.json`.

**Interfaces:**
- `KnowledgeBase.build(settings, data_dir=None, ...)` default `data_dir` becomes the packaged `arras_ai/kb_data` dir (via `importlib.resources`). `from_data_dir(data_dir, *, ...)` is unchanged (still reads `data_dir/codigo_civil.yaml` + `patrones.yaml`).

- [ ] **Step 1: Move the KB files into the package**

```bash
mkdir -p src/arras_ai/kb_data
git mv data/kb/codigo_civil.yaml src/arras_ai/kb_data/codigo_civil.yaml
git mv data/kb/patrones.yaml src/arras_ai/kb_data/patrones.yaml
# data/kb/README.md (if any) and data/ may now be empty of kb/ — leave data/evals/ intact.
```

- [ ] **Step 2: Write/adjust the failing test** — in `tests/test_rag_knowledge_base.py`, replace the hard-coded `DATA_DIR = repo/data/kb` with the packaged location, and add an assertion that the default `build`-path KB loads. Change the top:

```python
import importlib.resources
from pathlib import Path

# ... existing imports ...

DATA_DIR = Path(str(importlib.resources.files("arras_ai") / "kb_data"))


def test_default_kb_dir_is_packaged() -> None:
    # The KB ships inside the package, so a real install (no repo checkout) finds it.
    assert (DATA_DIR / "codigo_civil.yaml").is_file()
    assert (DATA_DIR / "patrones.yaml").is_file()
    kb = KnowledgeBase.from_data_dir(DATA_DIR, index_dir=Path("/tmp/unused-index"))
    assert kb.get_articulo("1454") is not None
```

Keep the other tests, but ensure any that referenced the old `repo/data/kb` now use this `DATA_DIR`.

- [ ] **Step 3: Run to verify it fails** — `uv run pytest tests/test_rag_knowledge_base.py -v` → the new/updated tests FAIL (files not yet resolvable at the packaged path if the default in code still points at repo `data/kb`, or the move + default aren't wired). Actually after Step 1 the files ARE at the packaged path, so `DATA_DIR` resolves; the RED here is that `knowledge_base.py`'s **default** still points at `parents[3]/data/kb` (now gone) — any test/flow using the default breaks. Confirm the failure, then fix in Step 4.

- [ ] **Step 4: Update `knowledge_base.py` default path** — add `import importlib.resources` at the top, and change `build`'s default `data_dir` resolution. Replace the `data_dir = data_dir or (Path(__file__).resolve().parents[3] / "data" / "kb")` line with:

```python
        data_dir = data_dir or _default_kb_dir()
```

and add a module-level helper:

```python
def _default_kb_dir() -> Path:
    """The KB YAML ships inside the package (works from any install, no repo checkout)."""
    return Path(str(importlib.resources.files("arras_ai") / "kb_data"))
```

(`arras_ai` is a regular filesystem package, so `files(...)` yields a real path.)

- [ ] **Step 5: Ensure the wheel ships the YAML** — verify hatchling includes the data files. In `pyproject.toml`, under `[tool.hatch.build.targets.wheel]` (which has `packages = ["src/arras_ai"]`), add an explicit artifact include so it is guaranteed regardless of hatchling defaults:

```toml
[tool.hatch.build.targets.wheel.force-include]
"src/arras_ai/kb_data" = "arras_ai/kb_data"
```

- [ ] **Step 6: Update other references**
  - `tests/test_riesgos.py`: the `citar` test builds a KB from `repo/data/kb` — repoint it to the packaged `DATA_DIR` (mirror the `importlib.resources` line, or import from the KB module). Make the test pass.
  - `vercel.json`: change `"includeFiles": "{src,data}/**"` → `"includeFiles": "src/**"` (the KB now resolves inside `src/arras_ai/kb_data`; `data/` is no longer needed at runtime).

- [ ] **Step 7: Run to verify pass + wheel contents**

```bash
uv run pytest -v            # full suite green
uv run mypy && uv run ruff check . && uv run ruff format --check .
uv build                    # builds sdist + wheel into dist/
python -c "import zipfile, glob; w=glob.glob('dist/*.whl')[0]; names=zipfile.ZipFile(w).namelist(); assert 'arras_ai/kb_data/codigo_civil.yaml' in names and 'arras_ai/kb_data/patrones.yaml' in names, names; print('wheel ships KB:', w)"
uv run python scripts/build_kb.py   # still builds the index from the packaged default
```
Expected: suite green; the wheel-contents assertion prints "wheel ships KB"; build_kb succeeds. (`dist/` is git-ignored.)

- [ ] **Step 8: Commit**

```bash
git add src/arras_ai/kb_data src/arras_ai/rag/knowledge_base.py pyproject.toml tests/test_rag_knowledge_base.py tests/test_riesgos.py vercel.json
git commit -m "refactor: ship the knowledge base as package data (self-contained install)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Dockerfile + .dockerignore + CI docker build

**Files:** Create `Dockerfile`, `.dockerignore`. Modify `.github/workflows/ci.yml`.

- [ ] **Step 1: Create `.dockerignore`:**

```
.git
.github
web
node_modules
tests
docs
data/evals
.superpowers
.arras_kb_index
dist
build
*.egg-info
__pycache__
.venv
.vercel
.mypy_cache
.ruff_cache
.pytest_cache
```

- [ ] **Step 2: Create `Dockerfile`** (self-contained package → plain `pip install .`):

```dockerfile
# Self-host image for the arras-ai CLI (core layer: local fastembed embeddings).
FROM python:3.12-slim

# Install the package (exposes the `arras` console script + runtime deps incl. fastembed).
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Route large caches (fastembed model via the HF hub + the KB index) into a mountable
# volume so they persist across runs. First run downloads the model (~large) once.
ENV HOME=/cache \
    HF_HOME=/cache/hf \
    ARRAS_KB_INDEX_DIR=/cache/kb_index
RUN mkdir -p /cache && chmod 0777 /cache

# Analyze files mounted at /data, e.g. `-v "$PWD:/data" ... analyze /data/contrato.pdf`.
WORKDIR /data
ENTRYPOINT ["arras"]
CMD ["--help"]
```

Note: `pip install .` reads `pyproject.toml` (which references `README.md`), so both are
copied before install; `src/` carries the package incl. `kb_data`. `data/` is NOT copied
(the KB now ships inside the package; `data/evals` is dev-only).

- [ ] **Step 3: Add the CI `docker` job** — in `.github/workflows/ci.yml`, add a third job (existing `check` and `web` jobs unchanged):

```yaml
  docker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build the self-host image
        run: docker build -t arras-ai:ci .
```

- [ ] **Step 4: Verify locally what is verifiable (no Docker here)**

Docker can't run in this environment; the CI `docker` job validates the build. Locally,
validate the packaged console script from a wheel install in a throwaway venv:

```bash
uv build
python -m venv /tmp/arras-venv
/tmp/arras-venv/bin/python -m pip install --quiet dist/*.whl
/tmp/arras-venv/bin/arras --version
/tmp/arras-venv/bin/arras --help | head -5
```
Expected: `--version` prints `arras-ai <v>`; `--help` shows the CLI usage — proving the
installed (non-repo) console script works and its imports resolve. Validate the CI YAML:
`python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`.

- [ ] **Step 5: Commit**

```bash
git add Dockerfile .dockerignore .github/workflows/ci.yml
git commit -m "feat: Dockerfile for the self-host CLI + CI docker build guard" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Install / self-host docs

**Files:** Modify `README.md`, `ARCHITECTURE.md`.

- [ ] **Step 1: README "Install / self-host" section** — add a section (near "Quick start") documenting the two self-host paths, and adjust the roadmap:

- pipx: `pipx install git+https://github.com/luispique/arras-ai`, then
  `export ANTHROPIC_API_KEY=sk-ant-...` and `arras analyze contrato.pdf`. Note the first
  run downloads the local embedding model (~large) once.
- Docker:
  ```bash
  docker build -t arras-ai .
  docker run --rm -e ANTHROPIC_API_KEY=sk-ant-... \
    -v "$PWD:/data" -v arras-cache:/cache \
    arras-ai analyze /data/contrato.pdf
  ```
  Note the slow first run (model download into the `arras-cache` volume; reused after).
- PyPI: "planned; not yet published."
- Roadmap: mark Sprint 5 complete (web demo + packaging); Sprint 6 (MCP) remaining.

Keep the legal disclaimer intact; no marketing-speak.

- [ ] **Step 2: ARCHITECTURE note** — add a short paragraph (in or after the Sprint 5
section): the KB now ships as **package data** (resolved via `importlib.resources`), so
the package is self-contained for pip/pipx/Docker installs; this is the self-host
packaging of the two-layer split (local fastembed), distinct from the Vercel demo
(hosted Voyage). Accurate to the code.

- [ ] **Step 3: Verify** — `uv run pytest -q` green; `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` OK. Docs claims match the code.

- [ ] **Step 4: Commit**

```bash
git add README.md ARCHITECTURE.md
git commit -m "docs: document pipx + Docker self-host install; Sprint 5 complete" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` — green.
- [ ] `uv build` → wheel contains `arras_ai/kb_data/*.yaml`; a wheel install in a fresh venv exposes a working `arras --version`/`--help`.
- [ ] `src/arras_ai/` change limited to the KB relocation + default-path resolution.
- [ ] CI `docker` job builds the image (validated on the runner via the PR).
- [ ] User-gated (documented): real `docker run ... analyze` + GHCR publish.
- [ ] Push branch and open a PR: `git push -u origin feat/sprint-5-packaging && gh pr create --fill`.
```
