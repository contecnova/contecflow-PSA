from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional, List
from datetime import date, datetime
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_admin_or_hr
from app.models.user import User, UserRole
from app.models.advanced_config import (
    CustomRole, ProjectTemplate, TemplatePhase, TemplateTask, TemplateRisk, TemplateDeliverable,
    TaskType, AlertConfig, RateTable, RateEntry, VacationPolicy, UserVacationBalance,
    Office, NumberingSequence, CustomField, CustomFieldValue
)
from app.core.config import settings

router = APIRouter()

# ── Default data seeders ──────────────────────────────────────────────────────

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

DEFAULT_MODULES = ["dashboard", "projects", "tasks", "imputations", "timesheets", "resources", "capacity", "profitability", "pipeline", "contracts", "risks", "changes", "deliverables", "skills", "absences", "reports", "alerts", "exports", "settings"]

DEFAULT_SYSTEM_ROLES = [
    ("admin", "Dirección / Admin", "#ff4757", True),
    ("pm", "Project Manager", "#00d4ff", True),
    ("hr", "RRHH", "#00e5a0", True),
    ("team_lead", "Team Lead", "#7c3aed", True),
    ("employee", "Empleado", "#7a8aaa", True),
]


def _seed_alert_configs(db: Session):
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


def _seed_task_types(db: Session):
    if db.query(TaskType).count() > 0:
        return
    for i, (value, name, icon, color, billable) in enumerate(DEFAULT_TASK_TYPES):
        db.add(TaskType(value=value, name=name, icon=icon, color=color, is_billable_default=billable, sort_order=i))
    db.commit()


def _seed_numbering(db: Session):
    if db.query(NumberingSequence).count() > 0:
        return
    for entity, prefix, suffix, sep, year, padding, reset, example in DEFAULT_NUMBERING:
        db.add(NumberingSequence(entity=entity, prefix=prefix, suffix=suffix, separator=sep, include_year=year, padding=padding, reset_yearly=reset, example=example))
    db.commit()


def _seed_system_roles(db: Session):
    if db.query(CustomRole).filter(CustomRole.is_system == True).count() > 0:
        return
    all_modules = {m: True for m in DEFAULT_MODULES}
    for name, description, color, is_system in DEFAULT_SYSTEM_ROLES:
        db.add(CustomRole(name=name, description=description, color=color, is_system=is_system, module_access=json.dumps(all_modules)))
    db.commit()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CustomRoleUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[dict] = None
    is_active: Optional[bool] = None

class CustomRoleIn(BaseModel):
    name: str
    description: Optional[str] = None
    color: str = "#7a8aaa"
    module_access: Optional[dict] = None
    permissions: Optional[dict] = None

class TaskTypeIn(BaseModel):
    name: str
    value: str
    icon: str = "📋"
    color: str = "#7a8aaa"
    is_billable_default: bool = True
    sort_order: int = 0

class AlertConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    threshold_value: Optional[float] = None
    severity: Optional[str] = None
    notify_admin: Optional[bool] = None
    notify_pm: Optional[bool] = None
    notify_hr: Optional[bool] = None
    notify_employee: Optional[bool] = None
    notify_email: Optional[bool] = None

class RateTableIn(BaseModel):
    name: str
    description: Optional[str] = None
    applies_to: str = "role"
    is_default: bool = False

class RateEntryIn(BaseModel):
    label: str
    cost_rate: Optional[float] = None
    billing_rate: Optional[float] = None
    currency: str = settings.DEFAULT_CURRENCY
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None

class VacationPolicyIn(BaseModel):
    name: str
    description: Optional[str] = None
    days_per_year: float = settings.DEFAULT_VACATION_DAYS_PER_YEAR
    accrual_type: str = "annual"
    carries_over: bool = True
    max_carryover_days: Optional[float] = None
    carryover_expiry_months: Optional[int] = None
    applies_to_roles: Optional[list] = None
    is_default: bool = False

class OfficeIn(BaseModel):
    name: str
    country: Optional[str] = None
    city: Optional[str] = None
    timezone: str = settings.DEFAULT_TIMEZONE

