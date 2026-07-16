# Diseño — Capa de anonimización de PII (Sprint 7)

**Fecha:** 2026-07-16
**Estado:** aprobado (diseño); implementación pendiente de revisión del usuario.

## Objetivo

Que **ningún dato personal salga hacia el LLM de terceros** (Anthropic) ni hacia el
proveedor de embeddings. Antes de enviar el texto del contrato para su análisis, se
detecta y enmascara la PII **localmente**. El razonamiento jurídico (tipo de arras,
riesgos, importes, fechas) no necesita saber *quién* firma ni *dónde* está el inmueble,
así que enmascararla no degrada el análisis.

Principio rector: **la detección es siempre local.** Cualquier llamada a la nube para
detectar PII reintroduce la fuga que queremos evitar, así que queda descartada por
diseño (esto excluye Gemini/OpenAI/etc. como detectores; un modelo *local* de pesos
abiertos sí sería admisible como backend futuro — ver «Backends futuros»).

## No-objetivos (YAGNI)

- **No** se restaura la PII (modelo «enmascarar y no mostrar»): el informe muestra
  *roles* y el análisis, nunca nombres/NIF. La respuesta del API no lleva PII.
- **No** se implementan backends pesados (Presidio, NER, LLM local) en este sprint. Se
  deja la interfaz preparada y se documentan como extensión para self-host.
- **No** se persiste ningún mapa de sustitución: el enmascarado es unidireccional.

## Modelo de privacidad

Seudonimización **unidireccional** (mask-only). `«María Fernández»` → `«NOMBRE_1»`,
`«12345678Z»` → `«NIF_1»`. El texto enmascarado es lo único que ve el LLM. No se guarda
correspondencia inversa.

**Garantía honesta (irá en UI/docs, sin sobrevender):**
- **Fuerte (100%, por formato):** NIF, NIE, CIF, IBAN, email, teléfono, referencia
  catastral.
- **Best-effort (heurística):** nombres de persona.
- **Fuera de alcance (limitación declarada):** direcciones postales en texto libre (no
  detectables por regex de forma fiable; menos identificativas que el NIF; además el
  análisis no las usa). Documentado como limitación conocida; el backend NER futuro las
  cubriría.

## Arquitectura

Interfaz abstracta, coherente con `EmbeddingModel` / `VectorStore`.

```
src/arras_ai/anonimizacion.py
  Anonimizador (ABC)
    anonimizar(texto: str) -> ResultadoAnonimizacion
  ResultadoAnonimizacion (pydantic)
    texto: str                 # texto enmascarado
    recuentos: dict[str, int]  # p.ej. {"NIF": 2, "NOMBRE": 2} — para transparencia/tests, sin PII
  RegexAnonimizador(Anonimizador)   # única implementación de este sprint
  make_anonimizador(settings) -> Anonimizador   # factory (dispatch por provider)
  AnonimizadorNulo(Anonimizador)    # passthrough, para ARRAS_ANONIMIZAR=false y tests
```

`ResultadoAnonimizacion.recuentos` expone **cuánta** PII se enmascaró por tipo (para
tests, logging y una nota de transparencia en la UI), **nunca los valores**.

### Detectores de `RegexAnonimizador`

Orden de aplicación importante (los estructurados primero, luego nombres):

1. **Email** — RFC-simplificado.
2. **IBAN** — `ES` + 22 dígitos (con o sin espacios).
3. **Teléfono** — móviles/fijos españoles (`+34` opcional, 9 dígitos empezando por 6/7/8/9).
4. **NIF/NIE** — 8 dígitos + letra / `[XYZ]` + 7 dígitos + letra. **Se valida el dígito
   de control** para no enmascarar números que casualmente encajen (p.ej. importes).
5. **CIF** — letra + 7 dígitos + control.
6. **Referencia catastral** — 20 caracteres alfanuméricos.
7. **Nombres (heurística, best-effort):** capturas ancladas en el contexto formulario de
   los contratos de arras:
   - Honoríficos: `D.`, `D.ª`, `Dña.`, `Don`, `Doña` + secuencia de palabras
     capitalizadas.
   - Proximidad a un NIF ya enmascarado: `Nombre Apellidos, con NIF «NIF_1»`.

Cada tipo tiene su contador y numeración propia (`NIF_1`, `NIF_2`, `NOMBRE_1`…). Mismo
valor original → mismo token dentro de una llamada (consistencia intra-documento) para
no romper correferencias en el texto.

**Nunca se enmascaran:** importes, porcentajes, fechas, ni el texto de las cláusulas.
El validador de dígito de control del NIF/CIF evita colisiones con cifras de dinero.

### Punto de inyección

Único, en `analizar_texto` (`src/arras_ai/agent.py`), justo tras la comprobación de
texto vacío y **antes** de construir `EstadoAnalisis`:

