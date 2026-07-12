# Sprint 2 — LangGraph agent with risk detection

**Status:** approved (design)
**Date:** 2026-07-12
**Depends on:** Sprint 1 foundation (structured extraction into `AnalisisArras`)

## Goal

Migrate the single-call extraction of Sprint 1 to a **LangGraph state machine** that
adds genuinely new capability: after extracting the facts, the agent **detects
problematic clauses and produces a risk report**. RAG grounding of those risks is
explicitly deferred to Sprint 3 — Sprint 2 detects risks with deterministic rules
plus one focused LLM pass.

This is both a real capability increase (the tool now tells the user *what is wrong*,
not just *what the contract says*) and a portfolio demonstration of a typed,
multi-step agent.

### Non-goals (deferred)

- RAG / vector store grounding of risks and jurisprudence → Sprint 3.
- Evals / ground-truth dataset → Sprint 4.
- Web frontend → Sprint 5; MCP server → Sprint 6.
- Self-correction / retry loops in the graph (considered and rejected for now, YAGNI).

## Architecture decisions

1. **LangGraph for orchestration only.** The graph is a `StateGraph`; nodes are plain
   functions. We do **not** adopt `langchain-anthropic` / `ChatAnthropic`. Nodes reuse
   the validated Sprint 1 path: `anthropic.Anthropic` + `messages.parse(output_format=...)`.
   Rationale: fewer dependencies, the structured-output path is already proven (3/3 smoke
   test), easier to mock, and low provider lock-in. LangGraph does not require LangChain models.
2. **Hybrid risk detection (rules + one LLM pass).** The four "obvious" risks are derived
   deterministically from the structured `AnalisisArras` — free, reliable, testable without
   an API (valuable for Sprint 4 evals). One LLM pass adds nuance, writes user-facing
   recommendations, and catches text-only issues (cost split). This is Approach A from
   brainstorming (chosen over pure-LLM and fully-decomposed graphs).
3. **Wrapper output model.** A new `InformeArras` wraps the unchanged `AnalisisArras` plus
   the risk layer. Extraction ("what the contract says") stays separate from judgement
   ("what is wrong"). Each node owns its output.
4. **Typed Pydantic state.** Consistent with the project's `mypy --strict` posture.
5. **Graceful degradation.** If the LLM risk pass fails, the report is still produced from
   the deterministic rules alone.

## Data models (in `models.py`)

`AnalisisArras` is unchanged. New:

```python
class CategoriaRiesgo(StrEnum):
    tipo_ambiguo
    falta_financiacion
    fechas_mal_definidas
    inmueble_mal_identificado
    reparto_gastos_ambiguo
    otro

class Severidad(StrEnum):   alta | media | baja
class NivelRiesgo(StrEnum): alto | medio | bajo

class Riesgo(BaseModel):            # extra="forbid"
    categoria: CategoriaRiesgo
    severidad: Severidad
    descripcion: str        # what is wrong, referencing the contract
    recomendacion: str      # what the user should do / ask a professional
    fuente: Literal["regla", "llm"]   # provenance — used for evals/debugging

class InformeArras(BaseModel):     # extra="forbid"
    analisis: AnalisisArras
    riesgos: list[Riesgo]
    nivel_riesgo_global: NivelRiesgo
```

## Modules

```
src/arras_ai/
  models.py     # + Riesgo, CategoriaRiesgo, Severidad, NivelRiesgo, InformeArras
  riesgos.py    # NEW: deterministic detectors (pure fns) + severity aggregation + dedup
  prompts.py    # + risk-detection prompt (English instructions, Spanish domain/output)
  analyzer.py   # UNCHANGED — still produces AnalisisArras; is the engine of the `extraer` node
  agent.py      # NEW: EstadoAnalisis, node fns, build_graph(), analizar_texto/analizar_pdf()
  cli.py        # updated: invoke the agent, render InformeArras
  pdf.py, config.py  # unchanged
```

New dependency: `langgraph`.

`agent.py` public API (what the CLI uses):
- `analizar_texto(texto, *, client=None, model=DEFAULT_MODEL) -> InformeArras`
- `analizar_pdf(path, *, client=None, model=DEFAULT_MODEL) -> InformeArras`

## Graph

Typed state:

```python
class EstadoAnalisis(BaseModel):
    texto_contrato: str
    analisis: AnalisisArras | None = None
    riesgos_regla: list[Riesgo] = []
    riesgos_llm: list[Riesgo] = []
    informe: InformeArras | None = None
```

Flow (linear, 3 nodes, 2 LLM calls):

```
texto ─▶ [extraer] ─▶ [detectar_riesgos] ─▶ [componer_informe] ─▶ InformeArras
          LLM #1         rules + LLM #2         deterministic (0 LLM)
```

