"""OKRs — Objectives & Key Results."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse
from app.models.user import User
from app.services import okr_service
from app.services.okr_service import (
    serialize_kr as _ser_kr,
    serialize_objective as _ser_objective,
    sync_kr_from_tasks as _sync_kr_from_tasks,
)
from app.schemas.okrs import ObjectiveIn, KeyResultIn, ObjectiveUpdate, KeyResultUpdate, OKRCheckinIn as CheckinIn
from datetime import datetime

router = APIRouter(tags=["OKRs"])


# ── Objectives CRUD ───────────────────────────────────────────────────────────
@router.get("", response_model=APIListResponse[dict], summary="Listar objetivos")
def list_objectives(
    year: int = Query(default=None),
    period: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    objectives = okr_service.list_objectives(
        db,
        year=year or datetime.now().year,
        period=period,
        status=status,
        owner_id=owner_id,
        is_superadmin=cu.is_superadmin,
        organization_id=cu.organization_id,
    )
    items = [_ser_objective(o) for o in objectives]
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("", summary="Crear objetivo", status_code=201)
def create_objective(payload: ObjectiveIn, db: Session = Depends(get_db),
                     cu: User = Depends(require_any_manager)):
    obj = okr_service.create_objective(db, payload.model_dump())
    return {"id": obj.id, "title": obj.title}


@router.patch("/{obj_id}", summary="Actualizar objetivo")
def update_objective(obj_id: str, payload: ObjectiveUpdate,
                     db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    obj = okr_service.get_objective(db, obj_id)
    if not obj:
        raise HTTPException(404, "Objetivo no encontrado")
    obj = okr_service.update_objective(db, obj, payload.model_dump(exclude_unset=True))
    return {"id": obj.id}


@router.delete("/{obj_id}", summary="Eliminar objetivo (soft delete)")
def delete_objective(obj_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_any_manager)):
    """Delete (soft) an OKR objective. Blocked if active Key Results exist."""
    enforce_abac(db, cu, "okr", obj_id, action="delete")
    obj = okr_service.get_objective(db, obj_id)
    if not obj:
        raise HTTPException(404, "Objetivo no encontrado")
    result = okr_service.delete_objective(db, obj)
    if not result["ok"]:
        raise HTTPException(400, result["message"])
    return result


# ── Key Results CRUD ──────────────────────────────────────────────────────────
@router.post("/key-results", summary="Añadir Key Result", status_code=201)
def create_kr(payload: KeyResultIn, db: Session = Depends(get_db),
              cu: User = Depends(require_any_manager)):
    obj = okr_service.get_objective(db, payload.objective_id)
    if not obj:
        raise HTTPException(404, "Objetivo no encontrado")
    kr = okr_service.create_kr(db, payload.model_dump())
    return _ser_kr(kr)


@router.patch("/key-results/{kr_id}", summary="Actualizar Key Result")
def update_kr(kr_id: str, payload: KeyResultUpdate,
              db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    kr = okr_service.get_key_result(db, kr_id)
    if not kr:
        raise HTTPException(404, "KR no encontrado")
    kr = okr_service.update_kr(db, kr, payload.model_dump(exclude_unset=True))
    return _ser_kr(kr)


@router.delete("/key-results/{kr_id}", summary="Eliminar Key Result (soft delete)")
def delete_kr(kr_id: str, db: Session = Depends(get_db),
              cu: User = Depends(require_any_manager)):
    """Delete (soft) a Key Result from its objective."""
    enforce_abac(db, cu, "kr", kr_id, action="delete")
    kr = okr_service.get_key_result(db, kr_id)
    if not kr:
        raise HTTPException(404, "KR no encontrado")
    result = okr_service.delete_kr(db, kr)
    return result


# ── Check-ins ─────────────────────────────────────────────────────────────────
@router.post("/key-results/{kr_id}/checkin", summary="Registrar progreso", status_code=201)
def checkin_kr(kr_id: str, payload: CheckinIn,
               db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    kr = okr_service.get_key_result(db, kr_id)
    if not kr:
        raise HTTPException(404, "KR no encontrado")
    kr = okr_service.checkin_kr(db, kr, payload.value, payload.note, cu.id)
    return {"progress": kr.progress, "current_value": kr.current_value}


# ── Project→Task cascade sync ─────────────────────────────────────────────────
@router.post(
    "/key-results/{kr_id}/sync-from-tasks",
    summary="Sincronizar KR con progreso de tareas del proyecto vinculado",
    status_code=200,
)
def sync_kr_from_tasks(
    kr_id: str,
    db: Session = Depends(get_db),
    cu: User = Depends(require_any_manager),
):
    return _sync_kr_from_tasks(kr_id, cu.id, db)
