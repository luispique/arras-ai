# Sprint 4 — Evals Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure the analysis pipeline against a labeled dataset with hybrid metrics — deterministic scoring for objective outputs and an independent LLM-as-judge for subjective text — via an on-demand harness that emits a report and supports `--fail-under` thresholds.

**Architecture:** A new `src/arras_ai/evals/` package: a typed YAML dataset (`data/evals/casos.yaml`) with by-construction ground truth; pure deterministic `metrics.py`; an independent-model `judge.py`; a `runner.py` that runs `analizar_texto` per case → scores → aggregates into an `EvalReport`; a `report.py` renderer; and a `scripts/run_evals.py` entrypoint. Not wired into default CI.

**Tech Stack:** Python 3.11+, Pydantic v2, Anthropic SDK (`messages.parse`), PyYAML, Rich, pytest, ruff, mypy. No new dependencies.

## Global Constraints

- Python `>=3.11`; `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy` (strict), `uv run pytest` must all pass; line length 100.
- All new Pydantic models set `model_config = ConfigDict(extra="forbid")`.
- Domain text (enum values, YAML content, judge output fields, user-facing text) in Spanish; LLM *instructions* in English.
- Deterministic scoring is **pure** (no API) and reproducible. Unit tests are **offline**: the analyzer and judge are mocked; no real API calls, no model download.
- LLM-as-judge uses an **independent** model: `ARRAS_JUDGE_MODEL` (default `claude-sonnet-5`), distinct from `ARRAS_MODEL` (default `claude-opus-4-8`); the runner logs a WARNING if they are equal.
- Risk P/R/F1 scores only the five named `CategoriaRiesgo` values; `CategoriaRiesgo.otro` is excluded from the detected set (a legitimate extra finding must not count as a false positive).
- `--fail-under` gates exactly three headline metrics: `tipo_accuracy`, `riesgos_f1_micro`, `juez_fidelidad_media` (mean 1-5 faithfulness score ÷ 5).
- No new runtime dependency. Conventional Commits; every commit ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Work on branch `feat/sprint-4-evals` (already checked out).

## File Structure

- `data/evals/casos.yaml` — **create**: the 12-case labeled dataset.
- `src/arras_ai/evals/__init__.py` — **create**.
- `src/arras_ai/evals/dataset.py` — **create**: `GroundTruth`, `CasoEval`, `load_casos`, `DEFAULT_CASOS_PATH`.
- `src/arras_ai/evals/metrics.py` — **create**: pure per-case scoring + aggregation.
- `src/arras_ai/evals/judge.py` — **create**: `VeredictoFidelidad`, `VeredictoRecomendacion`, `juzgar_fidelidad`, `juzgar_recomendaciones`, judge prompts.
- `src/arras_ai/evals/runner.py` — **create**: `EvalReport`, `CasoRegistro`, `run_evals`.
- `src/arras_ai/evals/report.py` — **create**: `render_human`, `to_json`.
- `src/arras_ai/config.py` — **modify**: add `judge_model` field + `DEFAULT_JUDGE_MODEL`.
- `scripts/run_evals.py` — **create**: entrypoint (`--json`, `--only`, `--fail-under`).
- `tests/test_evals_dataset.py`, `test_evals_metrics.py`, `test_evals_judge.py`, `test_evals_runner.py`, `test_evals_report.py` — **create**.
- `tests/test_integration.py` — **modify**: one real harness test over a subset.
- `ARCHITECTURE.md`, `README.md` — **modify**.

---

## Task 1: Dataset — models, loader, and the 12 labeled cases

**Files:** Create `src/arras_ai/evals/__init__.py`, `src/arras_ai/evals/dataset.py`, `data/evals/casos.yaml`, `tests/test_evals_dataset.py`.

**Interfaces:**
- Produces:
  - `GroundTruth(BaseModel)`: `tipo_arras: TipoArras`, `confianza_min: float | None = None`, `confianza_max: float | None = None`, `tiene_clausula_financiacion: bool`, `precio_total: float | None = None`, `importe_arras: float | None = None`, `fecha_limite_presente: bool`, `referencia_catastral_presente: bool`, `riesgos_esperados: list[CategoriaRiesgo] = []`, `nivel_riesgo_global: NivelRiesgo`.
  - `CasoEval(BaseModel)`: `id: str`, `texto: str`, `ground_truth: GroundTruth`.
  - `load_casos(path: Path | None = None) -> list[CasoEval]` (defaults to `DEFAULT_CASOS_PATH`).
  - `DEFAULT_CASOS_PATH: Path` (= repo `data/evals/casos.yaml`).

- [ ] **Step 1: Write the failing test** — create `tests/test_evals_dataset.py`:

```python
"""Tests for the eval dataset loader and the dataset's coverage. No API."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arras_ai.evals.dataset import CasoEval, GroundTruth, load_casos
from arras_ai.models import CategoriaRiesgo, NivelRiesgo, TipoArras


def test_loads_all_cases() -> None:
    casos = load_casos()
    assert len(casos) >= 12
    assert all(isinstance(c, CasoEval) for c in casos)
    assert len({c.id for c in casos}) == len(casos)  # ids unique


def test_dataset_covers_all_types_and_risk_categories() -> None:
    casos = load_casos()
    tipos = {c.ground_truth.tipo_arras for c in casos}
    assert {TipoArras.penitenciales, TipoArras.confirmatorias, TipoArras.penales,
            TipoArras.no_especificado} <= tipos
    esperados = {r for c in casos for r in c.ground_truth.riesgos_esperados}
    assert {CategoriaRiesgo.falta_financiacion, CategoriaRiesgo.fechas_mal_definidas,
            CategoriaRiesgo.inmueble_mal_identificado, CategoriaRiesgo.reparto_gastos_ambiguo,
            CategoriaRiesgo.tipo_ambiguo} <= esperados
    # at least one clean contract (no expected risks)
    assert any(not c.ground_truth.riesgos_esperados for c in casos)


def test_ground_truth_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        GroundTruth.model_validate(
            {"tipo_arras": "penitenciales", "tiene_clausula_financiacion": True,
             "fecha_limite_presente": True, "referencia_catastral_presente": True,
             "nivel_riesgo_global": "bajo", "unexpected": 1}
        )


def test_nivel_is_bajo_when_no_risks() -> None:
    for c in load_casos():
        if not c.ground_truth.riesgos_esperados:
            assert c.ground_truth.nivel_riesgo_global is NivelRiesgo.bajo
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_evals_dataset.py -v` → FAIL (module + data missing).

- [ ] **Step 3: Implement `evals/__init__.py`** (module docstring only) and `evals/dataset.py`:

```python
"""The evaluation dataset: by-construction ground truth for the analysis pipeline."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from arras_ai.models import CategoriaRiesgo, NivelRiesgo, TipoArras

DEFAULT_CASOS_PATH = Path(__file__).resolve().parents[3] / "data" / "evals" / "casos.yaml"


class GroundTruth(BaseModel):
    """Objective, by-construction labels for one contract."""

    model_config = ConfigDict(extra="forbid")

    tipo_arras: TipoArras
    confianza_min: float | None = None
    confianza_max: float | None = None
    tiene_clausula_financiacion: bool
    precio_total: float | None = None
    importe_arras: float | None = None
    fecha_limite_presente: bool = Field(
        description="True si fija fecha límite O plazo en días para la escritura"
    )
    referencia_catastral_presente: bool
    riesgos_esperados: list[CategoriaRiesgo] = Field(default_factory=list)
    nivel_riesgo_global: NivelRiesgo


class CasoEval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    texto: str
    ground_truth: GroundTruth


def load_casos(path: Path | None = None) -> list[CasoEval]:
    src = path or DEFAULT_CASOS_PATH
    with src.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list of cases in {src}")
    return [CasoEval.model_validate(item) for item in data]
```