- **`extraer`** → `{"analisis": analyzer.analyze_text(estado.texto_contrato, ...)}`.
- **`detectar_riesgos`** → `{"riesgos_regla": riesgos.detectar_por_reglas(analisis),
  "riesgos_llm": <LLM pass or [] on failure>}`. The two sources are kept separate until
  composition. The LLM pass is instructed to catch nuance + `reparto_gastos_ambiguo` and
  NOT to repeat the obvious rule-based findings.
- **`componer_informe`** → merges the two lists, **dedups only the fixed rule
  categories**: if the LLM emits a finding whose `categoria` is one of the five rule
  categories that a `regla` finding already covers, the `regla` finding wins and the LLM
  duplicate is dropped. `categoria == otro` (and any rule category not produced by a rule
  this run) is never deduped — multiple `otro` findings all pass through. Then computes
  `nivel_riesgo_global` and builds `InformeArras`. Pure function, no LLM.

## Deterministic detectors and default severities (`riesgos.py`)

| Categoría | Condition on `AnalisisArras` | Severidad |
| --- | --- | --- |
| `tipo_ambiguo` | `tipo_arras == no_especificado` → alta; a type given but `confianza_tipo < 0.6` → media | alta / media |
| `falta_financiacion` | `tiene_clausula_financiacion is False` | **alta** |
| `fechas_mal_definidas` | no `fecha_limite_escritura` **and** no `plazo_dias` | media |
| `inmueble_mal_identificado` | no `referencia_catastral` (mention if `cargas` also absent) | media |
| `reparto_gastos_ambiguo` | LLM-only (not in the schema today) | baja |

`nivel_riesgo_global`: `alto` if any `alta`; else `medio` if any `media`; else `bajo`.
(Max severity, no accumulation — approved as simple and predictable.)

Each deterministic `Riesgo` carries a fixed, Spanish `descripcion` and `recomendacion`
template and `fuente="regla"`.

## CLI

- `arras analyze <pdf>` now yields `InformeArras`.
- Human render = the existing extraction table **+** a coloured
  `Nivel de riesgo: ALTO/MEDIO/BAJO` banner **+** a "Riesgos detectados" section
  (one row per risk: severidad · categoría · descripción · recomendación).
- `--json` dumps the full `InformeArras`.
- **Intentional breaking change:** JSON is now wrapped
  (`{analisis, riesgos, nivel_riesgo_global}`). Acceptable at 0.x; documented in README.
  No compatibility flag (YAGNI).
- Error handling keeps the existing exit codes (2 PDF, 3 analysis, 1 unexpected).

## Error handling

- PDF / extraction errors propagate as in Sprint 1 (no extraction → no report).
- The `detectar_riesgos` node catches exceptions from the LLM pass, logs a warning, and
  returns `riesgos_llm=[]`. The report is still produced from the deterministic rules.
- Graph invocation is wrapped in `agent.py`; the CLI's `try/except` and exit codes are
  preserved.

## Testing

- **Unit (offline, no API):**
  - `riesgos.py` detectors — table-driven, one case per condition, on hand-built
    `AnalisisArras` objects.
  - Severity aggregation (`nivel_riesgo_global`) and dedup in `componer_informe`.
  - Agent nodes with `analyzer.analyze_text` and the LLM risk pass mocked.
  - Graph-wiring test: invoking the compiled graph with both LLM calls mocked yields a
    valid `InformeArras`.
  - Graceful-degradation test: LLM pass raises → report still built from rule risks.
- **Integration (real API, `-m integration`, skipped without a key):**
  - `arras_confirmatorias_problematic` → contains `falta_financiacion` (alta),
    `nivel_riesgo_global == alto`.
  - `arras_penitenciales_clean` → `nivel_riesgo_global == bajo`.
  - `arras_ambiguas` → contains `tipo_ambiguo` (alta) and `falta_financiacion`.
- `scripts/smoke_test.py` extended to check risks and global level across the 3 fixtures.
- Existing fixtures cover all cases; no new fixtures needed.

## Docs

- `ARCHITECTURE.md`: add a "Sprint 2" section (LangGraph choice, direct client in nodes,
  hybrid rules+LLM rationale, typed state, graceful degradation).
- `README.md`: update the "How it works" diagram, tick Sprint 2 in the roadmap, refresh the
  demo to show the risk section.

## Success criteria

- `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` all pass.
- The three integration assertions above hold against the real API.
- The single-call analyzer path (`analyzer.analyze_text`) remains intact and used by the
  `extraer` node — Sprint 1 behaviour is preserved inside the new graph.
