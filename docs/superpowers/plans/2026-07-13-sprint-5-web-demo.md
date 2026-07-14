# Sprint 5 (part 1) — Public Web Demo — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-page Astro web demo + a Vercel Python function (`POST /api/analyze`) that reuses the Python core unchanged, uses hosted Voyage embeddings, and is protected by input caps + (documented) per-IP Firewall rate limiting + an Anthropic spend cap.

**Architecture:** Two layers. The core (`src/arras_ai/`) is untouched. New: `api/analyze.py` (stdlib `BaseHTTPRequestHandler`, thin wrapper over a testable pure `procesar()` that validates/caps input and calls `arras_ai.agent.analizar_texto` with a Voyage-configured KB in `/tmp`); and `web/` (Astro + Tailwind, one page, one vanilla-TS island, a unit-tested `InformeArras → view-model` mapper). Single Vercel deployment via `vercel.json`.

**Tech Stack:** Python 3.11+ (stdlib http handler, existing `arras_ai`), Astro + Tailwind + TypeScript, vitest, Vercel (Node + Python runtimes), Voyage embeddings. Existing Python tooling (ruff/mypy/pytest) for the Python side.

## Global Constraints

- **The core `src/arras_ai/` MUST NOT change behavior.** The demo only *configures* it (env vars) and calls it. No edits to existing `arras_ai` modules except if a genuinely missing seam is found (flag it, don't refactor).
- Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, `uv run pytest` stay green; line 100. New Python (the pure logic in `api/analyze.py`) is ruff/mypy-clean. New Pydantic models (if any) use `ConfigDict(extra="forbid")`.
- **No real API calls / no model download in tests.** Python API tests mock `analizar_texto`. Frontend tests are pure (vitest on the mapper). No secrets in CI.
- Demo runtime config (Vercel env, NOT committed): `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, `ARRAS_EMBEDDING_PROVIDER=voyage`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.
- `api/` third-party deps (in `api/requirements.txt`): `anthropic`, `pdfplumber`, `pydantic`, `pydantic-settings`, `pyyaml`, `lancedb`, `voyageai`, `langgraph`. **NOT** `fastembed`.
- UI text in **Spanish**; the legal disclaimer must be present and visible. No marketing-speak.
- Input caps: text ≤ 30000 chars; PDF ≤ 5 MB decoded and ≤ 15 pages.
- The production deploy, `VOYAGE_API_KEY` provisioning, Firewall rule, and Anthropic spend cap are **user-account steps** — deliver wired code + config + a launch checklist, not a live deployment.
- Conventional Commits; every commit ends with `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Work on branch `feat/sprint-5-web-demo` (already checked out).

## File Structure

- `api/analyze.py` — **create**: pure `procesar(payload, *, analizar)` + `handler(BaseHTTPRequestHandler)`.
- `api/requirements.txt` — **create**: runtime deps for the function.
- `tests/test_api_analyze.py` — **create**: offline handler-logic tests (analysis mocked).
- `web/` — **create**: Astro app (`package.json`, `astro.config.mjs`, `tsconfig.json`, `tailwind.config.mjs`, `src/pages/index.astro`, `src/components/Analizador.astro`, `src/lib/vista.ts`, `src/lib/vista.test.ts`, `src/examples/*.ts`, `src/styles/global.css`).
- `vercel.json` — **create**: build + routing + runtimes.
- `web/README.md` — **create**: local dev + launch checklist.
- `.github/workflows/ci.yml` — **modify**: add a `web` build job.
- `README.md`, `ARCHITECTURE.md` — **modify**: Sprint 5 docs + roadmap tick.
- `.gitignore` — **modify**: `web/node_modules`, `web/dist`, `.vercel`.

---

## Task 1: Python API function `POST /api/analyze`

**Files:** Create `api/analyze.py`, `api/requirements.txt`, `tests/test_api_analyze.py`. Modify `.gitignore`.

**Interfaces:**
- Produces: `procesar(payload: dict[str, Any], *, analizar: Callable[[str], InformeArras]) -> tuple[int, dict[str, Any]]` — pure request logic (validation, caps, error mapping); returns `(status, body)`. `handler(BaseHTTPRequestHandler)` wraps it and injects the real `analizar_texto`.
- Constants: `MAX_TEXTO = 30_000`, `MAX_PDF_BYTES = 5 * 1024 * 1024`, `MAX_PDF_PAGINAS = 15`.

- [ ] **Step 1: Add `.gitignore` entries** — append:

```
# Web demo
web/node_modules/
web/dist/
.vercel/
```

- [ ] **Step 2: Write the failing test** — create `tests/test_api_analyze.py`:

```python
"""Offline tests for the /api/analyze request logic. Analysis is mocked; no network."""

from __future__ import annotations

import base64
import importlib.util
from pathlib import Path
from typing import Any

import pytest

from arras_ai.analyzer import AnalysisError
from arras_ai.models import (
    AnalisisArras,
    Fechas,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    TipoArras,
)
from arras_ai.pdf import PdfExtractionError

# api/ is not a package; load the module by path.
_ANALYZE = Path(__file__).resolve().parent.parent / "api" / "analyze.py"
_spec = importlib.util.spec_from_file_location("api_analyze", _ANALYZE)
assert _spec and _spec.loader
analyze = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(analyze)


def _informe() -> InformeArras:
    return InformeArras(
        analisis=AnalisisArras(
            tipo_arras=TipoArras.penitenciales, confianza_tipo=0.9, justificacion_tipo="j",
            partes=[], inmueble=Inmueble(), importes=Importes(), fechas=Fechas(),
            referencias_codigo_civil=[], tiene_clausula_financiacion=True, resumen="r",
        ),
        riesgos=[], nivel_riesgo_global=NivelRiesgo.bajo,
    )


def _ok(_texto: str) -> InformeArras:
    return _informe()


def test_texto_ok() -> None:
    status, body = analyze.procesar({"texto": "un contrato de arras"}, analizar=_ok)
    assert status == 200
    assert body["nivel_riesgo_global"] == "bajo"
    assert body["analisis"]["tipo_arras"] == "penitenciales"


def test_empty_input() -> None:
    status, body = analyze.procesar({}, analizar=_ok)
    assert status == 400 and "error" in body


def test_multiple_inputs() -> None:
    status, body = analyze.procesar(
        {"texto": "x", "pdf_base64": "y"}, analizar=_ok
    )
    assert status == 400


def test_texto_too_long() -> None:
    status, body = analyze.procesar({"texto": "x" * (analyze.MAX_TEXTO + 1)}, analizar=_ok)
    assert status == 413


def test_analysis_error_maps_422() -> None:
    def boom(_t: str) -> InformeArras:
        raise AnalysisError("no se pudo analizar")

    status, body = analyze.procesar({"texto": "contrato"}, analizar=boom)
    assert status == 422


def test_pdf_too_big() -> None:
    big = base64.b64encode(b"%PDF-1.4" + b"0" * (analyze.MAX_PDF_BYTES + 1)).decode()
    status, body = analyze.procesar({"pdf_base64": big}, analizar=_ok)
    assert status == 413


def test_pdf_extraction_error_maps_422(monkeypatch: pytest.MonkeyPatch) -> None:
    def bad_extract(_b: bytes) -> str:
        raise PdfExtractionError("sin texto")

    monkeypatch.setattr(analyze, "extraer_texto_pdf", bad_extract)
    payload = {"pdf_base64": base64.b64encode(b"%PDF-1.4 mini").decode()}
    status, body = analyze.procesar(payload, analizar=_ok)
    assert status == 422
```

- [ ] **Step 3: Run to verify it fails** — `uv run pytest tests/test_api_analyze.py -v` → FAIL (no `api/analyze.py`).

- [ ] **Step 4: Implement `api/requirements.txt`:**

```
anthropic>=0.69
pdfplumber>=0.11
pydantic>=2.9
pydantic-settings>=2.5
pyyaml>=6.0
lancedb>=0.13
voyageai>=0.2
langgraph>=0.2
```

- [ ] **Step 5: Implement `api/analyze.py`:**

```python
"""Vercel Python function: POST /api/analyze.

Thin HTTP wrapper over a pure `procesar()` (validation + caps + error mapping) that
calls the unchanged Python core. The demo configures hosted Voyage embeddings and a
/tmp index via environment variables; the core is otherwise untouched.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import os
import sys
from http.server import BaseHTTPRequestHandler
from typing import Any, Callable

# The repo `src/` is bundled with the function; make `arras_ai` importable.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from arras_ai.analyzer import AnalysisError  # noqa: E402
from arras_ai.models import InformeArras  # noqa: E402
from arras_ai.pdf import PdfExtractionError  # noqa: E402

MAX_TEXTO = 30_000
MAX_PDF_BYTES = 5 * 1024 * 1024
MAX_PDF_PAGINAS = 15


def extraer_texto_pdf(data: bytes) -> str:
    """Extract text from PDF bytes with the same engine/limits as the core CLI."""
    import pdfplumber

    paginas: list[str] = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if len(pdf.pages) > MAX_PDF_PAGINAS:
            raise PdfExtractionError(
                f"El PDF tiene demasiadas páginas (máximo {MAX_PDF_PAGINAS})."
            )
        for page in pdf.pages:
            texto = page.extract_text() or ""
            if texto.strip():
                paginas.append(texto)
    full = "\n\n".join(paginas).strip()
    if not full:
        raise PdfExtractionError("No se pudo extraer texto del PDF (¿es un escaneo sin OCR?).")
    return full


def _analizar_real(texto: str) -> InformeArras:
    # The core resolves the Voyage provider + /tmp index from the environment.
    from arras_ai.agent import analizar_texto

    return analizar_texto(texto)


def procesar(
    payload: dict[str, Any], *, analizar: Callable[[str], InformeArras]
) -> tuple[int, dict[str, Any]]:
    """Validate, cap, and run one analysis request. Pure except for `analizar`."""
    texto_in = payload.get("texto")
    pdf_in = payload.get("pdf_base64")

    if (texto_in is None) == (pdf_in is None):
        return 400, {"error": "Envía exactamente uno: 'texto' o 'pdf_base64'."}

    if texto_in is not None:
        if not isinstance(texto_in, str) or not texto_in.strip():
            return 400, {"error": "El campo 'texto' está vacío."}
        if len(texto_in) > MAX_TEXTO:
            return 413, {"error": f"El texto supera el máximo de {MAX_TEXTO} caracteres."}
        texto = texto_in
    else:
        if not isinstance(pdf_in, str):
            return 400, {"error": "El campo 'pdf_base64' no es válido."}
        try:
            data = base64.b64decode(pdf_in, validate=True)
        except (binascii.Error, ValueError):
            return 400, {"error": "El PDF no está correctamente codificado en base64."}
        if len(data) > MAX_PDF_BYTES:
            return 413, {"error": "El PDF supera el máximo de 5 MB."}
        try:
            texto = extraer_texto_pdf(data)
        except PdfExtractionError as exc:
            return 422, {"error": str(exc)}

    try:
        informe = analizar(texto)
    except (AnalysisError, PdfExtractionError) as exc:
        return 422, {"error": str(exc)}
    except Exception:  # upstream model/API failure
        return 502, {"error": "Error del servicio de análisis. Inténtalo de nuevo más tarde."}

    return 200, json.loads(informe.model_dump_json())


class handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler API)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            self._send(400, {"error": "Content-Type debe ser application/json."})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_PDF_BYTES * 2:
            self._send(413, {"error": "Cuerpo de la petición ausente o demasiado grande."})
            return
        try:
            payload = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, ValueError):
            self._send(400, {"error": "JSON inválido."})
            return
        if not isinstance(payload, dict):
            self._send(400, {"error": "El cuerpo debe ser un objeto JSON."})
            return
        status, body = procesar(payload, analizar=_analizar_real)
        self._send(status, body)

    def do_GET(self) -> None:  # noqa: N802
        self._send(405, {"error": "Usa POST para analizar."})
```

- [ ] **Step 6: Run to verify pass** — `uv run pytest tests/test_api_analyze.py -v && uv run ruff check api tests/test_api_analyze.py && uv run ruff format --check api tests/test_api_analyze.py` → PASS/clean. (Note: `api/` is not in the mypy `files` config; that's the pre-existing repo pattern for scripts. Run `uv run mypy api/analyze.py` manually to confirm it is well-typed, but it need not be added to the gate.)

- [ ] **Step 7: Commit**

```bash
git add api/ tests/test_api_analyze.py .gitignore
git commit -m "feat: /api/analyze Vercel function reusing the core (validation, caps, error mapping)" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 2: Astro scaffold + view-model mapper (unit-tested)

**Files:** Create `web/package.json`, `web/astro.config.mjs`, `web/tsconfig.json`, `web/tailwind.config.mjs`, `web/src/styles/global.css`, `web/src/lib/vista.ts`, `web/src/lib/vista.test.ts`, `web/vitest.config.ts`.

**Interfaces:**
- Produces: `web/src/lib/vista.ts` exporting `type Informe` (the `/api/analyze` response shape) and `aVista(informe: Informe): VistaModel` — a pure mapper producing the display model: `{ tipo, confianzaPct, nivel, nivelColor, datos: {label,valor}[], riesgos: {severidad, sevColor, categoria, descripcion, recomendacion, citas: string[]}[] }`. Risks sorted alta→media→baja. Citations flattened as `tipo==codigo_civil ? referencia : "<Tipo>: <referencia>"`.

- [ ] **Step 1: Scaffold Astro app** — create `web/package.json`:

```json
{
  "name": "arras-ai-web",
  "type": "module",
  "private": true,
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview",
    "test": "vitest run"
  },
  "dependencies": {
    "astro": "^4.15.0"
  },
  "devDependencies": {
    "@astrojs/tailwind": "^5.1.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.5.0",
    "vitest": "^2.0.0"
  }
}
```

`web/astro.config.mjs`:

```javascript
import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";

export default defineConfig({
  integrations: [tailwind()],
});
```

`web/tsconfig.json`:

```json
{
  "extends": "astro/tsconfigs/strict",
  "include": ["src", "*.mjs", "*.ts"]
}
```

`web/tailwind.config.mjs`:

```javascript
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/**/*.{astro,html,js,ts}"],
  theme: { extend: {} },
  plugins: [],
};
```

`web/src/styles/global.css`:

```css
@tailwind base;
@tailwind components;
@tailwind utilities;
```

`web/vitest.config.ts`:

```typescript
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
```

- [ ] **Step 2: Write the failing mapper test** — create `web/src/lib/vista.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { aVista, type Informe } from "./vista";