- [ ] **Step 4: Create `data/evals/casos.yaml`** — transcribe verbatim (12 cases). Each `texto` uses YAML block scalar `|`.

```yaml
- id: penitenciales_limpio
  texto: |
    CONTRATO DE ARRAS PENITENCIALES. En Madrid, a 15 de marzo de 2025. Dña. María
    Fernández (NIF 12345678Z), vendedora, y D. Javier López (NIF 87654321X), comprador,
    sobre la vivienda en calle Goya 78, 3ºB, 28001 Madrid, referencia catastral
    9872023VH5797S0001WX, libre de cargas, precio 280.000 €. El comprador entrega
    28.000 € en concepto de arras penitenciales conforme al artículo 1454 del Código
    Civil; si desiste el comprador perderá las arras y si desiste la vendedora las
    devolverá duplicadas. La escritura se otorgará antes del 15 de junio de 2025. La
    eficacia se condiciona a la obtención de financiación hipotecaria en 45 días; de
    denegarse, se devolverán las arras. Gastos: notaría al vendedor, inscripción al
    comprador, plusvalía al vendedor.
  ground_truth:
    tipo_arras: penitenciales
    confianza_min: 0.7
    tiene_clausula_financiacion: true
    precio_total: 280000
    importe_arras: 28000
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: []
    nivel_riesgo_global: bajo
- id: confirmatorias_problematico
  texto: |
    CONTRATO PRIVADO DE COMPRAVENTA CON SEÑAL. En Valencia, a 3 de abril de 2025. D.
    Antonio Martínez (DNI 44556677P), vendedor, y Dña. Laura Gómez (DNI 11223344Q),
    compradora, sobre el piso en avenida del Puerto 210, 5º, Valencia. Precio 190.000 €.
    La compradora entrega 10.000 € en concepto de señal y como parte del precio, a
    cuenta del precio total; dicha cantidad confirma el contrato. Las partes se
    comprometen a elevar a escritura pública en el plazo más breve posible, cuando la
    documentación esté en regla. Los gastos se distribuirán conforme a la ley.
  ground_truth:
    tipo_arras: confirmatorias
    tiene_clausula_financiacion: false
    precio_total: 190000
    importe_arras: 10000
    fecha_limite_presente: false
    referencia_catastral_presente: false
    riesgos_esperados: [falta_financiacion, fechas_mal_definidas, inmueble_mal_identificado]
    nivel_riesgo_global: alto
- id: ambiguo
  texto: |
    DOCUMENTO DE ARRAS. En Sevilla, a 20 de febrero de 2025. D. Carlos Ruiz (NIF
    55667788M), parte transmitente, y Dña. Elena Navarro (NIF 99887766L), parte
    adquirente, sobre la vivienda en calle Betis 12, bajo, 41010 Sevilla. Precio
    210.000 €. En garantía del cumplimiento del acuerdo, la parte adquirente entrega
    15.000 € en concepto de arras. Las partes formalizarán la compraventa ante notario
    en el plazo de sesenta (60) días naturales desde la firma. Firmado.
  ground_truth:
    tipo_arras: no_especificado
    confianza_max: 0.6
    tiene_clausula_financiacion: false
    precio_total: 210000
    importe_arras: 15000
    fecha_limite_presente: true
    referencia_catastral_presente: false
    riesgos_esperados: [tipo_ambiguo, falta_financiacion, inmueble_mal_identificado]
    nivel_riesgo_global: alto
- id: penales_explicito
  texto: |
    CONTRATO DE ARRAS PENALES. En Bilbao, a 10 de enero de 2025. D. Ander Solozabal
    (NIF 30111222K), vendedor, y Dña. Nerea Aguirre (NIF 30333444L), compradora, sobre
    la vivienda en calle Gran Vía 5, 3ºA, Bilbao, referencia catastral
    1234567AB1234C0001DE, libre de cargas, por 350.000 €. La compradora entrega
    35.000 € en concepto de arras penales. Conforme a los artículos 1152 y 1153 del
    Código Civil, dicha cantidad operará como cláusula penal en caso de incumplimiento,
    sin que ninguna parte pueda desistir libremente: la parte cumplidora podrá exigir el
    cumplimiento del contrato o la pena. La escritura pública se otorgará antes del 10 de
    abril de 2025. La eficacia queda condicionada a la obtención de financiación
    hipotecaria por la compradora en 30 días; de denegarse, se resolverá con devolución
    de las arras. Gastos: notaría y matriz al vendedor, primera copia e inscripción al
    comprador, plusvalía al vendedor.
  ground_truth:
    tipo_arras: penales
    confianza_min: 0.7
    tiene_clausula_financiacion: true
    precio_total: 350000
    importe_arras: 35000
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: []
    nivel_riesgo_global: bajo
- id: penitenciales_sin_financiacion
  texto: |
    CONTRATO DE ARRAS PENITENCIALES. En Sevilla, a 5 de febrero de 2025. Dña. Carmen
    Ortiz (NIF 28111222M), vendedora, y D. Pablo Ramos (NIF 28333444N), comprador, sobre
    la vivienda en calle Feria 40, 2ºB, Sevilla, referencia catastral
    7654321ZZ7654X0001AB, libre de cargas, precio 220.000 €. El comprador entrega
    22.000 € en concepto de arras penitenciales conforme al artículo 1454 del Código
    Civil: si el comprador desiste perderá las arras; si desiste la vendedora las
    devolverá duplicadas. La escritura se firmará a más tardar el 5 de mayo de 2025. Los
    gastos se distribuirán conforme a la ley.
  ground_truth:
    tipo_arras: penitenciales
    confianza_min: 0.7
    tiene_clausula_financiacion: false
    precio_total: 220000
    importe_arras: 22000
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: [falta_financiacion]
    nivel_riesgo_global: alto
- id: confirmatorias_limpio
  texto: |
    CONTRATO DE COMPRAVENTA CON ARRAS CONFIRMATORIAS. En Zaragoza, a 12 de marzo de
    2025. D. Luis Marín (NIF 25111222P), vendedor, y Dña. Sara Gil (NIF 25333444Q),
    compradora, sobre el piso en paseo Independencia 8, 4ºC, Zaragoza, referencia
    catastral 3456789CD3456E0001FG, libre de cargas, precio 175.000 €. La compradora
    entrega 17.500 € en concepto de arras confirmatorias, como pago a cuenta del precio;
    las partes no podrán desistir y quedan obligadas a otorgar la escritura pública antes
    del 12 de junio de 2025. La eficacia se somete a la condición suspensiva de que la
    compradora obtenga préstamo hipotecario en 45 días. Gastos: notaría y registro por
    mitad, plusvalía municipal al vendedor.
  ground_truth:
    tipo_arras: confirmatorias
    confianza_min: 0.7
    tiene_clausula_financiacion: true
    precio_total: 175000
    importe_arras: 17500
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: []
    nivel_riesgo_global: bajo
- id: reparto_gastos_ambiguo
  texto: |
    CONTRATO DE ARRAS PENITENCIALES. En Málaga, a 20 de marzo de 2025. Dña. Rosa Díaz
    (NIF 26111222R), vendedora, y D. Jorge León (NIF 26333444S), comprador, sobre la
    vivienda en calle Larios 3, 1ºA, Málaga, referencia catastral 9988776YY9988Z0001CD,
    libre de cargas, precio 300.000 €. El comprador entrega 30.000 € en concepto de
    arras penitenciales (art. 1454 CC), con pérdida o devolución duplicada en caso de
    desistimiento. Escritura antes del 20 de junio de 2025. La operación queda
    condicionada a la concesión de hipoteca al comprador en 30 días. Los gastos de la
    operación correrán por cuenta de quien corresponda.
  ground_truth:
    tipo_arras: penitenciales
    confianza_min: 0.7
    tiene_clausula_financiacion: true
    precio_total: 300000
    importe_arras: 30000
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: [reparto_gastos_ambiguo]
    nivel_riesgo_global: bajo
- id: inmueble_sin_catastral
  texto: |
    CONTRATO DE ARRAS PENITENCIALES. En Murcia, a 2 de abril de 2025. D. Tomás Vera
    (NIF 48111222T), vendedor, y Dña. Ana Soler (NIF 48333444V), compradora, sobre la
    vivienda en avenida de la Libertad 22, 5ºD, Murcia, precio 160.000 €. La compradora
    entrega 16.000 € en concepto de arras penitenciales conforme al artículo 1454 del
    Código Civil. La escritura se otorgará antes del 2 de julio de 2025. La eficacia se
    condiciona a la obtención de financiación hipotecaria en 30 días. Gastos: notaría al
    vendedor, registro al comprador, plusvalía al vendedor.
  ground_truth:
    tipo_arras: penitenciales
    confianza_min: 0.7
    tiene_clausula_financiacion: true
    precio_total: 160000
    importe_arras: 16000
    fecha_limite_presente: true
    referencia_catastral_presente: false
    riesgos_esperados: [inmueble_mal_identificado]
    nivel_riesgo_global: medio
- id: fechas_sin_plazo
  texto: |
    CONTRATO DE ARRAS CONFIRMATORIAS. En Valladolid, a 8 de abril de 2025. Dña. Marta
    Cano (NIF 71111222W), vendedora, y D. Iván Prieto (NIF 71333444X), comprador, sobre
    el piso en calle Santiago 15, 2ºA, Valladolid, referencia catastral
    5566778WW5566V0001EF, libre de cargas, precio 140.000 €. El comprador entrega
    14.000 € en concepto de arras confirmatorias, como pago a cuenta del precio; las
    partes quedan obligadas a la compraventa. La eficacia se condiciona a la obtención de
    hipoteca por el comprador en 45 días. Gastos: notaría y registro por mitad, plusvalía
    al vendedor. Las partes firmarán la escritura pública cuando la documentación esté
    lista.
  ground_truth:
    tipo_arras: confirmatorias
    confianza_min: 0.6
    tiene_clausula_financiacion: true
    precio_total: 140000
    importe_arras: 14000
    fecha_limite_presente: false
    referencia_catastral_presente: true
    riesgos_esperados: [fechas_mal_definidas]
    nivel_riesgo_global: medio
- id: adversarial_senal_confirmatoria
  texto: |
    DOCUMENTO PRIVADO DE COMPRAVENTA. En Alicante, a 15 de abril de 2025. D. Raúl Mora
    (NIF 21111222Y), vendedor, y Dña. Lucía Ferrer (NIF 21333444Z), compradora, sobre el
    apartamento en calle San Fernando 9, 3ºB, Alicante, referencia catastral
    2233445UU2233T0001GH, libre de cargas, precio 200.000 €. En este acto la compradora
    entrega 20.000 € en concepto de señal y a cuenta del precio total; dicha entrega
    confirma la compraventa y las partes quedan obligadas a elevarla a escritura pública
    antes del 15 de julio de 2025. El documento no menciona derecho de desistimiento
    alguno.
  ground_truth:
    tipo_arras: confirmatorias
    confianza_min: 0.55
    tiene_clausula_financiacion: false
    precio_total: 200000
    importe_arras: 20000
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: [falta_financiacion]
    nivel_riesgo_global: alto
- id: minimo
  texto: |
    ARRAS. En Toledo, a 1 de mayo de 2025. Vendedor: D. Mario Gómez (NIF 06111222A).
    Comprador: Dña. Elena Ruiz (NIF 06333444B). Vivienda en calle Comercio 4, Toledo.
    Precio: 130.000 euros. Se entregan 13.000 euros en concepto de arras. Firmado por
    ambas partes.
  ground_truth:
    tipo_arras: no_especificado
    confianza_max: 0.6
    tiene_clausula_financiacion: false
    precio_total: 130000
    importe_arras: 13000
    fecha_limite_presente: false
    referencia_catastral_presente: false
    riesgos_esperados: [tipo_ambiguo, falta_financiacion, fechas_mal_definidas, inmueble_mal_identificado]
    nivel_riesgo_global: alto
- id: penitenciales_impecable
  texto: |
    CONTRATO DE ARRAS PENITENCIALES. En Madrid, a 3 de junio de 2025. Dña. Isabel Nieto
    (NIF 51111222C), vendedora, y D. Andrés Vidal (NIF 51333444D), comprador, sobre la
    vivienda en calle Velázquez 30, 6º izq, 28001 Madrid, referencia catastral
    8877665RR8877Q0001IJ, inscrita en el Registro de la Propiedad nº 5 de Madrid, libre
    de cargas y arrendatarios, precio 480.000 €. El comprador entrega 48.000 € en
    concepto de arras penitenciales conforme al artículo 1454 del Código Civil, con
    pérdida o devolución duplicada en caso de desistimiento. La escritura pública se
    otorgará ante notario a más tardar el 3 de septiembre de 2025. La eficacia queda
    sujeta a la condición suspensiva de obtención de financiación hipotecaria por importe
    mínimo de 350.000 € en 45 días; en su defecto, el contrato se resolverá con
    devolución íntegra de las arras. Gastos: escritura y matriz al vendedor, primera
    copia e inscripción al comprador, plusvalía al vendedor.
  ground_truth:
    tipo_arras: penitenciales
    confianza_min: 0.85
    tiene_clausula_financiacion: true
    precio_total: 480000
    importe_arras: 48000
    fecha_limite_presente: true
    referencia_catastral_presente: true
    riesgos_esperados: []
    nivel_riesgo_global: bajo
```

