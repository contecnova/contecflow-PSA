"""
Sprints endpoint — full Scrum/Agile sprint management.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import date, timedelta
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.models.task import Task
from app.models.sprints import Sprint, SprintTask, SprintStatus
from app.services.psa_flows import close_sprint_flow
import app.services.sprint_service as svc

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class SprintCreate(BaseModel):
    name: str
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None

class SprintUpdate(BaseModel):
    name: Optional[str] = None
    goal: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[str] = None
    went_well: Optional[str] = None
    to_improve: Optional[str] = None
    action_items: Optional[str] = None

class AddTasksToSprint(BaseModel):
    task_ids: List[str]

class ReorderBacklog(BaseModel):
    task_ids: List[str]  # ordered list of task IDs


# ── Helpers ───────────────────────────────────────────────────────────────────

def _task_out(t: Task) -> dict:
    return {
        "id": t.id, "code": t.code, "title": t.title,
        "status": t.status, "priority": t.priority,
        "story_points": t.story_points,
        "estimated_hours": t.estimated_hours,
        "assignee_id": t.assignee_id,
        "assignee_name": t.assignee.full_name if t.assignee else None,
        "due_date": str(t.due_date) if t.due_date else None,
        "tags": t.tags,
        "blocked_reason": t.blocked_reason,
    }


def _sprint_out(s: Sprint, include_tasks: bool = False) -> dict:
    duration_days = (s.end_date - s.start_date).days if s.start_date and s.end_date else 0
    today = date.today()
    days_remaining = (s.end_date - today).days if s.end_date and s.status == SprintStatus.active else None

    result = {
        "id": s.id, "number": s.number, "name": s.name,
        "goal": s.goal, "status": s.status,
        "start_date": str(s.start_date) if s.start_date else None,
        "end_date": str(s.end_date) if s.end_date else None,
        "duration_days": duration_days,
        "days_remaining": days_remaining,
        "planned_points": s.planned_points or 0,
        "completed_points": s.completed_points or 0,
        "velocity": s.velocity,
        "went_well": s.went_well,
        "to_improve": s.to_improve,
        "action_items": s.action_items,
        "created_at": str(s.created_at)[:10] if s.created_at else None,
        "task_count": len(s.sprint_tasks),
    }

    if include_tasks:
        result["tasks"] = [_task_out(st.task) for st in s.sprint_tasks if st.task]

    return result


def _compute_burndown(sprint: Sprint, db: Session):
    """Calculate daily burndown data for a sprint."""
    if not sprint.start_date or not sprint.end_date:
        return []

    tasks = [st.task for st in sprint.sprint_tasks if st.task]
    total_points = sum(t.story_points or 0 for t in tasks)

    today = date.today()
    end = min(sprint.end_date, today)
    start = sprint.start_date

    burndown = []
    current = start
    while current <= end:
        # Points remaining = total - points from completed tasks by this date
        completed = sum(
            t.story_points or 0 for t in tasks
            if t.status == "done" and t.completed_at and t.completed_at.date() <= current
        )
        ideal_pct = 1 - ((current - start).days / max((sprint.end_date - start).days, 1))
        burndown.append({
            "date": str(current)[5:],  # MM-DD
            "remaining": max(total_points - completed, 0),
            "ideal": round(total_points * ideal_pct, 1),
        })
        current += timedelta(days=1)

    return burndown


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", summary="Listar sprints de todos los proyectos (global)")
def list_all_sprints(
    status:   Optional[str] = None,
    limit:    int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Lista sprints cross-proyecto. Útil para el calendario global.
    """
    sprints = svc.list_all_sprints(
        db,
        organization_id=current_user.organization_id,
        is_superadmin=current_user.is_superadmin,
        status=status,
        limit=limit,
    )
    return [
        {
            "id":           s.id,
            "name":         s.name,
            "status":       s.status,
            "start_date":   str(s.start_date) if s.start_date else None,
            "end_date":     str(s.end_date)   if s.end_date   else None,
            "goal":         s.goal,
            "project_id":   s.project_id,
            "project_name": s.project.name if s.project else None,
            "project_code": s.project.code if s.project else None,
        }
        for s in sprints
    ]


