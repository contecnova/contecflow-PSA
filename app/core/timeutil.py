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

── Por qué hay una zona en el contexto y no un parámetro en 198 firmas ───────
Los 198 `date.today()` que quedaban viven casi todos en funciones de servicio
que no reciben —ni deben recibir— el usuario: `_calcular_vencimientos(db,
project_id)` no tiene por qué saber quién pregunta. Enhebrar un `user` o un
`zone` por esas 198 firmas, y por las que las llaman, habría contaminado media
capa de servicios con un parámetro de presentación y habría dejado la corrección
dependiendo de que nadie se olvide de pasarlo.

La zona resuelta se publica una vez por petición en un `ContextVar` y `today()`
la lee. Comprobado empíricamente antes de construir nada encima: un `ContextVar`
puesto en una dependencia **async** de FastAPI es visible en el endpoint —sea
async o sync en threadpool— y en las funciones que éste llame, a cualquier
profundidad. Puesto en una dependencia *sync* se pierde, porque corre en un hilo
trabajador; de ahí que `bind_request_timezone` sea `async def` y lo diga en su
propia documentación. Ver `app/core/timezone_context.py`.

Fuera de una petición —tareas programadas, seeds, scripts— no hay nadie a quien
preguntar, así que el contexto vale UTC y `today()` se comporta exactamente como
el `date.today()` de un servidor en UTC. Quien procesa por organización debe
abrir `using_zone(...)` explícitamente; es visible en el código en lugar de
depender de la zona del servidor.

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

import contextvars
import logging
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterator, Optional
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


# ── La zona del contexto actual ───────────────────────────────────────────────
# Publicada una vez por petición (ver la cabecera del módulo y
# app/core/timezone_context.py). UTC por defecto: fuera de una petición no hay a
# quién preguntar, y UTC reproduce el comportamiento anterior exactamente.
_ZONE: contextvars.ContextVar = contextvars.ContextVar("contecflow_zone", default=UTC)


def current_zone() -> timezone | ZoneInfo:
    """Zona del contexto actual. UTC si nadie la ha fijado."""
    return _ZONE.get()


def set_current_zone(zone) -> contextvars.Token:
    """Fija la zona del contexto. Devuelve el token para restaurarla.

    Sólo debe llamarlo la dependencia que enlaza la petición, o
    `using_zone` para un bloque acotado. En cualquier otro sitio, usar
    `using_zone`: dejar la zona fijada al salir contamina lo que venga después en
    la misma tarea.
    """
    return _ZONE.set(zone)


def reset_current_zone(token: contextvars.Token) -> None:
    """Restaura la zona anterior a partir del token de `set_current_zone`."""
    _ZONE.reset(token)


@contextmanager
def using_zone(zone) -> Iterator[None]:
    """Fija la zona para un bloque y la restaura al salir, incluso si hay error.

    Es la forma correcta de procesar por organización en una tarea programada:

        for org in organizaciones:
            with using_zone(resolve_zone(org.timezone)):
                generar_informe_mensual(db, org)

    Así el corte de cada organización se hace en SU zona y queda visible en el
    código, en vez de depender de la zona en que corra el servidor.
    """
    token = _ZONE.set(zone)
    try:
        yield
    finally:
        _ZONE.reset(token)


@contextmanager
def using_organization_zone(organization) -> Iterator[None]:
    """`using_zone` a partir de una organización. Atajo para las tareas
    programadas, que es donde más se necesita."""
    with using_zone(resolve_zone(getattr(organization, "timezone", None))):
        yield


def today() -> date:
    """El día de HOY en la zona del contexto.

    Sustituto directo de `date.today()`: misma firma, mismo tipo de retorno, y
    fuera de una petición se comporta igual que `date.today()` en un servidor
    UTC. Dentro de una petición devuelve el día del usuario que la hizo.
    """
    return datetime.now(_ZONE.get()).date()


def now_local() -> datetime:
    """'Ahora' con zona, en la del contexto.

    Para cuando se necesita la hora y no sólo el día: la cabecera de un informe,
    el nombre de un fichero exportado, un `.year`/`.month`. Para lo que se
    ALMACENA en una columna de fecha-hora hay que seguir usando `utcnow()` o
    `utcnow_aware()`: la base guarda UTC.
    """
    return datetime.now(_ZONE.get())


def month_key_in(value: datetime, zone=None) -> tuple[int, int]:
    """(año, mes) al que pertenece un instante EN LA ZONA dada.

    Auditoría 2026-08 (P2-14). Existe porque agrupar por mes con
    `extract("month", columna)` en SQL agrupa por el mes **UTC**, que es el mes
    en que la fila está almacenada, no el mes en que ocurrió para quien mira el
    informe. Las filas de las primeras o últimas horas de un mes caen en el mes
    contiguo: una incidencia de SLA de las 23:30 del 31 de julio en Madrid se
    cuenta en agosto.

    No se resuelve en SQL a propósito. `AT TIME ZONE` existe en PostgreSQL pero
    no en SQLite, así que una consulta con esa cláusula dejaría de funcionar en
    desarrollo y en los tests — exactamente el tipo de divergencia entre motores
    que ya causó el hallazgo 11. Convertir en Python funciona igual en los dos.

    Sólo aplica a columnas de fecha-HORA. Una columna `Date` es un día de
    calendario sin instante: no tiene zona que aplicar, y su `extract` ya es
    correcto. Ver el detalle en la cabecera de este módulo.
    """
    if value is None:
        raise ValueError("month_key_in necesita un instante, no None")
    local = as_utc(value).astimezone(zone if zone is not None else _ZONE.get())
    return local.year, local.month


def month_label_in(value: datetime, zone=None) -> str:
    """Etiqueta «AAAA-MM» del mes de un instante en la zona dada.

    Es el formato que ya usan los informes, así que centralizarlo evita que cada
    sitio lo componga a mano y se desalinee.
    """
    year, month = month_key_in(value, zone)
    return f"{year:04d}-{month:02d}"


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
    "current_zone",
    "day_bounds_in",
    "month_bounds_in",
    "month_key_in",
    "month_label_in",
    "now_local",
    "period_bounds_for_client",
    "reset_current_zone",
    "resolve_zone",
    "set_current_zone",
    "today",
    "today_for_client",
    "today_for_organization",
    "today_for_user",
    "today_in",
    "using_organization_zone",
    "using_zone",
    "utcnow",
    "utcnow_aware",
    "zone_for_client",
    "zone_for_user",
)
