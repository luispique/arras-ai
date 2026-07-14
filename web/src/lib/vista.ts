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

  const partes = a.partes.length
    ? a.partes.map((p) => `${p.rol}: ${p.nombre ?? "—"}`).join(", ")
    : "—";

  const datos = [
    { label: "Partes", valor: partes },
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
