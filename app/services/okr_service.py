"""OKR service — business logic for Objectives & Key Results."""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy.orm import Session, joinedload

from app.models.okrs import Objective, KeyResult, KRCheckin
from app.models.task import Task, TaskStatus


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

    Weights: done=1.0 | review=0.8 | in_progress=0.5 | others=0.0
    """
    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    if not tasks:
        return 0.0
    weighted = sum(
        1.0 if t.status == TaskStatus.done else
        0.8 if t.status == TaskStatus.review else
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
        from fastapi import HTTPException
        raise HTTPException(404, "KR no encontrado")

    obj = kr.objective
    if not obj or not obj.project_id:
        from fastapi import HTTPException
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
