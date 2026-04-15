"""
RACI service — business logic extracted from raci.py endpoint.
Covers: serialisers for User / RACIEntry / ChangelogEntry / UATCase,
        sprint retrospective insights computation, and burnout risk computation.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.task import Task, TaskStatus
from app.models.sprints import Sprint, SprintTask
from app.models.imputation import Imputation
from app.models.raci import (
    RACIEntry,
    BurnoutRiskLevel,
    ProjectChangelogEntry,
    UATCase,
)

if TYPE_CHECKING:
    pass   # avoid circular imports at runtime


# ── Serialisers ───────────────────────────────────────────────────────────────

def serialize_user(u: User) -> dict:
    return {
        "id": u.id,
        "full_name": u.full_name,
        "role": u.role,
        "department": u.department,
        "job_title": getattr(u, "job_title", None),
        "avatar_initials": u.full_name[:2].upper(),
    }


def serialize_raci_entry(e: RACIEntry) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "item_type": e.item_type,
        "item_label": e.item_label,
        "item_id": e.item_id,
        "user_id": e.user_id,
        "role": e.role.value,
        "user": serialize_user(e.user) if e.user else None,
    }


def serialize_changelog_entry(e: ProjectChangelogEntry) -> dict:
    return {
        "id": e.id,
        "project_id": e.project_id,
        "version_tag": e.version_tag,
        "entry_date": e.entry_date.isoformat() if e.entry_date else None,
        "entry_type": e.entry_type.value,
        "title": e.title,
        "description": e.description,
        "is_auto_generated": e.is_auto_generated,
        "author": serialize_user(e.author) if e.author else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


def serialize_uat_case(c: UATCase) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "task_id": c.task_id,
        "title": c.title,
        "description": c.description,
        "expected_result": c.expected_result,
        "actual_result": c.actual_result,
        "status": c.status.value if c.status else "pending",
        "priority": c.priority,
        "assigned_to_id": c.assigned_to_id,
        "assigned_to": serialize_user(c.assigned_to) if c.assigned_to else None,
        "task_title": c.task.title if c.task else None,
        "notes": c.notes,
        "executed_at": c.executed_at.isoformat() if c.executed_at else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


# ── Sprint retrospective ──────────────────────────────────────────────────────

def compute_retro_insights(sprint: Sprint, db: Session) -> dict:
    """
    Algorithmic retrospective insights from sprint data.
    No LLM required — derives meaningful conclusions from metrics.
    """
    sprint_tasks = (
        db.query(Task)
        .join(SprintTask, SprintTask.task_id == Task.id)
        .filter(SprintTask.sprint_id == sprint.id)
        .all()
    )

    total       = len(sprint_tasks)
    completed   = [t for t in sprint_tasks if t.status == TaskStatus.done]
    blocked     = [t for t in sprint_tasks if t.status == TaskStatus.blocked]
    in_progress = [t for t in sprint_tasks if t.status == TaskStatus.in_progress]

    planned_hours   = sum(t.estimated_hours or 0 for t in sprint_tasks)
    completed_hours = sum(t.actual_hours or t.estimated_hours or 0 for t in completed)
    completion_rate = round(len(completed) / total * 100, 1) if total > 0 else 0
    velocity_ratio  = round(completed_hours / planned_hours * 100, 1) if planned_hours > 0 else 0

    # Count tasks added after sprint start (scope creep indicator)
    added_mid = 0
    if sprint.start_date:
        start_dt = datetime.combine(sprint.start_date, datetime.min.time())
        added_mid = sum(
            1 for st in db.query(SprintTask).filter(SprintTask.sprint_id == sprint.id).all()
            if st.added_at and st.added_at > start_dt
        ) if hasattr(SprintTask, "added_at") else 0

    carryover = len(in_progress) + len([
        t for t in sprint_tasks
        if t.status not in (TaskStatus.done, TaskStatus.cancelled)
    ])

    went_well = []
    improve   = []
    actions   = []
    risks     = []

    if completion_rate >= 85:
        went_well.append(f"Alta tasa de completitud: {completion_rate}% de tareas entregadas")
    if completion_rate >= 95:
        went_well.append("Excelente predictibilidad — casi sin carryover")
    if not blocked:
        went_well.append("Ninguna tarea bloqueada durante el sprint")
    if velocity_ratio >= 90:
        went_well.append(f"Velocity muy ajustada a la planificación ({velocity_ratio}%)")

    if completion_rate < 70:
        improve.append(f"Tasa de completitud baja ({completion_rate}%) — revisar estimaciones o scope")
        actions.append({"text": "Revisar criterios de aceptación antes del siguiente sprint planning", "owner_id": None})
    if blocked:
        improve.append(f"{len(blocked)} tarea(s) bloqueadas — identificar patrones de impedimentos")
        actions.append({"text": "Daily standup: escalar bloqueos en máximo 24h", "owner_id": None})
    if added_mid > 2:
        improve.append(f"Scope creep detectado: {added_mid} tareas añadidas a mitad de sprint")
        actions.append({"text": "Reforzar la política de no añadir al sprint en curso salvo urgencias", "owner_id": None})
    if carryover > 0:
        improve.append(f"{carryover} tarea(s) con carryover — afecta a la previsibilidad")
    if velocity_ratio < 70:
        improve.append(f"Velocity {velocity_ratio}% — sobreestimación habitual, calibrar story points")
        risks.append("Estimaciones sistemáticamente optimistas → riesgo de promesas no cumplidas")

    if completion_rate >= 80 and not blocked:
        actions.append({"text": "Continuar con el ritmo actual; documentar las prácticas que funcionan", "owner_id": None})

    if not went_well:
        went_well.append("Sprint completado — analiza métricas para detectar áreas de mejora")
    if not improve:
        improve.append("No se detectaron problemas estructurales significativos")

    return {
        "metrics": {
            "total_tasks": total,
            "completed": len(completed),
            "blocked": len(blocked),
            "carryover": carryover,
            "added_mid_sprint": added_mid,
            "completion_rate_pct": completion_rate,
            "planned_hours": planned_hours,
            "completed_hours": completed_hours,
            "velocity_ratio_pct": velocity_ratio,
        },
        "went_well": went_well,
        "improve": improve,
        "actions": actions,
        "risks": risks,
    }


# ── Burnout risk ──────────────────────────────────────────────────────────────

def compute_user_burnout_risk(user: User, db: Session, today: date) -> dict:
    """
    Compute burnout risk for a user based on workload patterns.
    Uses last 8 weeks of imputation data.
    """
    weeks_data = []
    for w in range(8):
        week_end   = today - timedelta(days=today.weekday()) - timedelta(weeks=w - 1)
        week_start = week_end - timedelta(days=7)
        hours = db.query(func.sum(Imputation.hours)).filter(
            Imputation.user_id == user.id,
            Imputation.date >= week_start,
            Imputation.date < week_end,
        ).scalar() or 0.0
        capacity = user.weekly_capacity_hours or 40.0
        weeks_data.append({
            "week_start": week_start,
            "hours": hours,
            "capacity": capacity,
            "load_pct": round(hours / capacity * 100, 1),
        })

    current_load = weeks_data[0]["load_pct"] if weeks_data else 0
    avg_load_4w  = (
        sum(w["load_pct"] for w in weeks_data[:4]) / 4
        if len(weeks_data) >= 4 else current_load
    )

    streak = 0
    for w in weeks_data:
        if w["load_pct"] > 100:
            streak += 1
        else:
            break

    score = 0.0
    factors = []

    if current_load > 100:
        score += 25
        factors.append(f"Sobrecarga actual: {current_load:.0f}%")
    if avg_load_4w > 90:
        score += 20
        factors.append(f"Media 4 semanas: {avg_load_4w:.0f}%")
    if streak >= 2:
        score += streak * 10
        factors.append(f"{streak} semanas consecutivas al 100%+")
    if streak >= 4:
        factors.append("Riesgo alto de agotamiento sostenido")
    if current_load > 130:
        score += 20
        factors.append("Sobrecarga severa (>130%)")

    score = min(score, 100)

    if score >= 70:
        level = BurnoutRiskLevel.red
    elif score >= 45:
        level = BurnoutRiskLevel.orange
    elif score >= 20:
        level = BurnoutRiskLevel.yellow
    else:
        level = BurnoutRiskLevel.green

    return {
        "user_id": user.id,
        "full_name": user.full_name,
        "department": user.department,
        "job_title": getattr(user, "job_title", None),
        "current_load_pct": current_load,
        "avg_load_4w": round(avg_load_4w, 1),
        "overload_weeks_streak": streak,
        "risk_score": round(score, 1),
        "risk_level": level.value,
        "factors": factors,
        "weekly_history": [
            {
                "week_start": w["week_start"].isoformat(),
                "load_pct": w["load_pct"],
                "hours": round(w["hours"], 1),
            }
            for w in weeks_data
        ],
    }
