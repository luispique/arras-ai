# Architecture & technical decisions

This document records the decisions made in Sprint 1 (the foundation) and the
reasoning behind them. It is meant to be read by contributors and by anyone
evaluating the project's engineering judgement.

## Guiding principle

Sprint 1 is a **foundation**, not a feature race. The sophistication is reserved
for where it will actually earn its keep in later sprints — the LangGraph agent,
the RAG layer, the eval harness. Here the goal is a small, correct, well-typed
core with clean seams to grow into.

The data flow today is deliberately linear:

```
PDF ──pdfplumber──▶ text ──prompt + schema──▶ Claude ──structured output──▶ AnalisisArras ──▶ CLI (table | JSON)
      pdf.py                prompts.py         analyzer.py    models.py                        cli.py
```

Each stage is a separate module with a single responsibility, so later sprints
can replace a stage without touching the others (e.g. swap the single
`analyze_text` call for a LangGraph state machine, or insert a retrieval step
between the prompt and the model).

## Language: Python

Chosen over TypeScript because the roadmap leans on the Python ecosystem at
exactly the points where sophistication matters:

- **LangGraph** (Sprint 2) — the reference implementation and most examples are
  Python-first.
- **Structured outputs** — Pydantic is the de-facto standard and the Anthropic
  SDK integrates with it directly (`client.messages.parse(output_format=Model)`).
- **RAG / evals** (Sprints 3–4) — the vector-store, embedding, and evaluation
  tooling is more mature in Python.
- **PDF processing** — the strongest, most battle-tested parsers are Python.

TypeScript would be a better fit if this were primarily a web product; the web
frontend (Sprint 5) will talk to this core over a boundary (CLI/HTTP/MCP) rather
than sharing a language, so nothing is lost.

## Package manager: uv

- Single fast tool for environments, locking, and running (`uv sync`, `uv run`).
- Reproducible installs via `uv.lock`, committed to the repo.
- Manages the Python toolchain itself (`.python-version`), so `uv sync` bootstraps
  a contributor from zero without a separate pyenv/conda step.

`poetry` and `pip-tools` were the alternatives; `uv` wins on speed and on being a
single tool for the whole workflow.

## PDF parser: pdfplumber

The decision that mattered most here was **licensing**, not just features:

- **pdfplumber** is MIT-licensed (built on `pdfminer.six`, also MIT). It keeps the
  entire dependency tree MIT-compatible — important for an MIT open-source project.
- **PyMuPDF** (a.k.a. `fitz`) is fast and excellent, but it is **AGPL-3.0** (or a
  paid commercial licence). Shipping it as a default dependency would impose AGPL
  obligations on anyone building on this project — a poor default for a permissive
  OSS tool.
- `unstructured` was overkill for text-based contracts and pulls in a heavy
  dependency chain.

Arras contracts are almost always digitally-generated, text-based PDFs, so
pdfplumber's plain text extraction is sufficient today. OCR for scanned documents
is explicitly out of scope for Sprint 1; `pdf.py` raises a clear error telling the
user a scanned document has no text layer, which is the right behaviour until OCR
is a deliberate feature.

## LLM: Anthropic Claude (`claude-opus-4-8`)

A hard project constraint, and a good fit: the task is legal-reasoning-heavy and
multilingual, both Claude strengths. The model id is centralised in `config.py`
(`DEFAULT_MODEL`) and overridable via `ARRAS_MODEL` or the `--model` CLI flag, so
upgrading is a one-line change.

## Structured outputs: Pydantic + `messages.parse`

The schema (`models.py`) is the contract between the model and the rest of the
system. Using Anthropic's structured-output support (`output_config.format` under
the hood, via `client.messages.parse(output_format=AnalisisArras)`) means:

- The model is constrained to return schema-valid JSON — no brittle parsing of
  free-form text.
- Validation happens at the SDK boundary; `analyzer.py` gets a typed
  `AnalisisArras` or a clear error.
