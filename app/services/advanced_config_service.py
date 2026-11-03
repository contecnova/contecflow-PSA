"""
Advanced Config Service — business logic extracted from advanced_config.py router.
Covers: seeders, vacation balance computation, project template application.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Optional
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException

from app.core.config import settings
from app.core import timeutil

logger = logging.getLogger(__name__)
from app.models.advanced_config import AlertConfig
from app.models.advanced_config import TaskType
from app.models.advanced_config import NumberingSequence
from app.models.advanced_config import CustomRole
from app.models.advanced_config import UserVacationBalance
from app.models.advanced_config import ProjectTemplate, TemplatePhase
from app.models.advanced_config import RateTable
from app.models.advanced_config import RateEntry
from app.models.advanced_config import VacationPolicy
from app.models.advanced_config import Office
from app.models.advanced_config import CustomField
from app.models.advanced_config import CustomFieldValue
from app.models.advanced_config import TemplateTask, TemplateRisk, TemplateDeliverable
from app.models.marketplace import TemplateDocument
from app.models.marketplace import TemplateRole
from app.models.pipeline import Risk as RiskModel
from app.models.project import Project, ProjectPhase
from app.models.resources import Absence, AbsenceStatus, AbsenceType
from app.models.resources import Deliverable
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.user import User as UserModel
from fastapi import HTTPException as _HTTPException

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

# Los mismos modulos que aplica `app/core/modulos.py`.
DEFAULT_SYSTEM_ROLES = [
    ("admin",          "Dirección / Admin",         "#ff4757", True),
    ("pm",             "Project Manager",            "#00d4ff", True),
    ("hr",             "RRHH",                       "#00e5a0", True),
    ("team_lead",      "Team Lead",                  "#7c3aed", True),
    ("employee",       "Empleado",                   "#7a8aaa", True),
    ("subcontractor",  "Subcontratado",              "#f59e0b", True),
]


# ── Seeders ───────────────────────────────────────────────────────────────────

def seed_alert_configs(db: Session):
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
    if db.query(TaskType).count() > 0:
        return
    for i, (value, name, icon, color, billable) in enumerate(DEFAULT_TASK_TYPES):
        db.add(TaskType(
            value=value, name=name, icon=icon, color=color,
            is_billable_default=billable, sort_order=i,
        ))
    db.commit()


def seed_numbering(db: Session):
    if db.query(NumberingSequence).count() > 0:
        return
    for entity, prefix, suffix, sep, year, padding, reset, example in DEFAULT_NUMBERING:
        db.add(NumberingSequence(
            entity=entity, prefix=prefix, suffix=suffix, separator=sep,
            include_year=year, padding=padding, reset_yearly=reset, example=example,
        ))
    db.commit()


def seed_system_roles(db: Session, org_id: Optional[str] = None):
    """Una fila por rol base y organizacion (la de la sesion si no se da).

    Auditoria 2026-11: sembraba una sola vez en toda la instalacion, la fila
    quedaba sellada con la organizacion de quien abria la pantalla y la
    siguiente organizacion chocaba con el unico global del nombre.
    """
    org_id = org_id or db.info.get("organization_id")
    if not org_id:
        return
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        existentes = {n for (n,) in db.query(CustomRole.name).filter(CustomRole.organization_id == org_id)}
    all_modules = {m: True for m in DEFAULT_MODULES}
    nuevos = False
    for name, description, color, is_system in DEFAULT_SYSTEM_ROLES:
        if name not in existentes:
            db.add(CustomRole(
                name=name, description=description, color=color, organization_id=org_id,
                is_system=is_system, is_active=True,
                module_access=json.dumps(all_modules),
            ))
            nuevos = True
    if nuevos:
        db.commit()


# ── Vacation balances ─────────────────────────────────────────────────────────

def get_vacation_balances(year: Optional[int], db: Session) -> list:

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

    base_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else timeutil.today()
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
        logger.exception("Failed to apply project template; rolling back")
        db.rollback()
        raise


# ── Custom exceptions ─────────────────────────────────────────────────────────

class NotFoundError(ValueError):
    pass


# ── Roles ─────────────────────────────────────────────────────────────────────

def list_roles(db: Session) -> list:
    seed_system_roles(db)
    roles = (
        db.query(CustomRole)
        .filter(CustomRole.is_active == True)
        .order_by(CustomRole.is_system.desc(), CustomRole.name)
        .all()
    )
    return [
        {
            "id": r.id, "name": r.name, "description": r.description, "color": r.color,
            "is_system": r.is_system,
            "module_access": json.loads(r.module_access) if r.module_access else {},
            "permissions": json.loads(r.permissions) if r.permissions else {},
        }
        for r in roles
    ]


_ROLES_BASE = {name for name, *_ in DEFAULT_SYSTEM_ROLES}


def create_role(data: dict, db: Session) -> dict:
    from app.core.modulos import validar_acceso
    if data["name"] in _ROLES_BASE:
        raise HTTPException(422, "Ese nombre es el de un rol base")
    validar_acceso(data.get("module_access"))
    r = CustomRole(
        name=data["name"],
        description=data.get("description"),
        color=data.get("color", "#7a8aaa"),
        module_access=json.dumps(data.get("module_access") or {}),
        permissions=json.dumps(data.get("permissions") or {}),
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "name": r.name}


def update_role(role_id: str, data: dict, db: Session) -> dict:
    from app.core.modulos import validar_acceso
    r = db.query(CustomRole).filter(CustomRole.id == role_id).first()
    if not r:
        raise NotFoundError("Rol no encontrado")
    if "name" in data and r.is_system and data["name"] != r.name:
        raise ValueError("No se puede renombrar un rol del sistema")
    if "name" in data and not r.is_system and data["name"] in _ROLES_BASE:
        raise ValueError("Ese nombre es el de un rol base")
    validar_acceso(data.get("module_access"))
    for k, v in data.items():
        if k == "module_access" and v is not None:
            r.module_access = json.dumps(v)
        elif k == "permissions" and v is not None:
            r.permissions = json.dumps(v)
        elif hasattr(r, k) and k not in ("id", "organization_id", "is_system"):
            setattr(r, k, v)
    db.commit()
    db.refresh(r)
    return {"id": r.id, "name": r.name}


def delete_role(role_id: str, db: Session) -> dict:
    r = db.query(CustomRole).filter(CustomRole.id == role_id).first()
    if not r:
        raise NotFoundError("Rol no encontrado")
    if r.is_system:
        raise ValueError("No se pueden eliminar roles del sistema")
    r.is_active = False
    db.commit()
    return {"ok": True}


# ── Task types ────────────────────────────────────────────────────────────────

def list_task_types(db: Session) -> list:
    seed_task_types(db)
    types = (
        db.query(TaskType)
        .filter(TaskType.is_active == True)
        .order_by(TaskType.sort_order)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name, "value": t.value, "icon": t.icon,
            "color": t.color, "is_billable_default": t.is_billable_default,
            "is_active": t.is_active, "sort_order": t.sort_order,
        }
        for t in types
    ]


def create_task_type(data: dict, db: Session):
    if db.query(TaskType).filter(TaskType.value == data["value"]).first():
        raise ValueError("Ya existe un tipo con ese valor")
    t = TaskType(**data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def update_task_type(type_id: str, data: dict, db: Session):
    t = db.query(TaskType).filter(TaskType.id == type_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(t, k, v)
    db.commit()
    db.refresh(t)
    return t


def delete_task_type(type_id: str, db: Session) -> dict:
    t = db.query(TaskType).filter(TaskType.id == type_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ── Alert configs ─────────────────────────────────────────────────────────────

def list_alert_configs(db: Session) -> list:
    seed_alert_configs(db)
    configs = db.query(AlertConfig).order_by(AlertConfig.alert_type).all()
    return [
        {
            "id": c.id, "alert_type": c.alert_type, "label": c.label,
            "description": c.description, "is_enabled": c.is_enabled,
            "threshold_value": c.threshold_value, "threshold_unit": c.threshold_unit,
            "notify_admin": c.notify_admin, "notify_pm": c.notify_pm,
            "notify_hr": c.notify_hr, "notify_employee": c.notify_employee,
            "notify_email": c.notify_email, "severity": c.severity,
        }
        for c in configs
    ]


def update_alert_config(alert_type: str, data: dict, db: Session):
    cfg = db.query(AlertConfig).filter(AlertConfig.alert_type == alert_type).first()
    if not cfg:
        raise NotFoundError("Configuración no encontrada")
    for k, v in data.items():
        setattr(cfg, k, v)
    db.commit()
    db.refresh(cfg)
    return cfg


# ── Rate tables ───────────────────────────────────────────────────────────────

def list_rate_tables(db: Session) -> list:
    tables = (
        db.query(RateTable)
        .options(joinedload(RateTable.entries))
        .filter(RateTable.is_active == True)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "is_default": t.is_default, "is_active": t.is_active, "applies_to": t.applies_to,
            "entries": [
                {
                    "id": e.id, "label": e.label, "cost_rate": e.cost_rate,
                    "billing_rate": e.billing_rate,
                    "currency": getattr(e, "currency", settings.DEFAULT_CURRENCY),
                }
                for e in (t.entries or []) if getattr(e, "is_active", True)
            ],
        }
        for t in tables
    ]


def create_rate_table(data: dict, db: Session) -> dict:
    if data.get("is_default"):
        db.query(RateTable).filter(RateTable.is_default == True).update({"is_default": False})
    t = RateTable(**data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "name": t.name}


def add_rate_entry(table_id: str, data: dict, db: Session) -> dict:
    e = RateEntry(table_id=table_id, **data)
    db.add(e)
    db.commit()
    db.refresh(e)
    return {"id": e.id}


def update_rate_entry(table_id: str, entry_id: str, data: dict, db: Session) -> dict:
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id,
        RateEntry.table_id == table_id,
        RateEntry.is_active == True,
    ).first()
    if not e:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(e, k, v)
    db.commit()
    db.refresh(e)
    return {"id": e.id}


def delete_rate_entry(table_id: str, entry_id: str, db: Session) -> dict:
    e = db.query(RateEntry).filter(
        RateEntry.id == entry_id,
        RateEntry.table_id == table_id,
        RateEntry.is_active == True,
    ).first()
    if not e:
        raise NotFoundError("No encontrado")
    e.is_active = False
    db.commit()
    return {"ok": True, "message": "Tarifa eliminada"}


def delete_rate_table(table_id: str, db: Session) -> dict:
    t = db.query(RateTable).filter(RateTable.id == table_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ── Vacation policies ─────────────────────────────────────────────────────────

def list_vacation_policies(db: Session) -> list:
    policies = db.query(VacationPolicy).filter(VacationPolicy.is_active == True).all()
    return [
        {
            "id": p.id, "name": p.name, "description": p.description,
            "days_per_year": p.days_per_year, "carries_over": p.carries_over,
            "max_carryover_days": p.max_carryover_days,
            "carryover_expiry_months": p.carryover_expiry_months,
            "applies_to_roles": p.applies_to_roles, "is_default": p.is_default,
            "is_active": p.is_active,
        }
        for p in policies
    ]


def create_vacation_policy(data: dict, db: Session) -> dict:
    if data.get("is_default"):
        db.query(VacationPolicy).filter(VacationPolicy.is_default == True).update({"is_default": False})
    p = VacationPolicy(**{**data, "applies_to_roles": json.dumps(data.get("applies_to_roles") or [])})
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name}


def update_vacation_policy(policy_id: str, data: dict, db: Session) -> dict:
    p = db.query(VacationPolicy).filter(VacationPolicy.id == policy_id).first()
    if not p:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(p, k, json.dumps(v) if k == "applies_to_roles" else v)
    db.commit()
    db.refresh(p)
    return {"id": p.id}


def delete_vacation_policy(policy_id: str, db: Session) -> dict:
    p = db.query(VacationPolicy).filter(VacationPolicy.id == policy_id).first()
    if not p:
        raise NotFoundError("No encontrado")
    p.is_active = False
    db.commit()
    return {"ok": True}


# ── Offices ───────────────────────────────────────────────────────────────────

def list_offices(db: Session) -> list:
    offices = db.query(Office).filter(Office.is_active == True).order_by(Office.name).all()
    return [
        {"id": o.id, "name": o.name, "country": o.country, "city": o.city,
         "timezone": o.timezone, "is_active": o.is_active}
        for o in offices
    ]


def create_office(data: dict, db: Session) -> dict:
    o = Office(**data)
    db.add(o)
    db.commit()
    db.refresh(o)
    return {"id": o.id, "name": o.name}


def update_office(office_id: str, data: dict, db: Session) -> dict:
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(o, k, v)
    db.commit()
    db.refresh(o)
    return {"id": o.id}


def delete_office(office_id: str, db: Session) -> dict:
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o:
        raise NotFoundError("No encontrado")
    o.is_active = False
    db.commit()
    return {"ok": True}


# ── Numbering sequences ───────────────────────────────────────────────────────

def list_numbering(db: Session) -> list:
    seed_numbering(db)
    seqs = db.query(NumberingSequence).order_by(NumberingSequence.entity).all()
    result = []
    for s in seqs:
        year = datetime.now().year
        next_val = s.current_value + 1
        year_part = f"{year}{s.separator}" if s.include_year else ""
        padded = str(next_val).zfill(s.padding)
        preview = (
            f"{s.prefix}{s.separator}{year_part}{padded}{s.suffix}"
            if s.prefix
            else f"{year_part}{padded}{s.suffix}"
        )
        result.append({
            "id": s.id, "entity": s.entity, "prefix": s.prefix, "suffix": s.suffix,
            "separator": s.separator, "include_year": s.include_year, "padding": s.padding,
            "reset_yearly": s.reset_yearly, "current_value": s.current_value,
            "example": s.example, "next_preview": preview,
        })
    return result


def update_numbering_seq(entity: str, data: dict, db: Session) -> dict:
    s = db.query(NumberingSequence).filter(NumberingSequence.entity == entity).first()
    if not s:
        s = NumberingSequence(entity=entity, **data)
        db.add(s)
    else:
        for k, v in data.items():
            setattr(s, k, v)
    year = datetime.now().year
    year_part = f"{year}{data['separator']}" if data.get("include_year") else ""
    padded = "1".zfill(data.get("padding", 4))
    prefix = data.get("prefix", "")
    sep = data.get("separator", "-")
    suffix = data.get("suffix", "")
    s.example = (
        f"{prefix}{sep}{year_part}{padded}{suffix}"
        if prefix
        else f"{year_part}{padded}"
    )
    db.commit()
    db.refresh(s)
    return {"ok": True, "example": s.example}


def reset_numbering_seq(entity: str, db: Session) -> dict:
    s = db.query(NumberingSequence).filter(NumberingSequence.entity == entity).first()
    if not s:
        raise NotFoundError("No encontrado")
    s.current_value = 0
    db.commit()
    return {"ok": True}


# ── Custom fields ─────────────────────────────────────────────────────────────

def list_custom_fields(entity: Optional[str], db: Session) -> list:
    q = db.query(CustomField).filter(CustomField.is_active == True)
    if entity:
        q = q.filter(CustomField.entity == entity)
    fields = q.order_by(CustomField.entity, CustomField.sort_order).all()
    return [
        {
            "id": f.id, "entity": f.entity, "name": f.name, "field_key": f.field_key,
            "field_type": f.field_type,
            "options": json.loads(f.options) if f.options else None,
            "is_required": f.is_required, "placeholder": f.placeholder,
            "default_value": f.default_value,
            "visible_to_roles": json.loads(f.visible_to_roles) if f.visible_to_roles else None,
            "sort_order": f.sort_order,
        }
        for f in fields
    ]


def create_custom_field(data: dict, db: Session) -> dict:
    if db.query(CustomField).filter(
        CustomField.entity == data["entity"],
        CustomField.field_key == data["field_key"],
    ).first():
        raise ValueError("Ya existe un campo con esa clave para esa entidad")
    f = CustomField(**{
        **data,
        "options": json.dumps(data["options"]) if data.get("options") else None,
        "visible_to_roles": json.dumps(data["visible_to_roles"]) if data.get("visible_to_roles") else None,
    })
    db.add(f)
    db.commit()
    db.refresh(f)
    return {"id": f.id}


def update_custom_field(field_id: str, data: dict, db: Session) -> dict:
    f = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not f:
        raise NotFoundError("No encontrado")
    for k, v in data.items():
        setattr(f, k, json.dumps(v) if k in ("options", "visible_to_roles") and v else v)
    db.commit()
    db.refresh(f)
    return {"id": f.id}


def delete_custom_field(field_id: str, db: Session) -> dict:
    f = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not f:
        raise NotFoundError("No encontrado")
    f.is_active = False
    db.commit()
    return {"ok": True}


def get_custom_field_values(entity_id: str, db: Session) -> dict:
    values = (
        db.query(CustomFieldValue)
        .options(joinedload(CustomFieldValue.field))
        .filter(CustomFieldValue.entity_id == entity_id)
        .all()
    )
    return {v.field.field_key: v.value for v in values if v.field}


def save_custom_field_values(entity_id: str, values: dict, db: Session) -> dict:
    try:
        for field_key, value in values.items():
            field = db.query(CustomField).filter(
                CustomField.field_key == field_key,
                CustomField.is_active == True,
            ).first()
            if not field:
                continue
            existing = db.query(CustomFieldValue).filter(
                CustomFieldValue.field_id == field.id,
                CustomFieldValue.entity_id == entity_id,
            ).first()
            if existing:
                existing.value = str(value) if value is not None else None
            else:
                db.add(CustomFieldValue(
                    field_id=field.id,
                    entity_id=entity_id,
                    value=str(value) if value is not None else None,
                ))
        db.commit()
        return {"ok": True}
    except Exception:
        logger.exception("Failed to persist CustomFieldValue for entity=%s", entity_id)
        db.rollback()
        raise


# ── Templates ─────────────────────────────────────────────────────────────────

def list_templates(db: Session) -> list:
    templates = (
        db.query(ProjectTemplate)
        .options(
            joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
            joinedload(ProjectTemplate.risks),
            joinedload(ProjectTemplate.deliverables),
        )
        .filter(ProjectTemplate.is_active == True)
        .all()
    )
    return [
        {
            "id": t.id, "name": t.name, "description": t.description,
            "project_type": t.project_type, "estimated_weeks": t.estimated_weeks,
            "estimated_hours": t.estimated_hours,
            "phase_count": len(t.phases),
            "task_count": sum(len(p.tasks) for p in t.phases),
            "risk_count": len(t.risks),
            "deliverable_count": len(t.deliverables),
            "phases": [
                {
                    "id": p.id, "name": p.name, "order": p.order,
                    "estimated_weeks": p.estimated_weeks, "estimated_hours": p.estimated_hours,
                    "tasks": [
                        {"id": tk.id, "title": tk.title, "estimated_hours": tk.estimated_hours,
                         "skill_required": tk.skill_required}
                        for tk in p.tasks
                    ],
                }
                for p in sorted(t.phases, key=lambda x: x.order)
            ],
            "risks": [
                {"id": r.id, "title": r.title, "category": r.category,
                 "probability": r.probability, "impact": r.impact}
                for r in t.risks
            ],
            "deliverables": [
                {"id": d.id, "name": d.name, "format": d.format,
                 "week_offset": d.week_offset, "billing_pct": d.billing_pct}
                for d in t.deliverables
            ],
        }
        for t in templates
    ]


def create_template(data: dict, user_id: str, user_role: str, db: Session) -> dict:
    if user_role not in ("admin", "pm"):
        raise _HTTPException(403, "Acceso denegado")
    try:
        t = ProjectTemplate(
            name=data["name"],
            description=data.get("description"),
            project_type=data.get("project_type"),
            estimated_weeks=data.get("estimated_weeks"),
            estimated_hours=data.get("estimated_hours"),
            created_by=user_id,
        )
        db.add(t)
        db.flush()
        for i, ph in enumerate(data.get("phases") or []):
            phase = TemplatePhase(
                template_id=t.id,
                name=ph["name"],
                description=ph.get("description"),
                order=ph.get("order") or i,
                estimated_weeks=ph.get("estimated_weeks"),
                estimated_hours=ph.get("estimated_hours"),
            )
            db.add(phase)
            db.flush()
            for j, tk in enumerate(ph.get("tasks") or []):
                db.add(TemplateTask(
                    phase_id=phase.id,
                    title=tk.get("title", ""),
                    estimated_hours=tk.get("estimated_hours"),
                    skill_required=tk.get("skill_required"),
                    order=j,
                ))
        for r in data.get("risks") or []:
            db.add(TemplateRisk(
                template_id=t.id,
                title=r.get("title", ""),
                category=r.get("category"),
                probability=r.get("probability", "medium"),
                impact=r.get("impact", "moderate"),
                mitigation_plan=r.get("mitigation_plan"),
            ))
        for d in data.get("deliverables") or []:
            db.add(TemplateDeliverable(
                template_id=t.id,
                name=d.get("name", ""),
                format=d.get("format"),
                billing_pct=d.get("billing_pct"),
                week_offset=d.get("week_offset"),
            ))
        db.commit()
        return {"id": t.id, "name": t.name}
    except Exception:
        logger.exception("Failed to persist project template")
        db.rollback()
        raise


def delete_template(template_id: str, db: Session) -> dict:
    t = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if not t:
        raise NotFoundError("No encontrado")
    t.is_active = False
    db.commit()
    return {"ok": True}


# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATE DOCUMENTS + ROLES (v23.9.0)
# ──────────────────────────────────────────────────────────────────────────────

#: Los valores por defecto de `template_risks`, tal como los declara la tabla.
#: Se usan cuando el riesgo de origen no trae probabilidad o impacto.
PROBABILIDAD_POR_DEFECTO = "medium"
IMPACTO_POR_DEFECTO = "moderate"


def _valor_de_enum(valor, por_defecto: str) -> str:
    """El texto que hay que guardar para un enum de SQLAlchemy.

    Auditoria 2026-08 (hallazgo 22). `export_project_as_template` hacia
    `str(getattr(r, "probability", "medium"))`, y `Risk.probability` es un
    `Enum(RiskProbability)` **NOT NULL**, asi que `str()` no da `"medium"`: da
    `"RiskProbability.medium"`. Medido sobre los diez valores de los dos enums:

        str(RiskProbability.very_low)  -> 'RiskProbability.very_low'   24 chars
        str(RiskProbability.medium)    -> 'RiskProbability.medium'     22 chars
        str(RiskProbability.very_high) -> 'RiskProbability.very_high'  25 chars
        str(RiskImpact.negligible)     -> 'RiskImpact.negligible'      21 chars

    Y `template_risks.probability` es **VARCHAR(20)**. O sea dos defectos, no
    uno:

    1. **Siempre** se guardaba un texto que ningun lector puede volver a
       comparar contra el enum —`"RiskProbability.medium"` no es `"medium"`—,
       asi que la plantilla exportada salia con la probabilidad ilegible;
    2. y en **cuatro de los diez valores**, entre ellos `medium`, que es el
       valor por defecto y el mas frecuente, el texto **no cabe en la
       columna**: en PostgreSQL eso es `value too long for type character
       varying(20)` y la exportacion entera revienta con un 500. En SQLite se
       guarda truncado y en silencio, que es por lo que la suite no lo veia.

    El `getattr(..., por_defecto)` del original tampoco hacia nada: la columna
    es NOT NULL, asi que el atributo esta siempre. El respaldo que si hace
    falta es para `None`, que es lo que se comprueba aqui.
    """
    if valor is None:
        return por_defecto
    return getattr(valor, "value", None) or str(valor)


def plantilla_propia(db: Session, current_user, template_id: str) -> ProjectTemplate:
    """La plantilla, si es de la organizacion del sujeto. 404 si no.

    Auditoria 2026-08 (hallazgo 22): `endpoints/templates.py` tenia su propio
    `_get_template_or_404` que buscaba por id **sin ningun filtro**, y de el
    colgaban las dos altas. Anadir un documento o un rol a la plantilla de otro
    cliente era una escritura cruzada.
    """
    from app.core.tenancy import assert_same_org

    tmpl = (
        db.query(ProjectTemplate)
        .filter(ProjectTemplate.id == template_id)
        .first()
    )
    if not tmpl:
        raise HTTPException(404, "Template not found")
    assert_same_org(
        current_user, getattr(tmpl, "organization_id", None),
        detail="Template not found")
    return tmpl


def agregar_documento_a_plantilla(
    db: Session, current_user, template_id: str, datos: dict
) -> TemplateDocument:
    """Un documento nuevo en una plantilla propia. No confirma.

    Sustituye a `add_template_document`, que estaba aqui, **no la llamaba
    nadie** —comprobado en `app/` y en `tests/`— y tampoco filtraba por
    organizacion: el endpoint habia reimplementado lo mismo a mano en vez de
    usarla. Dos implementaciones muertas de la misma cosa es exactamente como
    aparecen las dos puertas de §3.septies, asi que se deja una.
    """
    plantilla_propia(db, current_user, template_id)
    doc = TemplateDocument(
        id=str(uuid4()),
        template_id=template_id,
        name=datos.get("name", "Document"),
        document_type=datos.get("document_type", "spec"),
        description=datos.get("description"),
        url=datos.get("url"),
        is_required=bool(datos.get("is_required", False)),
        due_week_offset=datos.get("due_week_offset"),
        organization_id=getattr(current_user, "organization_id", None),
    )
    db.add(doc)
    return doc


def agregar_rol_a_plantilla(
    db: Session, current_user, template_id: str, datos: dict
) -> TemplateRole:
    """Un rol nuevo en una plantilla propia. No confirma.

    Sustituye a `add_template_role`, en las mismas condiciones que el de
    documentos.
    """
    plantilla_propia(db, current_user, template_id)
    rol = TemplateRole(
        id=str(uuid4()),
        template_id=template_id,
        role_name=datos.get("role_name") or datos.get("name", "Role"),
        skill_required=datos.get("skill_required"),
        min_seniority=datos.get("min_seniority"),
        estimated_hours=datos.get("estimated_hours"),
        is_mandatory=bool(datos.get("is_mandatory", True)),
        notes=datos.get("notes"),
        organization_id=getattr(current_user, "organization_id", None),
    )
    db.add(rol)
    return rol




def get_full_template(template_id: str, db: Session, current_user=None) -> dict:
    """La plantilla entera con sus fases, tareas, riesgos y entregables.

    Auditoria 2026-08: esta funcion **no recibia al sujeto**, asi que no podia
    comprobar nada aunque quisiera — la misma forma que el endpoint de coste
    activo, que si lo recibia y lo descartaba. Ahora lo recibe, y el
    parametro es opcional por una razon acotada: los llamadores internos que no
    tienen sujeto (scripts, siembra) siguen funcionando. Todo endpoint tiene
    sujeto y **debe** pasarlo.

    El resto de las consultas van por `template_id` de una plantilla ya
    comprobada, asi que el ambito llega por la clave padre.
    """
    if current_user is not None:
        tmpl = plantilla_propia(db, current_user, template_id)
    else:
        tmpl = db.query(ProjectTemplate).filter(
            ProjectTemplate.id == template_id).first()
        if not tmpl:
            raise HTTPException(404, "Template not found")

    phases = db.query(TemplatePhase).filter(
        TemplatePhase.template_id == template_id
    ).order_by(TemplatePhase.order).all()
    phase_out = []
    for ph in phases:
        tasks = db.query(TemplateTask).filter(
            TemplateTask.phase_id == ph.id
        ).order_by(TemplateTask.order).all()
        phase_out.append({
            "id": ph.id, "name": ph.name, "description": ph.description,
            "order": ph.order, "estimated_weeks": ph.estimated_weeks,
            "estimated_hours": ph.estimated_hours,
            "tasks": [{"id": t.id, "title": t.title, "description": t.description,
                        "estimated_hours": t.estimated_hours, "skill_required": t.skill_required,
                        "order": t.order} for t in tasks],
        })

    risks = db.query(TemplateRisk).filter(TemplateRisk.template_id == template_id).all()
    deliverables = db.query(TemplateDeliverable).filter(
        TemplateDeliverable.template_id == template_id
    ).all()
    documents = db.query(TemplateDocument).filter(
        TemplateDocument.template_id == template_id
    ).all()
    roles = db.query(TemplateRole).filter(TemplateRole.template_id == template_id).all()

    return {
        "id": tmpl.id, "name": tmpl.name, "description": tmpl.description,
        "project_type": tmpl.project_type, "estimated_weeks": tmpl.estimated_weeks,
        "estimated_hours": tmpl.estimated_hours, "is_active": tmpl.is_active,
        "phases": phase_out,
        "risks": [{"id": r.id, "title": r.title, "category": r.category,
                   "probability": r.probability, "impact": r.impact,
                   "mitigation_plan": r.mitigation_plan} for r in risks],
        "deliverables": [{"id": d.id, "name": d.name, "format": d.format,
                           "acceptance_criteria": d.acceptance_criteria,
                           "week_offset": d.week_offset, "billing_pct": d.billing_pct}
                          for d in deliverables],
        "documents": [{"id": d.id, "name": d.name, "document_type": d.document_type,
                        "description": d.description, "url": d.url,
                        "is_required": d.is_required, "due_week_offset": d.due_week_offset}
                       for d in documents],
        "roles": [{"id": r.id, "role_name": r.role_name, "skill_required": r.skill_required,
                   "min_seniority": r.min_seniority, "estimated_hours": r.estimated_hours,
                   "is_mandatory": r.is_mandatory, "notes": r.notes} for r in roles],
    }


def export_project_as_template(
    project_id: str, name, description, user_id: str, db: Session,
    current_user=None,
) -> dict:
    """Convierte un proyecto en plantilla: sus tareas y sus riesgos.

    Auditoria 2026-08 (hallazgo 22). Aqui habia tres cosas:

    1. **Sin comprobar de quien es el proyecto.** Recibia `user_id`, una cadena,
       que no sirve para verificar nada. Cualquiera podia exportar el proyecto de
       otro cliente y quedarse con los titulos de sus tareas y sus riesgos.
    2. **Cinco `hasattr` muertos.** `Project.project_type`, `Task.description`,
       `Task.estimated_hours`, `Risk.category` y `Risk.mitigation_plan` existen
       todos, comprobado. Lo que hacian no era proteger: si alguna columna se
       renombrara, escribirian NULL en silencio en vez de fallar. Fuera.
    3. **El `str()` sobre los enums**, que es el defecto de verdad. Ver el
       docstring de `_valor_de_enum`.

    `current_user` es opcional por lo mismo que en `get_full_template`, y todo
    endpoint debe pasarlo.
    """
    from app.core.tenancy import assert_same_org

    proj = db.query(Project).filter(Project.id == project_id).first()
    if not proj:
        raise HTTPException(404, "Project not found")
    if current_user is not None:
        assert_same_org(
            current_user, getattr(proj, "organization_id", None),
            detail="Project not found")

    org_id = (
        getattr(current_user, "organization_id", None)
        if current_user is not None
        else getattr(proj, "organization_id", None)
    )

    tmpl_name = name or f"Template from {proj.name}"
    tmpl = ProjectTemplate(
        name=tmpl_name,
        description=description or proj.description,
        project_type=proj.project_type,
        created_by=user_id,
        organization_id=org_id,
    )
    db.add(tmpl); db.flush()

    phase = TemplatePhase(template_id=tmpl.id, name="Fase Principal", order=0,
                          organization_id=org_id)
    db.add(phase); db.flush()

    tasks = db.query(Task).filter(Task.project_id == project_id).all()
    for i, t in enumerate(tasks):
        db.add(TemplateTask(
            phase_id=phase.id, title=t.title,
            description=t.description,
            estimated_hours=t.estimated_hours,
            order=i,
            organization_id=org_id,
        ))

    risks = db.query(RiskModel).filter(RiskModel.project_id == project_id).all()
    for r in risks:
        db.add(TemplateRisk(
            template_id=tmpl.id, title=r.title,
            category=r.category,
            probability=_valor_de_enum(r.probability, PROBABILIDAD_POR_DEFECTO),
            impact=_valor_de_enum(r.impact, IMPACTO_POR_DEFECTO),
            mitigation_plan=r.mitigation_plan,
            organization_id=org_id,
        ))

    db.commit(); db.refresh(tmpl)
    return {
        "template_id": tmpl.id, "name": tmpl.name,
        "tasks_exported": len(tasks),
        "risks_exported": len(risks),
        "created": True,
    }
