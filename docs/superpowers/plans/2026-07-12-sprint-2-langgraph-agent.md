# Sprint 2 — LangGraph Agent with Risk Detection — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Sprint 1 single-call extraction to a typed LangGraph state machine that, after extracting the facts, detects problematic clauses and produces a risk report (`InformeArras`).

**Architecture:** A 3-node linear `StateGraph` (`extraer` → `detectar_riesgos` → `componer_informe`). Nodes call Claude directly via the existing `anthropic` SDK `messages.parse` path — no LangChain models. Risk detection is hybrid: deterministic rules over the structured `AnalisisArras` plus one focused LLM pass, merged and deduped by a pure function. If the LLM pass fails, the report degrades to rule-based risks.

**Tech Stack:** Python 3.11+, LangGraph, Pydantic v2, Anthropic SDK (`claude-opus-4-8`), Typer + Rich, pytest, ruff, mypy.

## Global Constraints

- Python `>=3.11`; `uv run mypy` (strict) must pass; `uv run ruff check .` and `uv run ruff format --check .` must pass; line length 100.
- All new Pydantic models set `model_config = ConfigDict(extra="forbid")`.
- Domain stays in Spanish (enum values, field names, all user-facing text); LLM *instructions* in English.
- Anthropic Claude only; default model from `config.DEFAULT_MODEL` (`claude-opus-4-8`); structured output via `client.messages.parse(output_format=...)`.
- New dependencies must be MIT-compatible. `langgraph` (MIT) is the only new runtime dep.
- Conventional Commits; every commit ends with the trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Work happens on branch `feat/sprint-2-langgraph` (already checked out).
- `AnalisisArras` and `analyzer.analyze_text` are NOT modified — the `extraer` node reuses them as-is.

---

## File Structure

- `src/arras_ai/models.py` — **modify**: add risk enums, `RiesgoBase`, `Riesgo`, `RiesgosDetectadosLLM`, `InformeArras`.
- `src/arras_ai/riesgos.py` — **create**: pure deterministic detectors + severity aggregation + report composition/dedup.
- `src/arras_ai/prompts.py` — **modify**: add the risk-detection system prompt and user-message builder.
- `src/arras_ai/agent.py` — **create**: `detectar_riesgos_llm`, `EstadoAnalisis`, node functions, `build_graph`, `analizar_texto`, `analizar_pdf`.
- `src/arras_ai/cli.py` — **modify**: call `agent.analizar_pdf`, render `InformeArras`.
- `pyproject.toml` — **modify**: add `langgraph` dependency.
- `tests/conftest.py` — **modify**: add `fake_informe` fixture.
- `tests/test_models.py` — **modify**: risk-model tests.
- `tests/test_riesgos.py` — **create**: detector/aggregation/dedup tests.
- `tests/test_agent_unit.py` — **create**: LLM-pass + graph unit tests (mocked).
- `tests/test_integration.py` — **modify**: agent-level integration assertions.
- `scripts/smoke_test.py` — **modify**: check risks and global level.
- `ARCHITECTURE.md`, `README.md` — **modify**: document Sprint 2.

---

## Task 1: Risk data models

**Files:**
- Modify: `src/arras_ai/models.py`
- Modify: `tests/test_models.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: existing `AnalisisArras` (unchanged).
- Produces:
  - `class CategoriaRiesgo(StrEnum)` — values `tipo_ambiguo`, `falta_financiacion`, `fechas_mal_definidas`, `inmueble_mal_identificado`, `reparto_gastos_ambiguo`, `otro`.
  - `class Severidad(StrEnum)` — `alta`, `media`, `baja`.
  - `class NivelRiesgo(StrEnum)` — `alto`, `medio`, `bajo`.
  - `class RiesgoBase(BaseModel)` — `categoria: CategoriaRiesgo`, `severidad: Severidad`, `descripcion: str`, `recomendacion: str`.
  - `class Riesgo(RiesgoBase)` — adds `fuente: Literal["regla", "llm"]`.
  - `class RiesgosDetectadosLLM(BaseModel)` — `riesgos: list[RiesgoBase]` (schema for the LLM pass; no `fuente`).
  - `class InformeArras(BaseModel)` — `analisis: AnalisisArras`, `riesgos: list[Riesgo]`, `nivel_riesgo_global: NivelRiesgo`.
  - conftest fixture `fake_informe() -> InformeArras`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_models.py`:

```python
from arras_ai.models import (
    CategoriaRiesgo,
    InformeArras,
    NivelRiesgo,
    Riesgo,
    RiesgoBase,
    RiesgosDetectadosLLM,
    Severidad,
)


def test_riesgo_requires_fuente() -> None:
    r = Riesgo(
        categoria=CategoriaRiesgo.falta_financiacion,
        severidad=Severidad.alta,
        descripcion="d",
        recomendacion="r",
        fuente="regla",
    )
    assert r.fuente == "regla"
    with pytest.raises(ValidationError):
        Riesgo.model_validate(
            {"categoria": "otro", "severidad": "baja", "descripcion": "d", "recomendacion": "r"}
        )


def test_riesgos_detectados_llm_has_no_fuente() -> None:
    payload = {"riesgos": [{"categoria": "otro", "severidad": "baja",
                            "descripcion": "d", "recomendacion": "r"}]}
    parsed = RiesgosDetectadosLLM.model_validate(payload)
    assert isinstance(parsed.riesgos[0], RiesgoBase)
    assert not hasattr(parsed.riesgos[0], "fuente")


def test_informe_roundtrips(fake_informe: InformeArras) -> None:
    restored = InformeArras.model_validate_json(fake_informe.model_dump_json())
    assert restored == fake_informe
    assert restored.nivel_riesgo_global in NivelRiesgo
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -k "riesgo or informe" -v`
Expected: FAIL with `ImportError` (models not defined).