const base: Informe = {
  analisis: {
    tipo_arras: "confirmatorias",
    confianza_tipo: 0.78,
    justificacion_tipo: "a cuenta del precio",
    partes: [{ rol: "comprador", nombre: "Ana", nif: "1X" }],
    inmueble: { direccion: "calle X", referencia_catastral: null },
    importes: { precio_total: 190000, importe_arras: 10000, porcentaje_arras: 5.26, moneda: "EUR" },
    fechas: { fecha_contrato: "2025-04-03", fecha_limite_escritura: null, plazo_dias: null },
    tiene_clausula_financiacion: false,
  },
  riesgos: [
    { categoria: "fechas_mal_definidas", severidad: "media", descripcion: "d1", recomendacion: "r1", referencias: [] },
    {
      categoria: "falta_financiacion", severidad: "alta", descripcion: "d2", recomendacion: "r2",
      referencias: [{ tipo: "doctrina", referencia: "Cláusula suspensiva", texto: "t" }],
    },
  ],
  nivel_riesgo_global: "alto",
};

describe("aVista", () => {
  it("orders risks alta before media", () => {
    const v = aVista(base);
    expect(v.riesgos.map((r) => r.severidad)).toEqual(["alta", "media"]);
  });

  it("flattens citations with type label for non-CC", () => {
    const v = aVista(base);
    expect(v.riesgos[0].citas).toEqual(["Doctrina: Cláusula suspensiva"]);
  });

  it("formats confidence and nivel", () => {
    const v = aVista(base);
    expect(v.confianzaPct).toBe("78%");
    expect(v.nivel).toBe("ALTO");
  });
});
```

- [ ] **Step 3: Run to verify it fails** — from `web/`: `npm install` then `npm run test` → FAIL (no `vista.ts`).

- [ ] **Step 4: Implement `web/src/lib/vista.ts`:**

```typescript
export interface Fundamento {
  tipo: "codigo_civil" | "doctrina" | "jurisprudencia";
  referencia: string;
  texto: string;
}
export interface Riesgo {
  categoria: string;
  severidad: "alta" | "media" | "baja";
  descripcion: string;
  recomendacion: string;
  referencias: Fundamento[];
}
export interface Informe {
  analisis: {
    tipo_arras: string;
    confianza_tipo: number;
    justificacion_tipo: string;
    partes: { rol: string; nombre: string | null; nif: string | null }[];
    inmueble: { direccion: string | null; referencia_catastral: string | null };
    importes: {
      precio_total: number | null; importe_arras: number | null;
      porcentaje_arras: number | null; moneda: string;
    };
    fechas: {
      fecha_contrato: string | null; fecha_limite_escritura: string | null; plazo_dias: number | null;
    };
    tiene_clausula_financiacion: boolean;
  };
  riesgos: Riesgo[];
  nivel_riesgo_global: "alto" | "medio" | "bajo";
}