- [ ] **Step 5: Run to verify pass** — `uv run pytest tests/test_evals_dataset.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check .` → PASS/clean.

- [ ] **Step 6: Commit**

```bash
git add src/arras_ai/evals/__init__.py src/arras_ai/evals/dataset.py data/evals/casos.yaml tests/test_evals_dataset.py
git commit -m "feat: eval dataset with by-construction ground truth (12 cases)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Deterministic metrics

**Files:** Create `src/arras_ai/evals/metrics.py`, `tests/test_evals_metrics.py`.

**Interfaces:**
- Consumes: `InformeArras` (from `arras_ai.models`), `GroundTruth` (Task 1), `CategoriaRiesgo`, `NivelRiesgo`.
- Produces:
  - `precision_recall_f1(detectados: set[CategoriaRiesgo], esperados: set[CategoriaRiesgo]) -> tuple[float, float, float]`
  - `ResultadoDeterminista(BaseModel)`: `tipo_ok: bool`, `confianza_ok: bool | None`, `campos: dict[str, bool]`, `riesgos_precision: float`, `riesgos_recall: float`, `riesgos_f1: float`, `nivel_ok: bool`, `detectados: list[CategoriaRiesgo]`, `esperados: list[CategoriaRiesgo]`.
  - `puntuar_caso(informe: InformeArras, gt: GroundTruth) -> ResultadoDeterminista`
  - `AgregadoDeterminista(BaseModel)`: `tipo_accuracy: float`, `confianza_band_rate: float | None`, `campos_accuracy: dict[str, float]`, `riesgos_f1_micro: float`, `riesgos_precision_micro: float`, `riesgos_recall_micro: float`, `riesgos_f1_macro: float`, `nivel_accuracy: float`, `n: int`.
  - `agregar(resultados: list[ResultadoDeterminista]) -> AgregadoDeterminista`
  - constant `TOLERANCIA_IMPORTE = 0.01`

- [ ] **Step 1: Write the failing test** — create `tests/test_evals_metrics.py`:

```python
"""Unit tests for the pure deterministic metrics. No API."""

