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
