from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User, UserRole
from app.models.resources import AbsenceStatus
from app.services import absence_service
from app.services.absence_service import (
    TYPE_LABELS, count_working_days as _working_days, serialize_absence as _absence_out,
)
from app.schemas.absences import AbsenceIn, AbsenceReview

router = APIRouter()


@router.get("", summary="Listar ausencias con filtros de fecha (global)")
def list_absences(
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    user_id:   Optional[str]  = None,
    status:    Optional[str]  = None,
    limit:     int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista ausencias con filtros opcionales de fecha y usuario.
    Admins/managers ven todas; empleados solo las suyas.
    """
    absences = absence_service.list_absences(
        db,
        is_superadmin=current_user.is_superadmin,
        organization_id=current_user.organization_id,
        user_role=current_user.role,
        current_user_id=current_user.id,
        date_from=date_from,
        date_to=date_to,
        user_id=user_id,
        status=status,
        limit=limit,
    )
    return [_absence_out(a) for a in absences]


@router.get("/my", summary="Mis ausencias")
def get_my_absences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    absences = absence_service.get_my_absences(db, current_user.id)
    return [_absence_out(a) for a in absences]

@router.get("/my/vacation-balance", summary="Mi balance de vacaciones del año actual")
def get_my_vacation_balance(
    year: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Devuelve los días de vacaciones disponibles, usados y pendientes del usuario autenticado."""
    from datetime import datetime as dt_mod
    if not year:
        year = dt_mod.now().year
    return absence_service.get_vacation_balance(db, current_user.id, year)


@router.post("/my", summary="Solicitar ausencia")
def request_absence(
    payload: AbsenceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "La fecha de fin no puede ser anterior a la de inicio")

    overlap = absence_service.get_overlap(db, current_user.id, payload.start_date, payload.end_date)
    if overlap:
        raise HTTPException(400, f"Ya tienes una ausencia solapada del {overlap.start_date} al {overlap.end_date}")

    holidays = absence_service.get_holidays(db)
    days = _working_days(payload.start_date, payload.end_date, holidays)

    absence = absence_service.create_absence(
        db,
        user_id=current_user.id,
        type=payload.type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        working_days=days,
    )
    return _absence_out(absence)


@router.delete("/my/{absence_id}", summary="Cancelar ausencia")
def cancel_absence(
    absence_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = absence_service.get_absence_for_user(db, absence_id, current_user.id)
    if not a:
        raise HTTPException(404, "Ausencia no encontrada")
    if a.status == AbsenceStatus.approved and a.start_date <= date.today():
        raise HTTPException(400, "No puedes cancelar una ausencia ya iniciada")
    absence_service.cancel_absence(db, a)
    return {"ok": True}


@router.patch("/my/{absence_id}", summary="Editar ausencia pendiente")
def edit_absence(
    absence_id: str,
    payload: AbsenceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Permite editar una ausencia propia mientras esté en estado 'pending'."""
    a = absence_service.get_absence_for_user(db, absence_id, current_user.id)
    if not a:
        raise HTTPException(404, "Ausencia no encontrada")
    if a.status != AbsenceStatus.pending:
        raise HTTPException(400, f"Solo se pueden editar ausencias pendientes. Esta está '{a.status.value}'")
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "La fecha de fin no puede ser anterior a la de inicio")

    overlap = absence_service.get_overlap(
        db, current_user.id, payload.start_date, payload.end_date, exclude_id=absence_id
    )
    if overlap:
        raise HTTPException(400, f"Solapamiento con ausencia del {overlap.start_date} al {overlap.end_date}")

    holidays = absence_service.get_holidays(db)
    days = _working_days(payload.start_date, payload.end_date, holidays)

    a = absence_service.update_absence(
        db, a,
        type=payload.type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        reason=payload.reason,
        working_days=days,
    )
    return _absence_out(a)


@router.get("/team", summary="Ausencias del equipo")
def get_team_absences(
    month: Optional[str] = None,  # YYYY-MM
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    absences = absence_service.get_team_absences(db, month=month, user_id=user_id, status=status)
    return [_absence_out(a) for a in absences]


@router.get("/pending", summary="Ausencias pendientes de aprobación")
def get_pending_absences(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    absences = absence_service.get_pending_absences(db)
    return [_absence_out(a) for a in absences]


@router.post("/{absence_id}/review", summary="Aprobar o rechazar ausencia")
def review_absence(
    absence_id: str,
    payload: AbsenceReview,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    a = absence_service.get_absence_by_id(db, absence_id)
    if not a:
        raise HTTPException(404, "Ausencia no encontrada")
    if a.status != AbsenceStatus.pending:
        raise HTTPException(400, "Solo se pueden revisar ausencias pendientes")

    a = absence_service.review_absence(
        db, a,
        approved=payload.approved,
        approver_id=current_user.id,
        rejection_reason=payload.rejection_reason,
    )
    return {"message": "Aprobada" if payload.approved else "Rechazada", "status": a.status}


@router.get("/calendar", summary="Calendario de ausencias del equipo")
def get_absence_calendar(
    year: int = Query(default=None),
    month: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime
    if not year:
        year = datetime.now().year
    if not month:
        month = datetime.now().month

    month_start = date(year, month, 1)
    next_month = date(year + (month // 12), (month % 12) + 1, 1)
    month_end = next_month - timedelta(days=1)

    absences, holidays = absence_service.get_calendar_data(db, month_start, month_end)

    return {
        "year": year, "month": month,
        "absences": [_absence_out(a) for a in absences],
        "holidays": [{"date": h.date, "name": h.name, "type": h.type} for h in holidays],
    }


@router.get("/summary/{user_id}", summary="Resumen de ausencias de un usuario")
def get_user_absence_summary(
    user_id: str,
    year: int = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from datetime import datetime
    if not year:
        year = datetime.now().year
    if current_user.role not in [UserRole.admin, UserRole.hr] and current_user.id != user_id:
        raise HTTPException(403, "Acceso denegado")

    absences = absence_service.get_user_year_absences(db, user_id, year)

    by_type = {}
    for a in absences:
        t = a.type
        by_type[t] = by_type.get(t, 0) + (a.working_days or 0)

    return {
        "user_id": user_id, "year": year,
        "total_days": sum(by_type.values()),
        "by_type": {t: {"days": d, "label": TYPE_LABELS.get(t, t)} for t, d in by_type.items()},
        "vacation_days_taken": by_type.get("vacation", 0),
        "sick_days": by_type.get("sick", 0),
    }