class NumberingIn(BaseModel):
    prefix: str = ""
    suffix: str = ""
    separator: str = "-"
    include_year: bool = False
    padding: int = 4
    reset_yearly: bool = False

class CustomFieldIn(BaseModel):
    entity: str
    name: str
    field_key: str
    field_type: str
    options: Optional[list] = None
    is_required: bool = False
    placeholder: Optional[str] = None
    default_value: Optional[str] = None
    visible_to_roles: Optional[list] = None
    sort_order: int = 0

class TemplatePhaseIn(BaseModel):
    name: str
    description: Optional[str] = None
    order: int = 0
    estimated_weeks: Optional[int] = None
    estimated_hours: Optional[float] = None
    tasks: Optional[list] = []

class TemplateIn(BaseModel):
    name: str
    description: Optional[str] = None
    project_type: Optional[str] = None
    estimated_weeks: Optional[int] = None
    estimated_hours: Optional[float] = None
    phases: Optional[List[TemplatePhaseIn]] = []
    risks: Optional[list] = []
    deliverables: Optional[list] = []


# ── Roles ─────────────────────────────────────────────────────────────────────

@router.get("/roles", summary="Listar roles")
def get_roles(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _seed_system_roles(db)
    roles = db.query(CustomRole).filter(CustomRole.is_active == True).order_by(CustomRole.is_system.desc(), CustomRole.name).all()
    return [{
        "id": r.id, "name": r.name, "description": r.description, "color": r.color,
        "is_system": r.is_system,
        "module_access": json.loads(r.module_access) if r.module_access else {},
        "permissions": json.loads(r.permissions) if r.permissions else {},
    } for r in roles]

@router.post("/roles", summary="Crear rol personalizado")
def create_role(payload: CustomRoleIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = CustomRole(
        name=payload.name, description=payload.description, color=payload.color,
        module_access=json.dumps(payload.module_access or {}),
        permissions=json.dumps(payload.permissions or {}),
    )
    db.add(r); db.commit(); db.refresh(r)
    return {"id": r.id, "name": r.name}

@router.patch("/roles/{role_id}", summary="Actualizar rol")
def update_role(role_id: str, payload: CustomRoleUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.query(CustomRole).filter(CustomRole.id == role_id).first()
    if not r: raise HTTPException(404, "Rol no encontrado")
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and r.is_system and data["name"] != r.name:
        raise HTTPException(400, "No se puede renombrar un rol del sistema")
    for k, v in data.items():
        if k == "module_access" and v is not None:
            r.module_access = json.dumps(v)
        elif k == "permissions" and v is not None:
            r.permissions = json.dumps(v)
        elif hasattr(r, k):
            setattr(r, k, v)
    db.commit(); db.refresh(r)
    return {"id": r.id, "name": r.name}

@router.delete("/roles/{role_id}", summary="Eliminar rol")
def delete_role(role_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    r = db.query(CustomRole).filter(CustomRole.id == role_id).first()
    if not r: raise HTTPException(404, "Rol no encontrado")
    if r.is_system: raise HTTPException(400, "No se pueden eliminar roles del sistema")
    r.is_active = False; db.commit()
    return {"ok": True}

@router.get("/modules", summary="Lista de módulos disponibles")
def get_modules(_: User = Depends(get_current_user)):
    return [{"id": m, "label": m.replace("_", " ").title()} for m in DEFAULT_MODULES]


# ── Task types ────────────────────────────────────────────────────────────────

@router.get("/task-types", summary="Tipos de tarea")
def get_task_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _seed_task_types(db)
    types = db.query(TaskType).filter(TaskType.is_active == True).order_by(TaskType.sort_order).all()
    return [{"id": t.id, "name": t.name, "value": t.value, "icon": t.icon, "color": t.color,
             "is_billable_default": t.is_billable_default, "is_active": t.is_active, "sort_order": t.sort_order} for t in types]

@router.post("/task-types", summary="Crear tipo de tarea")
def create_task_type(payload: TaskTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(TaskType).filter(TaskType.value == payload.value).first():
        raise HTTPException(400, "Ya existe un tipo con ese valor")
    t = TaskType(**payload.model_dump()); db.add(t); db.commit(); db.refresh(t)
    return t

@router.patch("/task-types/{type_id}", summary="Actualizar tipo de tarea")
def update_task_type(type_id: str, payload: TaskTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    t = db.query(TaskType).filter(TaskType.id == type_id).first()
    if not t: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(t, k, v)
    db.commit(); db.refresh(t); return t

@router.delete("/task-types/{type_id}", summary="Eliminar tipo de tarea")
def delete_task_type(type_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    t = db.query(TaskType).filter(TaskType.id == type_id).first()
    if not t: raise HTTPException(404, "No encontrado")
    t.is_active = False; db.commit(); return {"ok": True}


# ── Alert configs ─────────────────────────────────────────────────────────────

@router.get("/alert-configs", summary="Configuración de alertas")
def get_alert_configs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    _seed_alert_configs(db)
    configs = db.query(AlertConfig).order_by(AlertConfig.alert_type).all()
    return [{"id": c.id, "alert_type": c.alert_type, "label": c.label, "description": c.description,
             "is_enabled": c.is_enabled, "threshold_value": c.threshold_value, "threshold_unit": c.threshold_unit,
             "notify_admin": c.notify_admin, "notify_pm": c.notify_pm, "notify_hr": c.notify_hr,
             "notify_employee": c.notify_employee, "notify_email": c.notify_email, "severity": c.severity} for c in configs]

@router.patch("/alert-configs/{alert_type}", summary="Actualizar configuración de alerta")
def update_alert_config(alert_type: str, payload: AlertConfigUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    cfg = db.query(AlertConfig).filter(AlertConfig.alert_type == alert_type).first()
    if not cfg: raise HTTPException(404, "Configuración no encontrada")
    for k, v in payload.model_dump(exclude_unset=True).items(): setattr(cfg, k, v)
    db.commit(); db.refresh(cfg); return cfg


# ── Rate tables ───────────────────────────────────────────────────────────────

@router.get("/rate-tables", summary="Tablas de tarifas")
def get_rate_tables(db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    tables = db.query(RateTable).options(joinedload(RateTable.entries)).filter(RateTable.is_active == True).all()
    return [{"id": t.id, "name": t.name, "description": t.description,
             "is_default": t.is_default, "is_active": t.is_active, "applies_to": t.applies_to,
             "entries": [{"id": e.id, "label": e.label,
                          "cost_rate": e.cost_rate, "billing_rate": e.billing_rate,
                          "currency": getattr(e, "currency", settings.DEFAULT_CURRENCY)} for e in (t.entries or [])]} for t in tables]

@router.post("/rate-tables", summary="Crear tabla de tarifas")
def create_rate_table(payload: RateTableIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if payload.is_default:
        db.query(RateTable).filter(RateTable.is_default == True).update({"is_default": False})
    t = RateTable(**payload.model_dump()); db.add(t); db.commit(); db.refresh(t)
    return {"id": t.id, "name": t.name}

@router.post("/rate-tables/{table_id}/entries", summary="Añadir tarifa")
def add_rate_entry(table_id: str, payload: RateEntryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    e = RateEntry(table_id=table_id, **payload.model_dump()); db.add(e); db.commit(); db.refresh(e)
    return {"id": e.id}

@router.patch("/rate-tables/{table_id}/entries/{entry_id}", summary="Actualizar tarifa")
def update_rate_entry(table_id: str, entry_id: str, payload: RateEntryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    e = db.query(RateEntry).filter(RateEntry.id == entry_id, RateEntry.table_id == table_id).first()
    if not e: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(e, k, v)
    db.commit(); db.refresh(e); return {"id": e.id}

@router.delete("/rate-tables/{table_id}/entries/{entry_id}", summary="Eliminar tarifa")
def delete_rate_entry(table_id: str, entry_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    e = db.query(RateEntry).filter(RateEntry.id == entry_id, RateEntry.table_id == table_id).first()
    if not e: raise HTTPException(404, "No encontrado")
    db.delete(e); db.commit(); return {"ok": True}

@router.delete("/rate-tables/{table_id}", summary="Eliminar tabla de tarifas")
def delete_rate_table(table_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    t = db.query(RateTable).filter(RateTable.id == table_id).first()
    if not t: raise HTTPException(404, "No encontrado")
    t.is_active = False; db.commit(); return {"ok": True}


# ── Vacation policies ─────────────────────────────────────────────────────────

@router.get("/vacation-policies", summary="Políticas de vacaciones")
def get_vacation_policies(db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    policies = db.query(VacationPolicy).filter(VacationPolicy.is_active == True).all()
    return [{"id": p.id, "name": p.name, "description": p.description,
             "days_per_year": p.days_per_year, "carries_over": p.carries_over,
             "max_carryover_days": p.max_carryover_days, "carryover_expiry_months": p.carryover_expiry_months,
             "applies_to_roles": p.applies_to_roles, "is_default": p.is_default, "is_active": p.is_active} for p in policies]

@router.post("/vacation-policies", summary="Crear política de vacaciones")
def create_vacation_policy(payload: VacationPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if payload.is_default:
        db.query(VacationPolicy).filter(VacationPolicy.is_default == True).update({"is_default": False})
    p = VacationPolicy(**{**payload.model_dump(), "applies_to_roles": json.dumps(payload.applies_to_roles or [])})
    db.add(p); db.commit(); db.refresh(p); return {"id": p.id, "name": p.name}

@router.patch("/vacation-policies/{policy_id}", summary="Actualizar política")
def update_vacation_policy(policy_id: str, payload: VacationPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = db.query(VacationPolicy).filter(VacationPolicy.id == policy_id).first()
    if not p: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items():
        setattr(p, k, json.dumps(v) if k == "applies_to_roles" else v)
    db.commit(); db.refresh(p); return {"id": p.id}

@router.delete("/vacation-policies/{policy_id}", summary="Eliminar política")
def delete_vacation_policy(policy_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    p = db.query(VacationPolicy).filter(VacationPolicy.id == policy_id).first()
    if not p: raise HTTPException(404, "No encontrado")
    p.is_active = False; db.commit(); return {"ok": True}

@router.get("/vacation-balances", summary="Saldos de vacaciones del equipo")
def get_vacation_balances(year: int = Query(default=None), db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    from datetime import datetime
    if not year: year = datetime.now().year
    from app.models.user import User as UserModel
    from app.models.resources import Absence, AbsenceStatus, AbsenceType
    users = db.query(UserModel).filter(UserModel.is_active == True).all()
    results = []
    for u in users:
        bal = db.query(UserVacationBalance).filter(UserVacationBalance.user_id == u.id, UserVacationBalance.year == year).first()
        year_start = date(year, 1, 1)
        year_end = date(year + 1, 1, 1)
        taken = db.query(func.sum(Absence.working_days)).filter(
            Absence.user_id == u.id, Absence.type == AbsenceType.vacation,
            Absence.status == AbsenceStatus.approved,
            Absence.start_date >= year_start,
            Absence.start_date < year_end,
        ).scalar() or 0
        pending = db.query(func.sum(Absence.working_days)).filter(
            Absence.user_id == u.id, Absence.type == AbsenceType.vacation,
            Absence.status == AbsenceStatus.pending,
            Absence.start_date >= year_start,
            Absence.start_date < year_end,
        ).scalar() or 0
        entitled = bal.days_entitled if bal else settings.DEFAULT_VACATION_DAYS_PER_YEAR
        results.append({
            "user_id": u.id, "user_name": u.full_name, "department": u.department,
            "year": year, "days_entitled": entitled, "days_taken": round(taken, 1),
            "days_pending": round(pending, 1), "days_remaining": round(entitled - taken - pending, 1),
            "days_carried_over": bal.days_carried_over if bal else 0,
        })
    return results

@router.patch("/vacation-balances/{user_id}", summary="Actualizar saldo de vacaciones")
def update_vacation_balance(user_id: str, year: int = Query(...), days_entitled: float = Query(...), db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    bal = db.query(UserVacationBalance).filter(UserVacationBalance.user_id == user_id, UserVacationBalance.year == year).first()
    if not bal:
        bal = UserVacationBalance(user_id=user_id, year=year, days_entitled=days_entitled)
        db.add(bal)
    else:
        bal.days_entitled = days_entitled
    db.commit(); return {"ok": True}


# ── Offices ───────────────────────────────────────────────────────────────────

@router.get("/offices", summary="Sedes / oficinas")
def get_offices(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    offices = db.query(Office).filter(Office.is_active == True).order_by(Office.name).all()
    return [{"id": o.id, "name": o.name, "country": o.country, "city": o.city,
             "timezone": o.timezone, "is_active": o.is_active} for o in offices]

@router.post("/offices", summary="Crear sede")
def create_office(payload: OfficeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    o = Office(**payload.model_dump()); db.add(o); db.commit(); db.refresh(o)
    return {"id": o.id, "name": o.name}

@router.patch("/offices/{office_id}", summary="Actualizar sede")
def update_office(office_id: str, payload: OfficeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(o, k, v)
    db.commit(); db.refresh(o); return {"id": o.id}

@router.delete("/offices/{office_id}", summary="Eliminar sede")
def delete_office(office_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    o = db.query(Office).filter(Office.id == office_id).first()
    if not o: raise HTTPException(404, "No encontrado")
    o.is_active = False; db.commit(); return {"ok": True}


# ── Numbering sequences ───────────────────────────────────────────────────────

@router.get("/numbering", summary="Secuencias de numeración")
def get_numbering(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    _seed_numbering(db)
    seqs = db.query(NumberingSequence).order_by(NumberingSequence.entity).all()
    result = []
    for s in seqs:
        year = datetime.now().year
        next_val = s.current_value + 1
        year_part = f"{year}{s.separator}" if s.include_year else ""
        padded = str(next_val).zfill(s.padding)
        preview = f"{s.prefix}{s.separator}{year_part}{padded}{s.suffix}" if s.prefix else f"{year_part}{padded}{s.suffix}"
        result.append({"id": s.id, "entity": s.entity, "prefix": s.prefix, "suffix": s.suffix, "separator": s.separator, "include_year": s.include_year, "padding": s.padding, "reset_yearly": s.reset_yearly, "current_value": s.current_value, "example": s.example, "next_preview": preview})
    return result

@router.patch("/numbering/{entity}", summary="Actualizar numeración")
def update_numbering(entity: str, payload: NumberingIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.query(NumberingSequence).filter(NumberingSequence.entity == entity).first()
    if not s:
        s = NumberingSequence(entity=entity, **payload.model_dump())
        db.add(s)
    else:
        for k, v in payload.model_dump().items(): setattr(s, k, v)
    # Update example
    year = datetime.now().year
    year_part = f"{year}{payload.separator}" if payload.include_year else ""
    padded = "1".zfill(payload.padding)
    s.example = f"{payload.prefix}{payload.separator}{year_part}{padded}{payload.suffix}" if payload.prefix else f"{year_part}{padded}"
    db.commit(); db.refresh(s); return {"ok": True, "example": s.example}

@router.post("/numbering/{entity}/reset", summary="Resetear contador")
def reset_numbering(entity: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    s = db.query(NumberingSequence).filter(NumberingSequence.entity == entity).first()
    if not s: raise HTTPException(404, "No encontrado")
    s.current_value = 0; db.commit(); return {"ok": True}


# ── Custom fields ─────────────────────────────────────────────────────────────

@router.get("/custom-fields", summary="Campos personalizados")
def get_custom_fields(entity: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(CustomField).filter(CustomField.is_active == True)
    if entity: q = q.filter(CustomField.entity == entity)
    fields = q.order_by(CustomField.entity, CustomField.sort_order).all()
    return [{
        "id": f.id, "entity": f.entity, "name": f.name, "field_key": f.field_key,
        "field_type": f.field_type,
        "options": json.loads(f.options) if f.options else None,
        "is_required": f.is_required, "placeholder": f.placeholder,
        "default_value": f.default_value,
        "visible_to_roles": json.loads(f.visible_to_roles) if f.visible_to_roles else None,
        "sort_order": f.sort_order,
    } for f in fields]

@router.post("/custom-fields", summary="Crear campo personalizado")
def create_custom_field(payload: CustomFieldIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    existing = db.query(CustomField).filter(CustomField.entity == payload.entity, CustomField.field_key == payload.field_key).first()
    if existing: raise HTTPException(400, "Ya existe un campo con esa clave para esa entidad")
    f = CustomField(**{**payload.model_dump(), "options": json.dumps(payload.options) if payload.options else None, "visible_to_roles": json.dumps(payload.visible_to_roles) if payload.visible_to_roles else None})
    db.add(f); db.commit(); db.refresh(f); return {"id": f.id}

@router.patch("/custom-fields/{field_id}", summary="Actualizar campo")
def update_custom_field(field_id: str, payload: CustomFieldIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    f = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not f: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items():
        if k in ("options", "visible_to_roles"):
            setattr(f, k, json.dumps(v) if v else None)
        else:
            setattr(f, k, v)
    db.commit(); db.refresh(f); return {"id": f.id}

@router.delete("/custom-fields/{field_id}", summary="Eliminar campo")
def delete_custom_field(field_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    f = db.query(CustomField).filter(CustomField.id == field_id).first()
    if not f: raise HTTPException(404, "No encontrado")
    f.is_active = False; db.commit(); return {"ok": True}

@router.get("/custom-fields/values/{entity_id}", summary="Valores de campos personalizados")
def get_field_values(entity_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    values = db.query(CustomFieldValue).options(joinedload(CustomFieldValue.field)).filter(CustomFieldValue.entity_id == entity_id).all()
    return {v.field.field_key: v.value for v in values if v.field}

@router.post("/custom-fields/values/{entity_id}", summary="Guardar valores de campos")
def save_field_values(entity_id: str, values: dict, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        for field_key, value in values.items():
            field = db.query(CustomField).filter(CustomField.field_key == field_key, CustomField.is_active == True).first()
            if not field: continue
            existing = db.query(CustomFieldValue).filter(CustomFieldValue.field_id == field.id, CustomFieldValue.entity_id == entity_id).first()
            if existing:
                existing.value = str(value) if value is not None else None
            else:
                db.add(CustomFieldValue(field_id=field.id, entity_id=entity_id, value=str(value) if value is not None else None))
        db.commit()
        return {"ok": True}
    except Exception:
        db.rollback()
        raise


# ── Project templates ─────────────────────────────────────────────────────────

@router.get("/templates", summary="Plantillas de proyecto")
def get_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    templates = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks),
        joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.is_active == True).all()
    return [{
        "id": t.id, "name": t.name, "description": t.description,
        "project_type": t.project_type, "estimated_weeks": t.estimated_weeks,
        "estimated_hours": t.estimated_hours,
        "phase_count": len(t.phases),
        "task_count": sum(len(p.tasks) for p in t.phases),
        "risk_count": len(t.risks),
        "deliverable_count": len(t.deliverables),
        "phases": [{
            "id": p.id, "name": p.name, "order": p.order,
            "estimated_weeks": p.estimated_weeks, "estimated_hours": p.estimated_hours,
            "tasks": [{"id": tk.id, "title": tk.title, "estimated_hours": tk.estimated_hours, "skill_required": tk.skill_required} for tk in p.tasks],
        } for p in sorted(t.phases, key=lambda x: x.order)],
        "risks": [{"id": r.id, "title": r.title, "category": r.category, "probability": r.probability, "impact": r.impact} for r in t.risks],
        "deliverables": [{"id": d.id, "name": d.name, "format": d.format, "week_offset": d.week_offset, "billing_pct": d.billing_pct} for d in t.deliverables],
    } for t in templates]

@router.post("/templates", summary="Crear plantilla")
def create_template(payload: TemplateIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    try:
        t = ProjectTemplate(name=payload.name, description=payload.description, project_type=payload.project_type, estimated_weeks=payload.estimated_weeks, estimated_hours=payload.estimated_hours, created_by=current_user.id)
        db.add(t); db.flush()
        for i, ph in enumerate(payload.phases or []):
            phase = TemplatePhase(template_id=t.id, name=ph.name, description=ph.description, order=ph.order or i, estimated_weeks=ph.estimated_weeks, estimated_hours=ph.estimated_hours)
            db.add(phase); db.flush()
            for j, tk in enumerate(ph.tasks or []):
                db.add(TemplateTask(phase_id=phase.id, title=tk.get("title", ""), estimated_hours=tk.get("estimated_hours"), skill_required=tk.get("skill_required"), order=j))
        for r in payload.risks or []:
            db.add(TemplateRisk(template_id=t.id, title=r.get("title", ""), category=r.get("category"), probability=r.get("probability", "medium"), impact=r.get("impact", "moderate"), mitigation_plan=r.get("mitigation_plan")))
        for d in payload.deliverables or []:
            db.add(TemplateDeliverable(template_id=t.id, name=d.get("name", ""), format=d.get("format"), billing_pct=d.get("billing_pct"), week_offset=d.get("week_offset")))
        db.commit()
        return {"id": t.id, "name": t.name}
    except Exception:
        db.rollback()
        raise

@router.delete("/templates/{template_id}", summary="Eliminar plantilla")
def delete_template(template_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    t = db.query(ProjectTemplate).filter(ProjectTemplate.id == template_id).first()
    if not t: raise HTTPException(404, "No encontrado")
    t.is_active = False; db.commit(); return {"ok": True}

@router.post("/templates/{template_id}/apply/{project_id}", summary="Aplicar plantilla a proyecto")
def apply_template(template_id: str, project_id: str, start_date: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(403, "Acceso denegado")
    from app.models.project import Project, ProjectPhase
    from app.models.task import Task, TaskStatus, TaskPriority
    from app.models.resources import Deliverable

    t = db.query(ProjectTemplate).options(
        joinedload(ProjectTemplate.phases).joinedload(TemplatePhase.tasks),
        joinedload(ProjectTemplate.risks), joinedload(ProjectTemplate.deliverables),
    ).filter(ProjectTemplate.id == template_id).first()
    if not t: raise HTTPException(404, "Plantilla no encontrada")

    project = db.query(Project).filter(Project.id == project_id).first()
    if not project: raise HTTPException(404, "Proyecto no encontrado")

    from datetime import datetime, timedelta
    base_date = datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else date.today()

    created_phases = 0; created_tasks = 0; created_risks = 0; created_deliverables = 0

    try:
        for ph in sorted(t.phases, key=lambda x: x.order):
            phase = ProjectPhase(project_id=project_id, name=ph.name, description=ph.description, order=ph.order, budget_hours=ph.estimated_hours)
            db.add(phase); db.flush()
            created_phases += 1
            for tk in sorted(ph.tasks, key=lambda x: x.order):
                task = Task(project_id=project_id, phase_id=phase.id, title=tk.title, description=tk.description, estimated_hours=tk.estimated_hours, status=TaskStatus.todo, priority=TaskPriority.medium)
                db.add(task); created_tasks += 1

        for i, r in enumerate(t.risks):
            from app.models.pipeline import Risk as RiskModel
            risk = RiskModel(project_id=project_id, code=f"RSK-{i+1:03d}", title=r.title, category=r.category, probability=r.probability, impact=r.impact, mitigation_plan=r.mitigation_plan, identified_by=current_user.id)
            db.add(risk); created_risks += 1

        for i, d in enumerate(t.deliverables):
            planned = None
            if d.week_offset is not None:
                planned = base_date + timedelta(weeks=d.week_offset)
            deliverable = Deliverable(project_id=project_id, code=f"DEL-{i+1:03d}", name=d.name, format=d.format, billing_pct=d.billing_pct, planned_date=planned)
            db.add(deliverable); created_deliverables += 1

        db.commit()
        return {"message": f"Plantilla aplicada: {created_phases} fases, {created_tasks} tareas, {created_risks} riesgos, {created_deliverables} entregables"}
    except Exception:
        db.rollback()
        raise