export interface VistaRiesgo {
  severidad: string;
  sevColor: string;
  categoria: string;
  descripcion: string;
  recomendacion: string;
  citas: string[];
}
export interface VistaModel {
  tipo: string;
  confianzaPct: string;
  justificacion: string;
  nivel: string;
  nivelColor: string;
  datos: { label: string; valor: string }[];
  riesgos: VistaRiesgo[];
}

const ORDEN_SEV: Record<string, number> = { alta: 0, media: 1, baja: 2 };
const SEV_COLOR: Record<string, string> = {
  alta: "text-red-600", media: "text-amber-600", baja: "text-slate-500",
};
const NIVEL_COLOR: Record<string, string> = {
  alto: "bg-red-600", medio: "bg-amber-500", bajo: "bg-emerald-600",
};
const TIPO_LABEL: Record<string, string> = { doctrina: "Doctrina", jurisprudencia: "Jurisprudencia" };

function dinero(v: number | null, moneda: string): string {
  return v === null ? "—" : `${v.toLocaleString("es-ES", { minimumFractionDigits: 2 })} ${moneda}`;
}

function cita(f: Fundamento): string {
  return f.tipo === "codigo_civil" ? f.referencia : `${TIPO_LABEL[f.tipo] ?? f.tipo}: ${f.referencia}`;
}