- [ ] **Step 3: Add the models**

Append to `src/arras_ai/models.py` (the `from typing import Literal` goes with the existing imports at the top):

```python
class CategoriaRiesgo(StrEnum):
    """Categorías de riesgo/cláusula problemática detectables."""

    tipo_ambiguo = "tipo_ambiguo"
    falta_financiacion = "falta_financiacion"
    fechas_mal_definidas = "fechas_mal_definidas"
    inmueble_mal_identificado = "inmueble_mal_identificado"
    reparto_gastos_ambiguo = "reparto_gastos_ambiguo"
    otro = "otro"


class Severidad(StrEnum):
    alta = "alta"
    media = "media"
    baja = "baja"


class NivelRiesgo(StrEnum):
    alto = "alto"
    medio = "medio"
    bajo = "bajo"


class RiesgoBase(BaseModel):
    """Un riesgo detectado en el contrato (sin marca de procedencia)."""

    model_config = ConfigDict(extra="forbid")

    categoria: CategoriaRiesgo = Field(description="Categoría del riesgo detectado")
    severidad: Severidad = Field(description="Gravedad del riesgo: alta, media o baja")
    descripcion: str = Field(
        description="Qué está mal, en español, citando la parte del contrato afectada"
    )
    recomendacion: str = Field(
        description="Qué debería hacer o preguntar el usuario, en español"
    )


class Riesgo(RiesgoBase):
    """Un riesgo con su procedencia (regla determinista o pase LLM)."""

    fuente: Literal["regla", "llm"] = Field(
        description="Origen del hallazgo: 'regla' (detector determinista) o 'llm'"
    )


class RiesgosDetectadosLLM(BaseModel):
    """Schema del pase LLM de detección de riesgos (structured output)."""

    model_config = ConfigDict(extra="forbid")

    riesgos: list[RiesgoBase] = Field(
        default_factory=list, description="Riesgos adicionales detectados en el texto"
    )


class InformeArras(BaseModel):
    """Informe completo: extracción + riesgos + nivel de riesgo global."""

    model_config = ConfigDict(extra="forbid")

    analisis: AnalisisArras = Field(description="Extracción estructurada del contrato")
    riesgos: list[Riesgo] = Field(default_factory=list, description="Riesgos detectados")
    nivel_riesgo_global: NivelRiesgo = Field(
        description="Nivel de riesgo agregado del contrato"
    )
```

Add `Literal` to the typing import at the top of the file. The file currently has no `from typing import ...` line, so add one after `from enum import StrEnum`:

```python
from typing import Literal
```

- [ ] **Step 4: Add the `fake_informe` fixture**

First, extend the existing `arras_ai.models` import block at the top of `tests/conftest.py` to also import the risk types:

```python
from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    Parte,
    ReferenciaCodigoCivil,
    Riesgo,
    RolParte,
    Severidad,
    TipoArras,
)
```

Then append the fixture (annotated with the real return type):

```python
@pytest.fixture
def fake_informe(fake_analisis: AnalisisArras) -> InformeArras:
    return InformeArras(
        analisis=fake_analisis,
        riesgos=[
            Riesgo(
                categoria=CategoriaRiesgo.falta_financiacion,
                severidad=Severidad.alta,
                descripcion="No consta cláusula suspensiva de financiación.",
                recomendacion="Incluye una condición suspensiva de financiación.",
                fuente="regla",
            )
        ],
        nivel_riesgo_global=NivelRiesgo.alto,
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_models.py -v && uv run mypy && uv run ruff check .`
Expected: PASS; mypy clean; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add src/arras_ai/models.py tests/test_models.py tests/conftest.py
git commit -m "feat: risk data models (Riesgo, InformeArras) and enums" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Deterministic detectors, aggregation, composition

**Files:**
- Create: `src/arras_ai/riesgos.py`
- Create: `tests/test_riesgos.py`

**Interfaces:**
- Consumes: `AnalisisArras`, `Riesgo`, `CategoriaRiesgo`, `Severidad`, `NivelRiesgo`, `InformeArras` from Task 1.
- Produces:
  - `detectar_por_reglas(analisis: AnalisisArras) -> list[Riesgo]`
  - `nivel_global(riesgos: list[Riesgo]) -> NivelRiesgo`
  - `componer_informe(analisis: AnalisisArras, riesgos_regla: list[Riesgo], riesgos_llm: list[Riesgo]) -> InformeArras`
  - constant `UMBRAL_CONFIANZA_TIPO: float = 0.6`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_riesgos.py`:

```python
"""Unit tests for the deterministic risk detectors (pure, no API)."""

from __future__ import annotations

import pytest

from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    Importes,
    Inmueble,
    NivelRiesgo,
    Riesgo,
    Severidad,
    TipoArras,
)
from arras_ai.riesgos import componer_informe, detectar_por_reglas, nivel_global