from __future__ import annotations

import pytest

from arras_ai.evals.dataset import GroundTruth
from arras_ai.evals.metrics import agregar, precision_recall_f1, puntuar_caso
from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    Fechas,
    Fundamento,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    Riesgo,
    Severidad,
    TipoArras,
)


def _riesgo(cat: CategoriaRiesgo, sev: Severidad = Severidad.alta) -> Riesgo:
    return Riesgo(categoria=cat, severidad=sev, descripcion="d", recomendacion="r", fuente="regla")


def _informe(**a: object) -> InformeArras:
    analisis = AnalisisArras(
        tipo_arras=TipoArras.penitenciales, confianza_tipo=0.9, justificacion_tipo="j",
        partes=[], inmueble=Inmueble(referencia_catastral="X"), importes=Importes(),
        fechas=Fechas(fecha_limite_escritura="2025-06-15"), referencias_codigo_civil=[],
        tiene_clausula_financiacion=True, resumen="r",
    ).model_copy(update=a.get("analisis", {}))  # type: ignore[arg-type]
    return InformeArras(
        analisis=analisis,
        riesgos=a.get("riesgos", []),  # type: ignore[arg-type]
        nivel_riesgo_global=a.get("nivel", NivelRiesgo.bajo),  # type: ignore[arg-type]
    )


def test_prf_perfect_and_empty() -> None:
    s = {CategoriaRiesgo.falta_financiacion}
    assert precision_recall_f1(s, s) == (1.0, 1.0, 1.0)
    # nothing expected, nothing detected -> all 1.0 (nothing wrong)
    assert precision_recall_f1(set(), set()) == (1.0, 1.0, 1.0)
    # detected a false positive
    p, r, f = precision_recall_f1({CategoriaRiesgo.fechas_mal_definidas}, s)
    assert p == 0.0 and r == 0.0 and f == 0.0


def test_otro_excluded_from_detected() -> None:
    informe = _informe(
        riesgos=[_riesgo(CategoriaRiesgo.falta_financiacion), _riesgo(CategoriaRiesgo.otro)],
        nivel=NivelRiesgo.alto,
    )
    gt = GroundTruth(
        tipo_arras=TipoArras.penitenciales, tiene_clausula_financiacion=True,
        fecha_limite_presente=True, referencia_catastral_presente=True,
        riesgos_esperados=[CategoriaRiesgo.falta_financiacion], nivel_riesgo_global=NivelRiesgo.alto,
    )
    res = puntuar_caso(informe, gt)
    # 'otro' must not count as a false positive
    assert res.riesgos_precision == 1.0
    assert CategoriaRiesgo.otro not in res.detectados


def test_puntuar_caso_fields_and_confidence() -> None:
    informe = _informe(analisis={"confianza_tipo": 0.5})
    gt = GroundTruth(
        tipo_arras=TipoArras.penitenciales, confianza_max=0.6, tiene_clausula_financiacion=True,
        fecha_limite_presente=True, referencia_catastral_presente=True, nivel_riesgo_global=NivelRiesgo.bajo,
    )
    res = puntuar_caso(informe, gt)
    assert res.tipo_ok is True
    assert res.confianza_ok is True  # 0.5 <= 0.6
    assert res.campos["tiene_clausula_financiacion"] is True
    assert res.campos["referencia_catastral_presente"] is True


def test_agregar_accuracy() -> None:
    gt_ok = GroundTruth(tipo_arras=TipoArras.penitenciales, tiene_clausula_financiacion=True,
                        fecha_limite_presente=True, referencia_catastral_presente=True,
                        nivel_riesgo_global=NivelRiesgo.bajo)
    gt_wrong = gt_ok.model_copy(update={"tipo_arras": TipoArras.confirmatorias})
    res = [puntuar_caso(_informe(), gt_ok), puntuar_caso(_informe(), gt_wrong)]
    agg = agregar(res)
    assert agg.tipo_accuracy == 0.5
    assert agg.n == 2
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_evals_metrics.py -v` → FAIL.

- [ ] **Step 3: Implement `metrics.py`:**

```python
"""Pure deterministic scoring of an InformeArras against ground truth. No API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from arras_ai.evals.dataset import GroundTruth
from arras_ai.models import CategoriaRiesgo, InformeArras

TOLERANCIA_IMPORTE = 0.01


def precision_recall_f1(
    detectados: set[CategoriaRiesgo], esperados: set[CategoriaRiesgo]
) -> tuple[float, float, float]:
    tp = len(detectados & esperados)
    fp = len(detectados - esperados)
    fn = len(esperados - detectados)
    precision = 1.0 if tp + fp == 0 else tp / (tp + fp)
    recall = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
    return precision, recall, f1


class ResultadoDeterminista(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_ok: bool
    confianza_ok: bool | None
    campos: dict[str, bool]
    riesgos_precision: float
    riesgos_recall: float
    riesgos_f1: float
    nivel_ok: bool
    detectados: list[CategoriaRiesgo]
    esperados: list[CategoriaRiesgo]


def _num_ok(actual: float | None, esperado: float | None) -> bool:
    if esperado is None:
        return True
    if actual is None:
        return False
    return abs(actual - esperado) <= abs(esperado) * TOLERANCIA_IMPORTE


def puntuar_caso(informe: InformeArras, gt: GroundTruth) -> ResultadoDeterminista:
    a = informe.analisis
    confianza_ok: bool | None = None
    if gt.confianza_min is not None or gt.confianza_max is not None:
        lo = gt.confianza_min if gt.confianza_min is not None else 0.0
        hi = gt.confianza_max if gt.confianza_max is not None else 1.0
        confianza_ok = lo <= a.confianza_tipo <= hi

    campos = {
        "precio_total": _num_ok(a.importes.precio_total, gt.precio_total),
        "importe_arras": _num_ok(a.importes.importe_arras, gt.importe_arras),
        "tiene_clausula_financiacion": a.tiene_clausula_financiacion
        == gt.tiene_clausula_financiacion,
        "referencia_catastral_presente": (a.inmueble.referencia_catastral is not None)
        == gt.referencia_catastral_presente,
        "fecha_limite_presente": (
            a.fechas.fecha_limite_escritura is not None or a.fechas.plazo_dias is not None
        )
        == gt.fecha_limite_presente,
    }

    detectados = {r.categoria for r in informe.riesgos if r.categoria is not CategoriaRiesgo.otro}
    esperados = set(gt.riesgos_esperados)
    p, r, f = precision_recall_f1(detectados, esperados)

    return ResultadoDeterminista(
        tipo_ok=a.tipo_arras == gt.tipo_arras,
        confianza_ok=confianza_ok,
        campos=campos,
        riesgos_precision=p,
        riesgos_recall=r,
        riesgos_f1=f,
        nivel_ok=informe.nivel_riesgo_global == gt.nivel_riesgo_global,
        detectados=sorted(detectados, key=lambda c: c.value),
        esperados=sorted(esperados, key=lambda c: c.value),
    )


class AgregadoDeterminista(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tipo_accuracy: float
    confianza_band_rate: float | None
    campos_accuracy: dict[str, float]
    riesgos_precision_micro: float
    riesgos_recall_micro: float
    riesgos_f1_micro: float
    riesgos_f1_macro: float
    nivel_accuracy: float
    n: int


def agregar(resultados: list[ResultadoDeterminista]) -> AgregadoDeterminista:
    n = len(resultados)
    if n == 0:
        raise ValueError("No results to aggregate")

    tipo_accuracy = sum(r.tipo_ok for r in resultados) / n
    nivel_accuracy = sum(r.nivel_ok for r in resultados) / n

    conf = [r.confianza_ok for r in resultados if r.confianza_ok is not None]
    confianza_band_rate = (sum(conf) / len(conf)) if conf else None

    campos_keys = resultados[0].campos.keys()
    campos_accuracy = {
        k: sum(r.campos[k] for r in resultados) / n for k in campos_keys
    }

    tp = fp = fn = 0
    for r in resultados:
        det, esp = set(r.detectados), set(r.esperados)
        tp += len(det & esp)
        fp += len(det - esp)
        fn += len(esp - det)
    p_micro = 1.0 if tp + fp == 0 else tp / (tp + fp)
    r_micro = 1.0 if tp + fn == 0 else tp / (tp + fn)
    f_micro = 0.0 if p_micro + r_micro == 0 else 2 * p_micro * r_micro / (p_micro + r_micro)
    f_macro = sum(r.riesgos_f1 for r in resultados) / n

    return AgregadoDeterminista(
        tipo_accuracy=tipo_accuracy,
        confianza_band_rate=confianza_band_rate,
        campos_accuracy=campos_accuracy,
        riesgos_precision_micro=p_micro,
        riesgos_recall_micro=r_micro,
        riesgos_f1_micro=f_micro,
        riesgos_f1_macro=f_macro,
        nivel_accuracy=nivel_accuracy,
        n=n,
    )
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_evals_metrics.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check .` → PASS/clean.

- [ ] **Step 5: Commit**

```bash
git add src/arras_ai/evals/metrics.py tests/test_evals_metrics.py
git commit -m "feat: deterministic eval metrics (type/field accuracy, risk P/R/F1)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: LLM-as-judge (independent model) + config

**Files:** Create `src/arras_ai/evals/judge.py`, `tests/test_evals_judge.py`. Modify `src/arras_ai/config.py`.

**Interfaces:**
- Consumes: `InformeArras`; `anthropic.Anthropic`; `config.DEFAULT_JUDGE_MODEL`.
- Produces:
  - `config.DEFAULT_JUDGE_MODEL = "claude-sonnet-5"`; `Settings.judge_model` (alias `ARRAS_JUDGE_MODEL`).
  - `VeredictoFidelidad(BaseModel)`: `veredicto: Literal["fiel","parcial","no_fiel"]`, `score: int` (1-5), `evidencia: str`, `razonamiento: str`.
  - `VeredictoRecomendacion(BaseModel)`: `score: int` (1-5), `razonamiento: str`.
  - `juzgar_fidelidad(texto: str, informe: InformeArras, *, client: anthropic.Anthropic, model: str = DEFAULT_JUDGE_MODEL) -> VeredictoFidelidad`
  - `juzgar_recomendaciones(texto: str, informe: InformeArras, *, client: anthropic.Anthropic, model: str = DEFAULT_JUDGE_MODEL) -> VeredictoRecomendacion`

- [ ] **Step 1: Add config** — in `src/arras_ai/config.py`, add near `DEFAULT_MODEL`:

```python
DEFAULT_JUDGE_MODEL = "claude-sonnet-5"
```

and a field on `Settings` (alongside the others):

```python
    judge_model: str = Field(default=DEFAULT_JUDGE_MODEL, validation_alias="ARRAS_JUDGE_MODEL")
```

- [ ] **Step 2: Write the failing test** — create `tests/test_evals_judge.py`:

```python
"""Unit tests for the LLM-as-judge with the client mocked. No network."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic

