# Sprint 3 — RAG: legal knowledge base and grounded risk citations

**Status:** approved (design)
**Date:** 2026-07-12
**Depends on:** Sprint 2 (LangGraph agent + hybrid risk detection producing `InformeArras`)

## Goal

Ground the risk report in a legal knowledge base so each detected risk carries a
verifiable citation. Two distinct mechanisms, deliberately NOT both "RAG":

1. **Código Civil** — a small, fixed set of articles with a known, deterministic
   mapping to risk types (penitenciales→1454, penales→1152/1153, …). Loaded in
   memory as a dict and cited by **exact lookup**. NOT embedded, NOT in the vector
   index — forcing keyed reference data through vector search would add noise and
   non-determinism to an exact lookup.
2. **Problematic-clause patterns / doctrine** — an authored corpus retrieved by
   **semantic similarity** against the contract's clauses. This is the genuine RAG
   surface: open-ended matching of contract prose to known problem patterns.

The LLM risk pass is grounded in retrieved patterns; deterministic rule risks are
cited by exact CC/pattern lookup. Every risk gains structured `referencias`.

### Non-goals (deferred)

- Full jurisprudence corpus / redistributing court rulings (authored, cited
  pattern+doctrine notes only in Sprint 3).
- Per-clause retrieval (Sprint 3 retrieves once per contract; per-clause is a
  later refinement).
- Evals / ground-truth dataset (Sprint 4).
- Web/CLI packaging beyond the existing CLI (Sprint 5+).

## Architecture decisions

1. **Two-path knowledge base.** `KnowledgeBase` exposes deterministic lookups
   (`get_articulo(id)`, `get_patron(id)`) over in-memory dicts AND a vector
   `retrieve(query, k)` over patterns only. CC never touches embeddings/LanceDB.
2. **Local embeddings by default, provider-agnostic.** `EmbeddingModel` is an
   abstract interface; the default `FastEmbedModel` (ONNX, multilingual, no key,
   no torch) works offline on clone. `OpenAIEmbeddingModel` and
   `VoyageEmbeddingModel` are optional adapters (lazy-imported; require an extra +
   API key). Honors the project's "no mandatory SaaS default / no vendor lock-in"
   constraint while satisfying the "abstract interfaces where they earn it" goal.
3. **LanceDB behind a `VectorStore` interface.** Embedded, file-based, no server,
   Apache-2.0. Swappable via the interface.
4. **Explicit retrieval node.** The graph gains `recuperar_contexto`, making the
   RAG step visible in the state machine and giving Sprint 4 evals a seam.
5. **Structured citations.** Risks carry `referencias: list[ReferenciaLegal]` —
   additive, backward-compatible.
6. **Lazy index build.** `KnowledgeBase` builds the LanceDB index if missing
   (idempotent); the index dir is git-ignored; `scripts/build_kb.py` rebuilds
   explicitly. Source YAML is committed and reviewable — that is the real artifact.
7. **`riesgos.py` stays pure.** Citation helpers receive the CC/pattern dicts as
   arguments (dependency injection); no KB import in the pure detectors.

## Knowledge base data (`data/kb/`)

- `codigo_civil.yaml` — list of `{id, articulo, titulo, texto}` for the relevant
  articles (1454, 1152, 1153, and connected 1124/1100/1101). Official BOE text
  (public domain). Loaded into an in-memory dict keyed by `id` (== article number).
- `patrones.yaml` — list of `{id, titulo, categoria, texto, referencia}` authored
  problematic-clause / doctrine notes (e.g. id `financiacion` → categoria
  `falta_financiacion`). Loaded into an in-memory dict by `id` AND embedded into
  the LanceDB index (document = `titulo` + `texto`, metadata = the rest).

A static `CATEGORIA_REFERENCIAS: dict[CategoriaRiesgo, list[tuple[Literal["codigo_civil",
"patron"], str]]]` maps each deterministic risk category to concrete reference keys —
`(tipo_fuente, id)` tuples — that cite it (e.g. `tipo_ambiguo → [("codigo_civil", "1454")]`,
`falta_financiacion → [("patron", "financiacion")]`).

## Data models (`models.py`)

`AnalisisArras` and existing risk models unchanged except the additive field.

```python
class ReferenciaLegal(BaseModel):        # extra="forbid"
    fuente_id: str
    tipo_fuente: Literal["codigo_civil", "patron"]
    titulo: str          # "Art. 1454 CC" / "Patrón: falta de condición suspensiva"
    extracto: str        # snippet for verification

class Riesgo(RiesgoBase):
    fuente: Literal["regla", "llm"]
    referencias: list[ReferenciaLegal] = []   # NEW, additive
```

The LLM risk schema (`RiesgoBase` used in `RiesgosDetectadosLLM`) gains an optional
`patron_ids: list[str] = []` so the model can name the retrieved patterns it used;
these map to `ReferenciaLegal` in code (the model never fabricates `referencias`
directly). Unknown ids are dropped.

## `rag` package (`src/arras_ai/rag/`)

