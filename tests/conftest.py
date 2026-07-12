"""Shared pytest fixtures.

Ensures the synthetic PDF fixtures exist (regenerating them if missing) so the
suite is self-contained, and provides sample data + a fake analysis object.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

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

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def _ensure_fixtures() -> None:
    """Generate the fixture PDFs once per session if any are missing."""
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import generate_fixtures  # noqa: PLC0415  (path set up just above)

    expected = [FIXTURES_DIR / f"{name}.pdf" for name in generate_fixtures.FIXTURES]
    if not all(p.is_file() for p in expected):
        generate_fixtures.main()


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def penitenciales_pdf(fixtures_dir: Path) -> Path:
    return fixtures_dir / "arras_penitenciales_clean.pdf"


@pytest.fixture
def sample_contract_text() -> str:
    return (
        "CONTRATO DE ARRAS PENITENCIALES. En Madrid, a 1 de enero de 2025. "
        "Las arras tienen carácter penitencial conforme al artículo 1454 del Código Civil. "
        "Precio total 200.000 €. Se entregan 20.000 € en concepto de arras."
    )


@pytest.fixture
def fake_analisis() -> AnalisisArras:
    """A fully-populated analysis object used by unit tests (no API call)."""
    return AnalisisArras(
        tipo_arras=TipoArras.penitenciales,
        confianza_tipo=0.95,
        justificacion_tipo="La cláusula segunda cita expresamente el artículo 1454.",
        partes=[
            Parte(nombre="María Fernández Ruiz", rol=RolParte.vendedor, nif="12345678Z"),
            Parte(nombre="Javier López Sánchez", rol=RolParte.comprador, nif="87654321X"),
        ],
        inmueble=Inmueble(
            direccion="calle Goya 78, 3º B, 28001 Madrid",
            referencia_catastral="9872023VH5797S0001WX",
        ),
        importes=Importes(precio_total=280000, importe_arras=28000, porcentaje_arras=10.0),
        fechas=Fechas(fecha_contrato="2025-03-15", fecha_limite_escritura="2025-06-15"),
        referencias_codigo_civil=[
            ReferenciaCodigoCivil(articulo="1454", contexto="carácter penitencial conforme al 1454")
        ],
        tiene_clausula_financiacion=True,
        resumen="Contrato de arras penitenciales sobre vivienda en Madrid por 280.000 €.",
    )


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
