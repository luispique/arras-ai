"""Typed schema for the analysis of a Spanish contrato de arras.

Field names and descriptions are kept in Spanish on purpose: they map directly to
the legal domain (`tipo_arras`, `precio_total`, `referencia_catastral`) and the
descriptions double as instructions the model reads when producing structured
output. See ARCHITECTURE.md for the language rationale.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TipoArras(StrEnum):
    """The three legal modalities of arras under the Spanish Código Civil.

    `no_especificado` is used when the contract does not state the type clearly.
    Courts default an unspecified contract to `confirmatorias` (the most binding),
    so surfacing this ambiguity is itself a finding.
    """

    penitenciales = "penitenciales"  # art. 1454 CC — allow either party to withdraw
    confirmatorias = "confirmatorias"  # payment on account, no right to withdraw
    penales = "penales"  # art. 1152/1153 CC — penalty clause, contract still enforceable
    no_especificado = "no_especificado"


class RolParte(StrEnum):
    comprador = "comprador"
    vendedor = "vendedor"
    otro = "otro"


class Parte(BaseModel):
    """Una parte firmante del contrato."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, description="Nombre completo o razón social")
    rol: RolParte = Field(description="Rol de la parte en la compraventa")
    nif: str | None = Field(default=None, description="NIF, NIE o CIF si aparece")
    domicilio: str | None = Field(default=None, description="Domicilio si aparece")


class Inmueble(BaseModel):
    """El inmueble objeto de la compraventa."""

    model_config = ConfigDict(extra="forbid")

    direccion: str | None = Field(default=None, description="Dirección completa del inmueble")
    referencia_catastral: str | None = Field(
        default=None, description="Referencia catastral de 20 caracteres si aparece"
    )
    descripcion: str | None = Field(
        default=None, description="Descripción registral o física (superficie, linderos, etc.)"
    )
    cargas: str | None = Field(
        default=None,
        description="Cargas o gravámenes registrales mencionados (hipotecas, embargos). "
        "null si el contrato no dice nada.",
    )


class Importes(BaseModel):
    """Importes económicos del contrato."""

    model_config = ConfigDict(extra="forbid")

    precio_total: float | None = Field(
        default=None, description="Precio total de compraventa pactado"
    )
    importe_arras: float | None = Field(
        default=None, description="Cantidad entregada en concepto de arras / señal"
    )
    porcentaje_arras: float | None = Field(
        default=None,
        description="Porcentaje que el importe de arras representa sobre el precio total, "
        "si es calculable (0-100)",
        ge=0,
        le=100,
    )
    moneda: str = Field(default="EUR", description="Código de moneda (normalmente EUR)")


class Fechas(BaseModel):
    """Fechas relevantes del contrato."""

    model_config = ConfigDict(extra="forbid")

    fecha_contrato: str | None = Field(
        default=None, description="Fecha de firma del contrato de arras (ISO 8601: AAAA-MM-DD)"
    )
    fecha_limite_escritura: str | None = Field(
        default=None,
        description="Fecha límite para otorgar la escritura pública de compraventa "
        "(ISO 8601: AAAA-MM-DD)",
    )
    plazo_dias: int | None = Field(
        default=None,
        description="Plazo en días naturales para elevar a público, si se expresa como plazo "
        "en lugar de fecha concreta",
    )


class ReferenciaCodigoCivil(BaseModel):
    """Una referencia al Código Civil encontrada en el texto del contrato."""

    model_config = ConfigDict(extra="forbid")

    articulo: str = Field(description='Número de artículo citado, p. ej. "1454"')
    contexto: str = Field(
        description="Fragmento del contrato donde aparece la cita, para poder verificarla"
    )


class AnalisisArras(BaseModel):
    """Resultado del análisis de un contrato de arras.

    Este es el schema que Claude rellena mediante structured outputs.
    """

    model_config = ConfigDict(extra="forbid")

    tipo_arras: TipoArras = Field(
        description="Modalidad de arras detectada. Usa 'no_especificado' si el contrato "
        "no lo indica de forma inequívoca."
    )
    confianza_tipo: float = Field(
        description="Confianza en la clasificación del tipo de arras, de 0 a 1",
        ge=0,
        le=1,
    )
    justificacion_tipo: str = Field(
        description="Explicación breve de por qué se ha clasificado así, citando la cláusula o "
        "el lenguaje concreto del contrato que lo determina"
    )
    partes: list[Parte] = Field(
        default_factory=list, description="Partes firmantes (comprador y vendedor)"
    )
    inmueble: Inmueble = Field(description="Datos del inmueble objeto del contrato")
    importes: Importes = Field(description="Importes económicos")
    fechas: Fechas = Field(description="Fechas y plazos relevantes")
    referencias_codigo_civil: list[ReferenciaCodigoCivil] = Field(
        default_factory=list,
        description="Referencias explícitas al Código Civil encontradas en el texto",
    )
    tiene_clausula_financiacion: bool = Field(
        description="True si el contrato incluye una cláusula suspensiva de financiación "
        "(protege al comprador si el banco deniega la hipoteca), False en caso contrario"
    )
    resumen: str = Field(
        description="Resumen en español de 2-3 frases del contrato y sus puntos clave"
    )


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
    recomendacion: str = Field(description="Qué debería hacer o preguntar el usuario, en español")


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
    nivel_riesgo_global: NivelRiesgo = Field(description="Nivel de riesgo agregado del contrato")