from arras_ai.evals import judge
from arras_ai.evals.judge import VeredictoFidelidad, VeredictoRecomendacion, juzgar_fidelidad
from arras_ai.models import (
    AnalisisArras,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    TipoArras,
)


class _FakeMessages:
    def __init__(self, parsed: object) -> None:
        self._parsed = parsed
        self.last_kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return SimpleNamespace(parsed_output=self._parsed, stop_reason="end_turn")


class _FakeClient:
    def __init__(self, parsed: object) -> None:
        self.messages = _FakeMessages(parsed)


def _informe() -> InformeArras:
    return InformeArras(
        analisis=AnalisisArras(
            tipo_arras=TipoArras.penitenciales, confianza_tipo=0.9,
            justificacion_tipo="Cita el art. 1454 y el derecho de desistimiento.",
            partes=[], inmueble=Inmueble(), importes=Importes(), fechas=Fechas(),
            referencias_codigo_civil=[], tiene_clausula_financiacion=True, resumen="r",
        ),
        riesgos=[], nivel_riesgo_global=NivelRiesgo.bajo,
    )


def test_juzgar_fidelidad_parses_and_passes_model(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    veredicto = VeredictoFidelidad(
        veredicto="fiel", score=5, evidencia="art. 1454", razonamiento="coherente"
    )
    client = _FakeClient(veredicto)
    out = juzgar_fidelidad(
        "texto del contrato", _informe(),
        client=cast(anthropic.Anthropic, client), model="claude-sonnet-5",
    )
    assert out.veredicto == "fiel" and out.score == 5
    assert client.messages.last_kwargs["model"] == "claude-sonnet-5"
    assert client.messages.last_kwargs["output_format"] is VeredictoFidelidad


def test_recomendacion_schema_bounds() -> None:
    import pytest
    from pydantic import ValidationError

    VeredictoRecomendacion(score=3, razonamiento="ok")
    with pytest.raises(ValidationError):
        VeredictoRecomendacion(score=9, razonamiento="fuera de rango")
```

- [ ] **Step 3: Run to verify it fails** — `uv run pytest tests/test_evals_judge.py -v` → FAIL.

- [ ] **Step 4: Implement `judge.py`:**

```python
"""LLM-as-judge for the subjective outputs, run on an independent model.

The judge checks FAITHFULNESS (is what the model said grounded in the contract?)
and pertinence — not absolute legal correctness, which the deterministic metrics
cover. It must cite the contract span backing each verdict.
"""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel, ConfigDict, Field

from arras_ai.config import DEFAULT_JUDGE_MODEL
from arras_ai.models import InformeArras

JUDGE_MAX_TOKENS = 2000

SYSTEM_FIDELIDAD = """\
You are an impartial evaluator of a Spanish earnest-money contract analysis. You are \
NOT re-deciding the law; you check whether the analysis's stated justification for the \
arras type is FAITHFUL to the contract text — i.e. supported by what the document \
actually says, with no invented facts. Base your verdict on evidence: quote the exact \
contract span that supports or contradicts the justification. Score 1 (unfaithful / \
hallucinated) to 5 (fully supported). All output fields in Spanish.
"""

SYSTEM_RECOMENDACIONES = """\
You are an impartial evaluator of the risk recommendations in a Spanish earnest-money \
contract analysis. Judge whether each recommendation is correct, actionable, and \
pertinent to the problem it addresses, given the contract. Do not reward generic or \
irrelevant advice. Score 1 (poor) to 5 (excellent). All output fields in Spanish.
"""


class VeredictoFidelidad(BaseModel):
    model_config = ConfigDict(extra="forbid")

    veredicto: Literal["fiel", "parcial", "no_fiel"] = Field(
        description="Si la justificación está sustentada en el contrato"
    )
    score: int = Field(ge=1, le=5, description="1 (no fiel) a 5 (totalmente sustentada)")
    evidencia: str = Field(description="Fragmento del contrato que sustenta o contradice")
    razonamiento: str = Field(description="Explicación breve en español")


class VeredictoRecomendacion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5, description="1 (pobre) a 5 (excelente)")
    razonamiento: str = Field(description="Explicación breve en español")


