# Sprint 4 — Evals: ground-truth dataset + hybrid metrics & LLM-as-judge

**Status:** approved (design)
**Date:** 2026-07-13
**Depends on:** Sprint 3 (LangGraph agent + RAG producing `InformeArras`)

## Goal

Measure the quality of the analysis pipeline against a labeled dataset. Two
complementary methods, matching the project's philosophy:

1. **Deterministic metrics** for the objective outputs — arras-type accuracy (+
   confidence appropriateness), field extraction accuracy, and risk-detection
   precision/recall/F1 — computed by pure comparison against ground truth.
2. **LLM-as-judge** for the subjective text — faithfulness of the type
   justification and quality of the risk recommendations — scored by an
   **independent** Claude model with an evidence-based rubric.

The harness is a developer/CI on-demand tool: it runs the real pipeline over the
dataset, scores it, and produces a report (human summary + JSON), with optional
`--fail-under` thresholds. It is NOT wired into the default push CI (API cost +
judge non-determinism would make that expensive and flaky).

### Non-goals (deferred)

- Result caching / incremental re-runs (noted as future; YAGNI for Sprint 4).
- Wiring evals into the default CI on every push.
- Prompt A/B experiments (the harness enables them later; not run here).
- Web/CLI packaging (Sprint 5), MCP (Sprint 6).

## Scope of what is judged (framing)

The **LLM-judge checks faithfulness/non-hallucination and pertinence** — that what
the model *says* is grounded in the contract — NOT absolute legal correctness.
Legal correctness of the classification and the flagged risks is covered by the
**deterministic** metrics against the by-construction ground truth. This keeps the
judge's job verifiable (cite the contract span) and avoids the judge re-litigating
doctrine.

## Dataset & ground truth

- **Location/format:** `data/evals/casos.yaml` — a single file, a list of cases
  (readable/reviewable, consistent with `data/kb/`). Loaded into typed Pydantic
  models (`CasoEval`, `GroundTruth`, both `extra="forbid"`).
- **Eval over TEXT** (`analizar_texto`), not PDF — isolates analysis quality (PDF
  parsing is deterministic and separately tested), faster, no PDF generation.
- **By-construction labels:** each synthetic contract is authored together with its
  objective ground truth, so labels are reliable.
- **Subjective outputs have no gold string** — `justificacion_tipo` and
  `recomendacion`s are judged by the LLM against the contract, not string-matched.

`CasoEval`: `id: str`, `texto: str`, `ground_truth: GroundTruth`.
`GroundTruth` fields:
- `tipo_arras: TipoArras`
- `confianza_min: float | None`, `confianza_max: float | None` (expected confidence band)
- `tiene_clausula_financiacion: bool`
- `precio_total: float | None`, `importe_arras: float | None`
- `fecha_limite_presente: bool`, `referencia_catastral_presente: bool`
- `riesgos_esperados: list[CategoriaRiesgo]` (categories that SHOULD be flagged)
- `nivel_riesgo_global: NivelRiesgo`

**Coverage (~12-15 cases):** all three types incl. an explicit **penales** (cites
1152/1153); clean vs problematic; every risk category represented
(`falta_financiacion`, `fechas_mal_definidas`, `inmueble_mal_identificado`,
`reparto_gastos_ambiguo`, `tipo_ambiguo`); edge/adversarial cases (mentions "arras"
but is confirmatoria-by-señal; a minimal contract; a flawless penitenciales with no
risks). The three existing fixtures are reused as cases.

## Metrics (deterministic — pure, no API for scoring)

`metrics.py` — pure functions from `(InformeArras, GroundTruth)` (and aggregations
over per-case records):
- **Type classification:** exact-match accuracy of `tipo_arras` + a confusion
  matrix; **confidence appropriateness** = fraction of cases whose `confianza_tipo`
  falls in the expected `[confianza_min, confianza_max]` band (when specified).
- **Field extraction:** per-field accuracy — `precio_total`/`importe_arras` (numeric
  match within a small relative tolerance), `tiene_clausula_financiacion` (bool),
  presence of `referencia_catastral`, presence of a deadline (`fecha_limite_escritura`
  or `plazo_dias`).
- **Risk detection:** precision / recall / F1 of detected risk categories vs
  `riesgos_esperados` (micro and macro), plus `nivel_riesgo_global` accuracy.

## LLM-as-judge (subjective — independent model)

`judge.py`:
- **Justification faithfulness:** given the contract text + detected `tipo_arras` +
  `justificacion_tipo`, the judge returns structured output
  `VeredictoFidelidad { veredicto: Literal["fiel","parcial","no_fiel"], score: int (1-5),
  evidencia: str (contract span), razonamiento: str }`. Penalizes unsupported
  claims / hallucination.
- **Recommendation quality:** given the contract + the flagged risks + their
  recommendations, the judge returns `VeredictoRecomendacion { score: int (1-5),
  razonamiento: str }` on correctness/actionability/pertinence.
