"""
settings_service — business logic extracted from app/api/v1/endpoints/settings.py
Covers: general settings, project types/statuses, task statuses,
        departments, holidays.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.settings import (
    AppSetting, CustomProjectType, CustomProjectStatus,
    CustomTaskStatus, Department, Holiday,
)
from app.core.config import settings as app_settings


DEFAULT_SETTINGS = {
    "company_name": ("Contecflow", "Nombre de la empresa"),
    "company_logo_url": ("", "URL del logotipo"),
    "currency": (app_settings.DEFAULT_CURRENCY, "Moneda principal"),
    "timezone": (app_settings.DEFAULT_TIMEZONE, "Zona horaria"),
    "language": (app_settings.DEFAULT_LANGUAGE, "Idioma de la interfaz"),
    "work_hours_per_day": (str(app_settings.DEFAULT_WORKING_HOURS_PER_DAY), "Horas laborales por día"),
    "work_days_per_week": ("5", "Días laborales por semana"),
    "budget_alert_threshold": ("90", "% presupuesto para alertas"),
    "overload_threshold": ("100", "% carga para alerta de sobrecarga"),
    "idle_timeout_enabled": ("false", "Cierre de sesión por inactividad (true/false)"),
    "idle_timeout_minutes": ("30", "Minutos de inactividad antes de cerrar sesión"),
}

DEFAULT_PROJECT_TYPES = [
    ("development", "Desarrollo", "#00d4ff"),
    ("maintenance", "Mantenimiento", "#ffb800"),
    ("rd", "I+D", "#7c3aed"),
    ("internal", "Interno", "#7a8aaa"),
    ("consulting", "Consultoría", "#00e5a0"),
]

DEFAULT_PROJECT_STATUSES = [
    ("planning", "Planificación", "#7a8aaa", True),
    ("active", "Activo", "#00d4ff", False),
    ("paused", "Pausado", "#ffb800", False),
    ("closed", "Cerrado", "#00e5a0", False),
    ("cancelled", "Cancelado", "#ff4757", False),
]

DEFAULT_TASK_STATUSES = [
    ("todo", "Pendiente", "#7a8aaa", True),
    ("in_progress", "En progreso", "#00d4ff", False),
    ("blocked", "Bloqueada", "#ff4757", False),
    ("in_review", "En revisión", "#ffb800", False),
    ("done", "Completada", "#00e5a0", False),
]


# ── General settings ──────────────────────────────────────────────────────────

def get_general_settings(db: Session) -> list:
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        exists = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)
        ).first()
        if not exists:
            db.add(AppSetting(key=key, value=value, description=desc, organization_id=None))
    db.commit()
    return db.query(AppSetting).order_by(AppSetting.key).all()


def update_setting(key: str, value: str, org_id: Optional[str], db: Session) -> AppSetting:
    setting = db.query(AppSetting).filter(
        AppSetting.key == key, AppSetting.organization_id == org_id
    ).first() if org_id else None
    if not setting:
        setting = db.query(AppSetting).filter(
            AppSetting.key == key, AppSetting.organization_id.is_(None)
        ).first()
    if not setting:
        setting = AppSetting(key=key, value=value, organization_id=org_id)
        db.add(setting)
    else:
        setting.value = value
    db.commit()
    db.refresh(setting)
    return setting


# ── Project types ─────────────────────────────────────────────────────────────

def get_project_types(db: Session) -> list:
    if db.query(CustomProjectType).count() == 0:
        for i, (value, label, color) in enumerate(DEFAULT_PROJECT_TYPES):
            db.add(CustomProjectType(value=value, label=label, color=color, sort_order=i))
        db.commit()
    return db.query(CustomProjectType).filter(
        CustomProjectType.is_active == True
    ).order_by(CustomProjectType.sort_order).all()


def create_project_type(payload_dict: dict, db: Session) -> CustomProjectType:
    if db.query(CustomProjectType).filter(
        CustomProjectType.value == payload_dict["value"],
        CustomProjectType.is_active == True
    ).first():
        raise ValueError("Ya existe un tipo con ese valor")
    item = CustomProjectType(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_project_type(item_id: str, payload_dict: dict, db: Session) -> CustomProjectType:
    item = db.query(CustomProjectType).filter(CustomProjectType.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_project_type(item_id: str, db: Session) -> dict:
    item = db.query(CustomProjectType).filter(CustomProjectType.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    item.is_active = False
    db.commit()
    return {"ok": True}


# ── Project statuses ──────────────────────────────────────────────────────────

def get_project_statuses(db: Session) -> list:
    if db.query(CustomProjectStatus).count() == 0:
        for i, (value, label, color, is_default) in enumerate(DEFAULT_PROJECT_STATUSES):
            db.add(CustomProjectStatus(value=value, label=label, color=color, is_default=is_default, sort_order=i))
        db.commit()
    return db.query(CustomProjectStatus).filter(
        CustomProjectStatus.is_active == True
    ).order_by(CustomProjectStatus.sort_order).all()


def create_project_status(payload_dict: dict, db: Session) -> CustomProjectStatus:
    if db.query(CustomProjectStatus).filter(
        CustomProjectStatus.value == payload_dict["value"],
        CustomProjectStatus.is_active == True
    ).first():
        raise ValueError("Ya existe un estado con ese valor")
    item = CustomProjectStatus(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_project_status(item_id: str, payload_dict: dict, db: Session) -> CustomProjectStatus:
    item = db.query(CustomProjectStatus).filter(CustomProjectStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_project_status(item_id: str, db: Session) -> dict:
    item = db.query(CustomProjectStatus).filter(CustomProjectStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    item.is_active = False
    db.commit()
    return {"ok": True}


# ── Task statuses ─────────────────────────────────────────────────────────────

def get_task_statuses(db: Session) -> list:
    if db.query(CustomTaskStatus).count() == 0:
        for i, (value, label, color, is_default) in enumerate(DEFAULT_TASK_STATUSES):
            db.add(CustomTaskStatus(value=value, label=label, color=color, is_default=is_default, sort_order=i))
        db.commit()
    return db.query(CustomTaskStatus).filter(
        CustomTaskStatus.is_active == True
    ).order_by(CustomTaskStatus.sort_order).all()


def create_task_status(payload_dict: dict, db: Session) -> CustomTaskStatus:
    if db.query(CustomTaskStatus).filter(
        CustomTaskStatus.value == payload_dict["value"],
        CustomTaskStatus.is_active == True
    ).first():
        raise ValueError("Ya existe un estado con ese valor")
    item = CustomTaskStatus(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_task_status(item_id: str, payload_dict: dict, db: Session) -> CustomTaskStatus:
    item = db.query(CustomTaskStatus).filter(CustomTaskStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_task_status(item_id: str, db: Session) -> dict:
    item = db.query(CustomTaskStatus).filter(CustomTaskStatus.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    item.is_active = False
    db.commit()
    return {"ok": True}


# ── Departments ───────────────────────────────────────────────────────────────

def get_departments(db: Session) -> list:
    return db.query(Department).filter(Department.is_active == True).order_by(Department.name).all()


def create_department(payload_dict: dict, db: Session) -> Department:
    if db.query(Department).filter(
        Department.name == payload_dict["name"],
        Department.is_active == True
    ).first():
        raise ValueError("Ya existe un departamento con ese nombre")
    item = Department(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_department(item_id: str, payload_dict: dict, db: Session) -> Department:
    item = db.query(Department).filter(Department.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_department(item_id: str, db: Session) -> dict:
    item = db.query(Department).filter(Department.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    
    # Check for dependencies (will be automatically SET NULL per FK config)
    dependencies = _check_department_dependencies(item_id, db)
    
    item.is_active = False
    db.commit()
    
    if dependencies:
        return {"ok": True, "warning": "Dependencias limpiadas", "details": dependencies}
    return {"ok": True}


# ── Holidays ──────────────────────────────────────────────────────────────────

def get_holidays(db: Session) -> list:
    return db.query(Holiday).order_by(Holiday.date).all()


def create_holiday(payload_dict: dict, db: Session) -> Holiday:
    item = Holiday(**payload_dict)
    db.add(item); db.commit(); db.refresh(item)
    return item


def update_holiday(item_id: str, payload_dict: dict, db: Session) -> Holiday:
    item = db.query(Holiday).filter(Holiday.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    for k, v in payload_dict.items():
        setattr(item, k, v)
    db.commit(); db.refresh(item)
    return item


def delete_holiday(item_id: str, db: Session) -> dict:
    item = db.query(Holiday).filter(Holiday.id == item_id).first()
    if not item:
        raise ValueError("not_found")
    db.delete(item); db.commit()
    return {"ok": True}


# ── Dependency validation before delete ────────────────────────────────────────

def _check_department_dependencies(department_id: str, db: Session) -> list[str]:
    """Check if department has active dependencies.
    
    Returns list of dependency descriptions if found, empty list otherwise.
    Dependencies are automatically SET NULL per FK config, but we validate
    for informational purposes.
    """
    from app.models.alm import ALMCostCenter, ALMAsset
    
    dependencies = []
    
    # Check Cost Centers with this department
    center_count = db.query(ALMCostCenter).filter(ALMCostCenter.department_id == department_id).count()
    if center_count > 0:
        dependencies.append(f"{center_count} Centro(s) de coste asignado(s)")
    
    # Check Assets with this department
    asset_count = db.query(ALMAsset).filter(ALMAsset.department_id == department_id).count()
    if asset_count > 0:
        dependencies.append(f"{asset_count} Activo(s) asignado(s)")
    
    return dependencies