def _user_fidelidad(texto: str, informe: InformeArras) -> str:
    a = informe.analisis
    return (
        f"Contrato:\n--- INICIO ---\n{texto.strip()}\n--- FIN ---\n\n"
        f"Tipo de arras detectado: {a.tipo_arras.value}\n"
        f"Justificación a evaluar:\n{a.justificacion_tipo}"
    )


def _user_recomendaciones(texto: str, informe: InformeArras) -> str:
    riesgos = "\n".join(
        f"- [{r.severidad.value}] {r.categoria.value}: {r.descripcion} -> {r.recomendacion}"
        for r in informe.riesgos
    ) or "(sin riesgos detectados)"
    return (
        f"Contrato:\n--- INICIO ---\n{texto.strip()}\n--- FIN ---\n\n"
        f"Riesgos y recomendaciones a evaluar:\n{riesgos}"
    )


def juzgar_fidelidad(
    texto: str,
    informe: InformeArras,
    *,
    client: anthropic.Anthropic,
    model: str = DEFAULT_JUDGE_MODEL,
) -> VeredictoFidelidad:
    response = client.messages.parse(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=SYSTEM_FIDELIDAD,
        messages=[{"role": "user", "content": _user_fidelidad(texto, informe)}],
        output_format=VeredictoFidelidad,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"Judge returned no verdict (stop_reason={response.stop_reason})")
    return parsed


def juzgar_recomendaciones(
    texto: str,
    informe: InformeArras,
    *,
    client: anthropic.Anthropic,
    model: str = DEFAULT_JUDGE_MODEL,
) -> VeredictoRecomendacion:
    response = client.messages.parse(
        model=model,
        max_tokens=JUDGE_MAX_TOKENS,
        system=SYSTEM_RECOMENDACIONES,
        messages=[{"role": "user", "content": _user_recomendaciones(texto, informe)}],
        output_format=VeredictoRecomendacion,
    )
    parsed = response.parsed_output
    if parsed is None:
        raise RuntimeError(f"Judge returned no verdict (stop_reason={response.stop_reason})")
    return parsed
```

- [ ] **Step 5: Run to verify pass** — `uv run pytest tests/test_evals_judge.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check .` → PASS/clean.

- [ ] **Step 6: Commit**

```bash
git add src/arras_ai/config.py src/arras_ai/evals/judge.py tests/test_evals_judge.py
git commit -m "feat: independent LLM-as-judge for justification faithfulness and recommendations" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Runner + EvalReport

**Files:** Create `src/arras_ai/evals/runner.py`, `tests/test_evals_runner.py`.

**Interfaces:**
- Consumes: `dataset.CasoEval`; `metrics.puntuar_caso`/`agregar`/`ResultadoDeterminista`/`AgregadoDeterminista`; `judge.juzgar_fidelidad`/`juzgar_recomendaciones`/`VeredictoFidelidad`/`VeredictoRecomendacion`; `agent.analizar_texto`; `config` models.
- Produces:
  - `CasoRegistro(BaseModel)`: `id: str`, `determinista: ResultadoDeterminista | None`, `fidelidad: VeredictoFidelidad | None`, `recomendacion: VeredictoRecomendacion | None`, `error: str | None`.
  - `EvalReport(BaseModel)`: `agregado: AgregadoDeterminista`, `fidelidad_media: float | None`, `recomendacion_media: float | None`, `distribucion_veredictos: dict[str, int]`, `registros: list[CasoRegistro]`, `analyzer_model: str`, `judge_model: str`, `n_errores: int`.
  - `run_evals(casos, *, analyzer_client=None, judge_client=None, analyzer_model=DEFAULT_MODEL, judge_model=DEFAULT_JUDGE_MODEL, kb=None) -> EvalReport`
  - `metricas_cabecera(report: EvalReport) -> dict[str, float]` → `{"tipo_accuracy", "riesgos_f1_micro", "juez_fidelidad_media"}` (faithfulness normalized 0-1; 0.0 if no verdicts).

- [ ] **Step 1: Write the failing test** — create `tests/test_evals_runner.py`:

```python
"""Unit tests for the eval runner with analyzer + judge mocked. No API."""

from __future__ import annotations

import pytest

from arras_ai.evals import judge, runner
from arras_ai.evals.dataset import CasoEval, GroundTruth
from arras_ai.evals.judge import VeredictoFidelidad, VeredictoRecomendacion
from arras_ai.evals.runner import metricas_cabecera, run_evals
from arras_ai.models import (
    AnalisisArras, Fechas, Importes, InformeArras, Inmueble, NivelRiesgo, TipoArras,
)


def _caso(cid: str, tipo: TipoArras) -> CasoEval:
    return CasoEval(
        id=cid, texto="texto",
        ground_truth=GroundTruth(
            tipo_arras=tipo, tiene_clausula_financiacion=True,
            fecha_limite_presente=True, referencia_catastral_presente=True,
            nivel_riesgo_global=NivelRiesgo.bajo,
        ),
    )


def _informe(tipo: TipoArras) -> InformeArras:
    return InformeArras(
        analisis=AnalisisArras(
            tipo_arras=tipo, confianza_tipo=0.9, justificacion_tipo="j", partes=[],
            inmueble=Inmueble(referencia_catastral="X"), importes=Importes(),
            fechas=Fechas(fecha_limite_escritura="2025-06-15"), referencias_codigo_civil=[],
            tiene_clausula_financiacion=True, resumen="r",
        ),
        riesgos=[], nivel_riesgo_global=NivelRiesgo.bajo,
    )


def _patch(monkeypatch: pytest.MonkeyPatch, *, fail_id: str | None = None) -> None:
    def fake_analizar(texto: str, **kw: object) -> InformeArras:
        return _informe(TipoArras.penitenciales)

    monkeypatch.setattr(runner, "analizar_texto", fake_analizar)
    monkeypatch.setattr(
        runner, "juzgar_fidelidad",
        lambda *a, **k: VeredictoFidelidad(veredicto="fiel", score=4, evidencia="e", razonamiento="r"),
    )
    monkeypatch.setattr(
        runner, "juzgar_recomendaciones",
        lambda *a, **k: VeredictoRecomendacion(score=4, razonamiento="r"),
    )


def test_run_evals_produces_report(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch)
    casos = [_caso("a", TipoArras.penitenciales), _caso("b", TipoArras.confirmatorias)]
    report = run_evals(casos, analyzer_client=object(), judge_client=object())  # type: ignore[arg-type]
    assert report.agregado.n == 2
    assert report.agregado.tipo_accuracy == 0.5  # 'b' expected confirmatorias, got penitenciales
    assert report.fidelidad_media == 4.0
    assert report.n_errores == 0
    head = metricas_cabecera(report)
    assert head["juez_fidelidad_media"] == pytest.approx(0.8)  # 4/5


def test_run_evals_records_case_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(texto: str, **kw: object) -> InformeArras:
        raise RuntimeError("analyzer down")

    monkeypatch.setattr(runner, "analizar_texto", boom)
    report = run_evals([_caso("a", TipoArras.penitenciales)],
                       analyzer_client=object(), judge_client=object())  # type: ignore[arg-type]
    assert report.n_errores == 1
    assert report.registros[0].error is not None
    assert report.agregado.n == 0 or report.registros[0].determinista is None


def test_warns_when_judge_equals_analyzer(monkeypatch: pytest.MonkeyPatch, caplog) -> None:  # type: ignore[no-untyped-def]
    _patch(monkeypatch)
    import logging

    with caplog.at_level(logging.WARNING):
        run_evals([_caso("a", TipoArras.penitenciales)], analyzer_client=object(),  # type: ignore[arg-type]
                  judge_client=object(), analyzer_model="m", judge_model="m")
    assert any("judge" in r.message.lower() for r in caplog.records)
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_evals_runner.py -v` → FAIL.

