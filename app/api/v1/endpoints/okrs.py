"""OKRs — Objectives & Key Results."""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from app.models.project import Project
from typing import Optional
from pydantic import BaseModel
from datetime import date
import uuid as _uuid

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.models.okrs import Objective, KeyResult, KRCheckin
from app.models.project import Project
from app.services.okr_service import (
    calc_progress as _calc_progress,
    serialize_kr as _ser_kr,
    serialize_objective as _ser_objective,
    task_progress_for_project as _task_progress_for_project,
    propagate_to_objective as _propagate_to_objective,
    sync_kr_from_tasks as _sync_kr_from_tasks,
)

router = APIRouter(prefix="/okrs", tags=["OKRs"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class ObjectiveIn(BaseModel):
    title: str
    description: Optional[str] = None
    owner_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    period: str = "Q1"
    year: int = 2025
    status: str = "draft"

class KeyResultIn(BaseModel):
    objective_id: str
    title: str
    kr_type: str = "percentage"
    target_value: float = 100
    current_value: float = 0
    unit: Optional[str] = None
    owner_id: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None

class ObjectiveUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    team_id: Optional[str] = None
    project_id: Optional[str] = None
    period: Optional[str] = None
    year: Optional[int] = None
    status: Optional[str] = None

class KeyResultUpdate(BaseModel):
    title: Optional[str] = None
    kr_type: Optional[str] = None
    target_value: Optional[float] = None
    current_value: Optional[float] = None
    unit: Optional[str] = None
    owner_id: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None

class CheckinIn(BaseModel):
    value: float
    note: Optional[str] = None



# ── Objectives CRUD ───────────────────────────────────────────────────────────
@router.get("", summary="Listar objetivos")
def list_objectives(
    year: int = Query(default=2025),
    period: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    db: Session = Depends(get_db),
    cu: User = Depends(get_current_user),
):
    q = db.query(Objective).options(
        joinedload(Objective.key_results).joinedload(KeyResult.owner),
        joinedload(Objective.owner)
    ).filter(Objective.year == year)
    if not cu.is_superadmin and cu.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == cu.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == cu.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                Objective.owner_id.in_(org_user_ids),
                Objective.project_id.in_(org_project_ids),
            )
        )
    if period:  q = q.filter(Objective.period == period)
    if status:  q = q.filter(Objective.status == status)
    if owner_id: q = q.filter(Objective.owner_id == owner_id)
    return [_ser_objective(o) for o in q.order_by(Objective.created_at.desc()).all()]


@router.post("", summary="Crear objetivo", status_code=201)
def create_objective(payload: ObjectiveIn, db: Session = Depends(get_db),
                     cu: User = Depends(require_any_manager)):
    obj = Objective(id=str(_uuid.uuid4()), **payload.model_dump())
    db.add(obj); db.commit(); db.refresh(obj)
    return {"id": obj.id, "title": obj.title}


@router.patch("/{obj_id}", summary="Actualizar objetivo")
def update_objective(obj_id: str, payload: ObjectiveUpdate,
                     db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    obj = db.query(Objective).filter(Objective.id == obj_id).first()
    if not obj: raise HTTPException(404, "Objetivo no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    db.commit(); db.refresh(obj)
    return {"id": obj.id}


@router.delete("/{obj_id}", summary="Eliminar objetivo")
def delete_objective(obj_id: str, db: Session = Depends(get_db),
                     cu: User = Depends(require_any_manager)):
    obj = db.query(Objective).filter(Objective.id == obj_id).first()
    if not obj: raise HTTPException(404, "Objetivo no encontrado")
    db.delete(obj); db.commit()
    return {"deleted": True}


# ── Key Results CRUD ──────────────────────────────────────────────────────────
@router.post("/key-results", summary="Añadir Key Result", status_code=201)
def create_kr(payload: KeyResultIn, db: Session = Depends(get_db),
              cu: User = Depends(require_any_manager)):
    obj = db.query(Objective).filter(Objective.id == payload.objective_id).first()
    if not obj: raise HTTPException(404, "Objetivo no encontrado")
    kr = KeyResult(id=str(_uuid.uuid4()), **payload.model_dump())
    db.add(kr); db.commit(); db.refresh(kr)
    return _ser_kr(kr)


@router.patch("/key-results/{kr_id}", summary="Actualizar Key Result")
def update_kr(kr_id: str, payload: KeyResultUpdate,
              db: Session = Depends(get_db), cu: User = Depends(require_any_manager)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr: raise HTTPException(404, "KR no encontrado")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(kr, k, v)
    kr.progress = _calc_progress(kr)
    _propagate_to_objective(db, kr)
    db.commit(); db.refresh(kr)
    return _ser_kr(kr)


@router.delete("/key-results/{kr_id}", summary="Eliminar Key Result")
def delete_kr(kr_id: str, db: Session = Depends(get_db),
              cu: User = Depends(require_any_manager)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr: raise HTTPException(404, "KR no encontrado")
    db.delete(kr); db.commit()
    return {"deleted": True}


# ── Check-ins ─────────────────────────────────────────────────────────────────
@router.post("/key-results/{kr_id}/checkin", summary="Registrar progreso", status_code=201)
def checkin_kr(kr_id: str, payload: CheckinIn,
               db: Session = Depends(get_db), cu: User = Depends(get_current_user)):
    kr = db.query(KeyResult).filter(KeyResult.id == kr_id).first()
    if not kr: raise HTTPException(404, "KR no encontrado")
    c = KRCheckin(id=str(_uuid.uuid4()), kr_id=kr_id,
                  value=payload.value, note=payload.note, author_id=cu.id)
    db.add(c)
    kr.current_value = payload.value
    kr.progress = _calc_progress(kr)
    _propagate_to_objective(db, kr)
    db.commit()
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
