# Sprint 5 (part 1) — Public web demo

**Status:** approved (design)
**Date:** 2026-07-13
**Depends on:** Sprints 1–4 (the Python core: `arras_ai.agent.analizar_texto` → `InformeArras`, with a provider-agnostic `EmbeddingModel` and the `KnowledgeBase` RAG layer)

## Goal

A public, single-page web demo of the arras analysis — an Astro frontend and a
Python serverless function, both on Vercel — that reuses the existing Python core
**unchanged**. A visitor can paste text, upload a PDF, or run a pre-loaded example,
and sees the extraction + risk report + citations. It is a **showcase, not an
unlimited service**: protected by app-level input caps, per-IP Vercel Firewall
rate limiting, and a monthly spend cap on the project's Anthropic key.

This is **part 1 of Sprint 5** (the web demo). CLI/Docker packaging (making `arras`
pip/pipx-installable + a Dockerfile for the self-host core layer) is a separate,
smaller follow-on and is **out of scope here**.

### Non-goals (deferred / excluded)

- CLI/Docker packaging (separate follow-on).
- Auth, user accounts, billing, saved history, or any persistence beyond the
  request lifecycle.
- Changing the Python core's behavior. The demo only *configures* it (hosted
  embeddings) and calls it.
- Local fastembed in the demo (the 2GB model is incompatible with serverless; the
  self-host core keeps fastembed).

## Two-layer distribution (from the project's recorded strategy)

- **Core** (`src/arras_ai/`, unchanged): CLI + analysis; self-host uses **local
  fastembed** embeddings.
- **Demo web** (new, this sprint): Astro + Vercel Python functions using **hosted
  Voyage embeddings** via the Sprint-3 `EmbeddingModel` abstraction. Single Vercel
  deployment.

## Architecture & repo layout (additive)

```
src/arras_ai/          # core Python — UNCHANGED behavior
web/                   # Astro app (frontend)
  package.json, astro.config.mjs, tailwind config
  src/pages/index.astro
  src/components/       # analyze form + results view (one interactive island)
  src/lib/             # pure InformeArras -> view-model mapper (unit-tested)
  src/examples/         # 2-3 example contract texts (bundled, for the example buttons)
api/
  analyze.py           # Vercel Python function: POST /api/analyze
  requirements.txt     # anthropic, pdfplumber, pydantic, pydantic-settings, pyyaml,
                       #   lancedb, voyageai, langgraph  (NO fastembed)
vercel.json            # Astro build + /api Python runtime + rewrites
```

**Data flow:**
```
browser → Astro island (paste text | upload PDF | example button)
        → POST /api/analyze {texto? | pdf_base64?}   (examples are client-side prefills → texto)
        → analyze.py: validate + cap; if PDF, arras_ai.pdf.extract_text(bytes);
          arras_ai.agent.analizar_texto(texto, kb=<Voyage KB in /tmp>)
        → InformeArras JSON → island renders extraction + risk report + citations
```

**Core reuse:** the function imports `arras_ai` (the repo `src/` is bundled; the
function inserts `src` on `sys.path`). Same LangGraph agent, risk detection, and
citations. Only the embedding provider changes.

## Embeddings on serverless (the key technical point)

The demo sets `ARRAS_EMBEDDING_PROVIDER=voyage` (model `voyage-law-2`) and
`ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`. Voyage is **API-only** — no 2GB model to
load — so on the first request of a warm instance the function lazily builds the
5-pattern LanceDB index in `/tmp` via ~5 Voyage calls (<1s), and reuses it for
subsequent requests (Fluid Compute keeps instances warm). No committed index, no
build step, and it respects the read-only serverless filesystem (`/tmp` is the only
writable path). The Sprint-3 index model-coherence guard still applies within a
warm instance.

## API contract — `POST /api/analyze`

Request JSON (exactly one of the inputs):
- `{"texto": "<contract text>"}` — pasted text (also how example buttons submit).
- `{"pdf_base64": "<base64>"}` — uploaded PDF.

Response: `200` with the `InformeArras` JSON (same shape as the CLI `--json`), or an
error object `{"error": "<mensaje en español>"}` with:
- `400` invalid/empty/multiple inputs;
- `413` input over caps;
- `422` analysis error (`AnalysisError`) / bad PDF (`PdfExtractionError`);
- `502` upstream model/API error;
- `405` non-POST.

**Input caps (app-level, in `analyze.py`):** text ≤ 30,000 chars; PDF ≤ 5 MB
decoded and ≤ 15 pages; reject over-cap with `413` and a clear Spanish message.
Content-type must be JSON.

