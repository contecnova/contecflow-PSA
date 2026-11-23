"""
timesheet_service.py — Funciones de servicio para gestión de timesheets.
"""
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date, timedelta

from app.models.financial import Timesheet, TimesheetStatus
from app.models.imputation import Imputation
from app.models.user import User
from app.core import timeutil
from app.core.paginacion import Pagina, Paginacion, paginar
from app.services.textos_guardados import pintar_campo


def get_timesheet_lines(db: Session, user_id: str, week_start: date) -> list:
    """Devuelve las líneas (imputaciones) de un timesheet para la semana dada."""
    week_end = week_start + timedelta(days=6)
    imputations = (
        db.query(Imputation)
        .options(joinedload(Imputation.project), joinedload(Imputation.task))
        .filter(
            Imputation.user_id == user_id,
            Imputation.date >= week_start,
            Imputation.date <= week_end,
            # Segunda auditoria 2026-11: las imputaciones borradas (soft-delete)
            # seguian saliendo como lineas del timesheet.
            Imputation.is_active == True,  # noqa: E712
        )
        .order_by(Imputation.date)
        .all()
    )
    return [
        {
            "id": imp.id,
            "date": str(imp.date),
            "hours": imp.hours,
            "project_id": imp.project_id,
            "project_name": imp.project.name if imp.project else None,
            "task_id": imp.task_id,
            "task_title": imp.task.title if imp.task else None,
            "description": imp.description,
            "billable": imp.is_billable,
            # Segunda auditoria 2026-11: la pantalla oculta editar y borrar en las aprobadas.
            "is_approved": bool(imp.is_approved),
        }
        for imp in imputations
    ]


def _filtrar_listado(q, buscar: Optional[str], desde: Optional[date], hasta: Optional[date]):
    """Filtros comunes de los listados de revisión: texto (persona o semana) y rango de semanas.

    Se aplican en SQL para que la paginación cuente y corte sobre lo ya filtrado.
    """
    if buscar and buscar.strip():
        patron = f"%{buscar.strip().lower()}%"
        q = q.join(User, User.id == Timesheet.user_id).filter(or_(
            func.lower(User.full_name).like(patron),
            cast(Timesheet.week_start, String).like(patron),
        ))
    if desde:
        q = q.filter(Timesheet.week_start >= desde)
    if hasta:
        q = q.filter(Timesheet.week_start <= hasta)
    return q


# Orden permitido en el listado del equipo (clave pública -> columna).
ORDENES_DEL_EQUIPO = {
    "week_start": Timesheet.week_start,
    "total_hours": Timesheet.total_hours,
    "billable_hours": Timesheet.billable_hours,
    "total_cost": Timesheet.total_cost,
    "status": Timesheet.status,
    "user_name": User.full_name,
}


def list_pending_timesheets(
    db: Session,
    pagina: Optional[Paginacion] = None,
    buscar: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
) -> Pagina:
    """Timesheets pendientes de revisión (una página; sin ella, hasta LIST_MAX_ROWS)."""
    q = (
        db.query(Timesheet)
        .options(joinedload(Timesheet.user))
        .filter(Timesheet.status == TimesheetStatus.submitted)
    )
    q = _filtrar_listado(q, buscar, desde, hasta)
    return paginar(q.order_by(Timesheet.week_start.desc(), Timesheet.id), pagina,
                   "timesheets.pending").mapear(_enrich_one)


def list_team_timesheets(
    db: Session,
    week_start: Optional[date],
    user_id: Optional[str],
    status: Optional[str],
    pagina: Optional[Paginacion] = None,
    buscar: Optional[str] = None,
    desde: Optional[date] = None,
    hasta: Optional[date] = None,
    orden: str = "week_start",
    sentido: str = "desc",
) -> Pagina:
    """Devuelve timesheets del equipo con filtros opcionales, ordenados en SQL."""
    q = db.query(Timesheet).options(joinedload(Timesheet.user))
    if week_start:
        q = q.filter(Timesheet.week_start == week_start)
    if user_id:
        q = q.filter(Timesheet.user_id == user_id)
    if status:
        q = q.filter(Timesheet.status == status)
    q = _filtrar_listado(q, buscar, desde, hasta)
    columna = ORDENES_DEL_EQUIPO.get(orden, Timesheet.week_start)
    if orden == "user_name" and not (buscar and buscar.strip()):
        q = q.join(User, User.id == Timesheet.user_id)
    criterio = columna.asc() if sentido == "asc" else columna.desc()
    return paginar(q.order_by(criterio, Timesheet.id), pagina,
                   "timesheets.team").mapear(_enrich_one)


def _enrich_one(ts) -> dict:
    return _enrich([ts])[0]


def _enrich(timesheets) -> list:
    """Añade user_name y reviewer_name a los resultados."""
    result = []
    for ts in timesheets:
        item = {
            "id": ts.id,
            "user_id": ts.user_id,
            "week_start": ts.week_start,
            "week_end": ts.week_end,
            "status": ts.status.value if hasattr(ts.status, "value") else ts.status,
            "total_hours": ts.total_hours or 0,
            "billable_hours": ts.billable_hours or 0,
            "total_cost": ts.total_cost or 0,
            "submitted_at": ts.submitted_at,
            "reviewed_at": ts.reviewed_at,
            "review_notes": pintar_campo(ts, "review_notes"),
            "user_name": ts.user.full_name if ts.user else None,
            "reviewer_name": None,
        }
        result.append(item)
    return result


# ── Date utilities ────────────────────────────────────────────────────────────

def get_week_bounds(week_start) -> tuple:
    """Return (week_start, week_end) for the given date, defaulting to current week."""
    if not week_start:
        today = timeutil.today()
        week_start = today - timedelta(days=today.weekday())
    return week_start, week_start + timedelta(days=6)