- [ ] **Step 3: Implement `runner.py`:**

```python
"""Orchestrate an eval run: analyze each case, score it, judge it, aggregate."""

from __future__ import annotations

import logging

import anthropic
from pydantic import BaseModel, ConfigDict

from arras_ai.agent import analizar_texto
from arras_ai.config import DEFAULT_JUDGE_MODEL, DEFAULT_MODEL
from arras_ai.evals.dataset import CasoEval
from arras_ai.evals.judge import (
    VeredictoFidelidad,
    VeredictoRecomendacion,
    juzgar_fidelidad,
    juzgar_recomendaciones,
)
from arras_ai.evals.metrics import (
    AgregadoDeterminista,
    ResultadoDeterminista,
    agregar,
    puntuar_caso,
)
from arras_ai.rag.knowledge_base import KnowledgeBase

logger = logging.getLogger("arras_ai.evals")


class CasoRegistro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    determinista: ResultadoDeterminista | None = None
    fidelidad: VeredictoFidelidad | None = None
    recomendacion: VeredictoRecomendacion | None = None
    error: str | None = None


class EvalReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agregado: AgregadoDeterminista
    fidelidad_media: float | None
    recomendacion_media: float | None
    distribucion_veredictos: dict[str, int]
    registros: list[CasoRegistro]
    analyzer_model: str
    judge_model: str
    n_errores: int


def run_evals(
    casos: list[CasoEval],
    *,
    analyzer_client: anthropic.Anthropic | None = None,
    judge_client: anthropic.Anthropic | None = None,
    analyzer_model: str = DEFAULT_MODEL,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    kb: KnowledgeBase | None = None,
) -> EvalReport:
    if judge_model == analyzer_model:
        logger.warning(
            "judge_model == analyzer_model (%s): self-evaluation bias; "
            "set ARRAS_JUDGE_MODEL to a different model",
            judge_model,
        )

    registros: list[CasoRegistro] = []
    for caso in casos:
        try:
            informe = analizar_texto(
                caso.texto, client=analyzer_client, model=analyzer_model, kb=kb
            )
            registros.append(
                CasoRegistro(
                    id=caso.id,
                    determinista=puntuar_caso(informe, caso.ground_truth),
                    fidelidad=juzgar_fidelidad(
                        caso.texto, informe, client=judge_client, model=judge_model
                    ),
                    recomendacion=juzgar_recomendaciones(
                        caso.texto, informe, client=judge_client, model=judge_model
                    ),
                )
            )
        except Exception as exc:  # noqa: BLE001 - one bad case must not abort the run
            logger.warning("case %s failed: %s", caso.id, exc)
            registros.append(CasoRegistro(id=caso.id, error=str(exc)))

    deterministas = [r.determinista for r in registros if r.determinista is not None]
    agregado = (
        agregar(deterministas)
        if deterministas
        else AgregadoDeterminista(
            tipo_accuracy=0.0, confianza_band_rate=None, campos_accuracy={},
            riesgos_precision_micro=0.0, riesgos_recall_micro=0.0, riesgos_f1_micro=0.0,
            riesgos_f1_macro=0.0, nivel_accuracy=0.0, n=0,
        )
    )

    fidelidades = [r.fidelidad for r in registros if r.fidelidad is not None]
    recomendaciones = [r.recomendacion for r in registros if r.recomendacion is not None]
    fidelidad_media = (
        sum(f.score for f in fidelidades) / len(fidelidades) if fidelidades else None
    )
    recomendacion_media = (
        sum(r.score for r in recomendaciones) / len(recomendaciones) if recomendaciones else None
    )
    distribucion: dict[str, int] = {}
    for f in fidelidades:
        distribucion[f.veredicto] = distribucion.get(f.veredicto, 0) + 1

    return EvalReport(
        agregado=agregado,
        fidelidad_media=fidelidad_media,
        recomendacion_media=recomendacion_media,
        distribucion_veredictos=distribucion,
        registros=registros,
        analyzer_model=analyzer_model,
        judge_model=judge_model,
        n_errores=sum(1 for r in registros if r.error is not None),
    )


def metricas_cabecera(report: EvalReport) -> dict[str, float]:
    return {
        "tipo_accuracy": report.agregado.tipo_accuracy,
        "riesgos_f1_micro": report.agregado.riesgos_f1_micro,
        "juez_fidelidad_media": (report.fidelidad_media / 5.0) if report.fidelidad_media else 0.0,
    }
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_evals_runner.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check .` → PASS/clean.

- [ ] **Step 5: Commit**

```bash
git add src/arras_ai/evals/runner.py tests/test_evals_runner.py
git commit -m "feat: eval runner producing an EvalReport with graceful per-case errors" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: Report rendering (human + JSON)

**Files:** Create `src/arras_ai/evals/report.py`, `tests/test_evals_report.py`.

**Interfaces:**
- Consumes: `runner.EvalReport`.
- Produces: `render_human(report: EvalReport, *, console: rich.console.Console | None = None) -> None`; `to_json(report: EvalReport) -> str`.

- [ ] **Step 1: Write the failing test** — create `tests/test_evals_report.py`:

```python
"""Unit tests for eval report rendering. No API."""

from __future__ import annotations

import json

from rich.console import Console

from arras_ai.evals.metrics import AgregadoDeterminista
from arras_ai.evals.report import render_human, to_json
from arras_ai.evals.runner import CasoRegistro, EvalReport


def _report() -> EvalReport:
    return EvalReport(
        agregado=AgregadoDeterminista(
            tipo_accuracy=0.9, confianza_band_rate=0.8, campos_accuracy={"precio_total": 1.0},
            riesgos_precision_micro=0.85, riesgos_recall_micro=0.8, riesgos_f1_micro=0.82,
            riesgos_f1_macro=0.8, nivel_accuracy=0.9, n=10,
        ),
        fidelidad_media=4.2, recomendacion_media=4.0,
        distribucion_veredictos={"fiel": 8, "parcial": 2},
        registros=[CasoRegistro(id="a")], analyzer_model="claude-opus-4-8",
        judge_model="claude-sonnet-5", n_errores=0,
    )


def test_to_json_roundtrips() -> None:
    payload = json.loads(to_json(_report()))
    assert payload["agregado"]["tipo_accuracy"] == 0.9
    assert payload["judge_model"] == "claude-sonnet-5"


def test_render_human_writes_summary() -> None:
    console = Console(record=True, width=100)
    render_human(_report(), console=console)
    text = console.export_text()
    assert "tipo_accuracy" in text or "Tipo" in text
    assert "claude-sonnet-5" in text
```

- [ ] **Step 2: Run to verify it fails** — `uv run pytest tests/test_evals_report.py -v` → FAIL.

- [ ] **Step 3: Implement `report.py`:**

```python
"""Render an EvalReport as a human summary (Rich) or JSON."""

from __future__ import annotations

from rich.console import Console
from rich.table import Table

from arras_ai.evals.runner import EvalReport


def to_json(report: EvalReport) -> str:
    return report.model_dump_json(indent=2)


