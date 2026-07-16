# Capa de anonimización de PII — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Steps use `- [ ]` tracking.

**Goal:** Enmascarar la PII localmente antes de que cualquier texto llegue al LLM/embeddings, sin degradar el análisis.

**Architecture:** Interfaz abstracta `Anonimizador` + backend `RegexAnonimizador` (única impl. de este sprint) + `AnonimizadorNulo`. Se inyecta en un único punto (`analizar_texto`). Modelo mask-only (no se restaura); la vista web muestra solo roles.

**Tech Stack:** Python 3.11+, Pydantic v2, `re` (stdlib), pytest; Astro/TS + vitest (web).

## Global Constraints

- LLM del análisis = Anthropic Claude (sin cambios). La detección de PII es **local**; nunca por red.
- Cero dependencias nuevas (solo stdlib `re`) → no toca el bundle de Vercel ni `api/requirements.txt`.
- `ruff`, `ruff format --check`, `mypy --strict`, `pytest` verdes; build web + vitest verdes.
- Línea ≤ 100. `ConfigDict(extra="forbid")` en modelos nuevos.
- No se persiste mapa de sustitución. Placeholders con formato `«TIPO_N»` (guillemets).

---

### Task 1: Módulo `anonimizacion.py` — interfaz, nulo, resultado

**Files:**
- Create: `src/arras_ai/anonimizacion.py`
- Test: `tests/test_anonimizacion.py`

**Interfaces produced:**
- `class ResultadoAnonimizacion(BaseModel)` — `texto: str`, `recuentos: dict[str, int]`.
- `class Anonimizador(ABC)` — `anonimizar(self, texto: str) -> ResultadoAnonimizacion`.
- `class AnonimizadorNulo(Anonimizador)` — passthrough, `recuentos={}`.

- [ ] **Step 1:** Test: `AnonimizadorNulo().anonimizar("D. Juan, NIF 12345678Z").texto` == input y `.recuentos == {}`.
- [ ] **Step 2:** Run `pytest tests/test_anonimizacion.py -v` → FAIL (import error).
- [ ] **Step 3:** Implement ABC + `ResultadoAnonimizacion` (`ConfigDict(extra="forbid")`) + `AnonimizadorNulo`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(core): Anonimizador interface + null backend`.

### Task 2: `RegexAnonimizador` — identificadores estructurados

**Files:**
- Modify: `src/arras_ai/anonimizacion.py`
- Test: `tests/test_anonimizacion.py`

**Interfaces produced:** `class RegexAnonimizador(Anonimizador)`.

Detectores (orden: email, IBAN, teléfono, NIF/NIE, CIF, ref. catastral). Token `«TIPO_N»`, numeración por tipo, mismo valor→mismo token. NIF/NIE con validación de dígito de control (`"TRWAGMYFPDXBNJZSQVHLCKE"[n % 23]`); NIE mapea X/Y/Z→0/1/2. CIF y ref. catastral por formato.

- [ ] **Step 1:** Tests:
  - `email a@b.com` → `«EMAIL_1»`; `IBAN ES9121000418450200051332` → `«IBAN_1»`.
  - `NIF 12345678Z` (válido) → `«NIF_1»`; `12345678A` (control inválido) → **sin cambio**.
  - `NIE X1234567L` válido → `«NIE_1»`; `CIF B12345674` → `«CIF_1»`; ref. catastral 20 chars → `«CATASTRO_1»`.
  - `Teléfono +34 612345678` → `«TELEFONO_1»`.
  - **No** enmascara `280.000 €`, `28.000 €`, `5 %`, `2025-03-15`.
  - Mismo NIF dos veces → mismo `«NIF_1»`; `recuentos["NIF"] == 1`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement detectores + validación de control.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(core): regex anonymizer for structured identifiers`.

### Task 3: `RegexAnonimizador` — nombres (heurística) + factory

**Files:**
- Modify: `src/arras_ai/anonimizacion.py`, `src/arras_ai/config.py`
- Test: `tests/test_anonimizacion.py`

**Interfaces produced:** `make_anonimizador(settings: Settings) -> Anonimizador`.

Nombres: honoríficos (`D.`, `D.ª`, `Dña.`, `Don`, `Doña`) + palabras capitalizadas; y `Nombre Apellidos, con NIF «NIF_N»`. Se ejecuta **después** de enmascarar NIF (para poder anclar en el token).

