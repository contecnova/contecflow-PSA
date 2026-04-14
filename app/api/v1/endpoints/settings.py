from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
from datetime import date as date_type
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_admin_or_hr
from app.models.user import User, UserRole
from app.models.settings import (
    AppSetting, CustomProjectType, CustomProjectStatus,
    CustomTaskStatus, Department, Holiday
)
from app.core.config import settings as app_settings

router = APIRouter()

# ── Pydantic schemas ──────────────────────────────────────────────────────────

class SettingOut(BaseModel):
    key: str
    value: Optional[str]
    description: Optional[str]
    model_config = {"from_attributes": True}

class SettingUpdate(BaseModel):
    value: str

class ProjectTypeIn(BaseModel):
    value: str
    label: str
    color: str = "#7a8aaa"
    sort_order: int = 0

class ProjectTypeOut(ProjectTypeIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}

class ProjectStatusIn(BaseModel):
    value: str
    label: str
    color: str = "#7a8aaa"
    is_default: bool = False
    sort_order: int = 0

class ProjectStatusOut(ProjectStatusIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}

class TaskStatusIn(BaseModel):
    value: str
    label: str
    color: str = "#7a8aaa"
    is_default: bool = False
    sort_order: int = 0

class TaskStatusOut(TaskStatusIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}

class DepartmentIn(BaseModel):
    name: str
    description: Optional[str] = None
    manager_id: Optional[str] = None

class DepartmentOut(DepartmentIn):
    id: str
    is_active: bool
    model_config = {"from_attributes": True}

class HolidayIn(BaseModel):
    name: str
    date: date_type
    type: str = "public"
    applies_to: Optional[str] = None

class HolidayOut(HolidayIn):
    id: str
    model_config = {"from_attributes": True}

# ── Helper: check PM or admin ─────────────────────────────────────────────────
def require_admin_or_pm(current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return current_user

# ── General settings ──────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    "company_name": ("Clarive", "Nombre de la empresa"),
    "company_logo_url": ("", "URL del logotipo"),
    "currency": (app_settings.DEFAULT_CURRENCY, "Moneda principal"),
    "timezone": (app_settings.DEFAULT_TIMEZONE, "Zona horaria"),
    "language": (app_settings.DEFAULT_LANGUAGE, "Idioma de la interfaz"),
    "work_hours_per_day": (str(app_settings.DEFAULT_WORKING_HOURS_PER_DAY), "Horas laborales por día"),
    "work_days_per_week": ("5", "Días laborales por semana"),
    "budget_alert_threshold": ("90", "% presupuesto para alertas"),
    "overload_threshold": ("100", "% carga para alerta de sobrecarga"),
}

