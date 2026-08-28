from __future__ import annotations

import json
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, get_db, require_any_manager
from app.core.responses import APIResponse, APIListResponse
from app.models.user import User
from app.core.abac_enforce import enforce_abac
from app.core import timeutil

router = APIRouter()


class BaselineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_initial: bool = False


@router.get("/projects/{project_id}/baselines", summary="List Gantt baselines for project")
def list_baselines(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.marketplace import GanttBaseline
    from app.models.project import Project

    if not db.query(Project).filter(Project.id == project_id).first():
        raise HTTPException(404, "Project not found")
    baselines = (
        db.query(GanttBaseline)
        .filter(GanttBaseline.project_id == project_id)
        .order_by(GanttBaseline.baseline_date.desc())
        .all()
    )
    return APIListResponse.ok(items=[
        {
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "baseline_date": str(b.baseline_date),
            "is_initial": b.is_initial,
            "total_tasks": b.total_tasks,
            "completed_tasks": b.completed_tasks,
            "total_hours": b.total_hours,
            "budget_at_freeze": b.budget_at_freeze,
            "created_at": str(b.created_at),
        }
        for b in baselines
    ])


@router.post("/projects/{project_id}/baselines", summary="Freeze current Gantt as baseline", status_code=201)
def create_baseline(
    project_id: str,
    payload: BaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.marketplace import GanttBaseline
    from app.models.project import Project
    from app.models.task import Task

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    snapshot = {
        "frozen_at": str(timeutil.today()),
        "tasks": [
            {
                "task_id": t.id,
                "title": t.title,
                "start": str(t.start_date) if hasattr(t, "start_date") and t.start_date else None,
                "end": str(t.due_date) if t.due_date else None,
                "progress": t.progress if hasattr(t, "progress") else 0,
                "status": str(t.status.value) if hasattr(t.status, "value") else str(t.status),
                "estimated_hours": t.estimated_hours if hasattr(t, "estimated_hours") else None,
                "assignee_id": t.assignee_id if hasattr(t, "assignee_id") else None,
            }
            for t in tasks
        ],
    }
    total_h = sum(
        (t.estimated_hours or 0)
        for t in tasks
        if hasattr(t, "estimated_hours") and t.estimated_hours
    )
    done = sum(
        1
        for t in tasks
        if str(getattr(t.status, "value", t.status)) in ("done", "closed", "completed")
    )

    baseline = GanttBaseline(
        project_id=project_id,
        name=payload.name,
        description=payload.description,
        baseline_date=timeutil.today(),
        schedule_snapshot=json.dumps(snapshot),
        total_tasks=len(tasks),
        completed_tasks=done,
        total_hours=total_h,
        budget_at_freeze=proj.budget if hasattr(proj, "budget") else None,
        is_initial=payload.is_initial,
        created_by=current_user.id,
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return APIResponse.ok(data={
        "id": baseline.id,
        "name": baseline.name,
        "baseline_date": str(baseline.baseline_date),
        "total_tasks": baseline.total_tasks,
        "total_hours": baseline.total_hours,
        "created": True,
    })


@router.get("/projects/{project_id}/baselines/{baseline_id}/compare", summary="Compare current schedule vs baseline")
def compare_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.marketplace import GanttBaseline
    from app.models.task import Task

    baseline = (
        db.query(GanttBaseline)
        .filter(GanttBaseline.id == baseline_id, GanttBaseline.project_id == project_id)
        .first()
    )
    if not baseline:
        raise HTTPException(404, "Baseline not found")

    frozen = json.loads(baseline.schedule_snapshot)
    frozen_tasks = {t["task_id"]: t for t in frozen.get("tasks", [])}

    current_tasks = db.query(Task).filter(Task.project_id == project_id).all()
    deltas = []
    for t in current_tasks:
        ft = frozen_tasks.get(t.id)
        if not ft:
            deltas.append({"task_id": t.id, "title": t.title, "delta": "new_task"})
            continue
        current_end = str(t.due_date) if t.due_date else None
        frozen_end = ft.get("end")
        slip_days: Optional[int] = None
        if current_end and frozen_end:
            try:
                slip_days = (date.fromisoformat(current_end) - date.fromisoformat(frozen_end)).days
            except ValueError:
                pass
        deltas.append(
            {
                "task_id": t.id,
                "title": t.title,
                "baseline_end": frozen_end,
                "current_end": current_end,
                "slip_days": slip_days,
                "baseline_status": ft.get("status"),
                "current_status": str(t.status.value) if hasattr(t.status, "value") else str(t.status),
                "baseline_hours": ft.get("estimated_hours"),
                "current_hours": t.estimated_hours if hasattr(t, "estimated_hours") else None,
            }
        )

    removed = [{"task_id": tid, "delta": "removed"} for tid in frozen_tasks if tid not in {t.id for t in current_tasks}]

    slipped = sum(1 for d in deltas if (d.get("slip_days") or 0) > 0)
    avg_slip = sum(d.get("slip_days") or 0 for d in deltas) / max(len(deltas), 1)

    return APIResponse.ok(data={
        "baseline_id": baseline_id,
        "baseline_name": baseline.name,
        "baseline_date": str(baseline.baseline_date),
        "summary": {
            "tasks_compared": len(deltas),
            "tasks_slipped": slipped,
            "avg_slip_days": round(avg_slip, 1),
            "tasks_removed": len(removed),
            "tasks_added": sum(1 for d in deltas if d.get("delta") == "new_task"),
        },
        "task_deltas": deltas + removed,
    })


@router.delete("/projects/{project_id}/baselines/{baseline_id}", summary="Delete baseline", status_code=204)
def delete_baseline(
    project_id: str,
    baseline_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.marketplace import GanttBaseline

    enforce_abac(db, current_user, "gantt_baseline", baseline_id, action="delete")
    b = (
        db.query(GanttBaseline)
        .filter(GanttBaseline.id == baseline_id, GanttBaseline.project_id == project_id)
        .first()
    )
    if not b:
        raise HTTPException(404, "Baseline not found")
    db.delete(b)
    db.commit()
    return None
