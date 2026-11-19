"""Tramos horarios: aritmética pura de intervalos en minutos (sin base de datos).

Un tramo es [inicio, fin) en minutos desde las 00:00 del día al que pertenece.
`fin` puede pasar de 1440: un turno de noche de 22:00 a 06:00 es (1320, 1800)
y sus horas cuentan en el día en que EMPIEZA (la convención de los cuadrantes).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Iterable, Optional, Sequence
from app.core.codigos_de_error import ErrorConCodigo

DIA = 1440


@dataclass(frozen=True, order=True)
class Tramo:
    inicio: int
    fin: int

    def __post_init__(self) -> None:
        if self.fin <= self.inicio:
            raise ErrorConCodigo("tramo_no_valido", detail="un tramo acaba después de empezar")

    @property
    def minutos(self) -> int:
        return self.fin - self.inicio

    @property
    def horas(self) -> float:
        return self.minutos / 60

    def texto(self) -> str:
        return f"{hhmm(self.inicio)}–{hhmm(self.fin)}"


def minutos(v) -> int:
    """'HH:MM' o time → minutos desde las 00:00. Error si no se entiende."""
    if isinstance(v, time):
        return v.hour * 60 + v.minute
    h, m = str(v).strip().split(":")[:2]
    h, m = int(h), int(m)
    if not (0 <= h <= 24 and 0 <= m < 60) or h * 60 + m > DIA:
        raise ErrorConCodigo("hora_no_valida", detail=f"hora no válida: {v}", valor=v)
    return h * 60 + m


def hhmm(m: int) -> str:
    m = m % DIA if m != DIA else DIA
    return f"{m // 60:02d}:{m % 60:02d}"


def desde_texto(inicio, fin) -> Tramo:
    """Un tramo de dos horas; si `fin` <= `inicio`, cruza la medianoche."""
    a, b = minutos(inicio), minutos(fin)
    if b <= a:
        b += DIA
    return Tramo(a, b)


def normalizar(tramos: Iterable[Tramo]) -> tuple[Tramo, ...]:
    """Ordenados y fundidos los que se tocan o solapan."""
    salida: list[Tramo] = []
    for t in sorted(tramos):
        if salida and t.inicio <= salida[-1].fin:
            if t.fin > salida[-1].fin:
                salida[-1] = Tramo(salida[-1].inicio, t.fin)
        else:
            salida.append(t)
    return tuple(salida)


def total_horas(tramos: Iterable[Tramo]) -> float:
    return round(sum(t.minutos for t in tramos) / 60, 4)


def interseccion(a: Sequence[Tramo], b: Sequence[Tramo]) -> tuple[Tramo, ...]:
    salida = []
    for x in a:
        for y in b:
            ini, fin = max(x.inicio, y.inicio), min(x.fin, y.fin)
            if fin > ini:
                salida.append(Tramo(ini, fin))
    return normalizar(salida)


def restar(a: Sequence[Tramo], b: Sequence[Tramo]) -> tuple[Tramo, ...]:
    """Lo de `a` que no está en `b`."""
    resto = list(normalizar(a))
    for y in normalizar(b):
        nuevo = []
        for x in resto:
            if y.fin <= x.inicio or y.inicio >= x.fin:
                nuevo.append(x)
                continue
            if y.inicio > x.inicio:
                nuevo.append(Tramo(x.inicio, y.inicio))
            if y.fin < x.fin:
                nuevo.append(Tramo(y.fin, x.fin))
        resto = nuevo
    return tuple(resto)


def recortar_horas(tramos: Sequence[Tramo], horas: float, *, desde_el_final: bool = True) -> tuple[Tramo, ...]:
    """Quita `horas` de los tramos (por el final o por el principio): una
    ausencia por horas sin franja, o medio día."""
    quitar = int(round(horas * 60))
    lista = list(normalizar(tramos))
    if desde_el_final:
        lista.reverse()
    salida = []
    for t in lista:
        if quitar <= 0:
            salida.append(t)
            continue
        if t.minutos <= quitar:
            quitar -= t.minutos
            continue
        salida.append(Tramo(t.inicio, t.fin - quitar) if desde_el_final else Tramo(t.inicio + quitar, t.fin))
        quitar = 0
    return normalizar(salida)


def mitad(tramos: Sequence[Tramo], cual: str) -> tuple[Tramo, ...]:
    """La primera o la segunda mitad (en horas) de un día: medio día."""
    total = total_horas(tramos)
    if cual == "primera":
        return restar(tramos, recortar_horas(tramos, total / 2, desde_el_final=False))
    return restar(tramos, recortar_horas(tramos, total / 2, desde_el_final=True))


def franja_en_dia(inicio, fin, tramos: Sequence[Tramo]) -> tuple[Tramo, ...]:
    """La franja de una ausencia por horas (`inicio`–`fin`) colocada en el día:
    en las horas de ese día o, en un turno de noche, en las de la madrugada
    siguiente (02:00–04:00 dentro de un turno de 22:00 a 06:00)."""
    base = desde_texto(inicio, fin)
    candidatas = [base, Tramo(base.inicio + DIA, base.fin + DIA)]
    mejor: tuple[Tramo, ...] = ()
    for c in candidatas:
        dentro = interseccion([c], tramos)
        if total_horas(dentro) > total_horas(mejor):
            mejor = dentro
    return mejor


def franjas(tramos: Sequence[Tramo], tam: int) -> list[int]:
    """Inicios (en minutos) de las franjas de `tam` minutos que tocan los tramos."""
    if tam <= 0:
        return []
    salida: list[int] = []
    for t in normalizar(tramos):
        f = (t.inicio // tam) * tam
        while f < t.fin:
            if f not in salida:
                salida.append(f)
            f += tam
    return salida


def a_lista(tramos: Iterable[Tramo]) -> list[list[str]]:
    return [[hhmm(t.inicio), hhmm(t.fin)] for t in tramos]


def de_lista(lista: Optional[Iterable]) -> tuple[Tramo, ...]:
    """[[inicio, fin], …] (texto) → tramos. Error si alguno no se entiende o se solapan."""
    salida = [desde_texto(a, b) for a, b in (lista or [])]
    orden = sorted(salida)
    for x, y in zip(orden, orden[1:]):
        if y.inicio < x.fin:
            raise ErrorConCodigo("tramos_solapados", detail="los tramos se solapan")
    return tuple(orden)
