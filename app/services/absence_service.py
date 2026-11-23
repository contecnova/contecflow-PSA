"""
absence_service.py — Lógica de negocio para ausencias.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.resources import Absence, AbsenceStatus
from app.models.settings import Holiday
from app.models.user import User
from app.models.user import UserRole
from datetime import timedelta
import logging
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)


# ── Queries ────────────────────────────────────────────────────────────────────

def list_absences(
    db: Session,
    *,
    is_superadmin: bool,
    organization_id: Optional[str],
    user_role: str,
    current_user_id: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
) -> tuple[list[Absence], int]:
    """(pagina de ausencias, total). Auditoria 2026-11: antes solo las 50 primeras."""

    q = db.query(Absence).options(joinedload(Absence.user)).filter(Absence.is_active == True)
    if not is_superadmin and organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == organization_id
        ).scalar_subquery()
        q = q.filter(Absence.user_id.in_(org_user_ids))

    if user_role in (UserRole.employee, UserRole.subcontractor):
        q = q.filter(Absence.user_id == current_user_id)
    elif user_id:
        q = q.filter(Absence.user_id == user_id)

    if date_from:
        q = q.filter(Absence.end_date >= date_from)
    if date_to:
        q = q.filter(Absence.start_date <= date_to)
    if status:
        q = q.filter(Absence.status == status)

    total = q.count()
    filas = q.order_by(Absence.start_date.desc()).offset((page - 1) * limit).limit(limit).all()
    return filas, total


def get_my_absences(db: Session, user_id: str) -> list[Absence]:
    return (
        db.query(Absence)
        .options(joinedload(Absence.user), joinedload(Absence.approver))
        .filter(Absence.user_id == user_id, Absence.is_active == True)
        .order_by(Absence.start_date.desc())
        .all()
    )


def _dias_por_defecto(db: Session, user_id: str) -> float:
    """Días de vacaciones de quien no tiene saldo propio: el ajuste de Admin de su
    empresa (revisión 2026-11; antes se leía el del fichero y Admin no hacía nada)."""
    from app.models.user import User
    from app.services.settings_service import get_runtime_int
    org_id = db.query(User.organization_id).filter(User.id == user_id).scalar()
    return float(get_runtime_int(db, "DEFAULT_VACATION_DAYS_PER_YEAR", org_id))


def exigir_saldo(db: Session, user_id: str, tipo, start_date: date, dias: float, liberados: float = 0) -> None:
    """Un tipo que descuenta del saldo de vacaciones no puede pasar de lo que queda.

    Revisión 167: el tipo es configurable (`tipos_de_ausencia.saldo`); la clave
    antigua `vacation` sigue valiendo.
    """
    from app.services.ausencias import catalogo
    t = catalogo.tipo_por_clave(db, str(getattr(tipo, "value", tipo)))
    if t is None or not t.descuenta_saldo or t.saldo != "vacaciones":
        return
    quedan = get_vacation_balance(db, user_id, start_date.year)["days_remaining"] + liberados
    if dias > quedan:
        raise error(400, "vacaciones_insuficientes", pedidos=dias, quedan=quedan, anio=start_date.year)


def get_vacation_balance(db: Session, user_id: str, year: int) -> dict:
    """El saldo de vacaciones (formato de siempre), sobre `ausencias.saldos`:
    cuentan todos los tipos con saldo «vacaciones»; lo pendiente incluye la lista de espera."""
    from app.services.ausencias import saldos
    v = saldos.vacaciones(db, user_id, year)
    return {
        "year": year,
        "days_entitled": v["derecho"],
        "days_carried": round(v["arrastre"], 1),
        "days_taken": round(v["usado"], 1),
        "days_pending": round(v["pedido"], 1),
        "days_remaining": round(v["restante"], 1),
    }


def get_overlap(
    db: Session,
    user_id: str,
    start_date: date,
    end_date: date,
    exclude_id: Optional[str] = None,
) -> Optional[Absence]:
    q = db.query(Absence).filter(
        Absence.user_id == user_id,
        Absence.is_active == True,
        Absence.status.in_([AbsenceStatus.pending, AbsenceStatus.approved]),
        Absence.start_date <= end_date,
        Absence.end_date >= start_date,
    )
    if exclude_id:
        q = q.filter(Absence.id != exclude_id)
    return q.first()


def get_holidays(db: Session) -> list[Holiday]:
    return db.query(Holiday).all()


def get_holidays_for_period(db: Session, start: date, end: date) -> list[Holiday]:
    return db.query(Holiday).filter(
        Holiday.date >= str(start),
        Holiday.date <= str(end),
    ).all()


def get_absence_for_user(db: Session, absence_id: str, user_id: str) -> Optional[Absence]:
    return db.query(Absence).filter(
        Absence.id == absence_id,
        Absence.user_id == user_id,
        Absence.is_active == True,
    ).first()


def get_absence_by_id(db: Session, absence_id: str) -> Optional[Absence]:
    return db.query(Absence).filter(Absence.id == absence_id, Absence.is_active == True).first()


def get_team_absences(
    db: Session,
    *,
    month: Optional[str] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
) -> list[Absence]:

    q = db.query(Absence).options(joinedload(Absence.user), joinedload(Absence.approver)).filter(Absence.is_active == True)
    if month:
        year, m = int(month.split("-")[0]), int(month.split("-")[1])
        month_start = date(year, m, 1)
        month_end = date(year, m, 28) + timedelta(days=4)
        month_end = month_end.replace(day=1) - timedelta(days=1)
        q = q.filter(Absence.start_date <= month_end, Absence.end_date >= month_start)
    if user_id:
        q = q.filter(Absence.user_id == user_id)
    if status:
        q = q.filter(Absence.status == status)
    return q.order_by(Absence.start_date.desc()).limit(200).all()


def get_pending_absences(db: Session) -> list[Absence]:
    return (
        db.query(Absence)
        .options(joinedload(Absence.user))
        .filter(Absence.is_active == True)
        .filter(Absence.status == AbsenceStatus.pending)
        .order_by(Absence.start_date)
        .all()
    )


def get_calendar_data(
    db: Session, month_start: date, month_end: date
) -> tuple[list[Absence], list[Holiday]]:
    absences = (
        db.query(Absence)
        .options(joinedload(Absence.user))
        .filter(
            Absence.is_active == True,
            Absence.status == AbsenceStatus.approved,
            Absence.start_date <= month_end,
            Absence.end_date >= month_start,
        )
        .all()
    )
    holidays = get_holidays_for_period(db, month_start, month_end)
    return absences, holidays


def get_user_year_absences(
    db: Session, user_id: str, year: int
) -> list[Absence]:
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)
    return db.query(Absence).filter(
        Absence.user_id == user_id,
        Absence.is_active == True,
        Absence.status == AbsenceStatus.approved,
        Absence.start_date >= year_start,
        Absence.start_date < year_end,
    ).all()


# ── Mutations ──────────────────────────────────────────────────────────────────

def create_absence(db: Session, *, user_id: str, type: str, start_date: date, end_date: date,
                   reason: Optional[str], working_days: float = 0) -> Absence:
    """Compatibilidad: pide la ausencia por el ciclo completo (políticas, cupos, aprobación)."""
    from app.services.ausencias import solicitudes
    usuario = db.query(User).filter(User.id == user_id).first()
    return solicitudes.solicitar(db, usuario, {"type": str(getattr(type, "value", type)), "start_date": start_date,
                                               "end_date": end_date, "reason": reason})


def cancel_absence(db: Session, absence: Absence, usuario=None) -> None:
    from app.services.ausencias import solicitudes
    usuario = usuario or db.query(User).filter(User.id == absence.user_id).first()
    solicitudes.cancelar(db, usuario, absence)


def update_absence(db: Session, absence: Absence, *, type: str, start_date: date, end_date: date,
                   reason: Optional[str], working_days: float = 0, usuario=None) -> Absence:
    from app.services.ausencias import solicitudes
    usuario = usuario or db.query(User).filter(User.id == absence.user_id).first()
    return solicitudes.editar(db, usuario, absence, {"type": str(getattr(type, "value", type)),
                                                     "start_date": start_date, "end_date": end_date, "reason": reason})


def review_absence(db: Session, absence: Absence, *, approved: bool, approver_id: Optional[str],
                   rejection_reason: Optional[str]) -> Absence:
    """La decisión final (bandeja de aprobaciones o responsable): `solicitudes.aplicar_decision`."""
    from app.services.ausencias import solicitudes
    actor = db.query(User).filter(User.id == approver_id).first() if approver_id else None
    return solicitudes.aplicar_decision(db, absence, approved, actor, rejection_reason)


# ── Label constants ─────────────────────────────────────────────────────────────

_TIPOS_DE_AUSENCIA = ("vacation", "sick", "personal", "training", "maternity", "paternity", "other")
_COLORES_DE_ESTADO = {"pending": "#ffb800", "approved": "#00e5a0", "rejected": "#ff4757",
                      "cancelled": "#7a8aaa", "waitlisted": "#4f8cff"}


def etiqueta_de_tipo(tipo: str, idioma: Optional[str] = None) -> str:
    """Nombre del tipo de ausencia de serie en `idioma` (23-11-2026: antes castellano fijo)."""
    from app.services.textos_de_salida import texto
    return texto(f"ausencia.tipo.{tipo}", idioma) if tipo in _TIPOS_DE_AUSENCIA or tipo == "private" else tipo


def etiqueta_de_estado(estado: str, idioma: Optional[str] = None) -> str:
    from app.services.textos_de_salida import texto
    return texto(f"ausencia.estado.{estado}", idioma) if estado in _COLORES_DE_ESTADO else estado


#: Por compatibilidad: etiquetas en el idioma de respaldo (castellano); lo que sale a una
#: persona se pide con `etiqueta_de_tipo` / `etiqueta_de_estado` en su idioma.
TYPE_LABELS = {t: etiqueta_de_tipo(t) for t in _TIPOS_DE_AUSENCIA}
STATUS_CFG = {e: {"label": etiqueta_de_estado(e), "color": c} for e, c in _COLORES_DE_ESTADO.items()}


# Auditoría 22-11-2026 (§5): `count_working_days` retirada (sin uso; el cómputo de
# días es `horario.efectivo`).


def serialize_absence(a, viewer=None, db=None) -> dict:
    """Formato de siempre más lo de la revisión 167 (tipo configurable, turno,
    sustituto, cantidad y unidad). Con `viewer`, un tipo privado (p. ej. baja
    médica) se enseña como «Ausencia» a quien no es la persona, RRHH o tiene
    acceso especial; y su motivo no se enseña."""
    st = getattr(a.status, "value", a.status)
    t = getattr(a, "absence_type", None)
    idioma = None
    if db is not None and viewer is not None:
        from app.services.formato_regional import idioma_de_salida
        idioma = idioma_de_salida(db, user_id=getattr(viewer, "id", None),
                                  org_id=getattr(viewer, "organization_id", None))
    # M47 (auditoría 22-11-2026): falla cerrado. Sin quien mira, solo se enseña
    # un tipo visible para todos (antes, sin `viewer`, se enseñaba todo, también
    # una baja médica: dato de salud, art. 9 RGPD).
    if viewer is None or db is None:
        oculto = getattr(t, "visibilidad", "equipo") != "todos"
    else:
        oculto = not puede_ver_tipo(db, viewer, a)
    # El MOTIVO (texto libre, puede llevar el diagnóstico) solo lo ven la persona,
    # RR. HH., administración y el acceso especial; no el PM ni el team lead.
    motivo_visible = not oculto and viewer is not None and db is not None and puede_ver_motivo(db, viewer, a)
    return {
        "id": a.id,
        "user_id": a.user_id,
        "user_name": a.user.full_name if a.user else "—",
        "type": "private" if oculto else a.type,
        "type_label": etiqueta_de_tipo("private", idioma) if oculto else (t.nombre if t else etiqueta_de_tipo(a.type, idioma)),
        "absence_type_id": None if oculto else a.absence_type_id,
        "type_color": "#7a8aaa" if oculto or t is None else t.color,
        "type_icon": "circle" if oculto or t is None else t.icono,
        "status": st,
        "status_label": etiqueta_de_estado(st, idioma),
        "status_color": _COLORES_DE_ESTADO.get(st, "#7a8aaa"),
        "start_date": str(a.start_date),
        "end_date": str(a.end_date),
        "working_days": a.working_days,
        "amount": a.amount, "unit": a.unit, "hours": a.hours,
        # Rev. 180: por horas (franja de cada día) y horas de su horario que cubre.
        "modo": a.modo or ("horas" if a.start_time else "dias"),
        "start_time": a.start_time.strftime("%H:%M") if a.start_time else None,
        "end_time": a.end_time.strftime("%H:%M") if a.end_time else None,
        "scheduled_hours": a.scheduled_hours,
        "half_day_start": bool(a.half_day_start), "half_day_end": bool(a.half_day_end),
        "shift_id": a.shift_id, "substitute_id": a.substitute_id,
        "substitute_name": a.substitute.full_name if getattr(a, "substitute", None) else None,
        "reason": a.reason if motivo_visible else None,
        "approved_by": a.approver.full_name if a.approver else None,
        "approved_at": str(a.approved_at)[:10] if a.approved_at else None,
        "rejection_reason": a.rejection_reason if motivo_visible else None,
        "created_at": str(a.created_at)[:10] if a.created_at else None,
        "requested_at": a.requested_at.isoformat() if a.requested_at else None,
        "private": oculto,
    }


def puede_ver_motivo(db: Session, viewer, a) -> bool:
    """M47: el motivo de una ausencia, solo la persona, RR. HH., admin y el acceso especial."""
    if viewer.id == a.user_id or getattr(viewer, "is_superadmin", False):
        return True
    if str(getattr(viewer.role, "value", viewer.role)) in ("admin", "hr"):
        return True
    from app.services.ausencias.catalogo import tiene_acceso_especial
    return tiene_acceso_especial(db, viewer)


def puede_ver_tipo(db: Session, viewer, a) -> bool:
    """Visibilidad del tipo: `todos`; `equipo` (su equipo y quien gestiona); `privada`
    (la persona, RRHH y el acceso especial)."""
    if viewer.id == a.user_id or getattr(viewer, "is_superadmin", False):
        return True
    t = getattr(a, "absence_type", None)
    vis = t.visibilidad if t is not None else "equipo"
    rol = str(getattr(viewer.role, "value", viewer.role))
    if vis == "todos":
        return True
    if vis == "privada":
        from app.services.ausencias.catalogo import tiene_acceso_especial
        return tiene_acceso_especial(db, viewer)
    if rol in ("admin", "hr", "pm", "team_lead"):
        return True
    return bool(viewer.team) and a.user is not None and a.user.team == viewer.team
