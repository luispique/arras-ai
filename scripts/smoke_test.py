"""Manual smoke test: run the analyzer over the three synthetic fixtures with a
real Claude call and check the output against what we expect.

Unlike the pytest suite this is a developer tool, not CI — it makes real API
calls and prints a human-readable report. Needs ANTHROPIC_API_KEY (it reads
.env automatically via the same settings the CLI uses).

    uv run python scripts/smoke_test.py
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from arras_ai.agent import analizar_pdf
from arras_ai.models import CategoriaRiesgo, InformeArras, NivelRiesgo, Severidad, TipoArras

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"

Check = Callable[[InformeArras], bool]


@dataclass
class Case:
    fixture: str
    label: str
    # hard expectations: must pass, or the case fails
    hard: dict[str, Check] = field(default_factory=dict)
    # soft expectations: reported but do not fail the run (judgement calls)
    soft: dict[str, Check] = field(default_factory=dict)


def approx(value: float | None, target: float, rel: float = 0.02) -> bool:
    return value is not None and abs(value - target) <= abs(target) * rel


CASES = [
    Case(
        fixture="arras_penitenciales_clean.pdf",
        label="Penitenciales (well-drafted)",
        hard={
            "tipo == penitenciales": lambda i: i.analisis.tipo_arras is TipoArras.penitenciales,
            "confianza >= 0.7": lambda i: i.analisis.confianza_tipo >= 0.7,
            "cita art. 1454": lambda i: any(
                r.articulo == "1454" for r in i.analisis.referencias_codigo_civil
            ),
            "precio_total ~ 280000": lambda i: approx(i.analisis.importes.precio_total, 280000),
            "importe_arras ~ 28000": lambda i: approx(i.analisis.importes.importe_arras, 28000),
            "tiene_clausula_financiacion == True": (
                lambda i: i.analisis.tiene_clausula_financiacion is True
            ),
            "2 partes": lambda i: len(i.analisis.partes) == 2,
            "sin riesgos de severidad alta": lambda i: all(
                r.severidad is not Severidad.alta for r in i.riesgos
            ),
        },
        soft={
            "ref. catastral detectada": lambda i: bool(i.analisis.inmueble.referencia_catastral),
        },
    ),
    Case(
        fixture="arras_confirmatorias_problematic.pdf",
        label="Confirmatorias (problematic)",
        hard={
            "tipo == confirmatorias": lambda i: i.analisis.tipo_arras is TipoArras.confirmatorias,
            "precio_total ~ 190000": lambda i: approx(i.analisis.importes.precio_total, 190000),
            "importe_arras ~ 10000": lambda i: approx(i.analisis.importes.importe_arras, 10000),
            "NO cláusula financiación": lambda i: i.analisis.tiene_clausula_financiacion is False,
            "riesgo falta_financiacion detectado": lambda i: any(
                r.categoria is CategoriaRiesgo.falta_financiacion for r in i.riesgos
            ),
            "nivel_riesgo_global == alto": lambda i: i.nivel_riesgo_global is NivelRiesgo.alto,
        },
        soft={
            "sin ref. catastral (no consta)": (
                lambda i: i.analisis.inmueble.referencia_catastral is None
            ),
            "sin fecha límite (plazo vago)": (
                lambda i: i.analisis.fechas.fecha_limite_escritura is None
            ),
        },
    ),
    Case(
        fixture="arras_ambiguas.pdf",
        label="Ambiguous (type not stated)",
        hard={
            "precio_total ~ 210000": lambda i: approx(i.analisis.importes.precio_total, 210000),
            "importe_arras ~ 15000": lambda i: approx(i.analisis.importes.importe_arras, 15000),
            "NO cláusula financiación": lambda i: i.analisis.tiene_clausula_financiacion is False,
            "riesgo tipo_ambiguo detectado": lambda i: any(
                r.categoria is CategoriaRiesgo.tipo_ambiguo for r in i.riesgos
            ),
        },
        soft={
            # The key judgement call: an unspecified contract SHOULD read as
            # no_especificado. confirmatorias is the legal default but a confident
            # 'confirmatorias' here would mean the prompt over-applies the default.
            "tipo == no_especificado": lambda i: i.analisis.tipo_arras is TipoArras.no_especificado,
            "plazo_dias == 60": lambda i: i.analisis.fechas.plazo_dias == 60,
        },
    ),
]


def _run_case(case: Case) -> bool:
    print(f"\n{'=' * 70}\n{case.label}  ({case.fixture})\n{'=' * 70}")
    informe = analizar_pdf(FIXTURES_DIR / case.fixture)
    analisis = informe.analisis

    print(
        f"  -> tipo_arras       : {analisis.tipo_arras.value} "
        f"(confianza {analisis.confianza_tipo:.0%})"
    )
    print(f"  -> financiacion      : {analisis.tiene_clausula_financiacion}")
    print(
        f"  -> precio/arras      : {analisis.importes.precio_total} / "
        f"{analisis.importes.importe_arras}"
    )
    print(f"  -> partes            : {len(analisis.partes)}")
    print(f"  -> refs CC           : {[r.articulo for r in analisis.referencias_codigo_civil]}")
    print(f"  -> ref catastral     : {analisis.inmueble.referencia_catastral}")
    print(
        f"  -> plazo/limite      : {analisis.fechas.plazo_dias} / "
        f"{analisis.fechas.fecha_limite_escritura}"
    )
    print(f"  -> justificacion     : {analisis.justificacion_tipo[:200]}")
    print(f"  -> nivel_riesgo       : {informe.nivel_riesgo_global.value}")
    print(
        f"  -> riesgos            : "
        f"{[(r.categoria.value, r.severidad.value) for r in informe.riesgos]}"
    )

    def report(title: str, checks: dict[str, Check]) -> list[bool]:
        results = []
        for name, check in checks.items():
            try:
                ok = check(informe)
            except Exception:  # noqa: BLE001 - a check that errors counts as failing
                ok = False
            results.append(ok)
            print(f"    {'PASS' if ok else 'FAIL'}  [{title}] {name}")
        return results

    hard_results = report("hard", case.hard)
    report("soft", case.soft)
    return all(hard_results)


def main() -> int:
    results: dict[str, bool] = {c.label: _run_case(c) for c in CASES}
    print(f"\n{'=' * 70}\nSUMMARY (hard checks)\n{'=' * 70}")
    for label, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    passed = sum(results.values())
    print(f"\n{passed}/{len(results)} cases passed their hard checks.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