- `extra="forbid"` on every model produces `additionalProperties: false`, which
  structured outputs require and which also catches drift early.

The schema fields are **in Spanish** on purpose (see below), and their
descriptions double as extraction instructions the model reads.

## Prompt language: hybrid (the decision to argue)

The instructions to the model are in **English**; the legal domain and the output
are in **Spanish**. Concretely:

| Part | Language | Why |
| --- | --- | --- |
| System prompt / instructions | **English** | LLMs, including Claude, follow complex, multi-constraint instructions most reliably in English; it is the industry norm for system prompts; and it keeps the operational prompt readable for an international contributor base. |
| Legal terms, article numbers, the modality names the model must reason about and quote | **Spanish** | These *are* the source law. "arras penitenciales", "a cuenta del precio", "art. 1454 CC" are legal terms of art; translating them would blur the exact distinctions the tool exists to detect. The contracts themselves are in Spanish, so the model reasons over Spanish text regardless. |
| Schema field descriptions | **Spanish** | They map 1:1 to the domain (`referencia_catastral`, `precio_total`) and are read by the model when producing output. |
| Output (justifications, summaries) | **Spanish** | The audience is Spanish buyers, sellers, and small agencies. |

**Why hybrid rather than all-Spanish or all-English?**

- **All-Spanish** would be coherent but trades away the measurable reliability
  edge English instructions have for complex behaviour (the "default to
  confirmatorias when ambiguous" rule, the "never hallucinate a NIF" rule, the
  ISO-date rule). For a tool whose whole value is *precision* on edge cases, that
  reliability matters more than stylistic coherence.
- **All-English** would force translating the legal domain, which is exactly where
  meaning gets lost — and would produce English output for a Spanish audience,
  requiring a translation step that can itself introduce legal errors.

The hybrid keeps English where it buys instruction-following reliability and
Spanish where meaning lives, and is easy to revisit: the split is confined to
`prompts.py` and the schema descriptions, so it can be A/B tested in the eval
sprint rather than argued in the abstract forever.

## Sprint 2: the LangGraph agent and risk detection

Sprint 2 replaces the single `analyze_text` call with a 3-node linear
`StateGraph` (`agent.py`): `extraer` → `detectar_riesgos` → `componer_informe`.
State is a typed Pydantic model (`EstadoAnalisis`), consistent with the rest of
the codebase's `mypy --strict` discipline rather than the untyped dict state
LangGraph allows by default.

**LangGraph is used for orchestration only.** Nodes call Claude directly through
the `anthropic` SDK's `messages.parse`, the same structured-output path validated
in Sprint 1 — there is no `langchain-anthropic` model in the graph. This keeps
the dependency footprint small, reuses code and tests that already work, is
straightforward to unit-test (call a node function, assert on the returned
state), and avoids provider lock-in to LangChain's model abstraction.

**Risk detection is hybrid.** `riesgos.py` holds deterministic detectors — pure
functions over the structured `AnalisisArras` (no API calls) that catch the
"obvious" problems: missing type, no financing clause, undefined dates, an
unidentified property. They're free, reliable, and trivially unit-tested, and
they will double as ground truth for the Sprint 4 eval harness. A single focused
LLM pass then adds what rules can't reach — nuance like an ambiguous cost split,
plus user-facing recommendations. A pure `componer_informe` merges the two lists,
deduping only categories a rule already covers (rules win; `otro` is never
deduped) and setting the global level to the maximum severity present.

Severity (`alta`/`media`/`baja`) is assigned by consequence, not by how unusual a
clause looks — calibrated during testing to be conservative: the LLM is told not
to flag statutory-default clauses (e.g. "gastos conforme a la ley") and to use
`otro` sparingly, so a well-drafted contract can legitimately come back with no
risks.