```
embeddings.py     # EmbeddingModel (ABC): embed(texts)->list[list[float]], dim
                  #   FastEmbedModel (default), OpenAIEmbeddingModel, VoyageEmbeddingModel (lazy)
store.py          # VectorStore (ABC): add(ids, vectors, docs, metas); query(vector, k)->hits
                  #   LanceDBStore
knowledge_base.py # KnowledgeBase: loads YAML; get_articulo(id); get_patron(id);
                  #   retrieve(query, k)->list[PatronHit]; ensure_index() (lazy build)
ingest.py         # build_index(kb, embedding_model, store) — embed patterns, populate store
```

`make_embedding_model(settings)` picks the adapter by `ARRAS_EMBEDDING_PROVIDER`
(lazy-importing hosted adapters, raising a clear error if the extra is missing).

## Graph integration (`agent.py`)

Graph (4 nodes): `extraer → recuperar_contexto → detectar_riesgos → componer_informe`.

- **`recuperar_contexto`** — builds a query from `tipo_arras` + contract text (one
  retrieval per contract), calls `kb.retrieve(query, k)`, writes
  `patrones_recuperados: list[PatronHit]` to state. Vector path only.
- **`detectar_riesgos`**:
  - Rules (`riesgos.py`, pure): after producing each rule `Riesgo`, attach
    `referencias` via a pure `citar(categoria, articulos_cc, patrones)` using
    `CATEGORIA_REFERENCIAS` + the injected in-memory dicts.
  - LLM pass: prompt includes `patrones_recuperados` as grounding context and asks
    the model to list the `patron_ids` supporting each finding; code maps those ids
    to `ReferenciaLegal` (fallback: attach the top-k retrieved patterns as context
    references if the model names none).
- **`componer_informe`** — unchanged merge/dedup; risks now carry `referencias`.

`EstadoAnalisis` gains `patrones_recuperados: list[PatronHit] = []`. The graph is
built with a `KnowledgeBase` instance (bound into the nodes like the client/model).

## Config (`config.py`)

- `ARRAS_EMBEDDING_PROVIDER`: `local` (default) | `openai` | `voyage`.
- `OPENAI_API_KEY` / `VOYAGE_API_KEY`: only required if the matching provider is
  selected.
- `ARRAS_KB_INDEX_DIR`: LanceDB index directory (default under a cache path);
  git-ignored.

Dependencies: add `fastembed`, `lancedb`, `pyyaml` (all permissive). Hosted
adapters via `[project.optional-dependencies]` (`openai`, `voyage`), lazy-imported.

## CLI (`cli.py`)

Each risk renders its `referencias` as a sub-line (e.g. `Cf. art. 1454 CC · Patrón:
falta de condición suspensiva`). `--json` includes `referencias` (additive; not a
breaking change — `referencias` defaults to `[]`).

## Testing

- **Unit (offline, no network, no model download):**
  - `FakeEmbeddingModel` (deterministic vectors, e.g. hashed) so vector-store and
    retrieval plumbing are tested without downloading ONNX.
  - `LanceDBStore` add/query in a tmp dir with fake vectors.
  - `KnowledgeBase`: YAML loading; `get_articulo`/`get_patron` deterministic
    lookups; `retrieve` returns the seeded pattern for a query (plumbing).
  - `citar(...)` pure function: category → expected `ReferenciaLegal`s.
  - Agent `recuperar_contexto` node with a stub KB; risks carry `referencias`;
    LLM `patron_ids` → `ReferenciaLegal` mapping incl. unknown-id drop.
- **Integration (real, `-m integration`, skipped without a key):**
  - Real fastembed retrieval returns the financing pattern for a "sin cláusula de
    financiación" query (semantic quality).
  - Full agent over fixtures produces risks WITH `referencias`: confirmatorias
    problematic → a risk cites the financing pattern; penitenciales → `tipo`/type
    context cites art. 1454. `nivel` behavior from Sprint 2 unchanged.
  - `scripts/smoke_test.py` extended to print/verify citations.

## Docs

- `ARCHITECTURE.md`: Sprint 3 section — the two-path KB and why CC is a
  deterministic lookup not RAG; the `EmbeddingModel`/`VectorStore` abstractions
  and local default; LanceDB; lazy hosted adapters; the retrieval node + citations.
- `README.md`: update the "How it works" diagram (4 nodes), tick Sprint 3 in the
  roadmap, refresh the demo to show citations under a risk.

## Success criteria

- `ruff check` / `ruff format --check` / `mypy --strict` / `pytest` all green
  (offline suite uses `FakeEmbeddingModel`; integration skipped without a key).
- Clone → `uv sync` → first `arras analyze` builds the index and runs offline with
  no extra keys.
- Live: retrieval returns the relevant pattern; the agent attaches verifiable
  `referencias` to risks (integration + smoke test).

## Future project context (recorded here for traceability; NOT built in Sprint 3)

- **Distribution (Sprint 5+): web, not Electron.** Two layers: (1) Core = CLI +
  Docker + MCP server, self-hosted, bring-your-own API key or Ollama — this is
  where the portfolio value lives (RAG, LangGraph, evals, MCP). (2) Public demo =
  web (Astro + Vercel) using the project's key, protected by aggressive per-IP rate
  limiting + a pre-loaded example. Showcase, not an unlimited service.
- **Business model: no freemium/billing now.** Documented as open-core vision in
  the README, not built; billing only post-launch with real traction. MIT vs
  monetization tension noted (MIT gives no commercial moat) — irrelevant for the
  portfolio, revisit only if the business ever matters.