def _analisis(**overrides: object) -> AnalisisArras:
    base = AnalisisArras(
        tipo_arras=TipoArras.penitenciales,
        confianza_tipo=0.95,
        justificacion_tipo="cita art. 1454",
        partes=[],
        inmueble=Inmueble(referencia_catastral="9872023VH5797S0001WX", cargas="libre de cargas"),
        importes=Importes(),
        fechas=__import__("arras_ai.models", fromlist=["Fechas"]).Fechas(
            fecha_limite_escritura="2025-06-15"
        ),
        referencias_codigo_civil=[],
        tiene_clausula_financiacion=True,
        resumen="ok",
    )
    return base.model_copy(update=overrides)


def _cats(riesgos: list[Riesgo]) -> set[CategoriaRiesgo]:
    return {r.categoria for r in riesgos}


def test_clean_contract_has_no_rule_risks() -> None:
    assert detectar_por_reglas(_analisis()) == []


def test_tipo_no_especificado_is_high_risk() -> None:
    riesgos = detectar_por_reglas(_analisis(tipo_arras=TipoArras.no_especificado))
    tipo = next(r for r in riesgos if r.categoria is CategoriaRiesgo.tipo_ambiguo)
    assert tipo.severidad is Severidad.alta
    assert tipo.fuente == "regla"


def test_low_confidence_type_is_medium_risk() -> None:
    riesgos = detectar_por_reglas(_analisis(confianza_tipo=0.4))
    tipo = next(r for r in riesgos if r.categoria is CategoriaRiesgo.tipo_ambiguo)
    assert tipo.severidad is Severidad.media


def test_missing_financing_clause_detected() -> None:
    riesgos = detectar_por_reglas(_analisis(tiene_clausula_financiacion=False))
    assert CategoriaRiesgo.falta_financiacion in _cats(riesgos)


def test_missing_dates_detected() -> None:
    from arras_ai.models import Fechas

    riesgos = detectar_por_reglas(_analisis(fechas=Fechas()))
    assert CategoriaRiesgo.fechas_mal_definidas in _cats(riesgos)


def test_missing_cadastral_reference_detected() -> None:
    riesgos = detectar_por_reglas(_analisis(inmueble=Inmueble()))
    assert CategoriaRiesgo.inmueble_mal_identificado in _cats(riesgos)


def test_nivel_global_takes_max_severity() -> None:
    def r(sev: Severidad) -> Riesgo:
        return Riesgo(categoria=CategoriaRiesgo.otro, severidad=sev,
                      descripcion="d", recomendacion="r", fuente="regla")

    assert nivel_global([]) is NivelRiesgo.bajo
    assert nivel_global([r(Severidad.baja), r(Severidad.media)]) is NivelRiesgo.medio
    assert nivel_global([r(Severidad.media), r(Severidad.alta)]) is NivelRiesgo.alto


def test_componer_dedups_rule_categories_but_keeps_otro() -> None:
    analisis = _analisis(tiene_clausula_financiacion=False)
    reglas = detectar_por_reglas(analisis)  # includes falta_financiacion (regla)
    llm = [
        Riesgo(categoria=CategoriaRiesgo.falta_financiacion, severidad=Severidad.media,
               descripcion="dup", recomendacion="r", fuente="llm"),
        Riesgo(categoria=CategoriaRiesgo.otro, severidad=Severidad.baja,
               descripcion="extra1", recomendacion="r", fuente="llm"),
        Riesgo(categoria=CategoriaRiesgo.otro, severidad=Severidad.baja,
               descripcion="extra2", recomendacion="r", fuente="llm"),
    ]
    informe = componer_informe(analisis, reglas, llm)
    # the LLM's duplicate falta_financiacion is dropped (rule wins)...
    fin = [r for r in informe.riesgos if r.categoria is CategoriaRiesgo.falta_financiacion]
    assert len(fin) == 1 and fin[0].fuente == "regla"
    # ...but both 'otro' findings survive
    otros = [r for r in informe.riesgos if r.categoria is CategoriaRiesgo.otro]
    assert len(otros) == 2
    assert informe.nivel_riesgo_global is NivelRiesgo.alto
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_riesgos.py -v`
Expected: FAIL with `ModuleNotFoundError: arras_ai.riesgos`.

- [ ] **Step 3: Implement `riesgos.py`**

Create `src/arras_ai/riesgos.py`:

```python
"""Deterministic risk detectors and report composition.

Pure functions, no API calls — the reliable, free, testable half of the hybrid
risk detection (the other half is the LLM pass in agent.py). Kept pure so it is
trivially unit-tested and reusable by the Sprint 4 eval harness.
"""

from __future__ import annotations

from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    InformeArras,
    NivelRiesgo,
    Riesgo,
    Severidad,
    TipoArras,
)

UMBRAL_CONFIANZA_TIPO = 0.6