- [ ] **Step 1:** Tests:
  - `Dña. María Fernández Gil` → `Dña. «NOMBRE_1»`.
  - `Juan Pérez López, con NIF «NIF_1»` (texto ya con NIF enmascarado) → `«NOMBRE_1», con NIF «NIF_1»`.
  - `make_anonimizador(Settings(anonimizar=False))` → `AnonimizadorNulo`; `provider="regex"` → `RegexAnonimizador`; `provider="desconocido"` → `ValueError`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Add `anonimizar: bool = True` (`ARRAS_ANONIMIZAR`) y `anonimizador_provider: str = "regex"` (`ARRAS_ANONIMIZADOR_PROVIDER`) a `Settings`; implement name heuristics + `make_anonimizador`.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(core): name heuristics + anonymizer factory + settings`.

### Task 4: Inyección en `analizar_texto` (fail-closed)

**Files:**
- Modify: `src/arras_ai/agent.py:178-198`
- Test: `tests/test_agent_anonimizacion.py`

**Interfaces consumed:** `make_anonimizador`, `AnalysisError`.

- [ ] **Step 1:** Test: monkeypatch `analyze_text` para capturar el `texto` recibido; con `ARRAS_ANONIMIZAR=true`, analizar `"D. Juan, NIF 12345678Z, precio 280.000 €"` → el texto capturado **no** contiene `12345678Z` pero **sí** `280.000`. Y test: si el anonimizador lanza, `analizar_texto` lanza `AnalysisError` (no envía crudo).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** En `analizar_texto`, tras el check de vacío: `texto = _anonimizar_o_fallar(texto, settings)` donde el helper llama `make_anonimizador(settings).anonimizar(texto).texto` y envuelve excepciones inesperadas en `AnalysisError`. `load_settings()` ya se llama ahí.
- [ ] **Step 4:** Run → PASS + suite completa offline verde.
- [ ] **Step 5:** Commit `feat(agent): anonymize contract text before LLM (fail-closed)`.

### Task 5: Vista web — solo roles, ocultar placeholders + nota

**Files:**
- Modify: `web/src/lib/vista.ts`, `web/src/components/Analizador.astro`
- Test: `web/src/lib/vista.test.ts`

- [ ] **Step 1:** Tests en `vista.test.ts`:
  - Partes con `nombre="«NOMBRE_1»"` → la fila «Partes» del `datos` muestra solo roles (`"comprador, vendedor"`), sin el placeholder.
  - `inmueble.direccion="«...»"`-like o placeholder → valor mostrado `—`.
  - Valor normal (no placeholder) se muestra tal cual.
- [ ] **Step 2:** Run `npm run test` → FAIL.
- [ ] **Step 3:** En `vista.ts`: helper `esPlaceholder(s)` (`/^«[A-Z_]+_\d+»$/`); la fila Partes pasa a `roles.join(", ")`; cualquier valor placeholder → `—`. En `Analizador.astro`: nota de transparencia (footer del formulario): «Los datos personales (NIF, IBAN, email, teléfono, nombres detectables) se eliminan del texto antes de enviarlo para el análisis.»
- [ ] **Step 4:** Run test + `npm run build` → PASS.
- [ ] **Step 5:** Commit `feat(web): show roles only, hide anonymized PII + transparency note`.

### Task 6: Docs + verificación final

**Files:** Modify `ARCHITECTURE.md` (sección corta «Sprint 7: privacidad»), `README.md` (roadmap: añadir Sprint 7).

- [ ] **Step 1:** Añadir sección en ARCHITECTURE.md y línea en el roadmap del README.
- [ ] **Step 2:** Run puertas: `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` y `cd web && npm run test && npm run build` → todo verde.
- [ ] **Step 3:** Commit `docs: document Sprint 7 privacy layer`.
- [ ] **Step 4:** Push branch + abrir PR (NO merge — dejar para revisión del usuario).

## Self-Review

- **Cobertura spec:** interfaz+nulo (T1), IDs estructurados+control (T2), nombres+factory+config (T3), inyección fail-closed (T4), vista roles-only+nota (T5), docs+gates (T6). ✅ Backends futuros = documentados, no implementados (spec §Backends futuros → sin tarea, correcto).
- **Placeholders:** ninguno pendiente. Formato de token `«TIPO_N»` consistente en T2/T3/T5.
- **Tipos:** `ResultadoAnonimizacion.texto/recuentos`, `Anonimizador.anonimizar`, `make_anonimizador(settings)` consistentes entre tareas.