@router.get("/{project_id}/sprints", summary="Listar sprints de un proyecto")
def list_sprints(
    project_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprints = svc.list_sprints_for_project(db, project_id, status)
    return [_sprint_out(s, include_tasks=True) for s in sprints]


@router.post("/{project_id}/sprints", summary="Crear sprint")
def create_sprint(
    project_id: str,
    payload: SprintCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Auto-number
    number = svc.get_next_sprint_number(db, project_id)
    sprint = Sprint(
        project_id=project_id,
        number=number,
        name=payload.name,
        goal=payload.goal,
        start_date=payload.start_date,
        end_date=payload.end_date,
        created_by=current_user.id,
    )
    svc.create_sprint(db, sprint)
    db.refresh(sprint)
    return _sprint_out(sprint)


@router.patch("/{project_id}/sprints/{sprint_id}", summary="Actualizar sprint")
def update_sprint(
    project_id: str,
    sprint_id: str,
    payload: SprintUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sprint = svc.get_sprint_simple(db, sprint_id, project_id)
    if not sprint: raise HTTPException(404, "Sprint no encontrado")

    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(sprint, k, v)

    svc.commit_db(db)
    db.refresh(sprint)

    # Reload with tasks
    sprint = svc.get_sprint_with_tasks_by_id(db, sprint_id)
    return _sprint_out(sprint, include_tasks=True)


@router.post("/{project_id}/sprints/{sprint_id}/start", summary="Iniciar sprint")
def start_sprint(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sprint = svc.get_sprint_with_tasks(db, sprint_id, project_id)
    if not sprint: raise HTTPException(404, "Sprint no encontrado")

    # Only one active sprint per project
    active = svc.get_active_sprint_for_project(db, project_id)
    if active and active.id != sprint_id:
        raise HTTPException(400, f"Ya hay un sprint activo: {active.name}")

    sprint.status = SprintStatus.active
    if not sprint.start_date:
        sprint.start_date = date.today()

    # Calculate planned points
    sprint.planned_points = sum(st.task.story_points or 0 for st in sprint.sprint_tasks if st.task)

    svc.commit_db(db)
    return {"ok": True, "sprint": _sprint_out(sprint)}


@router.post("/{project_id}/sprints/{sprint_id}/close", summary="Cerrar sprint")
def close_sprint(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return close_sprint_flow(db, project_id, sprint_id)


@router.post("/{project_id}/sprints/{sprint_id}/tasks", summary="Añadir tareas al sprint")
def add_tasks_to_sprint(
    project_id: str,
    sprint_id: str,
    payload: AddTasksToSprint,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    sprint = svc.get_sprint_simple(db, sprint_id, project_id)
    if not sprint: raise HTTPException(404, "Sprint no encontrado")

    added = svc.add_tasks_to_sprint(db, sprint_id, project_id, payload.task_ids)
    return {"ok": True, "added": added}


@router.delete("/{project_id}/sprints/{sprint_id}/tasks/{task_id}", summary="Quitar tarea del sprint")
def remove_task_from_sprint(
    project_id: str,
    sprint_id: str,
    task_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    st = svc.get_sprint_task(db, sprint_id, task_id)
    if not st: raise HTTPException(404)
    svc.delete_sprint_task(db, st)
    return {"ok": True}


@router.put("/{project_id}/sprints/{sprint_id}/reorder", summary="Reordenar backlog del sprint")
def reorder_sprint_backlog(
    project_id: str,
    sprint_id: str,
    payload: ReorderBacklog,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc.reorder_sprint_backlog(db, sprint_id, payload.task_ids)
    return {"ok": True}


@router.get("/{project_id}/sprints/{sprint_id}/burndown", summary="Datos de burndown chart")
def get_burndown(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprint = svc.get_sprint_for_charts(db, sprint_id, project_id)
    if not sprint: raise HTTPException(404)
    return {"burndown": _compute_burndown(sprint, db)}


@router.get("/{project_id}/sprints/{sprint_id}/burnup", summary="Datos de burnup chart (scope + completed)")
def get_burnup(
    project_id: str,
    sprint_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Returns daily burnup data:
      - scope: total story points in the sprint by that date (shows scope creep)
      - completed: cumulative story points marked done by that date
    """
    sprint = svc.get_sprint_for_charts(db, sprint_id, project_id)
    if not sprint:
        raise HTTPException(404)

    if not sprint.start_date or not sprint.end_date:
        return {"burnup": [], "sprint": _sprint_out(sprint)}

    tasks = [st.task for st in sprint.sprint_tasks if st.task]
    total_scope = sum(t.story_points or 0 for t in tasks)

    today  = date.today()
    end    = min(sprint.end_date, today)
    start  = sprint.start_date

    burnup = []
    current = start
    while current <= end:
        # Completed points by this date
        done_pts = sum(
            t.story_points or 0 for t in tasks
            if t.status == "done"
            and t.completed_at
            and t.completed_at.date() <= current
        )
        # Scope on this date: base scope (no history), treat as constant
        burnup.append({
            "date":      str(current)[5:],  # MM-DD
            "scope":     total_scope,
            "completed": done_pts,
        })
        current += timedelta(days=1)

    return {
        "burnup":   burnup,
        "sprint":   _sprint_out(sprint),
        "target":   total_scope,
    }


@router.get("/{project_id}/backlog", summary="Backlog del proyecto (tareas sin sprint)")
def get_project_backlog(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks = svc.get_project_backlog_tasks(db, project_id)
    return [_task_out(t) for t in tasks]


@router.get("/{project_id}/velocity", summary="Histórico de velocidad por sprint")
def get_velocity_history(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    sprints = svc.get_velocity_sprints(db, project_id)

    data = [{
        "sprint": f"Sprint {s.number}",
        "name": s.name,
        "planned": s.planned_points or 0,
        "completed": s.completed_points or 0,
        "velocity": s.velocity or 0,
    } for s in sprints]

    avg_velocity = sum(d["velocity"] for d in data) / len(data) if data else 0
    return {"sprints": data, "avg_velocity": round(avg_velocity, 1)}