def detectar_por_reglas(analisis: AnalisisArras) -> list[Riesgo]:
    """Derive the 'obvious' risks directly from the structured extraction."""
    riesgos: list[Riesgo] = []

    if analisis.tipo_arras is TipoArras.no_especificado:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.tipo_ambiguo,
                severidad=Severidad.alta,
                descripcion=(
                    "El contrato no especifica la modalidad de arras. Por defecto, los "
                    "tribunales las interpretan como confirmatorias, la modalidad más vinculante."
                ),
                recomendacion=(
                    "Exige que el contrato indique expresamente el tipo de arras y cite el "
                    "artículo del Código Civil correspondiente."
                ),
                fuente="regla",
            )
        )
    elif analisis.confianza_tipo < UMBRAL_CONFIANZA_TIPO:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.tipo_ambiguo,
                severidad=Severidad.media,
                descripcion=(
                    f"La modalidad detectada ({analisis.tipo_arras.value}) no aparece de forma "
                    f"inequívoca (confianza {analisis.confianza_tipo:.0%})."
                ),
                recomendacion="Aclara en el contrato la modalidad de arras para evitar dudas.",
                fuente="regla",
            )
        )

    if analisis.tiene_clausula_financiacion is False:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.falta_financiacion,
                severidad=Severidad.alta,
                descripcion=(
                    "No consta cláusula suspensiva de financiación. Si el banco deniega la "
                    "hipoteca, el comprador puede perder la señal entregada."
                ),
                recomendacion=(
                    "Incluye una condición suspensiva de financiación que permita recuperar la "
                    "señal si no se concede el préstamo."
                ),
                fuente="regla",
            )
        )

    if analisis.fechas.fecha_limite_escritura is None and analisis.fechas.plazo_dias is None:
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.fechas_mal_definidas,
                severidad=Severidad.media,
                descripcion="No se fija fecha límite ni plazo para otorgar la escritura pública.",
                recomendacion=(
                    "Fija una fecha límite concreta (o un plazo en días) para elevar a público "
                    "la compraventa."
                ),
                fuente="regla",
            )
        )

    if analisis.inmueble.referencia_catastral is None:
        descripcion = "El contrato no incluye la referencia catastral del inmueble."
        if analisis.inmueble.cargas is None:
            descripcion += " Tampoco indica si el inmueble está libre de cargas."
        riesgos.append(
            Riesgo(
                categoria=CategoriaRiesgo.inmueble_mal_identificado,
                severidad=Severidad.media,
                descripcion=descripcion,
                recomendacion=(
                    "Añade la referencia catastral y el estado de cargas (nota simple registral) "
                    "para identificar el inmueble sin ambigüedad."
                ),
                fuente="regla",
            )
        )

    return riesgos


def nivel_global(riesgos: list[Riesgo]) -> NivelRiesgo:
    """Aggregate to a global level by maximum severity (no accumulation)."""
    severidades = {r.severidad for r in riesgos}
    if Severidad.alta in severidades:
        return NivelRiesgo.alto
    if Severidad.media in severidades:
        return NivelRiesgo.medio
    return NivelRiesgo.bajo


