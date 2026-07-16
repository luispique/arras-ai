"""Unit tests for the local PII anonymizer. All offline, no network."""

from __future__ import annotations

import pytest

from arras_ai.anonimizacion import (
    AnonimizadorNulo,
    RegexAnonimizador,
    es_placeholder,
    make_anonimizador,
)
from arras_ai.config import Settings


def _anon(texto: str) -> str:
    return RegexAnonimizador().anonimizar(texto).texto


# --- Null backend -----------------------------------------------------------


def test_nulo_passthrough() -> None:
    r = AnonimizadorNulo().anonimizar("D. Juan, NIF 12345678Z")
    assert r.texto == "D. Juan, NIF 12345678Z"
    assert r.recuentos == {}


# --- Structured identifiers -------------------------------------------------


def test_email_masked() -> None:
    assert _anon("Contacto: ana.lopez@example.com aquí") == "Contacto: «EMAIL_1» aquí"


def test_iban_masked() -> None:
    out = _anon("IBAN ES91 2100 0418 4502 0005 1332 para el pago")
    assert "«IBAN_1»" in out and "2100" not in out


def test_telefono_masked() -> None:
    assert "«TELEFONO_1»" in _anon("Tel. +34 612 345 678")


def test_nif_masked_by_format_regardless_of_checksum() -> None:
    # Mask by shape, NOT checksum: a real (or mistyped) NIF must never leak.
    assert _anon("NIF 12345678Z") == "NIF «NIF_1»"
    assert _anon("DNI 44556677P") == "DNI «NIF_1»"  # invalid checksum, still masked
    assert _anon("NIF 12345678-Z") == "NIF «NIF_1»"  # hyphen separator


def test_nif_shape_does_not_eat_digits_then_word() -> None:
    # "<8 digits> <word>" must NOT be masked as a NIF (only hyphen, not space).
    assert _anon("El importe 12345678 y sus intereses") == "El importe 12345678 y sus intereses"


def test_nie_valid_masked() -> None:
    # X1234567L is a valid NIE.
    assert _anon("NIE X1234567L") == "NIE «NIE_1»"


def test_cif_masked() -> None:
    assert "«CIF_1»" in _anon("Sociedad con CIF B12345674")


def test_cadastral_reference_masked() -> None:
    out = _anon("Ref. catastral 9872023VH5797S0001WX libre")
    assert "«CATASTRO_1»" in out and "9872023VH5797S0001WX" not in out


# --- What must NOT be touched ----------------------------------------------


def test_amounts_dates_percentages_untouched() -> None:
    texto = "Precio 280.000 €, señal 28.000 €, 5 % del total, firmado 2025-03-15."
    assert _anon(texto) == texto


# --- Consistency & counts ---------------------------------------------------


def test_same_value_reuses_token_and_counts() -> None:
    r = RegexAnonimizador().anonimizar("NIF 12345678Z y otra vez 12345678Z")
    assert r.texto == "NIF «NIF_1» y otra vez «NIF_1»"
    assert r.recuentos["NIF"] == 1


def test_distinct_values_get_distinct_tokens() -> None:
    r = RegexAnonimizador().anonimizar("12345678Z y 87654321X")
    assert "«NIF_1»" in r.texto and "«NIF_2»" in r.texto
    assert r.recuentos["NIF"] == 2


# --- Names (best-effort heuristics) ----------------------------------------


def test_name_after_honorific() -> None:
    assert _anon("Dña. María Fernández Gil, vendedora") == "Dña. «NOMBRE_1», vendedora"


def test_name_before_nif_token() -> None:
    # After NIFs are masked, a name sitting right before a «NIF_n» is caught.
    out = _anon("Juan Pérez López, con NIF 87654321X, comprador")
    assert "«NOMBRE_1»" in out and "«NIF_1»" in out
    assert "Juan" not in out


# --- Helpers & factory ------------------------------------------------------


def test_es_placeholder() -> None:
    assert es_placeholder("«NOMBRE_1»")
    assert es_placeholder("  «NIF_12» ")
    assert not es_placeholder("María")
    assert not es_placeholder("")


def test_factory_dispatch() -> None:
    assert isinstance(make_anonimizador(Settings(anonimizar=True)), RegexAnonimizador)
    assert isinstance(make_anonimizador(Settings(anonimizar=False)), AnonimizadorNulo)
    assert isinstance(make_anonimizador(Settings(anonimizador_provider="nulo")), AnonimizadorNulo)
    with pytest.raises(ValueError):
        make_anonimizador(Settings(anonimizador_provider="desconocido"))
