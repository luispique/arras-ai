"""The evaluation dataset: by-construction ground truth for the analysis pipeline."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from arras_ai.models import CategoriaRiesgo, NivelRiesgo, TipoArras

DEFAULT_CASOS_PATH = Path(__file__).resolve().parents[3] / "data" / "evals" / "casos.yaml"


class GroundTruth(BaseModel):
    """Objective, by-construction labels for one contract."""

    model_config = ConfigDict(extra="forbid")

    tipo_arras: TipoArras
    confianza_min: float | None = None
    confianza_max: float | None = None
    tiene_clausula_financiacion: bool
    precio_total: float | None = None
    importe_arras: float | None = None
    fecha_limite_presente: bool = Field(
        description="True si fija fecha límite O plazo en días para la escritura"
    )
    referencia_catastral_presente: bool
    riesgos_esperados: list[CategoriaRiesgo] = Field(default_factory=list)
    nivel_riesgo_global: NivelRiesgo


class CasoEval(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    texto: str
    ground_truth: GroundTruth


def load_casos(path: Path | None = None) -> list[CasoEval]:
    src = path or DEFAULT_CASOS_PATH
    with src.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, list):
        raise ValueError(f"Expected a YAML list of cases in {src}")
    return [CasoEval.model_validate(item) for item in data]
