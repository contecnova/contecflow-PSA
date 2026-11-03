"""SLA Service — business logic for SLA calculations.

Extracted from app/api/v1/endpoints/service_desk.py so it can be unit-tested
independently of the HTTP layer.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from datetime import time as dt_time
from datetime import tzinfo
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import cast, func, Integer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.client_portal import ClientUser
from app.models.service_desk import Ticket
from app.models.service_desk import Problem
from app.models.service_desk import KBArticle
from app.models.service_desk import ConfigurationItem
from app.models.service_desk import SDSLAHoliday
from app.models.service_desk import TicketHistory
from jose import jwt, JWTError
from app.core import timeutil

if TYPE_CHECKING:
    from app.models.service_desk import SLAPolicy, Ticket, TicketHistory
    from app.models.client_portal import ClientUser

logger = logging.getLogger(__name__)

# ── Label / display dictionaries (shared with endpoint) ──────────────────────

PRIORITY_MATRIX = {
    ("critical", "enterprise"): "p1_critical",
    ("critical", "department"): "p1_critical",
    ("critical", "user"):       "p2_high",
    ("critical", "minimal"):    "p3_medium",
    ("high",     "enterprise"): "p1_critical",
    ("high",     "department"): "p2_high",
    ("high",     "user"):       "p2_high",
    ("high",     "minimal"):    "p3_medium",
    ("medium",   "enterprise"): "p2_high",
    ("medium",   "department"): "p3_medium",
    ("medium",   "user"):       "p3_medium",
    ("medium",   "minimal"):    "p4_low",
    ("low",      "enterprise"): "p3_medium",
    ("low",      "department"): "p3_medium",
    ("low",      "user"):       "p4_low",
    ("low",      "minimal"):    "p4_low",
}

TICKET_PREFIXES = {
    "incident": "INC",
    "service_request": "REQ",
    "change": "CHG",
    "problem": "PRB",
    "question": "QST",
}

PRIORITY_LABELS = {
    "p1_critical": {"label": "P1 Crítico", "color": "#ff4757"},
    "p2_high":     {"label": "P2 Alto",    "color": "#ff6b35"},
    "p3_medium":   {"label": "P3 Medio",   "color": "#ffb800"},
    "p4_low":      {"label": "P4 Bajo",    "color": "#00e5a0"},
}

STATUS_LABELS = {
    "new":            {"label": "Nuevo",              "color": "#7a8aaa"},
    "assigned":       {"label": "Asignado",           "color": "#00d4ff"},
    "in_progress":    {"label": "En progreso",        "color": "#7c3aed"},
    "pending_client": {"label": "Pendiente cliente",  "color": "#ffb800"},
    "pending_third":  {"label": "Pendiente tercero",  "color": "#f97316"},
    "resolved":       {"label": "Resuelto",           "color": "#00e5a0"},
    "closed":         {"label": "Cerrado",            "color": "#3d4f6e"},
    "cancelled":      {"label": "Cancelado",          "color": "#3d4f6e"},
}

TYPE_LABELS = {
    "incident":        {"label": "Incidencia", "icon": "🔥"},
    "service_request": {"label": "Solicitud",  "icon": "📋"},
    "change":          {"label": "Cambio",     "icon": "🔀"},
    "problem":         {"label": "Problema",   "icon": "🔍"},
    "question":        {"label": "Consulta",   "icon": "❓"},
}

SLA_HOURS: dict[str, tuple[float, float]] = {
    "p1_critical": (settings.SLA_P1_RESPONSE_HOURS, settings.SLA_P1_RESOLUTION_HOURS),
    "p2_high":     (settings.SLA_P2_RESPONSE_HOURS, settings.SLA_P2_RESOLUTION_HOURS),
    "p3_medium":   (settings.SLA_P3_RESPONSE_HOURS, settings.SLA_P3_RESOLUTION_HOURS),
    "p4_low":      (settings.SLA_P4_RESPONSE_HOURS, settings.SLA_P4_RESOLUTION_HOURS),
}


def get_sla_hours(db: Optional[Session], org_id: Optional[str] = None) -> dict[str, tuple[float, float]]:
    """Effective (response_h, resolution_h) per priority.

    Resolution order: org override → global override → env default. Falls back
    to the env-frozen `SLA_HOURS` constant when `db` is None (callsites that
    don't have a session, like serializers).
    """
    if db is None:
        return SLA_HOURS
    from app.services import settings_service as _ss
    g = _ss.get_runtime_float
    return {
        "p1_critical": (g(db, "SLA_P1_RESPONSE_HOURS", org_id), g(db, "SLA_P1_RESOLUTION_HOURS", org_id)),
        "p2_high":     (g(db, "SLA_P2_RESPONSE_HOURS", org_id), g(db, "SLA_P2_RESOLUTION_HOURS", org_id)),
        "p3_medium":   (g(db, "SLA_P3_RESPONSE_HOURS", org_id), g(db, "SLA_P3_RESOLUTION_HOURS", org_id)),
        "p4_low":      (g(db, "SLA_P4_RESPONSE_HOURS", org_id), g(db, "SLA_P4_RESOLUTION_HOURS", org_id)),
    }


# ── Pure utilities ────────────────────────────────────────────────────────────

def norm_enum(val) -> str:
    """Normalize an enum value or string to lowercase for PRIORITY_MATRIX lookup."""
    if hasattr(val, 'value'):
        return val.value.lower()
    return str(val).lower()


def aware(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize naive datetime → timezone-aware UTC. Safe with None."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def advisory_lock_key(name: str) -> int:
    """Return a deterministic 64-bit positive integer from *name* for pg_advisory_xact_lock."""
    return int(hashlib.md5(name.encode(), usedforsecurity=False).hexdigest()[:15], 16) % (2 ** 63)


#: Lunes a viernes, en numeración ISO (1 = lunes ... 7 = domingo).
DIAS_LABORABLES_POR_DEFECTO = frozenset({1, 2, 3, 4, 5})


def _es_laborable(d: date, holidays: set, days: frozenset = DIAS_LABORABLES_POR_DEFECTO) -> bool:
    """Día de la semana laborable (ISO) que no sea festivo."""
    return d.isoweekday() in days and d not in holidays


def _siguiente_momento_laborable(current: datetime, work_start: dt_time, work_end: dt_time,
                                 holidays: set,
                                 days: frozenset = DIAS_LABORABLES_POR_DEFECTO) -> datetime:
    """Adelanta hasta el primer instante laborable a partir de `current`.

    Tres casos y ninguno más: el día no se trabaja, la jornada ya acabó, o
    todavía no ha empezado. El bucle es necesario porque saltar un viernes por
    la tarde cae en sábado, que tampoco vale.
    """
    if not days:
        raise ValueError("el calendario no tiene ningún día laborable")
    while True:
        dia = current.date()
        if not _es_laborable(dia, holidays, days) or current.time() >= work_end:
            current = datetime.combine(dia + timedelta(days=1), work_start).replace(
                tzinfo=current.tzinfo,
            )
            continue
        if current.time() < work_start:
            current = datetime.combine(dia, work_start).replace(tzinfo=current.tzinfo)
        return current


def add_working_hours(
    start_dt: datetime,
    hours: float,
    work_start: dt_time = dt_time(8, 0),
    work_end: dt_time = dt_time(18, 0),
    holidays: Optional[set] = None,
    days: frozenset = DIAS_LABORABLES_POR_DEFECTO,
) -> datetime:
    """Adelanta *start_dt* en *hours* horas **de trabajo**.

    Respeta:
    - la jornada (work_start..work_end),
    - los días laborables (`days`, ISO; por defecto lunes a viernes),
    - los festivos que se pasen como conjunto de :class:`datetime.date`.

    La aritmética es de reloj de pared en la zona de `start_dt`: quien quiera
    la jornada de otra zona pasa `start_dt` ya convertido (ver
    :func:`sumar_horas_sla`).

    Auditoría 2026-09 (hallazgo 18): eran dos bucles `while` con tres ayudantes
    anidados, complejidad 13. El primer bucle —«ponte en horario laborable»— es
    una pregunta con nombre propio y ahora lo tiene.
    """
    holidays = holidays or set()

    jornada = (
        datetime.combine(timeutil.today(), work_end)
        - datetime.combine(timeutil.today(), work_start)
    ).total_seconds()
    if jornada <= 0:
        raise ValueError("work_end must be after work_start")

    current = _siguiente_momento_laborable(start_dt, work_start, work_end, holidays, days)
    restantes = hours

    while restantes > 0:
        fin_de_jornada = datetime.combine(current.date(), work_end).replace(
            tzinfo=current.tzinfo,
        )
        disponibles = (fin_de_jornada - current).total_seconds() / 3600.0
        if restantes <= disponibles:
            return current + timedelta(hours=restantes)
        restantes -= disponibles
        # Al día siguiente, saltando lo que no se trabaje.
        current = _siguiente_momento_laborable(
            datetime.combine(current.date() + timedelta(days=1), work_start).replace(
                tzinfo=current.tzinfo,
            ),
            work_start, work_end, holidays, days,
        )

    return current


@dataclass(frozen=True)
class CalendarioSLA:
    """Cuándo corre el reloj de un SLA.

    `continuo` es el 24x7: corre siempre y el resto de campos no se mira. Si
    no, corre de `inicio` a `fin` los `dias` laborables (ISO) que no sean
    `festivos`, en la hora local de `zona`.
    """
    zona: tzinfo
    continuo: bool = False
    inicio: dt_time = dt_time(8, 0)
    fin: dt_time = dt_time(18, 0)
    dias: frozenset = DIAS_LABORABLES_POR_DEFECTO
    festivos: frozenset = frozenset()


def _zona(nombre: Optional[str]) -> tzinfo:
    """La zona por nombre IANA; una desconocida es un error de configuración."""
    try:
        return ZoneInfo(nombre or settings.DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"zona horaria desconocida: {nombre!r}") from exc


def parse_dias_laborables(raw: Optional[str]) -> frozenset:
    """'1,2,3,4,5' -> {1..5}. Rechaza lo que no sea un día ISO del 1 al 7."""
    dias = set()
    for trozo in (raw or "").split(","):
        trozo = trozo.strip()
        if not trozo:
            continue
        if not trozo.isdigit() or not 1 <= int(trozo) <= 7:
            raise ValueError(f"día laborable inválido: {trozo!r} (1 = lunes ... 7 = domingo)")
        dias.add(int(trozo))
    if not dias:
        raise ValueError("el calendario no tiene ningún día laborable")
    return frozenset(dias)


def parse_hora(raw: str) -> dt_time:
    """'09:00' -> time(9, 0); '24:00' es el final del dia."""
    try:
        hh, mm = (int(x) for x in str(raw).strip().split(":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"hora inválida: {raw!r} (usa HH:MM)") from exc
    if (hh, mm) == (24, 0):
        return dt_time(23, 59, 59, 999999)
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"hora inválida: {raw!r} (usa HH:MM)")
    return dt_time(hh, mm)


def _festivos_del_calendario(db: Session, calendar_id: str) -> set:
    from app.models.cmdb import V21SLAHoliday
    dias = set()
    for r in db.query(V21SLAHoliday).filter(
        V21SLAHoliday.calendar_id == calendar_id, V21SLAHoliday.is_active == True,  # noqa: E712
    ).all():
        try:
            dias.add(date.fromisoformat(r.holiday_date))
        except (ValueError, TypeError):
            logger.warning("festivo de calendario con fecha inválida ignorado: %s", r.id)
    return dias


def _calendario_de_servicio(db: Session, policy: "SLAPolicy", org_id: Optional[str]) -> Optional[CalendarioSLA]:
    """El calendario de servicio que la política tiene elegido, si sigue activo."""
    from app.models.cmdb import SLACalendar
    cal = db.get(SLACalendar, policy.calendar_id)
    if cal is None or not cal.is_active:
        logger.warning("la política SLA %s apunta a un calendario que ya no existe; usa su propio horario",
                       policy.id)
        return None
    inicio, fin = parse_hora(cal.work_start), parse_hora(cal.work_end)
    if fin <= inicio:
        raise ValueError(f"jornada inválida en el calendario {cal.name}: {cal.work_start}-{cal.work_end}")
    return CalendarioSLA(
        zona=_zona(cal.timezone), inicio=inicio, fin=fin,
        dias=parse_dias_laborables(cal.work_days),
        festivos=frozenset(_festivos_del_calendario(db, cal.id) | _festivos(db, policy, org_id)),
    )


def _festivos(db: Session, policy: "Optional[SLAPolicy]", org_id: Optional[str]) -> frozenset:
    """Los festivos de la política más los generales de la organización.

    Un festivo sin política (`sla_policy_id` NULL) es de toda la organización:
    antes sólo se leían cuando el ticket tenía política, así que sin ella no
    contaba ningún festivo.
    """
    q = db.query(SDSLAHoliday)
    if policy is not None:
        q = q.filter((SDSLAHoliday.sla_policy_id == policy.id) | (SDSLAHoliday.sla_policy_id.is_(None)))
    else:
        q = q.filter(SDSLAHoliday.sla_policy_id.is_(None))
    if org_id:
        q = q.filter((SDSLAHoliday.organization_id == org_id) | (SDSLAHoliday.organization_id.is_(None)))
    dias = set()
    for r in q.all():
        try:
            dias.add(date.fromisoformat(r.holiday_date))
        except (ValueError, TypeError):
            logger.warning("festivo con fecha inválida ignorado: %s=%r", r.id, r.holiday_date)
    return frozenset(dias)


def calendario_sla(
    db: Optional[Session],
    policy: "Optional[SLAPolicy]" = None,
    org_id: Optional[str] = None,
) -> CalendarioSLA:
    """El calendario de la política, o el de los ajustes si no hay política.

    Por orden: 24x7 si la política no es de horario laboral; el calendario de
    servicio que tenga elegido (los de la página «Calendarios SLA», que hasta
    2026-11 no los leía ningún cálculo); y si no, su propio horario.

    Antes la jornada era siempre 08-18 de lunes a viernes en UTC: la política
    guardaba `business_start`, `business_end`, `business_days` y
    `business_hours_only`, y nadie los leía.
    """
    from app.services import settings_service as _ss

    org_id = org_id or getattr(policy, "organization_id", None)
    if policy is not None:
        zona = _zona(getattr(policy, "timezone", None)
                     or (_ss.get_runtime_str(db, "DEFAULT_TIMEZONE", org_id) if db is not None else None))
        if not policy.business_hours_only:
            return CalendarioSLA(zona=zona, continuo=True)
        if getattr(policy, "calendar_id", None) and db is not None:
            de_servicio = _calendario_de_servicio(db, policy, org_id)
            if de_servicio is not None:
                return de_servicio
        inicio, fin = policy.business_start, policy.business_end
        dias = parse_dias_laborables(policy.business_days)
    elif db is not None:
        zona = _zona(_ss.get_runtime_str(db, "DEFAULT_TIMEZONE", org_id))
        if not _ss.get_runtime_bool(db, "SLA_BUSINESS_HOURS_ONLY", org_id):
            return CalendarioSLA(zona=zona, continuo=True)
        inicio = _ss.get_runtime_int(db, "SLA_BUSINESS_START_HOUR", org_id)
        fin = _ss.get_runtime_int(db, "SLA_BUSINESS_END_HOUR", org_id)
        dias = parse_dias_laborables(_ss.get_runtime_str(db, "SLA_BUSINESS_DAYS", org_id))
    else:
        zona = _zona(settings.DEFAULT_TIMEZONE)
        if not settings.SLA_BUSINESS_HOURS_ONLY:
            return CalendarioSLA(zona=zona, continuo=True)
        inicio, fin = settings.SLA_BUSINESS_START_HOUR, settings.SLA_BUSINESS_END_HOUR
        dias = parse_dias_laborables(settings.SLA_BUSINESS_DAYS)

    if not (0 <= inicio < fin <= 24):
        raise ValueError(f"jornada inválida: {inicio}-{fin}")
    return CalendarioSLA(
        zona=zona,
        inicio=dt_time(inicio, 0),
        # 24 es «hasta medianoche»; `time` no admite 24:00.
        fin=dt_time(23, 59, 59, 999999) if fin == 24 else dt_time(fin, 0),
        dias=dias,
        festivos=_festivos(db, policy, org_id) if db is not None else frozenset(),
    )


def sumar_horas_sla(inicio: datetime, horas: float, cal: CalendarioSLA) -> datetime:
    """`inicio` + `horas` de reloj de SLA. Entra y sale en UTC."""
    inicio = aware(inicio)
    if cal.continuo:
        return inicio + timedelta(hours=horas)
    local = inicio.astimezone(cal.zona)
    fin = add_working_hours(local, horas, cal.inicio, cal.fin, set(cal.festivos), cal.dias)
    return fin.astimezone(timezone.utc)


def horas_sla_entre(desde: datetime, hasta: datetime, cal: CalendarioSLA) -> float:
    """Horas de reloj de SLA entre dos instantes (0 si `hasta` no es posterior)."""
    desde, hasta = aware(desde), aware(hasta)
    if hasta <= desde:
        return 0.0
    if cal.continuo:
        return (hasta - desde).total_seconds() / 3600.0
    a = desde.astimezone(cal.zona)
    b = hasta.astimezone(cal.zona)
    total = 0.0
    dia = a.date()
    while dia <= b.date():
        if _es_laborable(dia, set(cal.festivos), cal.dias):
            ini = datetime.combine(dia, cal.inicio, tzinfo=cal.zona)
            fin = datetime.combine(dia, cal.fin, tzinfo=cal.zona)
            tramo_ini, tramo_fin = max(ini, a), min(fin, b)
            if tramo_fin > tramo_ini:
                total += (tramo_fin - tramo_ini).total_seconds() / 3600.0
        dia += timedelta(days=1)
    return total


def vencimiento_efectivo(due: Optional[datetime], pause_minutes: Optional[int]) -> Optional[datetime]:
    """El vencimiento más el tiempo en pausa: mientras se espera, no corre."""
    if due is None:
        return None
    return aware(due) + timedelta(minutes=pause_minutes or 0)


def estado_sla(
    inicio: datetime,
    due: Optional[datetime],
    pause_minutes: Optional[int],
    cal: CalendarioSLA,
    aviso_pct: float,
    ahora: Optional[datetime] = None,
) -> str:
    """'breached', 'at_risk' u 'ok' para un vencimiento.

    En riesgo cuando se ha consumido `aviso_pct` (0-1) del tiempo de SLA,
    medido en horas del calendario: un P1 abierto el viernes a última hora no
    está en riesgo el domingo, porque su reloj no ha corrido.
    """
    efectivo = vencimiento_efectivo(due, pause_minutes)
    if efectivo is None:
        return "ok"
    ahora = ahora or datetime.now(timezone.utc)
    if ahora > efectivo:
        return "breached"
    total = horas_sla_entre(inicio, efectivo, cal)
    if total <= 0:
        return "ok"
    consumido = horas_sla_entre(inicio, ahora, cal) / total
    return "at_risk" if consumido >= aviso_pct else "ok"


# ── DB-coupled helpers ────────────────────────────────────────────────────────

def horas_por_prioridad(
    priority: str,
    policy: "Optional[SLAPolicy]" = None,
    db: Optional[Session] = None,
    org_id: Optional[str] = None,
) -> tuple[float, float]:
    """(respuesta_h, resolución_h) de una prioridad, por política o por ajustes."""
    if policy:
        pmap = {
            "p1_critical": (policy.p1_response_hours, policy.p1_resolution_hours),
            "p2_high":     (policy.p2_response_hours, policy.p2_resolution_hours),
            "p3_medium":   (policy.p3_response_hours, policy.p3_resolution_hours),
            "p4_low":      (policy.p4_response_hours, policy.p4_resolution_hours),
        }
        return pmap[priority]
    return get_sla_hours(db, org_id)[priority]


def calculate_sla_due(
    priority: str,
    policy: "Optional[SLAPolicy]" = None,
    db: Optional[Session] = None,
    *,
    org_id: Optional[str] = None,
    start: Optional[datetime] = None,
    hours: Optional[tuple[float, float]] = None,
) -> tuple[datetime, datetime]:
    """(vence_respuesta, vence_resolución) en el calendario de la política.

    `hours` sustituye a las horas de la prioridad: lo usa el catálogo, cuyos
    servicios declaran su propio SLA. Antes ese caso sumaba horas de reloj de
    pared y se saltaba el calendario.
    """
    resp_h, res_h = hours or horas_por_prioridad(priority, policy, db, org_id)
    cal = calendario_sla(db, policy, org_id)
    inicio = start or datetime.now(timezone.utc)
    return sumar_horas_sla(inicio, resp_h, cal), sumar_horas_sla(inicio, res_h, cal)


def _siguiente_numero(db: Session, modelo, prefijo: str, org_id: Optional[str]) -> str:
    """`PREFIJO-0001` siguiente dentro de la organizacion.

    El numero es unico por organizacion (`uq_*_org_number`). El maximo se
    busca con el filtro de organizacion EXPLICITO: en una sesion de worker no
    hay filtro de tenant y saldria el maximo de toda la base; y en PostgreSQL
    el cerrojo es por organizacion y prefijo, para que dos tickets a la vez no
    saquen el mismo numero.
    """
    from app.db.session import sin_filtro_de_tenant

    try:
        db.execute(func.pg_advisory_xact_lock(advisory_lock_key(f"{modelo.__tablename__}:{org_id}:{prefijo}")))
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except Exception:
        logger.debug("numeracion %s: SQLite / non-PG — best-effort", prefijo, exc_info=True)
    with sin_filtro_de_tenant(db):
        ultimo = (
            db.query(func.max(cast(func.substr(modelo.number, len(prefijo) + 2), Integer)))
            .filter(
                modelo.number.like(f"{prefijo}-%"),
                modelo.organization_id.is_(None) if org_id is None else modelo.organization_id == org_id,
            )
            .scalar()
        ) or 0
    return f"{prefijo}-{(ultimo + 1):04d}"


def next_ticket_number(ticket_type: str, db: Session, org_id: Optional[str] = None) -> str:
    """Siguiente numero de ticket del tipo, en la organizacion indicada o en la de la sesion."""
    prefix = TICKET_PREFIXES.get(_texto_historial(ticket_type), "TKT")
    return _siguiente_numero(db, Ticket, prefix, org_id or db.info.get("organization_id"))


def next_problem_number(db: Session, org_id: Optional[str] = None) -> str:
    return _siguiente_numero(db, Problem, "PRB", org_id or db.info.get("organization_id"))


def next_kb_number(db: Session, org_id: Optional[str] = None) -> str:
    return _siguiente_numero(db, KBArticle, "KB", org_id or db.info.get("organization_id"))


def next_ci_number(db: Session) -> str:
    last = db.query(func.max(cast(func.substr(ConfigurationItem.code, 4), Integer))).scalar() or 0
    return f"CI-{(last + 1):04d}"


def log_history(
    db: Session, ticket_id: str, field: str, old_val, new_val, user_id: str = None
) -> None:
    """Add a TicketHistory row when a field value changes.

    Los enums se guardan por su valor: `str()` de un enum de Python 3.12 da
    «TicketStatus.resolved», y eso es lo que se guardaba y se enseñaba.
    """
    antes, despues = _texto_historial(old_val), _texto_historial(new_val)
    if antes != despues:
        db.add(TicketHistory(
            ticket_id=ticket_id,
            field_name=field,
            old_value=antes,
            new_value=despues,
            changed_by_user_id=user_id,
        ))


def _texto_historial(valor) -> str:
    return str(getattr(valor, "value", valor) or "")[:500]


def get_client_from_token(authorization: Optional[str], db: Session) -> "Optional[ClientUser]":
    """Validate a client portal JWT and return the ClientUser, or None.

    Accepts either a standard "Bearer <token>" header value or the raw token.
    """
    if not authorization:
        return None

    token = authorization
    if authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1].strip()
    if not token:
        return None


    try:
        payload = jwt.decode(
            token,
            settings.CLIENT_PORTAL_SECRET,
            algorithms=["HS256"],
        )
        if payload.get("type") != "client":
            return None
        return db.query(ClientUser).filter(
            ClientUser.id == payload.get("sub"),
            ClientUser.is_active == True,
        ).first()
    except JWTError as exc:
        logger.debug("Client token validation failed: %s", exc)
        return None
    except Exception:
        logger.exception("Unexpected error in get_client_from_token")
        raise


def _estado_mostrado(due, pause_minutes, guardado, paused_at, now) -> str:
    """El estado de SLA que se enseña.

    El incumplimiento se calcula al leer, porque es exacto y no depende del
    calendario: o ya pasó el vencimiento o no. «En riesgo» sí depende —son
    horas de calendario consumidas— y lo escribe el escaneo periódico
    (`sla_monitor_service`); aquí se lee lo que dejó.
    """
    if paused_at is not None:
        return "paused"
    efectivo = vencimiento_efectivo(due, pause_minutes)
    if efectivo is not None and now > efectivo:
        return "breached"
    valor = getattr(guardado, "value", guardado)
    return "at_risk" if valor == "at_risk" else "ok"


def ticket_out(t: "Ticket", include_comments: bool = False) -> dict:
    """Serialize a Ticket ORM object to a response dict."""
    pri = PRIORITY_LABELS.get(t.priority, {"label": t.priority, "color": "#7a8aaa"})
    sta = STATUS_LABELS.get(t.status, {"label": t.status, "color": "#7a8aaa"})
    typ = TYPE_LABELS.get(t.ticket_type, {"label": t.ticket_type, "icon": "📋"})

    now = datetime.now(timezone.utc)
    resp_sla = (
        _estado_mostrado(t.sla_response_due, t.sla_pause_minutes, t.sla_response_status, t.sla_paused_at, now)
        if t.sla_response_due and not t.first_response_at
        else "ok"
    )
    res_sla = (
        _estado_mostrado(t.sla_resolution_due, t.sla_pause_minutes, t.sla_resolution_status, t.sla_paused_at, now)
        if t.sla_resolution_due and t.status not in ["resolved", "closed", "cancelled"]
        else "ok"
    )

    time_to_response = None
    if t.first_response_at and t.created_at:
        # Use pre-computed value when available (set at response time), fall back to live calc
        if getattr(t, "first_response_minutes", None) is not None:
            time_to_response = round(t.first_response_minutes / 60, 1)
        else:
            time_to_response = round(
                (aware(t.first_response_at) - aware(t.created_at)).total_seconds() / 3600, 1
            )

    time_to_resolution = None
    if t.resolved_at and t.created_at:
        # Use pre-computed value when available (set at resolution time), fall back to live calc
        if getattr(t, "resolution_minutes", None) is not None:
            time_to_resolution = round(t.resolution_minutes / 60, 1)
        else:
            time_to_resolution = round(
                (aware(t.resolved_at) - aware(t.created_at)).total_seconds() / 3600, 1
            )

    created_at_aware = aware(t.created_at)
    age_hours = round((now - created_at_aware).total_seconds() / 3600, 1) if created_at_aware else 0

    result = {
        "id": t.id,
        "number": t.number,
        "ticket_type": t.ticket_type,
        "type_label": typ["label"],
        "type_icon": typ["icon"],
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "status_label": sta["label"],
        "status_color": sta["color"],
        "priority": t.priority,
        "priority_label": pri["label"],
        "priority_color": pri["color"],
        "urgency": t.urgency,
        "impact": t.impact,
        "support_level": t.support_level,
        "source": t.source,
        "tags": t.tags,
        "requester_name": (
            t.requester_user.full_name if t.requester_user
            else (t.requester_client.full_name if t.requester_client else t.requester_name)
        ),
        "requester_email": (
            t.requester_user.email if t.requester_user
            else (t.requester_client.email if t.requester_client else t.requester_email)
        ),
        "requester_type": (
            "internal" if t.requester_user_id
            else ("client" if t.requester_client_id else "phone")
        ),
        "assigned_to_id": t.assigned_to_user_id,
        "assigned_to_name": t.assigned_to.full_name if t.assigned_to else None,
        "assigned_group_id": t.assigned_group_id,
        "assigned_group_name": t.assigned_group.name if t.assigned_group else None,
        "project_id": t.project_id,
        "project_name": t.project.name if t.project else None,
        "client_id": t.client_id,
        "client_name": (t.client.name if t.client else None) if hasattr(t, "client") else None,
        "ci_id": t.ci_id,
        "ci_name": t.ci.name if t.ci else None,
        "service_item_id": t.service_item_id,
        "service_item_name": t.service_item.name if t.service_item else None,
        "problem_id": t.problem_id,
        "sla_response_due": str(t.sla_response_due)[:16] if t.sla_response_due else None,
        "sla_resolution_due": str(t.sla_resolution_due)[:16] if t.sla_resolution_due else None,
        "sla_response_status": resp_sla,
        "sla_resolution_status": res_sla,
        "sla_response_breached": getattr(t, "sla_response_breached", False) or False,
        "sla_resolution_breached": getattr(t, "sla_resolution_breached", False) or False,
        "group_assigned_at": t.group_assigned_at.isoformat() if t.group_assigned_at else None,
        "ola_due": str(t.ola_due)[:16] if t.ola_due else None,
        "ola_breached": bool(t.ola_breached),
        "uc_contract_id": t.uc_contract_id,
        "uc_contract_name": " · ".join(x for x in (
            t.uc_contract.vendor.name if t.uc_contract and t.uc_contract.vendor else None,
            t.uc_contract.title if t.uc_contract else None) if x) or None,
        "uc_started_at": t.uc_started_at.isoformat() if t.uc_started_at else None,
        "uc_due": str(t.uc_due)[:16] if t.uc_due else None,
        "uc_breached": bool(t.uc_breached),
        "time_spent_minutes": t.time_spent_minutes,
        "time_to_response_hours": time_to_response,
        "time_to_resolution_hours": time_to_resolution,
        "age_hours": age_hours,
        "resolution": t.resolution,
        "resolution_code": t.resolution_code,
        "kb_article_id": t.kb_article_id,
        "csat_score": t.csat_score,
        "csat_comment": t.csat_comment,
        "created_at": str(t.created_at)[:16] if t.created_at else None,
        "updated_at": str(t.updated_at)[:16] if t.updated_at else None,
        "first_response_at": str(t.first_response_at)[:16] if t.first_response_at else None,
        "resolved_at": str(t.resolved_at)[:16] if t.resolved_at else None,
        "approval_status": t.approval_status,
    }

    if include_comments:
        result["comments"] = [
            {
                "id": c.id,
                "body": c.body,
                "is_public": c.is_public,
                "is_solution": c.is_solution,
                "author_name": (
                    c.author_user.full_name if c.author_user
                    else (c.author_client.full_name if c.author_client else c.author_name)
                ),
                "author_type": "agent" if c.author_user_id else "client",
                "created_at": str(c.created_at)[:16],
            }
            for c in t.comments
            if c.is_public
        ]
        result["history"] = [
            {
                "field": h.field_name,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "changed_by": h.changed_by.full_name if h.changed_by else "Sistema",
                "changed_at": str(h.changed_at)[:16],
            }
            for h in t.history
        ]

    return result
