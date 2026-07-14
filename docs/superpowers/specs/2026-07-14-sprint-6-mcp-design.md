# Sprint 6 — MCP server + polish + launch

**Status:** approved (design)
**Date:** 2026-07-14
**Depends on:** the core (`arras_ai.agent.analizar_texto → InformeArras`, `arras_ai.pdf.extract_text`, self-contained package from Sprint 5.2).

## Goal

Expose the arras analysis as an **MCP server** so agents (Claude Desktop/Code, etc.)
can call it as a tool — the final technical piece — plus light, concrete polish and a
launch checklist. This completes the 6-sprint roadmap.

## Non-goals

- Executing the public launch (announcement is a user activity; a checklist + draft
  are provided).
- Remote/hosted MCP transport (stdio only — the self-host pattern).
- Changing core behavior. The MCP server reuses the core unchanged.
- Broad "marketing" polish (README hero rewrite, GIFs). Polish is scoped to concrete
  items below.

## MCP server

`src/arras_ai/mcp_server.py`, structured for testability + lazy SDK import:

- **Pure tool functions** (module level, no `mcp` import):
  - `analizar_contrato_arras(texto: str) -> dict` — calls `analizar_texto(texto)` and
    returns `InformeArras.model_dump(mode="json")` (same shape as the CLI `--json`).
  - `analizar_contrato_pdf(ruta: str) -> dict` — `arras_ai.pdf.extract_text(ruta)` then
    the same analysis. A local-file path (self-host).
  - Core errors (`AnalysisError`, `PdfExtractionError`) are re-raised with a clear
    Spanish message so FastMCP surfaces them as a tool error (not a raw traceback).
- **`build_server()`** — lazily `from mcp.server.fastmcp import FastMCP`; if `mcp` is
  not installed, raise a clear `RuntimeError` ("instala arras-ai[mcp]"). Creates a
  `FastMCP("arras-ai")` server, registers the two tools (with docstrings that become
  the tool descriptions the agent sees, in Spanish/domain terms), returns it.
- **`main()`** — `build_server().run()` (FastMCP stdio transport by default). This is
  the `arras-mcp` entry point.

Embeddings: local fastembed (self-host default), same as the CLI — the server runs
locally.

## Packaging

- `pyproject.toml`: `[project.optional-dependencies] mcp = ["mcp>=1.2"]` and
  `[project.scripts] arras-mcp = "arras_ai.mcp_server:main"`.
- The base CLI install stays lean; `arras-mcp` without the extra fails with the clear
  RuntimeError (lazy import). Install: `pipx install 'arras-ai[mcp] @ git+https://github.com/luispique/arras-ai'`.

## Testing

- **Unit (offline, no `mcp` needed):** the two pure tool functions with `analizar_texto`
  mocked — success returns the `InformeArras` dict; `AnalysisError`/`PdfExtractionError`
  re-raise with a clear message. `analizar_contrato_pdf` monkeypatches `extract_text`.
- **Registration (with the extra):** `build_server()` registers exactly the two tools
  with the expected names; `@pytest.mark.skipif(mcp not importable)`. CI's `check` job
  runs `uv sync --extra mcp` so this executes.
- **Integration (real, `-m integration`, skipped without a key):** one real analysis via
  `analizar_contrato_arras` → a coherent `InformeArras` dict.

## Polish (scoped, concrete)

- Sweep the two inert stale `data/kb` comments (`src/arras_ai/rag/knowledge_base.py`,
  `tests/test_rag_knowledge_base.py`) → `src/arras_ai/kb_data`.
- Add a CI status badge to the top of `README.md`.
- Nothing else — no refactors, no hero rewrite.

## Docs

- `README.md`: a "Use as an MCP server" section — the install command and the Claude
  Desktop/Code `mcpServers` config snippet:
  ```json
  { "mcpServers": { "arras-ai": { "command": "arras-mcp", "env": { "ANTHROPIC_API_KEY": "sk-ant-..." } } } }
  ```
  plus CI badge; tick Sprint 6 in the roadmap → all six sprints complete.
- `ARCHITECTURE.md`: a "Sprint 6" section — the MCP server over stdio, the optional
  `[mcp]` extra, pure-tool-fns + lazy-`build_server` structure, and that it reuses the
  core with local embeddings (self-host layer).
- `docs/LAUNCH.md`: a short launch checklist (user-executed) — deploy the web demo
  (Sprint 5.1 checklist), tag a `v0.1.0` release, and a short announcement draft
  (Show HN / LinkedIn). No code.

## CI

Add `--extra mcp` to the existing `check` job's `uv sync` so the registration test runs.
The `web` and `docker` jobs are unchanged.

## Verification

- `uv run ruff check .` / `ruff format --check` / `mypy` / `pytest` green (with
  `--extra mcp` synced, the registration test runs; pure-tool tests run regardless).
- `uv build` still produces a valid wheel; `arras-mcp` is declared as an entry point.
- `src/arras_ai/` change limited to the new `mcp_server.py` + the two comment fixes
  (core behavior unchanged).
- User-gated (documented): running `arras-mcp` wired into a real Claude Desktop/Code
  client, and the public launch steps.

## Success criteria

- `arras-mcp` (with the `[mcp]` extra) starts an stdio MCP server exposing the two
  tools; without the extra it errors clearly.
- The pure tool functions are unit-tested offline; the registration test passes with the
  extra; the suite stays green.
- README documents MCP usage + the client config; roadmap shows all six sprints done;
  `docs/LAUNCH.md` gives the maintainer a clear launch path.