export function aVista(informe: Informe): VistaModel {
  const a = informe.analisis;
  const riesgos = [...informe.riesgos]
    .sort((x, y) => (ORDEN_SEV[x.severidad] ?? 9) - (ORDEN_SEV[y.severidad] ?? 9))
    .map((r) => ({
      severidad: r.severidad,
      sevColor: SEV_COLOR[r.severidad] ?? "text-slate-500",
      categoria: r.categoria,
      descripcion: r.descripcion,
      recomendacion: r.recomendacion,
      citas: r.referencias.map(cita),
    }));

  const datos = [
    { label: "Precio total", valor: dinero(a.importes.precio_total, a.importes.moneda) },
    { label: "Importe arras", valor: dinero(a.importes.importe_arras, a.importes.moneda) },
    { label: "Dirección", valor: a.inmueble.direccion ?? "—" },
    { label: "Ref. catastral", valor: a.inmueble.referencia_catastral ?? "—" },
    { label: "Fecha contrato", valor: a.fechas.fecha_contrato ?? "—" },
    { label: "Límite escritura", valor: a.fechas.fecha_limite_escritura ?? "—" },
    { label: "Cláusula financiación", valor: a.tiene_clausula_financiacion ? "sí" : "no" },
  ];

  return {
    tipo: a.tipo_arras,
    confianzaPct: `${Math.round(a.confianza_tipo * 100)}%`,
    justificacion: a.justificacion_tipo,
    nivel: informe.nivel_riesgo_global.toUpperCase(),
    nivelColor: NIVEL_COLOR[informe.nivel_riesgo_global] ?? "bg-slate-600",
    datos,
    riesgos,
  };
}
```

- [ ] **Step 5: Run to verify pass** — from `web/`: `npm run test` → PASS; `npm run build` → succeeds (an empty/placeholder page is fine at this task; a real page comes in Task 3, but `astro build` needs at least one page — create a minimal `src/pages/index.astro` with a placeholder `<h1>` now and replace it in Task 3). Add:

```astro
---
import "../styles/global.css";
---
<html lang="es"><head><meta charset="utf-8" /><title>arras-ai</title></head>
<body><h1>arras-ai (placeholder)</h1></body></html>
```

- [ ] **Step 6: Commit**

```bash
git add web/
git commit -m "feat: Astro scaffold and unit-tested InformeArras view-model mapper" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 3: Astro UI — page, analyze island, examples, results

