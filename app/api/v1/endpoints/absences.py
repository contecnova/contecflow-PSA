from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date, timedelta

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User, UserRole
from app.services import absence_service
from app.services.ausencias import solicitudes
from app.services.absence_service import (
    TYPE_LABELS, serialize_absence as _absence_out,
)
from app.schemas.absences import AbsenceIn, AbsenceReview
from app.core.constantes import MAX_TAMANO_DE_PAGINA

router = APIRouter()


@router.get("", summary="Listar ausencias con filtros de fecha (global)")
def list_absences(
    date_from: Optional[date] = None,
    date_to:   Optional[date] = None,
    user_id:   Optional[str]  = None,
    status:    Optional[str]  = None,
    limit:     Optional[int] = Query(None, ge=1, le=MAX_TAMANO_DE_PAGINA),
    page:      int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista ausencias con filtros opcionales de fecha y usuario, paginada.
    `limit` se conserva como alias de `page_size` (auditoria 2026-11: la
    pantalla mandaba `page_size` y se ignoraba).
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
        limit=limit or page_size,
        page=page,
    )
    absences, total = absences
    items = [_absence_out(a, current_user, db) for a in absences]
    return APIListResponse.ok(items=items, total=total, page=page, page_size=limit or page_size)


@router.get("/my", response_model=APIListResponse[dict], summary="Mis ausencias")
def get_my_absences(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    absences = absence_service.get_my_absences(db, current_user.id)
    items = [_absence_out(a, current_user, db) for a in absences]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)

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
    return APIResponse.ok(data=absence_service.get_vacation_balance(db, current_user.id, year))


@router.post("/my", summary="Solicitar ausencia")
def request_absence(
    payload: AbsenceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Pide una ausencia: políticas del dominio `ausencias`, cupos (con lista de
    espera) y flujo de aprobación (revisión 167). `type` (clave) sigue valiendo."""
    absence = solicitudes.solicitar(db, current_user, payload.model_dump())
    return APIResponse.ok(data=_absence_out(absence, current_user, db))


@router.delete("/my/{absence_id}", summary="Cancelar ausencia")
def cancel_absence(
    absence_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    a = absence_service.get_absence_for_user(db, absence_id, current_user.id)
    if not a:
        raise HTTPException(404, "Ausencia no encontrada")
    enforce_abac(db, current_user, "absence", absence_id, action="delete")
    solicitudes.cancelar(db, current_user, a)
    return APIResponse.ok(data={"ok": True, "message": "Ausencia cancelada correctamente"})


@router.patch("/my/{absence_id}", summary="Editar ausencia pendiente o en espera")
def edit_absence(
    absence_id: str,
    payload: AbsenceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edita una ausencia propia pendiente o en lista de espera: se vuelve a evaluar y a reservar."""
    a = absence_service.get_absence_for_user(db, absence_id, current_user.id)
    if not a:
        raise HTTPException(404, "Ausencia no encontrada")
    a = solicitudes.editar(db, current_user, a, payload.model_dump())
    return APIResponse.ok(data=_absence_out(a, current_user, db))


@router.get("/team", summary="Ausencias del equipo")
def get_team_absences(
    month: Optional[str] = None,  # YYYY-MM
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    absences = absence_service.get_team_absences(db, month=month, user_id=user_id, status=status)
    items = [_absence_out(a, current_user, db) for a in absences]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/pending", response_model=APIListResponse[dict], summary="Ausencias pendientes de aprobación")
def get_pending_absences(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=MAX_TAMANO_DE_PAGINA),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    absences = absence_service.get_pending_absences(db)
    items = [_absence_out(a, current_user, db) for a in absences]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


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
    # Quien pide no aprueba (segunda auditoría 2026-11): antes de elegir camino,
    # así vale igual para el voto en la bandeja que para la decisión directa.
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, a.user_id, current_user, "absence", a.id)
    # Revisión 167: con solicitud en la bandeja es un voto en ESA solicitud
    # (multinivel, en paralelo, delegación); sin ella, la decisión directa.
    a = solicitudes.revisar(db, current_user, a, payload.approved, payload.rejection_reason)
    estado = getattr(a.status, "value", a.status)
    return APIResponse.ok(data={"message": "Aprobada" if estado == "approved" else (
        "Rechazada" if estado == "rejected" else "Voto registrado"), "status": estado})


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

    return APIResponse.ok(data={
        "year": year, "month": month,
        "absences": [_absence_out(a, current_user, db) for a in absences],
        "holidays": [{"date": h.date, "name": h.name, "type": h.type} for h in holidays],
    })


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

    return APIResponse.ok(data={
        "user_id": user_id, "year": year,
        "total_days": sum(by_type.values()),
        "by_type": {t: {"days": d, "label": TYPE_LABELS.get(t, t)} for t, d in by_type.items()},
        "vacation_days_taken": by_type.get("vacation", 0),
        "sick_days": by_type.get("sick", 0),
    })
