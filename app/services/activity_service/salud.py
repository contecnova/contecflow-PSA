"""Salud de proyecto: calculo, instantaneas y vista de cartera.

Parte de `app.services.activity_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from sqlalchemy import func
from sqlalchemy.orm import Session
from app.models.activity import ProjectHealthSnapshot
from app.models.imputation import Imputation
from app.models.mfa import Budget
from app.models.nps import ClientHealthSnapshot
from app.models.project import Project, ProjectStatus
from app.models.task import Task, TaskStatus
from app.core import timeutil
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT HEALTH
# ═══════════════════════════════════════════════════════════════════════════════

_PROJECT_HEALTH_KEYS = {
    "PROJECT_HEALTH_WEIGHT_SCHEDULE": "float",
    "PROJECT_HEALTH_WEIGHT_BUDGET": "float",
    "PROJECT_HEALTH_WEIGHT_QUALITY": "float",
    "PROJECT_HEALTH_WEIGHT_VELOCITY": "float",
    "PROJECT_HEALTH_WEIGHT_CLIENT": "float",
    "PROJECT_HEALTH_TRAFFIC_GREEN": "float",
    "PROJECT_HEALTH_TRAFFIC_YELLOW": "float",
    "PROJECT_HEALTH_BUDGET_RATIO_GOOD": "float",
    "PROJECT_HEALTH_BUDGET_RATIO_OK": "float",
    "PROJECT_HEALTH_BUDGET_RATIO_WARN": "float",
}


def compute_health(db: Session, project_id: str) -> dict:
    """Compute composite health score (0-100) from live signals."""
    from app.services.settings_service import get_runtime_namespace

    today = timeutil.today()
    _project_for_org = db.query(Project).filter(Project.id == project_id).first()
    _org_id = getattr(_project_for_org, "organization_id", None) if _project_for_org else None
    _s = get_runtime_namespace(db, _PROJECT_HEALTH_KEYS, org_id=_org_id)

    total_tasks = db.query(func.count(Task.id)).filter(Task.project_id == project_id).scalar() or 0
    overdue = db.query(func.count(Task.id)).filter(
        Task.project_id == project_id,
        Task.due_date < today,
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).scalar() or 0
    schedule_score = round(max(0, 100 - (overdue / max(total_tasks, 1)) * 100), 1)

    budget_score = 80.0
    # Revisión 2026-11: el total de un presupuesto es la suma de sus partidas (ya
    # no `total_amount`), y las horas previstas del proyecto son `budget_hours`
    # (`estimated_hours` no existe en el modelo: esta puntuación nunca se calculaba).
    budget = db.query(Budget).filter(Budget.project_id == project_id).first()
    if budget and sum(l.importe for l in budget.lines):
        actual_cost_q = db.query(func.sum(Imputation.hours)).filter(
            Imputation.project_id == project_id
        ).scalar() or 0
        project = db.query(Project).filter(Project.id == project_id).first()
        estimated_hours = project.budget_hours if project else None
        if estimated_hours and estimated_hours > 0:
            ratio = actual_cost_q / estimated_hours
            if ratio <= _s.PROJECT_HEALTH_BUDGET_RATIO_GOOD:
                budget_score = 100.0
            elif ratio <= _s.PROJECT_HEALTH_BUDGET_RATIO_OK:
                budget_score = 80.0
            elif ratio <= _s.PROJECT_HEALTH_BUDGET_RATIO_WARN:
                budget_score = 50.0
            else:
                budget_score = 20.0

    open_risks = db.query(func.count(Task.id)).filter(
        Task.project_id == project_id,
        Task.issue_type == "bug",
        Task.status.not_in([TaskStatus.done, TaskStatus.cancelled]),
    ).scalar() or 0
    quality_score = round(max(0, 100 - min(open_risks * 10, 100)), 1)

    velocity_score = 70.0

    project_obj = db.query(Project).filter(Project.id == project_id).first()
    client_score = 75.0
    if project_obj and project_obj.client_id:
        latest_nps = db.query(ClientHealthSnapshot).filter(
            ClientHealthSnapshot.client_id == project_obj.client_id
        ).order_by(ClientHealthSnapshot.snapshot_at.desc()).first()
        if latest_nps:
            client_score = min(100.0, latest_nps.health_score)

    composite = round(
        schedule_score * _s.PROJECT_HEALTH_WEIGHT_SCHEDULE +
        budget_score   * _s.PROJECT_HEALTH_WEIGHT_BUDGET +
        quality_score  * _s.PROJECT_HEALTH_WEIGHT_QUALITY +
        velocity_score * _s.PROJECT_HEALTH_WEIGHT_VELOCITY +
        client_score   * _s.PROJECT_HEALTH_WEIGHT_CLIENT,
        1
    )

    return {
        "score": composite,
        "schedule_score": schedule_score,
        "budget_score": budget_score,
        "quality_score": quality_score,
        "velocity_score": velocity_score,
        "client_score": client_score,
        "traffic_light": "green" if composite >= _s.PROJECT_HEALTH_TRAFFIC_GREEN else ("yellow" if composite >= _s.PROJECT_HEALTH_TRAFFIC_YELLOW else "red"),
        "overdue_tasks": overdue,
        "total_tasks": total_tasks,
        "open_bugs": open_risks,
    }


def project_health_payload(db: Session, project_id: str) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorDeDominio(404)
    data = compute_health(db, project_id)
    history = db.query(ProjectHealthSnapshot).filter(
        ProjectHealthSnapshot.project_id == project_id
    ).order_by(ProjectHealthSnapshot.snapshot_at.desc()).limit(30).all()
    return {
        "project_id": project_id,
        "project_name": project.name,
        "current": data,
        "history": [{
            "score": h.score,
            "traffic_light": "green" if h.score >= 70 else ("yellow" if h.score >= 45 else "red"),
            "snapshot_at": h.snapshot_at.isoformat() if h.snapshot_at else None,
        } for h in history],
    }


def save_health_snapshot_record(db: Session, project_id: str) -> dict:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise ErrorDeDominio(404)
    data = compute_health(db, project_id)
    snap = ProjectHealthSnapshot(
        project_id=project_id,
        score=data["score"],
        schedule_score=data["schedule_score"],
        budget_score=data["budget_score"],
        quality_score=data["quality_score"],
        velocity_score=data["velocity_score"],
        client_score=data["client_score"],
        detail=json.dumps({k: v for k, v in data.items() if k not in ("score",)}),
    )
    db.add(snap)
    db.commit()
    return {"id": snap.id, **data}


def portfolio_health_payload(db: Session) -> list:
    projects = db.query(Project).filter(
        Project.status.in_([ProjectStatus.active, ProjectStatus.planning])
    ).all()
    result = []
    for p in projects:
        data = compute_health(db, p.id)
        result.append({
            "project_id": p.id,
            "project_code": p.code,
            "project_name": p.name,
            "score": data["score"],
            "traffic_light": data["traffic_light"],
            "overdue_tasks": data["overdue_tasks"],
        })
    result.sort(key=lambda x: x["score"])
    return result