**Files:** Modify `web/src/pages/index.astro`. Create `web/src/components/Analizador.astro`, `web/src/examples/index.ts`.

**Interfaces:** Consumes `aVista`/`Informe` from `web/src/lib/vista.ts`. The island `fetch`es `POST /api/analyze` and renders the view-model. Examples are bundled Spanish contract texts submitted as `texto`.

- [ ] **Step 1: Create example texts** — `web/src/examples/index.ts` (2 short synthetic contracts; reuse the flavor of `data/evals/casos.yaml` — a clean penitenciales and a problematic confirmatorias):

```typescript
export interface Ejemplo { id: string; etiqueta: string; texto: string; }

export const EJEMPLOS: Ejemplo[] = [
  {
    id: "penitenciales",
    etiqueta: "Penitenciales (bien redactado)",
    texto:
      "CONTRATO DE ARRAS PENITENCIALES. En Madrid, a 15 de marzo de 2025. Dña. María " +
      "Fernández (NIF 12345678Z), vendedora, y D. Javier López (NIF 87654321X), comprador, " +
      "sobre la vivienda en calle Goya 78, 3ºB, 28001 Madrid, referencia catastral " +
      "9872023VH5797S0001WX, libre de cargas, precio 280.000 €. El comprador entrega 28.000 € " +
      "en concepto de arras penitenciales conforme al artículo 1454 del Código Civil. La " +
      "escritura se otorgará antes del 15 de junio de 2025. La eficacia se condiciona a la " +
      "obtención de financiación hipotecaria en 45 días.",
  },
  {
    id: "confirmatorias",
    etiqueta: "Confirmatorias (con problemas)",
    texto:
      "CONTRATO PRIVADO DE COMPRAVENTA CON SEÑAL. En Valencia, a 3 de abril de 2025. D. Antonio " +
      "Martínez (DNI 44556677P), vendedor, y Dña. Laura Gómez (DNI 11223344Q), compradora, sobre " +
      "el piso en avenida del Puerto 210, 5º, Valencia. Precio 190.000 €. La compradora entrega " +
      "10.000 € en concepto de señal y a cuenta del precio total; dicha cantidad confirma el " +
      "contrato. Las partes elevarán a escritura pública en el plazo más breve posible. Los " +
      "gastos se distribuirán conforme a la ley.",
  },
];
```

