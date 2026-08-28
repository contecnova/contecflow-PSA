"""Tiempo y zonas horarias.

Auditoría 2026-08 (hallazgo 14). Este módulo sólo tenía un `utcnow()`, y el
resto del código usaba `date.today()` (209 puntos) y `datetime.now()` sin zona
(24 puntos). En una aplicación donde cada organización y cada usuario tienen su
zona horaria, eso significa que los bordes de día los decidía la zona del
servidor.

El caso concreto que fallaba: un empleado en México (UTC-6) imputa horas a las
23:30 del día 28. El servidor corre en UTC, donde ya son las 05:30 del día 29,
así que la imputación se registraba en el día 29. Su día 28 quedaba vacío y el 29
con horas que no trabajó ese día.

`Imputation.date` es un `Date` puro —un día de calendario, sin instante—, así que
la pregunta «qué día es hoy» no tiene una respuesta única: depende de para quién.

── Las dos cadenas de resolución ─────────────────────────────────────────────
Son distintas a propósito, porque responden a preguntas distintas.

1. «¿Qué día es HOY para esta persona?» → `today_for_user`
   usuario → organización → UTC
   Lo que espera quien imputa: su día, no el de la sede.

2. «¿Qué abarca el periodo de facturación?» → `period_bounds_for_client`
   cliente → organización → UTC
   Una factura tiene un periodo único, no uno por empleado. El cierre de agosto
   de un cliente es agosto en SU zona.

Ambas terminan en UTC como último recurso: es determinista y auditable, y nunca
lanza por una zona mal configurada.

── Sobre las fechas-hora ya almacenadas ──────────────────────────────────────
Se interpretan como UTC, porque lo son. Se comprobó antes de tocar nada: de las
escrituras a columnas de fecha-hora, 139 usan `utcnow()`, 374
`datetime.now(timezone.utc)` y 437 `func.now()` sobre columnas
`DateTime(timezone=True)` — todas UTC. Las 24 llamadas a `datetime.now()` sin
zona que quedaban no escriben ninguna columna: extraen `.year`/`.month` o
formatean la cabecera de un PDF.

Por eso NO hay migración de desplazamiento: aplicar un «hora local → UTC» sobre
datos que ya son UTC movería todos los instantes correctos por el offset del
servidor y corrompería el histórico de forma irreversible.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

logger = logging.getLogger("contecflow.timeutil")

UTC = timezone.utc


# ── Ahora ─────────────────────────────────────────────────────────────────────

def utcnow() -> datetime:
    """'Ahora' en UTC, sin tzinfo — misma semántica que el `datetime.utcnow()`
    obsoleto. Se conserva porque 139 puntos del código lo usan y su contrato es
    correcto: lo que guardan ES UTC.
    """
    return datetime.now(UTC).replace(tzinfo=None)


def utcnow_aware() -> datetime:
    """'Ahora' en UTC con tzinfo. Preferible en código nuevo: un datetime con
    zona no se puede comparar por error con uno local."""
    return datetime.now(UTC)


# ── Resolución de zonas ───────────────────────────────────────────────────────

def resolve_zone(name: Optional[str]) -> timezone | ZoneInfo:
    """ZoneInfo del nombre dado, o UTC si falta o no es válido.

    No lanza: una zona mal escrita en la configuración de un cliente no debe
    tumbar una petición. Se registra en warning para que sea visible y se sigue
    con UTC, que es el comportamiento anterior — así el fallo degrada, no rompe.
    """
    if not name:
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        logger.warning("Zona horaria no reconocida: %r — se usa UTC", name)
        return UTC


def zone_for_user(user, organization=None) -> timezone | ZoneInfo:
    """Zona de un usuario: la suya, y si no tiene, la de su organización.

    `organization` es opcional para evitar una consulta cuando quien llama ya la
    tiene cargada.
    """
    propia = getattr(user, "timezone", None) if user is not None else None
    if propia:
        return resolve_zone(propia)
    org_tz = getattr(organization, "timezone", None) if organization is not None else None
    return resolve_zone(org_tz)


def zone_for_client(client, organization=None) -> timezone | ZoneInfo:
    """Zona de un cliente: la suya, y si no tiene, la de su organización.

    Es la que manda en los cortes de periodo de su facturación.
    """
    propia = getattr(client, "timezone", None) if client is not None else None
    if propia:
        return resolve_zone(propia)
    org_tz = getattr(organization, "timezone", None) if organization is not None else None
    return resolve_zone(org_tz)


# ── "Hoy", según para quién ───────────────────────────────────────────────────

def today_in(zone) -> date:
    """Día de calendario actual en la zona dada."""
    return datetime.now(zone).date()


def today_for_user(user, organization=None) -> date:
    """El día de HOY para este usuario.

    Sustituye a `date.today()` en todo lo que dependa del calendario de una
    persona: imputaciones, fichajes, vencimientos que se muestran al usuario.
    """
    return today_in(zone_for_user(user, organization))


def today_for_client(client, organization=None) -> date:
    """El día de HOY para este cliente. Para vencimientos de su facturación."""
    return today_in(zone_for_client(client, organization))


def today_for_organization(organization) -> date:
    """El día de HOY para la organización. Cuando no hay usuario ni cliente en
    contexto (tareas programadas de ámbito de la organización)."""
    return today_in(resolve_zone(getattr(organization, "timezone", None)))


# ── Cortes de periodo ─────────────────────────────────────────────────────────

def day_bounds_in(day: date, zone) -> tuple[datetime, datetime]:
    """Instantes UTC que delimitan un día de calendario en `zone`.

    Devuelve [inicio, fin) — el fin es EXCLUSIVO a propósito: con un fin
    inclusivo hay que elegir un último instante representable (23:59:59) y se
    pierde todo lo ocurrido en el último segundo. Con intervalo semiabierto no
    hay huecos ni solapes entre días consecutivos.
    """
    inicio_local = datetime.combine(day, time.min, tzinfo=zone)
    fin_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    return inicio_local.astimezone(UTC), fin_local.astimezone(UTC)


def month_bounds_in(year: int, month: int, zone) -> tuple[datetime, datetime]:
    """Instantes UTC que delimitan un mes de calendario en `zone`.

    Es el corte que usa el cierre de facturación. Con la zona del cliente, el
    «agosto» de su factura es agosto para él: sin esto, una organización en
    Madrid perdía la primera hora del 1 de agosto y se colaba la primera hora del
    1 de septiembre.
    """
    if not 1 <= month <= 12:
        raise ValueError(f"Mes fuera de rango: {month}")
    inicio = datetime(year, month, 1, tzinfo=zone)
    if month == 12:
        fin = datetime(year + 1, 1, 1, tzinfo=zone)
    else:
        fin = datetime(year, month + 1, 1, tzinfo=zone)
    return inicio.astimezone(UTC), fin.astimezone(UTC)


def period_bounds_for_client(
    year: int, month: int, client, organization=None
) -> tuple[datetime, datetime]:
    """Corte mensual de facturación en la zona del cliente.

    Punto de entrada para cierres e informes: encapsula la cadena de resolución
    para que quien llama no tenga que recordarla.
    """
    return month_bounds_in(year, month, zone_for_client(client, organization))


def as_utc(value: datetime) -> datetime:
    """Normaliza a UTC con zona.

    Un datetime SIN zona se interpreta como UTC, no como hora local: es lo que
    los datos almacenados son de verdad (ver la cabecera del módulo). Tratarlo
    como local desplazaría instantes correctos.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = (
    "UTC",
    "as_utc",
    "day_bounds_in",
    "month_bounds_in",
    "period_bounds_for_client",
    "resolve_zone",
    "today_for_client",
    "today_for_organization",
    "today_for_user",
    "today_in",
    "utcnow",
    "utcnow_aware",
    "zone_for_client",
    "zone_for_user",
)