```python
texto = make_anonimizador(settings).anonimizar(texto).texto
```

Con esto, **todos** los nodos aguas abajo (`extraer`, `detectar_riesgos`) operan sobre
texto enmascarado, y la query de recuperación —que se construye de hechos ya extraídos
del texto enmascarado— tampoco contiene PII. Un solo cambio cubre analyzer + agente +
embeddings + evals (todos pasan por aquí).

### Fail-closed

Si el anonimizador lanza una excepción inesperada, `analizar_texto` **no** envía el
texto crudo: propaga un `AnalysisError` («No se pudo anonimizar el contrato»). En una
capa de privacidad, fallar cerrado (no analizar) es preferible a filtrar. Los detectores
por regex no deberían fallar; esto es una red de seguridad.

## Configuración

`Settings` (config.py):
- `anonimizar: bool = True` — alias `ARRAS_ANONIMIZAR`. Activado por defecto.
- `anonimizador_provider: str = "regex"` — alias `ARRAS_ANONIMIZADOR_PROVIDER`. Hoy solo
  `"regex"` (y `"nulo"` para desactivar explícitamente). `make_anonimizador` despacha por
  aquí; un valor desconocido → error claro.

`ARRAS_ANONIMIZAR=false` → `AnonimizadorNulo` (passthrough), útil para depurar o para
quien acepte el riesgo. La demo de Vercel lo deja en `true` (default).

## Salida / visualización (web)

El extractor, al operar sobre texto enmascarado, devolverá placeholders (o vacío) en
`partes.nombre` / `partes.nif` / `inmueble.*`. Como no restauramos:

- `web/src/lib/vista.ts`: la fila **«Partes»** muestra solo **roles** (`comprador,
  vendedor`), sin nombres. Cualquier valor con forma de placeholder (`/^«[A-Z_]+_\d+»$/`)
  o los campos de inmueble que sean placeholder se renderizan como `—`.
- Nota de transparencia en la UI (footer del formulario o del informe): *«Los datos
  personales (NIF, IBAN, email, teléfono, nombres detectables) se eliminan del texto
  antes de enviarlo para el análisis.»*

El modelo `InformeArras` **no cambia** (sigue teniendo `partes`, `inmueble`); solo cambia
cómo lo pinta la vista. Así el core queda agnóstico del formato de placeholder.

## Testing

- **Unitarios `RegexAnonimizador`** (nuevo `tests/test_anonimizacion.py`):
  - Enmascara NIF/NIE/CIF válidos; **no** enmascara números con formato de NIF pero
    control inválido; **no** toca importes (`280.000 €`), porcentajes ni fechas ISO.
  - Enmascara IBAN, email, teléfono, ref. catastral.
  - Nombres tras honorífico y junto a NIF.
  - Consistencia: mismo valor → mismo token; numeración incremental.
  - `recuentos` correctos; idempotencia (reanonimizar texto ya enmascarado no crea
    tokens nuevos de PII real).
  - `AnonimizadorNulo` devuelve el texto intacto y recuentos vacíos.
- **Wiring** (`tests/test_agent_*` o nuevo): con `ARRAS_ANONIMIZAR=true`, el texto que
  llega a `analyze_text` no contiene el NIF original (se inyecta un cliente/monkeypatch
  que captura el texto recibido).
- **Web** (`vista.test.ts`): `aVista` con partes que traen placeholders → la vista
  expone solo roles; campos placeholder → `—`.
- **Integración** (marcada, con API real): un contrato con NIF real analizado end-to-end
  sigue clasificando bien el tipo (el enmascarado no degrada el análisis).

Puertas: `ruff`, `ruff format`, `mypy --strict`, `pytest` (offline) verdes; build web +
vitest verdes.

## Backends futuros (documentados, NO implementados)

Detrás de `Anonimizador`, para self-host donde el peso no importa:
- **Presidio** (recomendado): NER + reconocedores de PII, soporte español, ligero-medio.
  Subiría el recall de nombres y podría cubrir direcciones.
- **LLM local de pesos abiertos** (p.ej. Gemma vía Ollama): máximo recall contextual,
  pero gigas + runtime; solo self-host con recursos. Admisible porque corre local (la
  PII no sale); no viola la regla «Claude para el análisis» al ser un componente
  auxiliar, no el LLM del producto.

Ambos se activarían con `ARRAS_ANONIMIZADOR_PROVIDER=presidio|gemma` sin tocar el resto
del código.

## Impacto en el deploy

- Cero dependencias nuevas (regex es stdlib) → no afecta al bundle de Vercel ni al
  `installCommand`. La demo lo hereda automáticamente al ir dentro de `analizar_texto`.
- `api/requirements.txt` no cambia.