- [ ] **Step 2: Create the island** — `web/src/components/Analizador.astro`. It renders the input controls + a results container, and a client `<script>` that handles examples, PDF→base64, the fetch, loading/error states, and renders `aVista(...)`. Use Tailwind classes for a clean layout.

```astro
---
import { EJEMPLOS } from "../examples";
---
<section class="mx-auto max-w-3xl px-4">
  <div class="flex gap-2 mb-3" id="tabs">
    <button data-modo="texto" class="tab px-3 py-1 rounded bg-slate-900 text-white">Pegar texto</button>
    <button data-modo="pdf" class="tab px-3 py-1 rounded bg-slate-200">Subir PDF</button>
  </div>

  <div id="panel-texto">
    <textarea id="texto" rows="10" maxlength="30000"
      class="w-full rounded border border-slate-300 p-3 font-mono text-sm"
      placeholder="Pega aquí el texto del contrato de arras…"></textarea>
    <div class="mt-2 flex flex-wrap gap-2 text-sm">
      <span class="text-slate-500 self-center">Ejemplos:</span>
      {EJEMPLOS.map((e) => (
        <button class="ejemplo rounded border border-slate-300 px-2 py-1" data-id={e.id}>{e.etiqueta}</button>
      ))}
    </div>
  </div>

  <div id="panel-pdf" class="hidden">
    <input id="pdf" type="file" accept="application/pdf" class="block w-full text-sm" />
    <p class="text-xs text-slate-500 mt-1">Máximo 5 MB / 15 páginas.</p>
  </div>

  <button id="analizar" class="mt-4 rounded bg-slate-900 px-4 py-2 text-white disabled:opacity-50">
    Analizar
  </button>

  <p id="error" class="mt-3 hidden rounded bg-red-50 p-3 text-sm text-red-700"></p>
  <div id="cargando" class="mt-4 hidden text-slate-500">Analizando…</div>
  <div id="resultado" class="mt-6"></div>
</section>

<script>
  import { aVista, type Informe } from "../lib/vista";
  import { EJEMPLOS } from "../examples";

  const $ = (id: string) => document.getElementById(id)!;
  const texto = $("texto") as HTMLTextAreaElement;
  const pdf = $("pdf") as HTMLInputElement;
  let modo: "texto" | "pdf" = "texto";

  document.querySelectorAll<HTMLButtonElement>(".tab").forEach((b) =>
    b.addEventListener("click", () => {
      modo = b.dataset.modo as "texto" | "pdf";
      $("panel-texto").classList.toggle("hidden", modo !== "texto");
      $("panel-pdf").classList.toggle("hidden", modo !== "pdf");
      document.querySelectorAll<HTMLButtonElement>(".tab").forEach((t) => {
        const on = t.dataset.modo === modo;
        t.className = `tab px-3 py-1 rounded ${on ? "bg-slate-900 text-white" : "bg-slate-200"}`;
      });
    }),
  );

  document.querySelectorAll<HTMLButtonElement>(".ejemplo").forEach((b) =>
    b.addEventListener("click", () => {
      const e = EJEMPLOS.find((x) => x.id === b.dataset.id);
      if (e) texto.value = e.texto;
    }),
  );

  function mostrarError(msg: string) {
    const el = $("error");
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  async function fileToBase64(f: File): Promise<string> {
    const buf = new Uint8Array(await f.arrayBuffer());
    let bin = "";
    for (const b of buf) bin += String.fromCharCode(b);
    return btoa(bin);
  }

  async function analizar() {
    $("error").classList.add("hidden");
    $("resultado").innerHTML = "";
    let body: Record<string, string>;
    if (modo === "texto") {
      if (!texto.value.trim()) return mostrarError("Pega el texto del contrato.");
      body = { texto: texto.value };
    } else {
      const f = pdf.files?.[0];
      if (!f) return mostrarError("Selecciona un PDF.");
      if (f.size > 5 * 1024 * 1024) return mostrarError("El PDF supera 5 MB.");
      body = { pdf_base64: await fileToBase64(f) };
    }
    ($("analizar") as HTMLButtonElement).disabled = true;
    $("cargando").classList.remove("hidden");
    try {
      const res = await fetch("/api/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) return mostrarError(data.error ?? "Error inesperado.");
      render(aVista(data as Informe));
    } catch {
      mostrarError("No se pudo conectar con el servicio.");
    } finally {
      ($("analizar") as HTMLButtonElement).disabled = false;
      $("cargando").classList.add("hidden");
    }
  }

  function esc(s: string): string {
    return s.replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" })[c]!);
  }

  function render(v: ReturnType<typeof aVista>) {
    const datos = v.datos.map((d) => `<div class="flex justify-between border-b py-1"><span class="text-slate-500">${esc(d.label)}</span><span>${esc(d.valor)}</span></div>`).join("");
    const riesgos = v.riesgos.length
      ? v.riesgos.map((r) => `<div class="rounded border border-slate-200 p-3 mb-2">
          <div class="${r.sevColor} font-semibold">${esc(r.severidad)} · ${esc(r.categoria)}</div>
          <p class="text-sm mt-1">${esc(r.descripcion)}</p>
          <p class="text-sm mt-1"><b>Recomendación:</b> ${esc(r.recomendacion)}</p>
          ${r.citas.length ? `<p class="text-xs text-slate-500 mt-1">Cf. ${r.citas.map(esc).join(" · ")}</p>` : ""}
        </div>`).join("")
      : `<p class="text-slate-500">Sin riesgos detectados.</p>`;
    $("resultado").innerHTML = `
      <div class="rounded-lg border border-slate-200 p-4">
        <div class="text-lg font-semibold">Tipo de arras: ${esc(v.tipo)} <span class="text-slate-500 text-sm">(confianza ${esc(v.confianzaPct)})</span></div>
        <p class="text-sm text-slate-600 mt-1">${esc(v.justificacion)}</p>
      </div>
      <div class="mt-4 rounded-lg border border-slate-200 p-4">${datos}</div>
      <div class="mt-4 inline-block rounded ${v.nivelColor} px-3 py-1 text-white font-semibold">Nivel de riesgo: ${esc(v.nivel)}</div>
      <div class="mt-3">${riesgos}</div>`;
  }

  $("analizar").addEventListener("click", analizar);
</script>
```

