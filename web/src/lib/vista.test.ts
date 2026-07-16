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

  it("renders the Partes row from analisis.partes", () => {
    const v = aVista(base);
    expect(v.datos[0]).toEqual({ label: "Partes", valor: "comprador: Ana" });
  });

  it("renders '—' for Partes when there are no parties", () => {
    const informe: Informe = {
      ...base,
      analisis: { ...base.analisis, partes: [] },
    };
    const v = aVista(informe);
    expect(v.datos[0]).toEqual({ label: "Partes", valor: "—" });
  });

  it("passes a codigo_civil citation through as the bare referencia", () => {
    const informe: Informe = {
      ...base,
      riesgos: [
        {
          categoria: "otro",
          severidad: "media",
          descripcion: "d",
          recomendacion: "r",
          referencias: [{ tipo: "codigo_civil", referencia: "Art. 1454 CC", texto: "t" }],
        },
      ],
    };
    const v = aVista(informe);
    expect(v.riesgos[0].citas).toEqual(["Art. 1454 CC"]);
  });

  it("formats a null precio_total as '—' in datos", () => {
    const informe: Informe = {
      ...base,
      analisis: {
        ...base.analisis,
        importes: { ...base.analisis.importes, precio_total: null },
      },
    };
    const v = aVista(informe);
    const precio = v.datos.find((d) => d.label === "Precio total");
    expect(precio?.valor).toBe("—");
  });

  it("orders baja severity after media", () => {
    const informe: Informe = {
      ...base,
      riesgos: [
        { categoria: "c1", severidad: "baja", descripcion: "d1", recomendacion: "r1", referencias: [] },
        { categoria: "c2", severidad: "media", descripcion: "d2", recomendacion: "r2", referencias: [] },
      ],
    };
    const v = aVista(informe);
    expect(v.riesgos.map((r) => r.severidad)).toEqual(["media", "baja"]);
  });

  it("falls back gracefully for an unknown severidad/nivel without crashing", () => {
    const informe = {
      ...base,
      riesgos: [
        {
          categoria: "c1",
          severidad: "desconocida" as unknown as Informe["riesgos"][number]["severidad"],
          descripcion: "d1",
          recomendacion: "r1",
          referencias: [],
        },
      ],
      nivel_riesgo_global: "inexistente" as unknown as Informe["nivel_riesgo_global"],
    };
    expect(() => aVista(informe)).not.toThrow();
    const v = aVista(informe);
    expect(v.riesgos[0].sevBadge).toBe("bg-surface-alt text-ink-muted");
    expect(v.nivelBadge).toBe("bg-surface-alt text-ink-muted");
  });
});