The result, `InformeArras`, wraps the unchanged `AnalisisArras` alongside
`riesgos: list[Riesgo]` and `nivel_riesgo_global` — extraction and judgement stay
separate types, so Sprint 1 consumers of `AnalisisArras` are unaffected. If the
LLM risk pass fails (timeout, bad output), the node catches it and the report is
still produced from the deterministic rule risks alone — degraded, not broken.

## Sprint 3: the RAG knowledge base and citations

Sprint 3 adds a legal knowledge base with **two deliberately different retrieval
paths**, because the two kinds of content have different correctness needs.

**Código Civil articles** (`data/kb/codigo_civil.yaml`, official BOE text) are a
small, fixed set — a handful of articles decide the whole domain. They are loaded
into memory and resolved by **deterministic exact lookup** (`get_articulo`,
`citar()` in `riesgos.py`), mapping a risk category to an article id directly.
This is *not* RAG: for a fixed, known statute, similarity search only adds a
chance of citing the wrong article, which is unacceptable in a legal tool. RAG
earns its keep only for the second path.

**Problematic-clause patterns and doctrine** (`data/kb/patrones.yaml`, authored,
not statute) are embedded and indexed in **LanceDB** (embedded, file-based), and
retrieved by semantic similarity (`KnowledgeBase.retrieve`). Embeddings sit
behind an `EmbeddingModel` interface — local `fastembed` (ONNX, no API key,
offline) is the default; `openai` and `voyage` adapters lazy-import their SDKs
so they stay optional extras, not hard dependencies. `VectorStore` is likewise
an interface, with `LanceDBStore` the only implementation today. Provider is
selected via `ARRAS_EMBEDDING_PROVIDER`. The index records the embedding model
id and dimension in `meta.json`; loading it with a different model raises
immediately instead of silently returning garbage matches.

A new `recuperar_contexto` node sits between `extraer` and `detectar_riesgos`
(`extraer → recuperar_contexto → detectar_riesgos → componer_informe`). Its query
is built from the *extracted facts* (type, detected absences, the model's own
justification) — never the raw contract text, which dilutes the signal and
exceeds the embedder's token limit.

Every `Riesgo` now carries `referencias: list[Fundamento]`, where `Fundamento`
(`tipo: codigo_civil|doctrina|jurisprudencia`) is a legal-*nature* taxonomy —
distinct from `Riesgo.fuente` (who found it: rule vs. LLM) and from Sprint 1's
`ReferenciaCodigoCivil` (citations the *contract itself* makes). Rule risks are
cited deterministically; LLM risks cite only the patterns the model explicitly
named, never an unrelated top-k match. `jurisprudencia` is reserved, unpopulated.

## Testing strategy

- **Unit tests** (offline, default `pytest` run): schema validation, PDF
  extraction, and the analyzer with Claude **mocked** — these are fast,
  deterministic, and need no API key or network.
- **Integration test** (`-m integration`): the full pipeline against a fixture
  PDF with a **real** Claude call, asserting on the extracted facts. It is skipped
  automatically unless `ANTHROPIC_API_KEY` is set, so CI and contributors without
  a key still get a green suite, while the real behaviour can be verified on
  demand.
- **Fixtures** are synthetic (`scripts/generate_fixtures.py`) and regenerated on
  demand, chosen to cover the interesting cases: a clean penitenciales contract, a
  problematic confirmatorias one, and a genuinely ambiguous one.

## Tooling

`ruff` (lint + format), `mypy --strict`, and `pytest` — all configured in
`pyproject.toml` and run in CI. Strict typing is worth it here because the schema
is the core abstraction and type errors in it would be silent data bugs.

## Deliberately out of scope for Sprint 1

LangGraph agent (Sprint 2), vector store / RAG (delivered in Sprint 3), eval harness with
ground truth (Sprint 4), web frontend (Sprint 5), and MCP server (Sprint 6). The
module boundaries above are drawn so each can be added without a rewrite.