- [ ] **Step 3: Build the page** — replace `web/src/pages/index.astro`:

```astro
---
import "../styles/global.css";
import Analizador from "../components/Analizador.astro";
---
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>arras-ai — analiza tu contrato de arras</title>
  </head>
  <body class="bg-slate-50 text-slate-900">
    <main class="py-10">
      <header class="mx-auto max-w-3xl px-4 mb-6">
        <h1 class="text-2xl font-bold">arras-ai</h1>
        <p class="text-slate-600 mt-1">
          Analiza un contrato de arras: detecta el tipo, extrae los datos clave y señala
          los riesgos, con referencias al Código Civil.
        </p>
        <p class="text-xs text-slate-500 mt-2">
          Demo pública con límites de uso. <a class="underline" href="#disclaimer">No es asesoramiento legal.</a>
        </p>
      </header>
      <Analizador />
      <footer id="disclaimer" class="mx-auto max-w-3xl px-4 mt-10 border-t pt-4 text-xs text-slate-500">
        <strong>Aviso legal:</strong> arras-ai es una herramienta experimental y NO sustituye el
        asesoramiento de un abogado o notario. Puede cometer errores; verifica siempre el resultado
        con el contrato original.
      </footer>
    </main>
  </body>
</html>
```

- [ ] **Step 4: Verify** — from `web/`: `npm run build` → succeeds; `npm run test` → still passes. (No live API in build; the island only calls `/api/analyze` at runtime.)

- [ ] **Step 5: Commit**

