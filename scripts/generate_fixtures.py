"""Generate the synthetic contract PDFs used as test fixtures.

Run with: `uv run python scripts/generate_fixtures.py`

The contracts below are 100% synthetic. Names, NIFs, addresses and cadastral
references are invented and do not correspond to real people or properties. They
are deliberately written to exercise specific analysis cases (a clean
penitenciales contract, a problematic confirmatorias one, and an ambiguous one).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures"


# --- arras_penitenciales_clean -------------------------------------------------
# Well-drafted: explicit penitenciales + art. 1454, cadastral ref, financing
# contingency clause, clear dates and amounts.
PENITENCIALES_CLEAN = """\
CONTRATO DE ARRAS PENITENCIALES

En Madrid, a 15 de marzo de 2025.

REUNIDOS

De una parte, DÑA. MARÍA FERNÁNDEZ RUIZ, mayor de edad, con NIF 12345678Z y \
domicilio en calle Alcalá 100, 28009 Madrid, en adelante la PARTE VENDEDORA.

De otra parte, D. JAVIER LÓPEZ SÁNCHEZ, mayor de edad, con NIF 87654321X y \
domicilio en calle Serrano 45, 28001 Madrid, en adelante la PARTE COMPRADORA.

EXPONEN

I. Que la parte vendedora es propietaria del pleno dominio de la vivienda sita en \
calle Goya 78, 3º B, 28001 Madrid, con una superficie construida de 95 metros \
cuadrados, referencia catastral 9872023VH5797S0001WX, inscrita en el Registro de \
la Propiedad nº 4 de Madrid, finca registral 45.678, libre de cargas y gravámenes.

II. Que ambas partes han convenido la compraventa de dicha vivienda por un precio \
total de DOSCIENTOS OCHENTA MIL EUROS (280.000 €).

CLÁUSULAS

PRIMERA. En este acto la parte compradora entrega a la parte vendedora, en concepto \
de ARRAS PENITENCIALES, la cantidad de VEINTIOCHO MIL EUROS (28.000 €), que se \
imputará al precio final de la compraventa.

SEGUNDA. Las presentes arras tienen carácter penitencial conforme al artículo 1454 \
del Código Civil. En consecuencia, si la parte compradora desistiera de la \
compraventa, perderá las cantidades entregadas. Si fuera la parte vendedora quien \
desistiera, deberá devolver por duplicado las cantidades recibidas.

TERCERA. La escritura pública de compraventa se otorgará ante notario a más tardar \
el día 15 de junio de 2025.

CUARTA. La eficacia del presente contrato queda sujeta a la condición suspensiva de \
que la parte compradora obtenga financiación hipotecaria por importe mínimo de \
200.000 €. Si transcurridos 45 días la entidad financiera denegara la hipoteca, el \
contrato quedará resuelto y la parte vendedora devolverá íntegramente las arras.

QUINTA. Los gastos e impuestos se distribuirán conforme a la ley.

Y en prueba de conformidad, firman por duplicado en el lugar y fecha indicados.
"""


# --- arras_confirmatorias_problematic -----------------------------------------
# Confirmatorias by wording ("a cuenta del precio"), but riddled with the common
# problems: no financing contingency, vague deadline, missing cadastral reference.
CONFIRMATORIAS_PROBLEMATIC = """\
CONTRATO PRIVADO DE COMPRAVENTA CON ENTREGA DE SEÑAL

En Valencia, a 3 de abril de 2025.

De una parte D. ANTONIO MARTÍNEZ GIL, con DNI 44556677P (el VENDEDOR), y de otra \
parte DÑA. LAURA GÓMEZ TORRES, con DNI 11223344Q (la COMPRADORA), acuerdan la \
compraventa del piso situado en avenida del Puerto 210, 5º, Valencia.

El precio de la operación se fija en CIENTO NOVENTA MIL EUROS (190.000 euros).

La compradora entrega en este acto la cantidad de DIEZ MIL EUROS (10.000 €) en \
concepto de señal y como parte del precio, a cuenta del precio total pactado. Dicha \
cantidad confirma el presente contrato de compraventa.

Las partes se comprometen a elevar a escritura pública la presente compraventa en el \
plazo más breve posible, una vez la parte vendedora tenga la documentación en regla.

Los gastos serán por cuenta de quien corresponda.

Ambas partes firman en señal de conformidad.
"""


# --- arras_ambiguas ------------------------------------------------------------
# Uses the word "arras" but never states the modality; the deposit language is
# neutral. Should classify as no_especificado with lower confidence.
AMBIGUAS = """\
DOCUMENTO DE ARRAS

En Sevilla, a 20 de febrero de 2025.

Los abajo firmantes, D. CARLOS RUIZ DELGADO (con NIF 55667788M), como parte \
transmitente, y DÑA. ELENA NAVARRO PRIETO (con NIF 99887766L), como parte \
adquirente, manifiestan su voluntad de comprar y vender, respectivamente, la \
vivienda ubicada en calle Betis 12, bajo, 41010 Sevilla.

Se pacta un precio de DOSCIENTOS DIEZ MIL EUROS (210.000 €).

En garantía del cumplimiento del presente acuerdo, la parte adquirente hace entrega \
de la cantidad de QUINCE MIL EUROS (15.000 €) en concepto de arras.

Las partes acuerdan formalizar la compraventa ante notario en el plazo de sesenta \
(60) días naturales desde la firma del presente documento.

Y para que conste, firman el presente documento.
"""


FIXTURES: dict[str, str] = {
    "arras_penitenciales_clean": PENITENCIALES_CLEAN,
    "arras_confirmatorias_problematic": CONFIRMATORIAS_PROBLEMATIC,
    "arras_ambiguas": AMBIGUAS,
}


def _build_pdf(text: str, out_path: Path) -> None:
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=15,
        spaceAfter=8,
    )
    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2.5 * cm,
        rightMargin=2.5 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2.5 * cm,
        title=out_path.stem,
    )
    flowables: list[object] = []
    for block in text.split("\n\n"):
        flowables.append(Paragraph(block.replace("\n", " ").strip(), body))
        flowables.append(Spacer(1, 4))
    doc.build(flowables)


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in FIXTURES.items():
        pdf_path = FIXTURES_DIR / f"{name}.pdf"
        _build_pdf(text, pdf_path)
        print(f"wrote {pdf_path.relative_to(FIXTURES_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
