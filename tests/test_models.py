"""Unit tests for the Pydantic schema (pure functions, no API)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from arras_ai.models import (
    AnalisisArras,
    CategoriaRiesgo,
    Importes,
    InformeArras,
    Inmueble,
    NivelRiesgo,
    Riesgo,
    RiesgoBase,
    RiesgosDetectadosLLM,
    Severidad,
    TipoArras,
)


def test_analisis_roundtrips_through_json(fake_analisis: AnalisisArras) -> None:
    dumped = fake_analisis.model_dump_json()
    restored = AnalisisArras.model_validate_json(dumped)
    assert restored == fake_analisis
    assert restored.tipo_arras is TipoArras.penitenciales


def test_tipo_arras_values() -> None:
    assert {t.value for t in TipoArras} == {
        "penitenciales",
        "confirmatorias",
        "penales",
        "no_especificado",
    }


def test_confianza_out_of_range_is_rejected(fake_analisis: AnalisisArras) -> None:
    payload = fake_analisis.model_dump()
    payload["confianza_tipo"] = 1.4
    with pytest.raises(ValidationError):
        AnalisisArras.model_validate(payload)


def test_porcentaje_arras_out_of_range_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Importes(precio_total=200000, importe_arras=20000, porcentaje_arras=150)


def test_unknown_field_is_forbidden() -> None:
    with pytest.raises(ValidationError):
        Inmueble.model_validate({"direccion": "x", "unexpected": "y"})


def test_optional_fields_default_to_none() -> None:
    inmueble = Inmueble()
    assert inmueble.direccion is None
    assert inmueble.referencia_catastral is None


def test_riesgo_requires_fuente() -> None:
    r = Riesgo(
        categoria=CategoriaRiesgo.falta_financiacion,
        severidad=Severidad.alta,
        descripcion="d",
        recomendacion="r",
        fuente="regla",
    )
    assert r.fuente == "regla"
    with pytest.raises(ValidationError):
        Riesgo.model_validate(
            {"categoria": "otro", "severidad": "baja", "descripcion": "d", "recomendacion": "r"}
        )


def test_riesgos_detectados_llm_has_no_fuente() -> None:
    payload = {
        "riesgos": [
            {"categoria": "otro", "severidad": "baja", "descripcion": "d", "recomendacion": "r"}
        ]
    }
    parsed = RiesgosDetectadosLLM.model_validate(payload)
    assert isinstance(parsed.riesgos[0], RiesgoBase)
    assert not hasattr(parsed.riesgos[0], "fuente")


def test_informe_roundtrips(fake_informe: InformeArras) -> None:
    restored = InformeArras.model_validate_json(fake_informe.model_dump_json())
    assert restored == fake_informe
    assert restored.nivel_riesgo_global in NivelRiesgo