def render_human(report: EvalReport, *, console: Console | None = None) -> None:
    console = console or Console()
    agg = report.agregado

    tabla = Table(title="Evals — métricas deterministas", show_header=True, header_style="bold")
    tabla.add_column("Métrica")
    tabla.add_column("Valor", justify="right")
    tabla.add_row("tipo_accuracy", f"{agg.tipo_accuracy:.2%}")
    if agg.confianza_band_rate is not None:
        tabla.add_row("confianza_band_rate", f"{agg.confianza_band_rate:.2%}")
    tabla.add_row("riesgos_precision_micro", f"{agg.riesgos_precision_micro:.2%}")
    tabla.add_row("riesgos_recall_micro", f"{agg.riesgos_recall_micro:.2%}")
    tabla.add_row("riesgos_f1_micro", f"{agg.riesgos_f1_micro:.2%}")
    tabla.add_row("riesgos_f1_macro", f"{agg.riesgos_f1_macro:.2%}")
    tabla.add_row("nivel_accuracy", f"{agg.nivel_accuracy:.2%}")
    for campo, acc in agg.campos_accuracy.items():
        tabla.add_row(f"campo:{campo}", f"{acc:.2%}")
    console.print(tabla)

    juez = Table(title="Evals — LLM-as-judge", show_header=True, header_style="bold")
    juez.add_column("Métrica")
    juez.add_column("Valor", justify="right")
    juez.add_row("fidelidad_media (1-5)", "—" if report.fidelidad_media is None else f"{report.fidelidad_media:.2f}")
    juez.add_row(
        "recomendacion_media (1-5)",
        "—" if report.recomendacion_media is None else f"{report.recomendacion_media:.2f}",
    )
    juez.add_row("veredictos", str(report.distribucion_veredictos))
    console.print(juez)

    console.print(
        f"[dim]casos: {agg.n} · errores: {report.n_errores} · "
        f"analizador: {report.analyzer_model} · juez: {report.judge_model}[/dim]"
    )
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_evals_report.py -v && uv run mypy && uv run ruff check . && uv run ruff format --check .` → PASS/clean.

- [ ] **Step 5: Commit**

```bash
git add src/arras_ai/evals/report.py tests/test_evals_report.py
git commit -m "feat: eval report rendering (Rich summary + JSON)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: `run_evals.py` entrypoint

**Files:** Create `scripts/run_evals.py`.

**Interfaces:** Consumes `dataset.load_casos`, `runner.run_evals`/`metricas_cabecera`, `report.render_human`/`to_json`, `config.load_settings`, `analyzer._build_client`.

- [ ] **Step 1: Implement `scripts/run_evals.py`** (this is a thin dev-tool entrypoint; it is exercised by the Task 7 integration run and by `--help`, so it carries no unit test of its own):

```python
"""Run the eval harness over the dataset and print/emit a report.

    uv run python scripts/run_evals.py
    uv run python scripts/run_evals.py --only minimo
    uv run python scripts/run_evals.py --json report.json --fail-under 0.7
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from arras_ai.analyzer import _build_client
from arras_ai.config import load_settings
from arras_ai.evals.dataset import load_casos
from arras_ai.evals.report import render_human, to_json
from arras_ai.evals.runner import metricas_cabecera, run_evals


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the arras-ai eval harness.")
    parser.add_argument("--json", type=Path, default=None, help="Write the JSON report here.")
    parser.add_argument("--only", default=None, help="Run only the case with this id.")
    parser.add_argument(
        "--fail-under", type=float, default=None,
        help="Exit non-zero if any headline metric is below this (0-1).",
    )
    args = parser.parse_args()

    settings = load_settings()
    casos = load_casos()
    if args.only:
        casos = [c for c in casos if c.id == args.only]
        if not casos:
            print(f"No case with id {args.only!r}", file=sys.stderr)
            return 2

    client = _build_client(settings.anthropic_api_key)
    report = run_evals(
        casos,
        analyzer_client=client,
        judge_client=client,
        analyzer_model=settings.model,
        judge_model=settings.judge_model,
    )

    render_human(report)
    if args.json:
        args.json.write_text(to_json(report), encoding="utf-8")
        print(f"\nJSON report written to {args.json}")

    if args.fail_under is not None:
        head = metricas_cabecera(report)
        bajos = {k: v for k, v in head.items() if v < args.fail_under}
        if bajos:
            print(f"\nFAIL: below --fail-under={args.fail_under}: {bajos}", file=sys.stderr)
            return 1
        print(f"\nPASS: all headline metrics >= {args.fail_under}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Verify it imports and parses args (offline)**

Run: `uv run python scripts/run_evals.py --help`
Expected: prints usage with `--json`, `--only`, `--fail-under`; exit 0.
Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add scripts/run_evals.py
git commit -m "feat: run_evals entrypoint with --json/--only/--fail-under" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Integration test + documentation

**Files:** Modify `tests/test_integration.py`, `ARCHITECTURE.md`, `README.md`.

- [ ] **Step 1: Add a real-harness integration test** — append to `tests/test_integration.py` (inherits the module `pytestmark` skip gate):

```python
def test_eval_harness_runs_on_a_case() -> None:
    from arras_ai.config import load_settings
    from arras_ai.evals.dataset import load_casos
    from arras_ai.evals.runner import run_evals

    settings = load_settings()
    caso = next(c for c in load_casos() if c.id == "penitenciales_impecable")
    report = run_evals(
        [caso],
        analyzer_model=settings.model,
        judge_model=settings.judge_model,
    )
    assert report.agregado.n == 1
    assert report.n_errores == 0
    # An unambiguous penitenciales contract must classify correctly.
    assert report.agregado.tipo_accuracy == 1.0
    assert report.fidelidad_media is not None and report.fidelidad_media >= 3
```

Note: this needs both an API key (Claude) and a first-run fastembed download (via the analyzer's KB build); it is gated by the module `skipif(not ANTHROPIC_API_KEY)`.

- [ ] **Step 2: Verify offline suite still green** — `uv run pytest && uv run mypy && uv run ruff check . && uv run ruff format --check .` → all pass, the new test SKIPPED without a key.

- [ ] **Step 3: Document in `ARCHITECTURE.md`** — add a "Sprint 4" section after the Sprint 3 section: the hybrid eval methodology (deterministic scoring for objective outputs; LLM-as-judge only for subjective faithfulness/pertinence — not re-deciding the law); why the judge is an **independent** model (self-evaluation bias) with the equality warning; by-construction ground truth in `data/evals/casos.yaml`; and the on-demand harness (`scripts/run_evals.py`) that is deliberately NOT in the default CI (API cost + judge non-determinism). ~250 words, matching the file's tone.

- [ ] **Step 4: Document in `README.md`** — tick `- [x] **Sprint 4 — Evals.**` in the roadmap; add a short "Evals" section: what it measures (type/field/risk deterministic metrics + judge faithfulness/recommendation scores), how to run (`uv run python scripts/run_evals.py`, `--fail-under`, `--only`), and a small example summary snippet. Keep the legal disclaimer intact; no marketing-speak.

- [ ] **Step 5: Verify** — `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` → all green.

- [ ] **Step 6: Commit**

```bash
git add tests/test_integration.py ARCHITECTURE.md README.md
git commit -m "test: eval-harness integration test; docs: document Sprint 4 evals" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` — all green (offline; integration skipped without a key).
- [ ] With `ANTHROPIC_API_KEY` set: `uv run python scripts/run_evals.py` produces a coherent report over all 12 cases; `uv run pytest -m integration` passes (incl. the new harness test).
- [ ] Deterministic metrics reproduce exactly on a second run (only judge scores vary).
- [ ] `uv run python scripts/run_evals.py --only minimo --fail-under 0.5` exercises the threshold path.
- [ ] Push branch and open a PR: `git push -u origin feat/sprint-4-evals && gh pr create --fill`.
```
