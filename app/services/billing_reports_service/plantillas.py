"""Plantillas de proyecto: alta, listado e instanciacion.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

from datetime import date, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from app.core.config import settings
from app.models.user import User
from app.models.project import Project, ProjectPhase
from app.models.task import Task
from app.models.advanced_config import (
    ProjectTemplate, TemplatePhase, TemplateTask, TemplateRisk, TemplateDeliverable,
)
from app.services.audit import audit_log
from app.core import timeutil


# ═══════════════════════════════════════════════════════════════════════════════
# PROJECT TEMPLATE CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_template(payload, current_user: User, db: Session) -> dict:
    t = ProjectTemplate(
        name=payload.name, description=payload.description,
        project_type=payload.project_type,
        estimated_weeks=payload.estimated_weeks,
        estimated_hours=payload.estimated_hours,
        created_by=current_user.id,
    )
    db.add(t)
    db.flush()

    for i, ph_data in enumerate(payload.phases):
        phase_order = ph_data.get("phase_order", i)
        ph = TemplatePhase(
            template_id=t.id, name=ph_data["name"],
            description=ph_data.get("description"),
            order=phase_order, estimated_weeks=ph_data.get("estimated_weeks", 1),
        )
        db.add(ph)
        db.flush()
        for j, tk_data in enumerate(ph_data.get("tasks", [])):
            task_order = tk_data.get("task_order", j)
            db.add(TemplateTask(
                phase_id=ph.id, title=tk_data["title"],
                description=tk_data.get("description"),
                estimated_hours=tk_data.get("estimated_hours", 0),
                skill_required=tk_data.get("skill_required") or tk_data.get("role_required"),
                order=task_order,
            ))

    for rk_data in payload.risks:
        db.add(TemplateRisk(
            template_id=t.id,
            title=rk_data.get("title", "Riesgo"),
            category=rk_data.get("category"),
            probability=rk_data.get("probability", "medium"),
            impact=rk_data.get("impact", "moderate"),
            mitigation_plan=rk_data.get("mitigation_plan"),
        ))
    for dl_data in payload.deliverables:
        db.add(TemplateDeliverable(
            template_id=t.id,
            name=dl_data.get("name") or dl_data.get("title") or "Entregable",
            format=dl_data.get("format"),
            acceptance_criteria=dl_data.get("acceptance_criteria"),
            week_offset=dl_data.get("week_offset") if dl_data.get("week_offset") is not None else dl_data.get("deliverable_order"),
            billing_pct=dl_data.get("billing_pct"),
        ))

    audit_log(db, current_user, "CREATE", "project_templates", t.id, t.name)
    db.commit()
    return {"ok": True, "id": t.id}


def list_templates_all(db: Session) -> list:
    templates = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.is_active == True).all()
    return [{
        "id": t.id, "name": t.name, "description": t.description,
        "project_type": t.project_type,
        "estimated_weeks": t.estimated_weeks,
        "estimated_hours": t.estimated_hours,
        "phases": [{
            "id": ph.id, "name": ph.name, "order": ph.order,
            "estimated_weeks": ph.estimated_weeks,
            "tasks": [{
                "id": tk.id, "title": tk.title, "estimated_hours": tk.estimated_hours,
                "skill_required": tk.skill_required,
            } for tk in ph.tasks],
        } for ph in sorted(t.phases, key=lambda x: x.order)],
        "risk_count": len(t.risks),
        "deliverable_count": len(t.deliverables),
    } for t in templates]


# ═══════════════════════════════════════════════════════════════════════════════
# TEMPLATE INSTANTIATION
# ═══════════════════════════════════════════════════════════════════════════════

def instantiate_template(template_id: str, payload: dict, current_user: User, db: Session) -> dict:
    """Create a real project from a template, copying phases/tasks/risks/deliverables."""
    tpl = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.id == template_id).first()
    if not tpl:
        raise ValueError("template_not_found")

    project_name = payload.get("name", f"{tpl.name} — {timeutil.today()}")
    start = date.fromisoformat(payload["start_date"]) if payload.get("start_date") else timeutil.today()

    last = db.query(Project).order_by(Project.created_at.desc()).first()
    next_num = 1
    if last and last.code and last.code.startswith("PRJ-"):
        parts = last.code.split("-")
        if len(parts) > 1 and parts[1].isdigit():
            next_num = int(parts[1]) + 1
    code = f"PRJ-{next_num:03d}"

    from app.services.settings_service import get_runtime_str
    _proj_type = get_runtime_str(db, "DEFAULT_PROJECT_TYPE", db.info.get("organization_id")) or settings.DEFAULT_PROJECT_TYPE
    _bill_type = get_runtime_str(db, "DEFAULT_BILLING_TYPE", db.info.get("organization_id")) or settings.DEFAULT_BILLING_TYPE
    project = Project(
        code=payload.get("code", code),
        name=project_name,
        description=payload.get("description", tpl.description),
        project_type=tpl.project_type or _proj_type,
        client_name=payload.get("client_name"),
        pm_id=payload.get("pm_id"),
        start_date=start,
        end_date_planned=start + timedelta(weeks=tpl.estimated_weeks or 12) if tpl.estimated_weeks else None,
        budget_hours=tpl.estimated_hours,
        budget_amount=payload.get("budget_amount"),
        billing_type=payload.get("billing_type", _bill_type),
        is_billable=payload.get("is_billable", True),
        created_by=current_user.id,
    )
    db.add(project)
    db.flush()

    phase_offset = 0
    for ph_tpl in sorted(tpl.phases, key=lambda x: x.order):
        phase_start = start + timedelta(weeks=phase_offset)
        ph = ProjectPhase(
            project_id=project.id,
            name=ph_tpl.name,
            description=ph_tpl.description,
            order=ph_tpl.order,
            start_date=phase_start,
            end_date=phase_start + timedelta(weeks=ph_tpl.estimated_weeks or 1),
        )
        db.add(ph)
        db.flush()

        for tk_tpl in ph_tpl.tasks:
            task_due = phase_start + timedelta(weeks=ph_tpl.estimated_weeks or 1)
            db.add(Task(
                project_id=project.id,
                phase_id=ph.id,
                code=f"{project.code}-T{db.query(func.count(Task.id)).filter(Task.project_id == project.id).scalar() + 1:03d}",
                title=tk_tpl.title,
                description=tk_tpl.description,
                estimated_hours=tk_tpl.estimated_hours,
                priority="medium",
                due_date=task_due,
                created_by=current_user.id,
            ))

        phase_offset += ph_tpl.estimated_weeks or 1

    db.commit()
    audit_log(db, current_user, "CREATE_FROM_TEMPLATE", "projects", project.id, project.name,
              new_values={"template_id": template_id, "template_name": tpl.name})
    db.commit()

    return {
        "ok": True, "project_id": project.id, "project_code": project.code,
        "project_name": project.name,
        "phases_created": len(tpl.phases),
        "tasks_created": sum(len(ph.tasks) for ph in tpl.phases),
    }