def componer_informe(
    analisis: AnalisisArras,
    riesgos_regla: list[Riesgo],
    riesgos_llm: list[Riesgo],
) -> InformeArras:
    """Merge rule + LLM risks, deduping only rule categories a rule already covered."""
    categorias_cubiertas = {r.categoria for r in riesgos_regla}
    llm_filtrados = [r for r in riesgos_llm if r.categoria not in categorias_cubiertas]
    riesgos = [*riesgos_regla, *llm_filtrados]
    return InformeArras(
        analisis=analisis,
        riesgos=riesgos,
        nivel_riesgo_global=nivel_global(riesgos),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_riesgos.py -v && uv run mypy && uv run ruff check .`
Expected: PASS; mypy clean; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add src/arras_ai/riesgos.py tests/test_riesgos.py
git commit -m "feat: deterministic risk detectors, severity aggregation, dedup" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Risk-detection prompt and LLM pass

**Files:**
- Modify: `src/arras_ai/prompts.py`
- Create: `src/arras_ai/agent.py`
- Create: `tests/test_agent_unit.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `AnalisisArras`, `Riesgo`, `RiesgosDetectadosLLM`, `DEFAULT_MODEL`, `SYSTEM_PROMPT` builder patterns.
- Produces:
  - `prompts.SYSTEM_PROMPT_RIESGOS: str`
  - `prompts.build_user_message_riesgos(texto: str, analisis: AnalisisArras) -> str`
  - `agent.detectar_riesgos_llm(texto: str, analisis: AnalisisArras, *, client: anthropic.Anthropic, model: str = DEFAULT_MODEL, max_tokens: int = 4000) -> list[Riesgo]`

- [ ] **Step 1: Add `langgraph` dependency**

In `pyproject.toml`, add to `dependencies`:

```toml
    "langgraph>=0.2",
```

Run: `uv sync`
Expected: resolves and installs langgraph.

- [ ] **Step 2: Write the failing test**

Create `tests/test_agent_unit.py`:

```python
"""Unit tests for the agent (LangGraph nodes + LLM pass) with Claude mocked."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import anthropic

from arras_ai import agent
from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    RiesgoBase,
    RiesgosDetectadosLLM,
    Severidad,
)


class _FakeMessages:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.last_kwargs: dict[str, Any] = {}

    def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.last_kwargs = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self.messages = _FakeMessages(response)


def test_detectar_riesgos_llm_marks_fuente_llm(fake_analisis: AnalisisArras) -> None:
    parsed = RiesgosDetectadosLLM(
        riesgos=[
            RiesgoBase(
                categoria=CategoriaRiesgo.reparto_gastos_ambiguo,
                severidad=Severidad.baja,
                descripcion="El reparto de gastos no está claro.",
                recomendacion="Detalla qué gastos asume cada parte.",
            )
        ]
    )
    client = _FakeClient(SimpleNamespace(parsed_output=parsed, stop_reason="end_turn"))
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, client=cast(anthropic.Anthropic, client)
    )
    assert len(riesgos) == 1
    assert riesgos[0].fuente == "llm"
    assert riesgos[0].categoria is CategoriaRiesgo.reparto_gastos_ambiguo


def test_detectar_riesgos_llm_returns_empty_when_unparsed(fake_analisis: AnalisisArras) -> None:
    client = _FakeClient(SimpleNamespace(parsed_output=None, stop_reason="max_tokens"))
    riesgos = agent.detectar_riesgos_llm(
        "texto", fake_analisis, client=cast(anthropic.Anthropic, client)
    )
    assert riesgos == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_agent_unit.py -v`
Expected: FAIL with `ImportError`/`AttributeError` (no `agent.detectar_riesgos_llm`).

- [ ] **Step 4: Add the risk prompt to `prompts.py`**

Append to `src/arras_ai/prompts.py`:

```python
SYSTEM_PROMPT_RIESGOS = """\
You review a Spanish earnest-money contract (contrato de arras) for problems that put the \
buyer or seller at risk. You are NOT a lawyer and do not give legal advice; you flag issues \
a person should check with a professional.

You are given the contract text and a structured extraction of it. Return ADDITIONAL risks \
that require reading the prose — especially an ambiguous or missing split of costs \
(reparto de gastos → categoria 'reparto_gastos_ambiguo'). Other genuine problems that do not \
fit a category go under 'otro'.

Do NOT repeat these, which are already handled by deterministic rules: the arras type being \
unspecified/ambiguous, a missing financing-contingency clause, missing deadline/plazo, or a \
missing cadastral reference. Only add something in those categories if you found a DIFFERENT, \
additional problem.

For each risk set: `severidad` (alta/media/baja by financial impact), a `descripcion` quoting \
the relevant contract wording, and a concrete `recomendacion`. If you find no additional \
risks, return an empty list. All text MUST be in Spanish.
"""

USER_INSTRUCTION_RIESGOS = """\
Texto del contrato:
--- INICIO ---
{contract_text}
--- FIN ---

Extracción estructurada (JSON):
{analisis_json}

Devuelve los riesgos ADICIONALES detectados.
"""


def build_user_message_riesgos(texto: str, analisis: "AnalisisArras") -> str:
    """Build the user-turn content for the risk-detection pass."""
    return USER_INSTRUCTION_RIESGOS.format(
        contract_text=texto.strip(),
        analisis_json=analisis.model_dump_json(indent=2),
    )
```

Add `from arras_ai.models import AnalisisArras` to `prompts.py` imports and change the annotation to `analisis: AnalisisArras` (drop the quotes). Confirm no circular import: `models.py` does not import `prompts.py`, so this is safe.

- [ ] **Step 5: Create `agent.py` with the LLM pass**

Create `src/arras_ai/agent.py`:

```python
"""LangGraph agent: extraction -> risk detection -> report.

Nodes call Claude directly through the anthropic SDK (no LangChain models). The
graph is a simple linear StateGraph; the sophistication is in the typed state and
the hybrid (rules + LLM) risk detection, not in control flow.
"""

from __future__ import annotations

import logging
from pathlib import Path

import anthropic

from arras_ai.analyzer import AnalysisError, _build_client, analyze_text
from arras_ai.config import DEFAULT_MODEL, load_settings
from arras_ai.models import AnalisisArras, InformeArras, Riesgo, RiesgosDetectadosLLM
from arras_ai.pdf import extract_text
from arras_ai.prompts import SYSTEM_PROMPT_RIESGOS, build_user_message_riesgos
from arras_ai.riesgos import componer_informe, detectar_por_reglas

logger = logging.getLogger("arras_ai.agent")

RIESGOS_MAX_TOKENS = 4000


def detectar_riesgos_llm(
    texto: str,
    analisis: AnalisisArras,
    *,
    client: anthropic.Anthropic,
    model: str = DEFAULT_MODEL,
    max_tokens: int = RIESGOS_MAX_TOKENS,
) -> list[Riesgo]:
    """Run the focused LLM risk pass; tag results with fuente='llm'.

    Returns an empty list if the model returns nothing parseable.
    """
    response = client.messages.parse(
        model=model,
        max_tokens=max_tokens,
        system=SYSTEM_PROMPT_RIESGOS,
        messages=[{"role": "user", "content": build_user_message_riesgos(texto, analisis)}],
        output_format=RiesgosDetectadosLLM,
    )
    parsed = response.parsed_output
    if parsed is None:
        return []
    return [Riesgo(**base.model_dump(), fuente="llm") for base in parsed.riesgos]
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_unit.py -v && uv run mypy && uv run ruff check .`
Expected: PASS; mypy clean; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock src/arras_ai/prompts.py src/arras_ai/agent.py tests/test_agent_unit.py
git commit -m "feat: risk-detection prompt and LLM pass (agent.detectar_riesgos_llm)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: The graph — state, nodes, public API

**Files:**
- Modify: `src/arras_ai/agent.py`
- Modify: `tests/test_agent_unit.py`

**Interfaces:**
- Consumes: `detectar_riesgos_llm`, `analyze_text`, `detectar_por_reglas`, `componer_informe`, `_build_client`, `extract_text`.
- Produces:
  - `class EstadoAnalisis(BaseModel)` — `texto_contrato: str`, `analisis: AnalisisArras | None`, `riesgos_regla: list[Riesgo]`, `riesgos_llm: list[Riesgo]`, `informe: InformeArras | None`.
  - `build_graph(client: anthropic.Anthropic, model: str) -> Any` (compiled graph).
  - `analizar_texto(texto: str, *, client: anthropic.Anthropic | None = None, model: str = DEFAULT_MODEL) -> InformeArras`.
  - `analizar_pdf(path: str | Path, *, client: anthropic.Anthropic | None = None, model: str = DEFAULT_MODEL) -> InformeArras`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_agent_unit.py`:

```python
import pytest

from arras_ai.models import InformeArras, NivelRiesgo


def _stub_extract(monkeypatch: pytest.MonkeyPatch, analisis: AnalisisArras) -> None:
    monkeypatch.setattr(agent, "analyze_text", lambda *a, **k: analisis)


def test_analizar_texto_builds_informe(
    monkeypatch: pytest.MonkeyPatch, fake_analisis: AnalisisArras
) -> None:
    # extraction returns a contract missing the financing clause -> rule risk
    analisis = fake_analisis.model_copy(update={"tiene_clausula_financiacion": False})
    _stub_extract(monkeypatch, analisis)
    monkeypatch.setattr(agent, "detectar_riesgos_llm", lambda *a, **k: [])

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
    )
    assert isinstance(informe, InformeArras)
    assert any(r.categoria is CategoriaRiesgo.falta_financiacion for r in informe.riesgos)
    assert informe.nivel_riesgo_global is NivelRiesgo.alto