```bash
git add web/
git commit -m "feat: web demo UI — analyze form, examples, and risk-report results view" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 4: Vercel config + local dev/launch docs

**Files:** Create `vercel.json`, `web/README.md`.

- [ ] **Step 1: Create `vercel.json`** (build the Astro app in `web/`, serve `api/` as Python functions, route `/api/*` to them, everything else to the Astro output):

```json
{
  "$schema": "https://openapi.vercel.sh/vercel.json",
  "buildCommand": "cd web && npm install && npm run build",
  "outputDirectory": "web/dist"
}
```

Vercel auto-detects `api/*.py` as Python Serverless Functions and installs
`api/requirements.txt`; no explicit `runtime` entry is needed (default timeout is
generous). **Before finalizing, verify the current Vercel config against the docs**
(the `functions`/`runtime` schema and the Python version pin have changed over
time) — use the `vercel:vercel-cli` / `vercel:vercel-functions` skill or
`vercel docs`. If a specific Python version or `maxDuration` is required, add a
`functions` block per the current schema; otherwise keep this minimal form.

- [ ] **Step 2: Create `web/README.md`** with local dev + the launch checklist:

```markdown
# arras-ai web demo

Astro frontend + a Vercel Python function (`/api/analyze`) that reuses the Python core.

## Local development

```bash
# from the repo root, with the Vercel CLI installed and env vars set (see below):
vercel dev
```

`vercel dev` serves the Astro app and the Python function together. You need, in a
`.env` (or your shell): `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
`ARRAS_EMBEDDING_PROVIDER=voyage`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.

Frontend-only work: `cd web && npm install && npm run dev` (the `/api/analyze` calls
will 404 without `vercel dev`).

## How the demo differs from the core

The self-host core uses local `fastembed` embeddings. The demo uses hosted **Voyage**
embeddings (no 2 GB model, serverless-friendly) via the same `EmbeddingModel`
interface; the 5-pattern index is built lazily in `/tmp` on the first request.

## Launch checklist (production)

1. `vercel link` this repo to a Vercel project.
2. Set project env vars (Production): `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`,
   `ARRAS_EMBEDDING_PROVIDER=voyage`, `ARRAS_KB_INDEX_DIR=/tmp/arras_kb_index`.
3. In the Anthropic Console, set a **monthly spend limit** on the key (hard cost cap).
4. In the Vercel dashboard → Firewall, add a **per-IP rate-limit rule** on
   `/api/analyze` (e.g. 5 requests/minute per IP).
5. `vercel deploy --prod`.
6. Put the resulting URL in the root `README.md` "Try it" section.
```

- [ ] **Step 3: Verify** — `python -c "import json; json.load(open('vercel.json'))"` parses; confirm `web/README.md` renders. No gate impact.

- [ ] **Step 4: Commit**

```bash
git add vercel.json web/README.md
git commit -m "feat: Vercel config and web demo dev/launch docs" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Task 5: CI web job + project docs

**Files:** Modify `.github/workflows/ci.yml`, `README.md`, `ARCHITECTURE.md`.

- [ ] **Step 1: Add a `web` CI job** — in `.github/workflows/ci.yml`, add a second job (the existing Python job stays as-is):

```yaml
  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - run: npm install
      - run: npm run test
      - run: npm run build
```

- [ ] **Step 2: README "Try it" + roadmap** — in `README.md`: add a short "Try it" section near the top (placeholder for the demo URL: "Live demo: _coming soon_ — see `web/README.md` to run it locally or deploy your own"), and update the roadmap so Sprint 5 shows the web demo done and CLI/Docker packaging remaining, e.g. `- [~] **Sprint 5 — Interfaces.** Web demo (done); CLI/Docker packaging (next).`

- [ ] **Step 3: ARCHITECTURE Sprint 5 section** — document: the two-layer split (self-host core with local fastembed vs the Vercel demo with hosted Voyage embeddings through the `EmbeddingModel` abstraction — the abstraction paying off); the serverless `/tmp` lazy-index approach (no 2 GB model, read-only FS); the thin `api/analyze.py` wrapper over a pure `procesar()` reusing the unchanged core; and the cost model (input caps + Vercel Firewall per-IP + Anthropic spend cap). ~250 words, matching the file's tone. Accurate to the code.

- [ ] **Step 4: Verify** — `uv run pytest -q` (Python unchanged, green); from `web/`: `npm run build && npm run test` green. Confirm the CI YAML is valid (`python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`).

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/ci.yml README.md ARCHITECTURE.md
git commit -m "ci: build/test the web demo; docs: document Sprint 5 web demo" \
  -m "Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Final verification (after all tasks)

- [ ] `uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest` — green (the core is unchanged; `api/analyze.py` tests pass offline). `uv run mypy api/analyze.py` clean.
- [ ] From `web/`: `npm install && npm run test && npm run build` — all green.
- [ ] `src/arras_ai/` has no behavior changes (diff touches only new files + docs/CI).
- [ ] **User-gated (documented, not done here):** `vercel dev` end-to-end with real keys; production deploy; `VOYAGE_API_KEY`; Firewall rule; Anthropic spend cap — all in `web/README.md`'s launch checklist.
- [ ] Push branch and open a PR: `git push -u origin feat/sprint-5-web-demo && gh pr create --fill`.
```