- **Evidence-based rubric:** the judge must cite the contract span backing each
  verdict (English instructions, Spanish domain/reasoning, per project convention).
- **Independence:** `judge_model` from `ARRAS_JUDGE_MODEL` (default
  `claude-sonnet-5`), distinct from the analyzer's `ARRAS_MODEL` (default
  `claude-opus-4-8`). The runner logs a WARNING if `judge_model == analyzer_model`.
- **Aggregation:** mean scores + verdict distribution.

Judge calls use the same `client.messages.parse(output_format=...)` structured path
as the rest of the codebase.

## Harness architecture

```
src/arras_ai/evals/
  dataset.py   # CasoEval + GroundTruth; load_casos(path) -> list[CasoEval]
  metrics.py   # pure deterministic scoring + aggregation
  judge.py     # LLM-as-judge verdicts (independent model)
  runner.py    # orchestrate: analizar_texto per caso -> metrics + judge -> EvalReport
  report.py    # human (Rich) summary + JSON dump
data/evals/casos.yaml
scripts/run_evals.py   # dev-tool entrypoint
```

**Runner flow** (per case, sequential): `analizar_texto(caso.texto)` → `InformeArras`
(system under test: opus analyzer + real fastembed KB) → deterministic scoring
(pure) → judge (independent model) → per-case record → aggregate → `EvalReport`.
~15 cases × (~2-3 analyzer calls + ~2 judge calls) ≈ 60-75 API calls per run.
Errors on a single case are recorded (the case is marked failed) and do not abort
the whole run.

**`scripts/run_evals.py`** options: `--json <path>` (machine report), `--only <id>`
(single case), `--fail-under <float>` (exit non-zero if any of the three **headline
metrics** falls below the threshold: `tipo_accuracy`, `riesgos_f1_micro`, and
`juez_fidelidad_media` — the mean 1-5 justification-faithfulness score normalized to
0-1; recommendation score is reported but not gated). A human summary always prints.
Reads `ANTHROPIC_API_KEY` from env/.env like the CLI.

**Public API** the entrypoint uses:
- `dataset.load_casos(path: Path) -> list[CasoEval]`
- `runner.run_evals(casos, *, analyzer_client=None, judge_client=None, analyzer_model, judge_model) -> EvalReport`
- `report.render_human(report)` / `report.to_json(report) -> str`

`EvalReport` (Pydantic): overall type accuracy, confusion matrix, confidence-band
rate, per-field accuracy, risk P/R/F1 (micro+macro), nivel accuracy, mean judge
scores + verdict distribution, and per-case records.

## Testing

- **Unit (offline, no API):**
  - `metrics.py`: table-driven over hand-built `InformeArras` + `GroundTruth` — exact
    accuracy, precision/recall/F1 (incl. zero-division edge cases), confidence band,
    field matching with tolerance.
  - `dataset.py`: loads/validates `casos.yaml`; rejects an extra/unknown field.
  - `judge.py`: mocked client returning a `VeredictoFidelidad`/`VeredictoRecomendacion`
    → correct parsing + aggregation; independence warning when models match.
  - `runner.py`: `analizar_texto` and the judge mocked → produces an `EvalReport`;
    `--fail-under` threshold logic (pass and fail); a case that raises is recorded as
    failed without aborting.
  - `report.py`: human render + JSON round-trips.
- **Integration (real, `-m integration`, skipped without a key):** run the harness
  over 1-2 dataset cases with the real analyzer + judge → an `EvalReport` with
  in-range numbers (e.g. type accuracy 1.0 on an unambiguous case; a judge score
  present). The full ~15-case run is the on-demand dev action, not a CI test.

## Docs

- `ARCHITECTURE.md`: a "Sprint 4" section — the hybrid eval methodology
  (deterministic where objective, LLM-judge only for subjective text), why the judge
  is an independent model, the by-construction ground truth, and the on-demand harness.
- `README.md`: tick Sprint 4 in the roadmap; add a short "Evals" section (how to run
  `scripts/run_evals.py`, what it measures, an example report snippet).

## Success criteria

- `ruff` / `ruff format --check` / `mypy --strict` / `pytest` green (offline suite;
  integration skipped without a key). Unit scoring tests are pure and deterministic.
- `uv run python scripts/run_evals.py` over the full dataset produces a coherent
  report; deterministic metrics reproduce exactly on re-run (only judge scores vary).
- The independent-judge default holds and warns on `judge_model == analyzer_model`.

## Future (recorded; not built in Sprint 4)

- Result caching keyed on (case id, model, prompt hash) for fast iteration.
- Prompt/model A/B experiments driven by the harness (e.g. testing the hybrid
  prompt-language decision empirically, as ARCHITECTURE.md anticipated).
- An opt-in CI job that runs evals with `--fail-under` on a schedule.