@router.get("/general", response_model=List[SettingOut])
def get_general_settings(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    # Seed defaults if not exist
    for key, (value, desc) in DEFAULT_SETTINGS.items():
        if not db.query(AppSetting).filter(AppSetting.key == key).first():
            db.add(AppSetting(key=key, value=value, description=desc))
    db.commit()
    return db.query(AppSetting).order_by(AppSetting.key).all()

@router.patch("/general/{key}", response_model=SettingOut)
def update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    setting = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not setting:
        setting = AppSetting(key=key, value=payload.value)
        db.add(setting)
    else:
        setting.value = payload.value
    db.commit()
    db.refresh(setting)
    return setting

# ── Project types ─────────────────────────────────────────────────────────────

DEFAULT_PROJECT_TYPES = [
    ("development", "Desarrollo", "#00d4ff"),
    ("maintenance", "Mantenimiento", "#ffb800"),
    ("rd", "I+D", "#7c3aed"),
    ("internal", "Interno", "#7a8aaa"),
    ("consulting", "Consultoría", "#00e5a0"),
]

@router.get("/project-types", response_model=List[ProjectTypeOut])
def get_project_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.query(CustomProjectType).count() == 0:
        for i, (value, label, color) in enumerate(DEFAULT_PROJECT_TYPES):
            db.add(CustomProjectType(value=value, label=label, color=color, sort_order=i))
        db.commit()
    return db.query(CustomProjectType).filter(CustomProjectType.is_active == True).order_by(CustomProjectType.sort_order).all()

@router.post("/project-types", response_model=ProjectTypeOut)
def create_project_type(payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    if db.query(CustomProjectType).filter(CustomProjectType.value == payload.value).first():
        raise HTTPException(400, "Ya existe un tipo con ese valor")
    item = CustomProjectType(**payload.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return item

@router.patch("/project-types/{item_id}", response_model=ProjectTypeOut)
def update_project_type(item_id: str, payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    item = db.query(CustomProjectType).filter(CustomProjectType.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@router.delete("/project-types/{item_id}")
def delete_project_type(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    item = db.query(CustomProjectType).filter(CustomProjectType.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    item.is_active = False; db.commit()
    return {"ok": True}

# ── Project statuses ──────────────────────────────────────────────────────────

DEFAULT_PROJECT_STATUSES = [
    ("planning", "Planificación", "#7a8aaa", True),
    ("active", "Activo", "#00d4ff", False),
    ("paused", "Pausado", "#ffb800", False),
    ("closed", "Cerrado", "#00e5a0", False),
    ("cancelled", "Cancelado", "#ff4757", False),
]

@router.get("/project-statuses", response_model=List[ProjectStatusOut])
def get_project_statuses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.query(CustomProjectStatus).count() == 0:
        for i, (value, label, color, is_default) in enumerate(DEFAULT_PROJECT_STATUSES):
            db.add(CustomProjectStatus(value=value, label=label, color=color, is_default=is_default, sort_order=i))
        db.commit()
    return db.query(CustomProjectStatus).filter(CustomProjectStatus.is_active == True).order_by(CustomProjectStatus.sort_order).all()

@router.post("/project-statuses", response_model=ProjectStatusOut)
def create_project_status(payload: ProjectStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    if db.query(CustomProjectStatus).filter(CustomProjectStatus.value == payload.value).first():
        raise HTTPException(400, "Ya existe un estado con ese valor")
    item = CustomProjectStatus(**payload.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item

@router.patch("/project-statuses/{item_id}", response_model=ProjectStatusOut)
def update_project_status(item_id: str, payload: ProjectStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    item = db.query(CustomProjectStatus).filter(CustomProjectStatus.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@router.delete("/project-statuses/{item_id}")
def delete_project_status(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    item = db.query(CustomProjectStatus).filter(CustomProjectStatus.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    item.is_active = False; db.commit(); return {"ok": True}

# ── Task statuses ─────────────────────────────────────────────────────────────

DEFAULT_TASK_STATUSES = [
    ("todo", "Pendiente", "#7a8aaa", True),
    ("in_progress", "En progreso", "#00d4ff", False),
    ("blocked", "Bloqueada", "#ff4757", False),
    ("review", "En revisión", "#ffb800", False),
    ("done", "Completada", "#00e5a0", False),
]

@router.get("/task-statuses", response_model=List[TaskStatusOut])
def get_task_statuses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if db.query(CustomTaskStatus).count() == 0:
        for i, (value, label, color, is_default) in enumerate(DEFAULT_TASK_STATUSES):
            db.add(CustomTaskStatus(value=value, label=label, color=color, is_default=is_default, sort_order=i))
        db.commit()
    return db.query(CustomTaskStatus).filter(CustomTaskStatus.is_active == True).order_by(CustomTaskStatus.sort_order).all()

@router.post("/task-statuses", response_model=TaskStatusOut)
def create_task_status(payload: TaskStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    if db.query(CustomTaskStatus).filter(CustomTaskStatus.value == payload.value).first():
        raise HTTPException(400, "Ya existe un estado con ese valor")
    item = CustomTaskStatus(**payload.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item

@router.patch("/task-statuses/{item_id}", response_model=TaskStatusOut)
def update_task_status(item_id: str, payload: TaskStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    item = db.query(CustomTaskStatus).filter(CustomTaskStatus.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@router.delete("/task-statuses/{item_id}")
def delete_task_status(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    item = db.query(CustomTaskStatus).filter(CustomTaskStatus.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    item.is_active = False; db.commit(); return {"ok": True}

# ── Departments ───────────────────────────────────────────────────────────────

@router.get("/departments", response_model=List[DepartmentOut])
def get_departments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Department).filter(Department.is_active == True).order_by(Department.name).all()

@router.post("/departments", response_model=DepartmentOut)
def create_department(payload: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    if db.query(Department).filter(Department.name == payload.name).first():
        raise HTTPException(400, "Ya existe un departamento con ese nombre")
    item = Department(**payload.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item

@router.patch("/departments/{item_id}", response_model=DepartmentOut)
def update_department(item_id: str, payload: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    item = db.query(Department).filter(Department.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@router.delete("/departments/{item_id}")
def delete_department(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    item = db.query(Department).filter(Department.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    item.is_active = False; db.commit(); return {"ok": True}

# ── Holidays ──────────────────────────────────────────────────────────────────

@router.get("/holidays", response_model=List[HolidayOut])
def get_holidays(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.query(Holiday).order_by(Holiday.date).all()

@router.post("/holidays", response_model=HolidayOut)
def create_holiday(payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    item = Holiday(**payload.model_dump())
    db.add(item); db.commit(); db.refresh(item); return item

@router.patch("/holidays/{item_id}", response_model=HolidayOut)
def update_holiday(item_id: str, payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    item = db.query(Holiday).filter(Holiday.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    for k, v in payload.model_dump().items(): setattr(item, k, v)
    db.commit(); db.refresh(item); return item

@router.delete("/holidays/{item_id}")
def delete_holiday(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    item = db.query(Holiday).filter(Holiday.id == item_id).first()
    if not item: raise HTTPException(404, "No encontrado")
    db.delete(item); db.commit(); return {"ok": True}


# ── Log Level (runtime configurable) ─────────────────────────────────────────

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

@router.get("/log-level", summary="Obtener nivel de log actual")
def get_log_level(_: User = Depends(require_admin)):
    root_level = logging.getLevelName(logging.getLogger().level)
    clarive_level = logging.getLevelName(logging.getLogger("clarive").level)
    uvicorn_level = logging.getLevelName(logging.getLogger("uvicorn").level)
    uvicorn_error_level = logging.getLevelName(logging.getLogger("uvicorn.error").level)
    uvicorn_access_level = logging.getLevelName(logging.getLogger("uvicorn.access").level)
    return {
        "root": root_level,
        "clarive": clarive_level if clarive_level != "NOTSET" else root_level,
        "uvicorn": uvicorn_level if uvicorn_level != "NOTSET" else root_level,
        "uvicorn_error": uvicorn_error_level if uvicorn_error_level != "NOTSET" else root_level,
        "uvicorn_access": uvicorn_access_level if uvicorn_access_level != "NOTSET" else root_level,
        "valid_levels": sorted(VALID_LOG_LEVELS),
    }

class LogLevelPayload(BaseModel):
    level: str
    logger: Optional[str] = None   # None = root; "clarive" | "sqlalchemy" etc.

@router.post("/log-level", summary="Cambiar nivel de log en tiempo real (requiere admin)")
def set_log_level(payload: LogLevelPayload, _: User = Depends(require_admin)):
    level_name = payload.level.upper()
    if level_name not in VALID_LOG_LEVELS:
        raise HTTPException(400, f"Nivel inválido. Use uno de: {', '.join(sorted(VALID_LOG_LEVELS))}")
    numeric = getattr(logging, level_name)

    if payload.logger:
        target_logger = logging.getLogger(payload.logger)
        target_logger.setLevel(numeric)
        affected = [payload.logger]
    else:
        # Apply globally to the server stack so the change is visible immediately.
        affected = ["root", "clarive", "uvicorn", "uvicorn.error", "uvicorn.access"]
        logging.getLogger().setLevel(numeric)
        logging.getLogger("clarive").setLevel(numeric)
        logging.getLogger("uvicorn").setLevel(numeric)
        logging.getLogger("uvicorn.error").setLevel(numeric)
        logging.getLogger("uvicorn.access").setLevel(numeric)

    # Keep effective level visible in-process (useful for diagnostics/endpoints).
    app_settings.LOG_LEVEL = level_name

    logging.getLogger("clarive").info(
        f"Log level changed to {level_name} for logger '{payload.logger or 'root'}'"
    )
    return {
        "ok": True,
        "logger": payload.logger or "global",
        "level": level_name,
        "affected": affected,
    }