def test_analizar_texto_degrades_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch, fake_analisis: AnalisisArras
) -> None:
    analisis = fake_analisis.model_copy(update={"tiene_clausula_financiacion": False})
    _stub_extract(monkeypatch, analisis)

    def _boom(*a: Any, **k: Any) -> list[Any]:
        raise RuntimeError("network down")

    monkeypatch.setattr(agent, "detectar_riesgos_llm", _boom)

    informe = agent.analizar_texto(
        "texto", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
    )
    # still produced from rule risks
    assert any(r.fuente == "regla" for r in informe.riesgos)
    assert all(r.fuente == "regla" for r in informe.riesgos)


def test_analizar_texto_rejects_empty() -> None:
    with pytest.raises(AnalysisError):
        agent.analizar_texto(
            "   ", client=cast(anthropic.Anthropic, _FakeClient(SimpleNamespace()))
        )
```

Add the missing import at the top of the test file: `from arras_ai.analyzer import AnalysisError`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agent_unit.py -k "analizar" -v`
Expected: FAIL with `AttributeError` (`agent.analizar_texto` not defined).

- [ ] **Step 3: Add state, nodes, graph, public API**

Append to `src/arras_ai/agent.py` (add `from functools import partial`, `from typing import Any`, `from pydantic import BaseModel, Field`, and `from langgraph.graph import END, START, StateGraph` to the imports):

```python
class EstadoAnalisis(BaseModel):
    """Typed state passed between graph nodes."""

    texto_contrato: str
    analisis: AnalisisArras | None = None
    riesgos_regla: list[Riesgo] = Field(default_factory=list)
    riesgos_llm: list[Riesgo] = Field(default_factory=list)
    informe: InformeArras | None = None


def _nodo_extraer(
    estado: EstadoAnalisis, *, client: anthropic.Anthropic, model: str
) -> dict[str, Any]:
    analisis = analyze_text(estado.texto_contrato, client=client, model=model)
    return {"analisis": analisis}


def _nodo_detectar(
    estado: EstadoAnalisis, *, client: anthropic.Anthropic, model: str
) -> dict[str, Any]:
    assert estado.analisis is not None  # extraer ran first
    riesgos_regla = detectar_por_reglas(estado.analisis)
    try:
        riesgos_llm = detectar_riesgos_llm(
            estado.texto_contrato, estado.analisis, client=client, model=model
        )
    except Exception:
        logger.warning("risk LLM pass failed; using rule-based risks only", exc_info=True)
        riesgos_llm = []
    return {"riesgos_regla": riesgos_regla, "riesgos_llm": riesgos_llm}


def _nodo_componer(estado: EstadoAnalisis) -> dict[str, Any]:
    assert estado.analisis is not None
    informe = componer_informe(estado.analisis, estado.riesgos_regla, estado.riesgos_llm)
    return {"informe": informe}


def build_graph(client: anthropic.Anthropic, model: str) -> Any:
    """Compile the extraction -> risk-detection -> report graph."""
    builder: StateGraph = StateGraph(EstadoAnalisis)
    builder.add_node("extraer", partial(_nodo_extraer, client=client, model=model))
    builder.add_node("detectar_riesgos", partial(_nodo_detectar, client=client, model=model))
    builder.add_node("componer_informe", _nodo_componer)
    builder.add_edge(START, "extraer")
    builder.add_edge("extraer", "detectar_riesgos")
    builder.add_edge("detectar_riesgos", "componer_informe")
    builder.add_edge("componer_informe", END)
    return builder.compile()


def analizar_texto(
    texto: str,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> InformeArras:
    """Analyze already-extracted contract text end to end."""
    if not texto.strip():
        raise AnalysisError("Empty contract text.")
    if client is None:
        client = _build_client(load_settings().anthropic_api_key)
    graph = build_graph(client, model)
    final = graph.invoke(EstadoAnalisis(texto_contrato=texto))
    estado = EstadoAnalisis.model_validate(final)
    if estado.informe is None:
        raise AnalysisError("The agent did not produce a report.")
    return estado.informe


def analizar_pdf(
    path: str | Path,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> InformeArras:
    """Extract text from a PDF and analyze it. See :func:`analizar_texto`."""
    return analizar_texto(extract_text(path), client=client, model=model)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_agent_unit.py -v && uv run mypy && uv run ruff check .`
