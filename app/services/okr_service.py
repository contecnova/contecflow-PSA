"""OKR service — business logic for Objectives & Key Results."""
from __future__ import annotations

import uuid as _uuid
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.okrs import Objective, KeyResult, KRCheckin
from app.models.project import Project
from app.models.task import Task, TaskStatus
from app.models.user import User
from fastapi import HTTPException


def calc_progress(kr: KeyResult) -> float:
    """Compute 0–100 progress for a Key Result."""
    if kr.kr_type == "boolean":
        return 100.0 if kr.current_value and kr.current_value >= 1 else 0.0
    if not kr.target_value or kr.target_value == 0:
        return 0.0
    return round(min(100, max(0, (kr.current_value or 0) / kr.target_value * 100)), 1)


def serialize_kr(kr: KeyResult) -> dict:
    return {
        "id": kr.id,
        "objective_id": kr.objective_id,
        "title": kr.title,
        "kr_type": kr.kr_type,
        "target_value": kr.target_value,
        "current_value": kr.current_value,
        "unit": kr.unit,
        "progress": calc_progress(kr),
        "owner_id": kr.owner_id,
        "owner_name": kr.owner.full_name if kr.owner else None,
        "due_date": str(kr.due_date) if kr.due_date else None,
        "notes": kr.notes,
    }


def serialize_objective(obj: Objective) -> dict:
    krs = obj.key_results or []
    avg_progress = round(sum(calc_progress(kr) for kr in krs) / len(krs), 1) if krs else 0
    return {
        "id": obj.id,
        "title": obj.title,
        "description": obj.description,
        "owner_id": obj.owner_id,
        "owner_name": obj.owner.full_name if obj.owner else None,
        "team_id": obj.team_id,
        "project_id": obj.project_id,
        "period": obj.period,
        "year": obj.year,
        "status": obj.status,
        "progress": avg_progress,
        "key_results": [serialize_kr(kr) for kr in krs],
        "created_at": str(obj.created_at)[:10] if obj.created_at else None,
    }


def task_progress_for_project(db: Session, project_id: str) -> float:
    """Compute 0–100 progress for *project_id* based on weighted task completion.

    Weights: done=1.0 | in_review=0.8 | in_progress=0.5 | others=0.0
    """
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    if not tasks:
        return 0.0
    weighted = sum(
        1.0 if t.status == TaskStatus.done else
        0.8 if t.status == TaskStatus.in_review else
        0.5 if t.status == TaskStatus.in_progress else
        0.0
        for t in tasks
    )
    return round(min(100.0, (weighted / len(tasks)) * 100), 1)


def propagate_to_objective(db: Session, kr: KeyResult) -> None:
    """Recalculate parent Objective progress after a KR update."""
    obj = (
        db.query(Objective)
        .options(joinedload(Objective.key_results))
        .filter(Objective.id == kr.objective_id)
        .first()
    )
    if obj and obj.key_results:
        obj.progress = round(
            sum(calc_progress(k) for k in obj.key_results) / len(obj.key_results), 1
        )


