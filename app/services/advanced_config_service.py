"""
Advanced Config Service — business logic extracted from advanced_config.py router.
Covers: seeders, vacation balance computation, project template application.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from app.core.config import settings

DEFAULT_ALERT_CONFIGS = [
    ("overload", "Sobrecarga de recursos", "Recurso supera el % de capacidad configurado", 100, "%", True, True, False, False, "critical"),
    ("burnout_risk", "Riesgo de burnout", "Recurso con alta carga durante N semanas consecutivas", 85, "%", True, True, True, False, "warning"),
    ("budget_exceeded", "Presupuesto superado", "Proyecto supera el % de presupuesto configurado", 90, "%", True, True, False, False, "warning"),
    ("budget_critical", "Presupuesto crítico", "Proyecto supera el 100% del presupuesto", 100, "%", True, True, False, False, "critical"),
    ("deadline_risk", "Riesgo de plazo", "Proyecto con retraso en días", 0, "days", True, True, False, False, "warning"),
    ("no_imputation", "Sin imputaciones", "Recurso sin imputar durante N días laborables", 2, "days", False, False, True, True, "info"),
    ("task_blocked", "Tarea bloqueada", "Tarea bloqueada durante más de N días", 2, "days", False, True, False, False, "warning"),
    ("hours_deviation", "Desviación de horas", "Tarea supera el % de horas estimadas", 50, "%", False, True, False, False, "warning"),
]

DEFAULT_TASK_TYPES = [
    ("development", "Desarrollo", "💻", "#00d4ff", True),
    ("bug", "Bug / Incidencia", "🐛", "#ff4757", False),
    ("review", "Revisión / QA", "👁", "#ffb800", True),
    ("meeting", "Reunión", "🤝", "#7c3aed", False),
    ("documentation", "Documentación", "📄", "#7a8aaa", True),
    ("analysis", "Análisis", "🔍", "#00e5a0", True),
    ("training", "Formación", "📚", "#f97316", False),
    ("support", "Soporte", "🔧", "#06b6d4", True),
]

DEFAULT_NUMBERING = [
    ("project", "PRJ", "", "-", False, 4, False, "PRJ-0001"),
    ("task", "TSK", "", "-", False, 4, False, "TSK-0001"),
    ("contract", "CTR", "", "-", False, 4, False, "CTR-0001"),
    ("opportunity", "OPP", "", "-", False, 4, False, "OPP-0001"),
    ("change_request", "CR", "", "-", False, 3, False, "CR-001"),
    ("deliverable", "DEL", "", "-", False, 3, False, "DEL-001"),
    ("risk", "RSK", "", "-", False, 3, False, "RSK-001"),
]

DEFAULT_MODULES = [
    "dashboard", "projects", "tasks", "imputations", "timesheets", "resources",
    "capacity", "profitability", "pipeline", "contracts", "risks", "changes",
    "deliverables", "skills", "absences", "reports", "alerts", "exports", "settings",
]

DEFAULT_SYSTEM_ROLES = [
    ("admin", "Dirección / Admin", "#ff4757", True),
    ("pm", "Project Manager", "#00d4ff", True),
    ("hr", "RRHH", "#00e5a0", True),
    ("team_lead", "Team Lead", "#7c3aed", True),
    ("employee", "Empleado", "#7a8aaa", True),
]


# ── Seeders ───────────────────────────────────────────────────────────────────

def seed_alert_configs(db: Session):
    from app.models.advanced_config import AlertConfig
    if db.query(AlertConfig).count() > 0:
        return
    for at, label, desc, threshold, unit, notify_admin, notify_pm, notify_hr, notify_emp, severity in DEFAULT_ALERT_CONFIGS:
        db.add(AlertConfig(
            alert_type=at, label=label, description=desc,
            threshold_value=threshold, threshold_unit=unit,
            notify_admin=notify_admin, notify_pm=notify_pm,
            notify_hr=notify_hr, notify_employee=notify_emp,
            severity=severity,
        ))
    db.commit()


def seed_task_types(db: Session):
    from app.models.advanced_config import TaskType
    if db.query(TaskType).count() > 0:
        return
    for i, (value, name, icon, color, billable) in enumerate(DEFAULT_TASK_TYPES):
        db.add(TaskType(
            value=value, name=name, icon=icon, color=color,
            is_billable_default=billable, sort_order=i,
        ))
    db.commit()


def seed_numbering(db: Session):
    from app.models.advanced_config import NumberingSequence
    if db.query(NumberingSequence).count() > 0:
        return
    for entity, prefix, suffix, sep, year, padding, reset, example in DEFAULT_NUMBERING:
        db.add(NumberingSequence(
            entity=entity, prefix=prefix, suffix=suffix, separator=sep,
            include_year=year, padding=padding, reset_yearly=reset, example=example,
        ))
    db.commit()


def seed_system_roles(db: Session):
    from app.models.advanced_config import CustomRole
    if db.query(CustomRole).filter(CustomRole.is_system == True).count() > 0:
        return
    all_modules = {m: True for m in DEFAULT_MODULES}
    for name, description, color, is_system in DEFAULT_SYSTEM_ROLES:
        db.add(CustomRole(
            name=name, description=description, color=color,
            is_system=is_system, module_access=json.dumps(all_modules),
        ))
    db.commit()


# ── Vacation balances ─────────────────────────────────────────────────────────

def get_vacation_balances(year: Optional[int], db: Session) -> list:
    from app.models.user import User as UserModel
    from app.models.advanced_config import UserVacationBalance
    from app.models.resources import Absence, AbsenceStatus, AbsenceType

    if not year:
        year = datetime.now().year
    year_start = date(year, 1, 1)
    year_end = date(year + 1, 1, 1)

    users = db.query(UserModel).filter(UserModel.is_active == True).all()
    results = []
    for u in users:
        bal = db.query(UserVacationBalance).filter(
            UserVacationBalance.user_id == u.id,
            UserVacationBalance.year == year,
        ).first()
        taken = db.query(func.sum(Absence.working_days)).filter(
            Absence.user_id == u.id,
            Absence.type == AbsenceType.vacation,
            Absence.status == AbsenceStatus.approved,
            Absence.start_date >= year_start,
            Absence.start_date < year_end,
        ).scalar() or 0
        pending = db.query(func.sum(Absence.working_days)).filter(
            Absence.user_id == u.id,
            Absence.type == AbsenceType.vacation,
            Absence.status == AbsenceStatus.pending,
            Absence.start_date >= year_start,
            Absence.start_date < year_end,
        ).scalar() or 0
        entitled = bal.days_entitled if bal else settings.DEFAULT_VACATION_DAYS_PER_YEAR
        results.append({
            "user_id": u.id, "user_name": u.full_name, "department": u.department,
            "year": year, "days_entitled": entitled,
            "days_taken": round(taken, 1),
            "days_pending": round(pending, 1),
            "days_remaining": round(entitled - taken - pending, 1),
            "days_carried_over": bal.days_carried_over if bal else 0,
        })
    return results


def update_vacation_balance(
    user_id: str, year: int, days_entitled: float, db: Session,
) -> dict:
    from app.models.advanced_config import UserVacationBalance
    bal = db.query(UserVacationBalance).filter(
        UserVacationBalance.user_id == user_id,
        UserVacationBalance.year == year,
    ).first()
    if not bal:
        bal = UserVacationBalance(
            user_id=user_id, year=year, days_entitled=days_entitled,
        )
        db.add(bal)
    else:
        bal.days_entitled = days_entitled
    db.commit()
    return {"ok": True}


# ── Project template application ──────────────────────────────────────────────

def apply_template_to_project(
    template_id: str, project_id: str,
    start_date: Optional[str], user_id: str, user_role: str, db: Session,
) -> dict:
    from app.models.advanced_config import ProjectTemplate, TemplatePhase
    from app.models.project import Project, ProjectPhase
    from app.models.task import Task, TaskStatus, TaskPriority
    from app.models.resources import Deliverable

    if user_role not in ("admin", "pm"):
        raise HTTPException(403, "Acceso denegado")

    template = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Plantilla no encontrada")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Proyecto no encontrado")

    base_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else date.today()
    created_phases = 0
    created_tasks = 0
    created_risks = 0
    created_deliverables = 0

    try:
        for ph in sorted(template.phases, key=lambda x: x.order):
            phase = ProjectPhase(
                project_id=project_id, name=ph.name, description=ph.description,
                order=ph.order, budget_hours=ph.estimated_hours,
            )
            db.add(phase)
            db.flush()
            created_phases += 1
            for tk in sorted(ph.tasks, key=lambda x: x.order):
                db.add(Task(
                    project_id=project_id, phase_id=phase.id,
                    title=tk.title, description=tk.description,
                    estimated_hours=tk.estimated_hours,
                    status=TaskStatus.todo, priority=TaskPriority.medium,
                ))
                created_tasks += 1

        for i, r in enumerate(template.risks):
            from app.models.pipeline import Risk as RiskModel
            db.add(RiskModel(
                project_id=project_id, code=f"RSK-{i+1:03d}",
                title=r.title, category=r.category,
                probability=r.probability, impact=r.impact,
                mitigation_plan=r.mitigation_plan, identified_by=user_id,
            ))
            created_risks += 1

        for i, d in enumerate(template.deliverables):
            planned = None
            if d.week_offset is not None:
                planned = base_date + timedelta(weeks=d.week_offset)
            db.add(Deliverable(
                project_id=project_id, code=f"DEL-{i+1:03d}",
                name=d.name, format=d.format,
                billing_pct=d.billing_pct, planned_date=planned,
            ))
            created_deliverables += 1

        db.commit()
        return {
            "message": (
                f"Plantilla aplicada: {created_phases} fases, "
                f"{created_tasks} tareas, {created_risks} riesgos, "
                f"{created_deliverables} entregables"
            )
        }
    except Exception:
        db.rollback()
        raise