Expected: PASS (all agent unit tests); mypy clean; ruff clean.

Note: if mypy complains about `StateGraph` generics, the `builder: StateGraph = ...` annotation and `-> Any` return keep it strict-clean without depending on langgraph stubs.

- [ ] **Step 5: Commit**

```bash
git add src/arras_ai/agent.py tests/test_agent_unit.py
git commit -m "feat: LangGraph state machine wiring extraction and risk detection" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CLI renders the risk report

**Files:**
- Modify: `src/arras_ai/cli.py`
- Create: `tests/test_cli.py`

**Interfaces:**
- Consumes: `agent.analizar_pdf`, `InformeArras`, `NivelRiesgo`, `Severidad`.
- Produces: updated `analyze` command; `_render_informe(informe: InformeArras) -> None`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
"""CLI tests with the agent mocked (no API)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from arras_ai import cli
from arras_ai.models import InformeArras

runner = CliRunner()


def test_analyze_human_output(
    monkeypatch: pytest.MonkeyPatch, penitenciales_pdf: Path, fake_informe: InformeArras
) -> None:
    monkeypatch.setattr(cli, "analizar_pdf", lambda *a, **k: fake_informe)
    result = runner.invoke(cli.app, ["analyze", str(penitenciales_pdf)])
    assert result.exit_code == 0
    assert "Nivel de riesgo" in result.stdout
    assert "ALTO" in result.stdout


def test_analyze_json_output(
    monkeypatch: pytest.MonkeyPatch, penitenciales_pdf: Path, fake_informe: InformeArras
) -> None:
    monkeypatch.setattr(cli, "analizar_pdf", lambda *a, **k: fake_informe)
    result = runner.invoke(cli.app, ["analyze", str(penitenciales_pdf), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    InformeArras.model_validate(payload)  # round-trips
    assert "nivel_riesgo_global" in payload
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL (CLI still imports/returns `AnalisisArras`; no `analizar_pdf` in cli).

- [ ] **Step 3: Update `cli.py`**

In `src/arras_ai/cli.py`:

1. Replace the analyzer import line
   `from arras_ai.analyzer import AnalysisError, analyze_pdf`
   with:

```python
from arras_ai.agent import analizar_pdf
from arras_ai.analyzer import AnalysisError
```

2. Update the models import to add the risk types:

```python
from arras_ai.models import AnalisisArras, InformeArras, NivelRiesgo, Severidad, TipoArras
```

3. Add style maps near `_TIPO_STYLE`:

```python
_NIVEL_STYLE = {
    NivelRiesgo.alto: "bold red",
    NivelRiesgo.medio: "yellow",
    NivelRiesgo.bajo: "green",
}
_SEV_STYLE = {
    Severidad.alta: "red",
    Severidad.media: "yellow",
    Severidad.baja: "dim",
}
```

4. Add the report renderer (keeps `_render_human(analisis)` for the extraction block):

```python
def _render_informe(informe: InformeArras) -> None:
    _render_human(informe.analisis)

    nivel = informe.nivel_riesgo_global
    style = _NIVEL_STYLE.get(nivel, "white")
    console.print(
        Panel(
            f"[{style}]Nivel de riesgo global: {nivel.value.upper()}[/{style}]",
            border_style=style,
        )
    )

    if not informe.riesgos:
        console.print("Sin riesgos detectados.")
        return

    tabla = Table(title="Riesgos detectados", show_header=True, header_style="bold")
    tabla.add_column("Sev.")
    tabla.add_column("Categoría")
    tabla.add_column("Descripción")
    tabla.add_column("Recomendación")
    for r in informe.riesgos:
        sev_style = _SEV_STYLE.get(r.severidad, "white")
        tabla.add_row(
            f"[{sev_style}]{r.severidad.value}[/{sev_style}]",
            r.categoria.value,
            r.descripcion,
            r.recomendacion,
        )
    console.print(tabla)
