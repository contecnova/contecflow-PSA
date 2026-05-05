"""
settings — thin router delegating to app.services.settings_service
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_admin_or_hr
from app.core.config import settings as app_settings
from app.models.user import User, UserRole
import app.services.settings_service as _svc
from app.schemas.settings import (
    SettingOut,
    SettingUpdate,
    ProjectTypeIn,
    ProjectTypeOut,
    ProjectStatusIn,
    ProjectStatusOut,
    TaskStatusIn,
    TaskStatusOut,
    DepartmentIn,
    DepartmentOut,
    HolidayIn,
    HolidayOut,
    LogLevelPayload,
)

router = APIRouter()


def require_admin_or_pm(current_user: User = Depends(get_current_user)):
    if current_user.role not in [UserRole.admin, UserRole.pm]:
        raise HTTPException(status_code=403, detail="Acceso denegado")
    return current_user

# ── General settings ──────────────────────────────────────────────────────────

@router.get("/org-defaults", summary="Defaults de organización (moneda, zona horaria, idioma, jornada)")
def get_org_defaults(_: User = Depends(get_current_user)):
    """Returns the system-level organisation defaults (read from env / config)."""
    return {
        "currency": app_settings.DEFAULT_CURRENCY,
        "timezone": app_settings.DEFAULT_TIMEZONE,
        "language": app_settings.DEFAULT_LANGUAGE,
        "working_hours_per_day": app_settings.DEFAULT_WORKING_HOURS_PER_DAY,
        "weekly_capacity_hours": app_settings.DEFAULT_WEEKLY_CAPACITY_HOURS,
        "vacation_days_per_year": app_settings.DEFAULT_VACATION_DAYS_PER_YEAR,
        "tax_rate": app_settings.DEFAULT_TAX_RATE,
    }

@router.get("/general", response_model=List[SettingOut])
def get_general_settings(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _svc.get_general_settings(db)

@router.patch("/general/{key}", response_model=SettingOut)
def update_setting(key: str, payload: SettingUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    return _svc.update_setting(key, payload.value, current_user.organization_id, db)

# ── Project types ─────────────────────────────────────────────────────────────

@router.get("/project-types", response_model=List[ProjectTypeOut])
def get_project_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.get_project_types(db)

@router.post("/project-types", response_model=ProjectTypeOut)
def create_project_type(payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.create_project_type(payload.model_dump(), db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.patch("/project-types/{item_id}", response_model=ProjectTypeOut)
def update_project_type(item_id: str, payload: ProjectTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.update_project_type(item_id, payload.model_dump(), db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

@router.delete("/project-types/{item_id}")
def delete_project_type(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.delete_project_type(item_id, db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

# ── Project statuses ──────────────────────────────────────────────────────────

@router.get("/project-statuses", response_model=List[ProjectStatusOut])
def get_project_statuses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.get_project_statuses(db)

@router.post("/project-statuses", response_model=ProjectStatusOut)
def create_project_status(payload: ProjectStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.create_project_status(payload.model_dump(), db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.patch("/project-statuses/{item_id}", response_model=ProjectStatusOut)
def update_project_status(item_id: str, payload: ProjectStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.update_project_status(item_id, payload.model_dump(), db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

@router.delete("/project-statuses/{item_id}")
def delete_project_status(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.delete_project_status(item_id, db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

# ── Task statuses ─────────────────────────────────────────────────────────────

@router.get("/task-statuses", response_model=List[TaskStatusOut])
def get_task_statuses(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.get_task_statuses(db)

@router.post("/task-statuses", response_model=TaskStatusOut)
def create_task_status(payload: TaskStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.create_task_status(payload.model_dump(), db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.patch("/task-statuses/{item_id}", response_model=TaskStatusOut)
def update_task_status(item_id: str, payload: TaskStatusIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.update_task_status(item_id, payload.model_dump(), db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

@router.delete("/task-statuses/{item_id}")
def delete_task_status(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_pm)):
    try:
        return _svc.delete_task_status(item_id, db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

# ── Departments ───────────────────────────────────────────────────────────────

@router.get("/departments", response_model=List[DepartmentOut])
def get_departments(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.get_departments(db)

@router.post("/departments", response_model=DepartmentOut)
def create_department(payload: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    try:
        return _svc.create_department(payload.model_dump(), db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.patch("/departments/{item_id}", response_model=DepartmentOut)
def update_department(item_id: str, payload: DepartmentIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    try:
        return _svc.update_department(item_id, payload.model_dump(), db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

@router.delete("/departments/{item_id}")
def delete_department(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    try:
        return _svc.delete_department(item_id, db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

# ── Holidays ──────────────────────────────────────────────────────────────────

@router.get("/holidays", response_model=List[HolidayOut])
def get_holidays(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.get_holidays(db)

@router.post("/holidays", response_model=HolidayOut)
def create_holiday(payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    return _svc.create_holiday(payload.model_dump(), db)

@router.patch("/holidays/{item_id}", response_model=HolidayOut)
def update_holiday(item_id: str, payload: HolidayIn, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    try:
        return _svc.update_holiday(item_id, payload.model_dump(), db)
    except ValueError:
        raise HTTPException(404, "No encontrado")

@router.delete("/holidays/{item_id}")
def delete_holiday(item_id: str, db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    try:
        return _svc.delete_holiday(item_id, db)
    except ValueError:
        raise HTTPException(404, "No encontrado")


# ── Log Level (runtime configurable) ─────────────────────────────────────────

VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

@router.get("/log-level", summary="Obtener nivel de log actual")
def get_log_level(_: User = Depends(require_admin)):
    root_level = logging.getLevelName(logging.getLogger().level)
    contecflow_level = logging.getLevelName(logging.getLogger("contecflow").level)
    uvicorn_level = logging.getLevelName(logging.getLogger("uvicorn").level)
    uvicorn_error_level = logging.getLevelName(logging.getLogger("uvicorn.error").level)
    uvicorn_access_level = logging.getLevelName(logging.getLogger("uvicorn.access").level)
    return {
        "root": root_level,
        "contecflow": contecflow_level if contecflow_level != "NOTSET" else root_level,
        "uvicorn": uvicorn_level if uvicorn_level != "NOTSET" else root_level,
        "uvicorn_error": uvicorn_error_level if uvicorn_error_level != "NOTSET" else root_level,
        "uvicorn_access": uvicorn_access_level if uvicorn_access_level != "NOTSET" else root_level,
        "valid_levels": sorted(VALID_LOG_LEVELS),
    }

from app.core.config import settings as app_settings

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
        affected = ["root", "contecflow", "uvicorn", "uvicorn.error", "uvicorn.access"]
        logging.getLogger().setLevel(numeric)
        logging.getLogger("contecflow").setLevel(numeric)
        logging.getLogger("uvicorn").setLevel(numeric)
        logging.getLogger("uvicorn.error").setLevel(numeric)
        logging.getLogger("uvicorn.access").setLevel(numeric)
    app_settings.LOG_LEVEL = level_name
    logging.getLogger("contecflow").info(
        f"Log level changed to {level_name} for logger '{payload.logger or 'root'}'"
    )
    return {
        "ok": True,
        "logger": payload.logger or "global",
        "level": level_name,
        "affected": affected,
    }