## Frontend (Astro + Tailwind, one page, Spanish UI)

- **Hero**: name + one-liner + prominent link to the legal disclaimer.
- **Input**: toggle "Pegar texto" ⇆ "Subir PDF" + 2–3 example buttons that prefill
  the textarea (from `web/src/examples/`, submitted as `texto`); an "Analizar"
  button. Client-side guard mirrors the server caps (length/size).
- **States**: idle → loading (spinner) → results | error (Spanish message).
- **Results**: mirrors the CLI's information design — `Tipo de arras` + confidence,
  a "Datos clave" panel (parties, amounts, dates, property), and the **risk report**
  (coloured `Nivel de riesgo` banner + one card per risk: severity, description,
  recommendation, and a `Cf. …` citation line).
- **Disclaimer**: always visible; not legal advice.
- One interactive island; the rest is static Astro. A pure `informe → view-model`
  mapper in `web/src/lib/` is unit-tested.
- UI text in **Spanish** (audience); README/portfolio stay English.

## Rate limiting & cost control

- **App-level (built here):** the input caps above bound per-request cost; method
  and content-type guards reject junk cheaply.
- **Platform (documented; user configures):** a Vercel Firewall per-IP rate-limit
  rule on `/api/analyze` (e.g. a small N per minute per IP). Exact rule documented.
- **Hard ceiling (user configures):** a monthly spend limit on the project's
  Anthropic key in the console. This is the true cost cap.

## Deploy (Vercel)

- `vercel.json`: Astro build (output dir), Python function runtime for `api/`,
  rewrite `/api/analyze` → the function. Node + Python runtimes.
- Project env vars (set in Vercel by the user): `ANTHROPIC_API_KEY`,
  `VOYAGE_API_KEY`, `ARRAS_EMBEDDING_PROVIDER=voyage`,
  `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.
- The production deploy (`vercel` login/link/deploy), key provisioning, Firewall
  rule, and Anthropic spend cap are **user-account steps**; this sprint delivers the
  wired code + config + a launch checklist, not a live deployment.

## Testing

- **Python API (`api/analyze.py`), offline unit tests** with `arras_ai.agent.analizar_texto`
  mocked: input routing (text/pdf), caps → 413, empty/multiple inputs → 400,
  `AnalysisError`/`PdfExtractionError` → 422, non-POST → 405, success → 200
  with `InformeArras` JSON. A `pdf_base64` path is exercised with a tiny generated PDF
  + mocked analysis. No real API calls.
- **Frontend, offline unit tests (vitest):** the pure `informe → view-model` mapper
  (severity ordering, citation flattening, None-field handling) against a sample
  `InformeArras`.
- **CI:** the existing Python job unchanged; add a lightweight `web` job that runs
  `npm ci && npm run build` (+ vitest) — no secrets.
- **Local end-to-end:** `vercel dev` runs Astro + the function together; documented.
  The real analysis end-to-end (Voyage + Anthropic) is verifiable only with the keys
  provisioned — a user step.

## Docs

- `web/README.md`: local dev (`vercel dev`), env vars, how the demo differs from the
  core (hosted embeddings).
- `README.md`: a "Try it" section (demo URL once deployed) + tick Sprint 5 (web) in
  the roadmap, noting CLI/Docker packaging is the remaining part.
- `ARCHITECTURE.md`: a "Sprint 5" section — the two-layer split, why the demo uses
  hosted Voyage embeddings on serverless (the abstraction paying off), the `/tmp`
  lazy-index approach, and the rate-limit/cost model.
- A **launch checklist** (in `web/README.md`): the exact user steps — `vercel` link,
  set the 4 env vars, create the Firewall rate-limit rule, set the Anthropic spend
  cap, `vercel deploy`.

## Success criteria

- `web` builds (`npm run build`) and its vitest passes; `api/analyze.py` unit tests
  pass offline; the existing Python suite stays green; `ruff`/`mypy` clean for any
  new Python.
- `vercel dev` serves the page and the function locally; with keys present, a full
  analysis renders end-to-end (user-verifiable step).
- The core (`src/arras_ai/`) is unchanged in behavior; the demo only configures it.
- A launch checklist lets the user deploy without further code changes.

## Future (recorded; not built here)

- Sprint 5 part 2: CLI/Docker packaging (pip/pipx entry point, Dockerfile) for the
  self-host core layer.
- Sprint 6: MCP server + polish + public launch.
