"""Local, mask-only PII anonymization applied before any text reaches the LLM.

The detection is always local (regex here); routing PII through a cloud model to
detect it would reintroduce the very leak this layer prevents. The masking is
one-way: `«María Fernández»` -> `«NOMBRE_1»`, `«12345678Z»` -> `«NIF_1»`. No
reverse map is kept — the legal analysis does not need who signs or where the
property is, so nothing personal is restored or returned.

Structured identifiers (NIF/NIE/CIF, IBAN, email, phone, cadastral reference) are
matched by strict format and masked reliably. Person names are best-effort, anchored
on the formulaic structure of Spanish arras contracts (honorifics, NIF proximity).
Free-text addresses are out of scope (documented limitation).
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from arras_ai.config import Settings

_CONTROL_NIF = "TRWAGMYFPDXBNJZSQVHLCKE"
_NIE_PREFIJO = {"X": "0", "Y": "1", "Z": "2"}
_TOKEN_RE = re.compile(r"^«[A-Z_]+_\d+»$")


class ResultadoAnonimizacion(BaseModel):
    """Outcome of anonymizing one text.

    `recuentos` reports how many spans of each type were masked (for tests, logging
    and a transparency note) — never the values themselves.
    """

    model_config = ConfigDict(extra="forbid")

    texto: str
    recuentos: dict[str, int] = Field(default_factory=dict)


class Anonimizador(ABC):
    """Masks PII in contract text before it is sent for analysis."""

    @abstractmethod
    def anonimizar(self, texto: str) -> ResultadoAnonimizacion: ...


class AnonimizadorNulo(Anonimizador):
    """Passthrough: returns the text unchanged. For `ARRAS_ANONIMIZAR=false`."""

    def anonimizar(self, texto: str) -> ResultadoAnonimizacion:
        return ResultadoAnonimizacion(texto=texto, recuentos={})


def _nif_valido(numero: str, letra: str) -> bool:
    return _CONTROL_NIF[int(numero) % 23] == letra.upper()


def _nie_valido(prefijo: str, resto: str, letra: str) -> bool:
    return _nif_valido(_NIE_PREFIJO[prefijo.upper()] + resto, letra)


class RegexAnonimizador(Anonimizador):
    """Format-based masking for structured identifiers + heuristic name masking."""

    # Structured identifiers, applied in this order (before names).
    _EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
    _IBAN = re.compile(r"\bES\d{2}(?:[ \-]?\d{4}){5}\b", re.IGNORECASE)
    _TELEFONO = re.compile(r"(?<!\d)(?:(?:\+|00)34[ \-]?)?[6-9]\d{2}[ \-]?\d{3}[ \-]?\d{3}(?!\d)")
    _NIF = re.compile(r"(?<![\w-])(\d{8})[ \-]?([A-Za-z])(?![\w-])")
    _NIE = re.compile(r"(?<![\w-])([XYZxyz])[ \-]?(\d{7})[ \-]?([A-Za-z])(?![\w-])")
    _CIF = re.compile(r"(?<![\w-])[ABCDEFGHJNPQRSUVW][ \-]?\d{7}[ \-]?[0-9A-Ja-j](?![\w-])")
    _CATASTRO = re.compile(r"(?<![\w-])[0-9A-Za-z]{20}(?![\w-])")

    # Names: honorific-led, or immediately before an already-masked NIF token.
    _NOMBRE_TITULO = re.compile(
        r"(D\.ª|Dña\.|D\.|Doña|Don)\s+"
        r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+(?:de|del|la|las|los|y)\s+|\s+)"
        r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){0,3})"
    )
    _NOMBRE_ANTES_NIF = re.compile(
        r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+){1,4})"
        r"(,?\s+(?:con\s+)?(?:N\.?I\.?F\.?|D\.?N\.?I\.?)\.?\s+«NIF_\d+»)"
    )

    def anonimizar(self, texto: str) -> ResultadoAnonimizacion:
        recuentos: dict[str, int] = defaultdict(int)
        # Per-type token numbering; same original value reuses its token.
        asignados: dict[tuple[str, str], str] = {}

        def token(tipo: str, valor: str) -> str:
            clave = (tipo, valor)
            if clave not in asignados:
                recuentos[tipo] += 1
                asignados[clave] = f"«{tipo}_{recuentos[tipo]}»"
            return asignados[clave]

        def sub(pattern: re.Pattern[str], tipo: str, repl: Callable[[re.Match[str]], str]) -> None:
            nonlocal texto
            texto = pattern.sub(repl, texto)

        sub(self._EMAIL, "EMAIL", lambda m: token("EMAIL", m.group(0)))
        sub(self._IBAN, "IBAN", lambda m: token("IBAN", _norm(m.group(0))))
        sub(self._TELEFONO, "TELEFONO", lambda m: token("TELEFONO", _norm(m.group(0))))

        def _nif(m: re.Match[str]) -> str:
            if not _nif_valido(m.group(1), m.group(2)):
                return m.group(0)
            return token("NIF", m.group(1) + m.group(2).upper())

        sub(self._NIF, "NIF", _nif)

        def _nie(m: re.Match[str]) -> str:
            if not _nie_valido(m.group(1), m.group(2), m.group(3)):
                return m.group(0)
            return token("NIE", _norm(m.group(0)).upper())

        sub(self._NIE, "NIE", _nie)
        sub(self._CIF, "CIF", lambda m: token("CIF", _norm(m.group(0)).upper()))
        sub(self._CATASTRO, "CATASTRO", lambda m: token("CATASTRO", m.group(0).upper()))

        # Names last, so `_NOMBRE_ANTES_NIF` can anchor on the «NIF_n» tokens above.
        sub(self._NOMBRE_TITULO, "NOMBRE", lambda m: f"{m.group(1)} {token('NOMBRE', m.group(2))}")
        sub(
            self._NOMBRE_ANTES_NIF,
            "NOMBRE",
            lambda m: f"{token('NOMBRE', m.group(1))}{m.group(2)}",
        )

        return ResultadoAnonimizacion(texto=texto, recuentos=dict(recuentos))


def _norm(s: str) -> str:
    """Collapse separators so the same identifier written differently reuses a token."""
    return re.sub(r"[ \-]", "", s)


def es_placeholder(valor: str) -> bool:
    """True if `valor` is an anonymization placeholder like «NOMBRE_1»."""
    return bool(_TOKEN_RE.match(valor.strip()))


def make_anonimizador(settings: Settings) -> Anonimizador:
    """Build the anonymizer from settings. Detection is always local."""
    if not settings.anonimizar:
        return AnonimizadorNulo()
    provider = settings.anonimizador_provider
    if provider in {"regex", "reglas"}:
        return RegexAnonimizador()
    if provider in {"nulo", "none", "off"}:
        return AnonimizadorNulo()
    raise ValueError(
        f"Proveedor de anonimización desconocido: {provider!r} "
        "(usa 'regex' o desactiva con ARRAS_ANONIMIZAR=false)."
    )