def sync_kr_from_tasks(
    kr_id: str,
    author_id: str,
    db: Session,
) -> dict:
    """Update a KR's current_value from the task-completion percentage of the
    linked project and record a check-in.  Returns the result dict."""
    kr = (
        db.query(KeyResult)
        .options(joinedload(KeyResult.objective))
        .filter(KeyResult.id == kr_id)
        .first()
    )
    if not kr:
        raise HTTPException(404, "KR no encontrado")

    obj = kr.objective
    if not obj or not obj.project_id:
        raise HTTPException(
            400,
            "El Objetivo vinculado al KR no tiene proyecto asociado. "
            "Establece project_id en el Objetivo antes de sincronizar.",
        )

    progress_pct = task_progress_for_project(db, obj.project_id)

    if kr.kr_type in ("percentage",):
        new_value = progress_pct
    elif kr.target_value and kr.target_value > 0:
        new_value = round((progress_pct / 100) * kr.target_value, 2)
    else:
        new_value = progress_pct

    kr.current_value = new_value
    kr.progress = calc_progress(kr)

    checkin = KRCheckin(
        id=str(_uuid.uuid4()),
        kr_id=kr.id,
        value=new_value,
        note=f"Auto-sync desde tareas del proyecto {obj.project_id} ({progress_pct}% completado)",
        author_id=author_id,
    )
    db.add(checkin)
    propagate_to_objective(db, kr)
    db.commit()

    return {
        "kr_id": kr.id,
        "new_value": new_value,
        "progress": kr.progress,
        "project_progress_pct": progress_pct,
        "synced_from_project": obj.project_id,
    }


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def list_objectives(
    db: Session,
    year: int,
    period: Optional[str] = None,
    status: Optional[str] = None,
    owner_id: Optional[str] = None,
    is_superadmin: bool = False,
    organization_id: Optional[str] = None,
) -> list:
    q = db.query(Objective).options(
        joinedload(Objective.key_results).joinedload(KeyResult.owner),
        joinedload(Objective.owner),
    ).filter(
        Objective.year == year,
        Objective.is_active == True  # Soft-delete filter
    )
    if not is_superadmin and organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                Objective.owner_id.in_(org_user_ids),
                Objective.project_id.in_(org_project_ids),
            )
        )
    if period:
        q = q.filter(Objective.period == period)
    if status:
        q = q.filter(Objective.status == status)
    if owner_id:
        q = q.filter(Objective.owner_id == owner_id)
    return q.order_by(Objective.created_at.desc()).all()


def create_objective(db: Session, data: dict) -> Objective:
    obj = Objective(id=str(_uuid.uuid4()), **data)
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def get_objective(db: Session, obj_id: str) -> Optional[Objective]:
    return db.query(Objective).filter(
        Objective.id == obj_id,
        Objective.is_active == True,
    ).first()


def update_objective(db: Session, obj: Objective, data: dict) -> Objective:
    for k, v in data.items():
        setattr(obj, k, v)
    db.commit()
    db.refresh(obj)
    return obj


def delete_objective(db: Session, obj: Objective) -> dict:
    """Soft-delete an objective (soft delete). Cascades to soft-delete active KRs."""
    # Soft-delete all active key results (cascade)
    active_krs = db.query(KeyResult).filter(
        KeyResult.objective_id == obj.id,
        KeyResult.is_active == True
    ).all()

    for kr in active_krs:
        kr.is_active = False

    # Perform soft delete of objective
    obj.is_active = False
    db.commit()

    return {
        "ok": True,
        "message": f"Objetivo eliminado junto con {len(active_krs)} Key Result(s) (soft delete)",
        "kr_count": len(active_krs)
    }


def get_key_result(db: Session, kr_id: str) -> Optional[KeyResult]:
    return db.query(KeyResult).filter(
        KeyResult.id == kr_id,
        KeyResult.is_active == True,
    ).first()


def create_kr(db: Session, data: dict) -> KeyResult:
    kr = KeyResult(id=str(_uuid.uuid4()), **data)
    db.add(kr)
    db.commit()
    db.refresh(kr)
    return kr


def update_kr(db: Session, kr: KeyResult, data: dict) -> KeyResult:
    for k, v in data.items():
        setattr(kr, k, v)
    kr.progress = calc_progress(kr)
    propagate_to_objective(db, kr)
    db.commit()
    db.refresh(kr)
    return kr


def delete_kr(db: Session, kr: KeyResult) -> dict:
    """Soft-delete a key result (soft delete)."""
    kr.is_active = False
    db.commit()
    return {
        "ok": True,
        "message": "Key Result eliminado (soft delete)"
    }


def checkin_kr(
    db: Session,
    kr: KeyResult,
    value: float,
    note: Optional[str],
    author_id: str,
) -> KeyResult:
    c = KRCheckin(
        id=str(_uuid.uuid4()),
        kr_id=kr.id,
        value=value,
        note=note,
        author_id=author_id,
    )
    db.add(c)
    kr.current_value = value
    kr.progress = calc_progress(kr)
    propagate_to_objective(db, kr)
    db.commit()
    return kr