```

5. In `analyze`, replace the call and the render/JSON block:

```python
    try:
        informe = analizar_pdf(pdf, model=chosen_model)
    except PdfExtractionError as exc:
        err_console.print(f"[red]PDF error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    except AnalysisError as exc:
        err_console.print(f"[red]Analysis error:[/red] {exc}")
        raise typer.Exit(code=3) from exc
    except Exception as exc:  # network / auth / API errors from the SDK
        err_console.print(f"[red]Unexpected error:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    if json_output:
        sys.stdout.write(informe.model_dump_json(indent=2))
        sys.stdout.write("\n")
    else:
        _render_informe(informe)
```

Note: `AnalisisArras` and `TipoArras` are still imported/used by `_render_human`; keep them.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v && uv run mypy && uv run ruff check .`
Expected: PASS; mypy clean; ruff clean.

- [ ] **Step 5: Full offline suite**

Run: `uv run pytest`
Expected: all pass, integration skipped without a key.

- [ ] **Step 6: Commit**

```bash
git add src/arras_ai/cli.py tests/test_cli.py
git commit -m "feat: CLI renders risk report and global risk level" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 6: Integration tests and smoke test

**Files:**
- Modify: `tests/test_integration.py`
- Modify: `scripts/smoke_test.py`

**Interfaces:**
- Consumes: `agent.analizar_pdf`, `InformeArras`, `CategoriaRiesgo`, `NivelRiesgo`.

- [ ] **Step 1: Add agent integration tests**

Append to `tests/test_integration.py`:

```python
from arras_ai.agent import analizar_pdf
from arras_ai.models import CategoriaRiesgo, NivelRiesgo


def test_agente_confirmatorias_flags_financing(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_confirmatorias_problematic.pdf")
    cats = {r.categoria for r in informe.riesgos}
    assert CategoriaRiesgo.falta_financiacion in cats
    assert informe.nivel_riesgo_global is NivelRiesgo.alto


def test_agente_penitenciales_low_risk(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_penitenciales_clean.pdf")
    assert informe.nivel_riesgo_global is NivelRiesgo.bajo


def test_agente_ambiguo_flags_type_and_financing(fixtures_dir: Path) -> None:
    informe = analizar_pdf(fixtures_dir / "arras_ambiguas.pdf")
    cats = {r.categoria for r in informe.riesgos}
    assert CategoriaRiesgo.tipo_ambiguo in cats
    assert CategoriaRiesgo.falta_financiacion in cats
```

These inherit the module-level `pytestmark` (integration + skip without key) already at the top of the file.

- [ ] **Step 2: Run integration (only if a key is available)**

Run: `uv run pytest -m integration -v`
Expected: with `ANTHROPIC_API_KEY` set, PASS; without it, SKIPPED.

- [ ] **Step 3: Extend the smoke test**

In `scripts/smoke_test.py`, switch the import from `analyze_pdf` to the agent and add
risk checks. Replace `from arras_ai.analyzer import analyze_pdf` with
`from arras_ai.agent import analizar_pdf`, then in `_run_case` call
`informe = analizar_pdf(...)`, use `informe.analisis` where `analisis` was used, and after
the existing prints add:

```python
    print(f"  -> nivel_riesgo       : {informe.nivel_riesgo_global.value}")
    print(f"  -> riesgos            : "
          f"{[(r.categoria.value, r.severidad.value) for r in informe.riesgos]}")
```

Update each `Case` to accept the informe (change the `Check` type alias to operate on
`InformeArras`, and update the lambdas to read `a.analisis.tipo_arras`, etc.). Add these
hard checks:
- `arras_penitenciales_clean`: `lambda i: i.nivel_riesgo_global is NivelRiesgo.bajo`
- `arras_confirmatorias_problematic`:
  `lambda i: any(r.categoria is CategoriaRiesgo.falta_financiacion for r in i.riesgos)` and
  `lambda i: i.nivel_riesgo_global is NivelRiesgo.alto`
- `arras_ambiguas`:
  `lambda i: any(r.categoria is CategoriaRiesgo.tipo_ambiguo for r in i.riesgos)`

- [ ] **Step 4: Run the smoke test (with a key)**

Run: `uv run python scripts/smoke_test.py`
Expected: `3/3 cases passed their hard checks.`

- [ ] **Step 5: Commit**

```bash
git add tests/test_integration.py scripts/smoke_test.py
git commit -m "test: agent-level integration and smoke checks for risk detection" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 7: Documentation

**Files:**
- Modify: `ARCHITECTURE.md`
- Modify: `README.md`

- [ ] **Step 1: Add the Sprint 2 section to `ARCHITECTURE.md`**

Add a new section after the "Structured outputs" section documenting: the LangGraph
choice (orchestration only, direct anthropic client in nodes, no LangChain models); the
3-node linear graph and typed `EstadoAnalisis`; the hybrid rules + one-LLM-pass risk
detection and why rules stay pure (free, reliable, testable, feeds Sprint 4 evals); the
`InformeArras` wrapper keeping extraction separate from judgement; and graceful degradation
when the LLM pass fails. Keep it to ~250 words, matching the file's existing tone.

- [ ] **Step 2: Update `README.md`**

- Update the "How it works" diagram to show the 3-node graph
  (`PDF → extraer → detectar_riesgos → componer_informe → InformeArras`).
- Tick Sprint 2 in the roadmap: change `- [ ] **Sprint 2 — Agent.**` to `- [x]`.
- Refresh the "What this does" / demo section to include the risk report output
  (a `Nivel de riesgo` line and a couple of example risks).

- [ ] **Step 3: Verify docs render and full gate passes**

Run: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add ARCHITECTURE.md README.md
git commit -m "docs: document Sprint 2 LangGraph agent and risk detection" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` — all green.
- [ ] With `ANTHROPIC_API_KEY` set: `uv run pytest -m integration` passes and
  `uv run python scripts/smoke_test.py` reports `3/3`.
- [ ] `uv run arras analyze tests/fixtures/arras_confirmatorias_problematic.pdf` shows a
  `Nivel de riesgo: ALTO` banner and a `falta_financiacion` risk.
- [ ] Push branch and open a PR:
  `git push -u origin feat/sprint-2-langgraph && gh pr create --fill`.
```
