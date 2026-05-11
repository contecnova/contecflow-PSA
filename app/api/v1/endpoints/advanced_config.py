from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_admin_or_hr
from app.core.abac_enforce import enforce_abac
from app.models.user import User
from app.core.config import settings
import app.services.advanced_config_service as _svc

router = APIRouter()

DEFAULT_MODULES = _svc.DEFAULT_MODULES


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
    return _svc.list_roles(db)

@router.post("/roles", summary="Crear rol personalizado")
def create_role(payload: CustomRoleIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.create_role(payload.model_dump(), db)

@router.patch("/roles/{role_id}", summary="Actualizar rol")
def update_role(role_id: str, payload: CustomRoleUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_role(role_id, payload.model_dump(exclude_unset=True), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.delete("/roles/{role_id}", summary="Eliminar rol")
def delete_role(role_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "custom_role", role_id, action="delete")
    try:
        return _svc.delete_role(role_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.get("/modules", summary="Lista de módulos disponibles")
def get_modules(_: User = Depends(get_current_user)):
    return [{"id": m, "label": m.replace("_", " ").title()} for m in DEFAULT_MODULES]


# ── Task types ────────────────────────────────────────────────────────────────

@router.get("/task-types", summary="Tipos de tarea")
def get_task_types(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.list_task_types(db)

@router.post("/task-types", summary="Crear tipo de tarea")
def create_task_type(payload: TaskTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.create_task_type(payload.model_dump(), db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.patch("/task-types/{type_id}", summary="Actualizar tipo de tarea")
def update_task_type(type_id: str, payload: TaskTypeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_task_type(type_id, payload.model_dump(), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.delete("/task-types/{type_id}", summary="Eliminar tipo de tarea")
def delete_task_type(type_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "task_type", type_id, action="delete")
    try:
        return _svc.delete_task_type(type_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))


# ── Alert configs ─────────────────────────────────────────────────────────────

@router.get("/alert-configs", summary="Configuración de alertas")
def get_alert_configs(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.list_alert_configs(db)

@router.patch("/alert-configs/{alert_type}", summary="Actualizar configuración de alerta")
def update_alert_config(alert_type: str, payload: AlertConfigUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_alert_config(alert_type, payload.model_dump(exclude_unset=True), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))


# ── Rate tables ───────────────────────────────────────────────────────────────

@router.get("/rate-tables", summary="Tablas de tarifas")
def get_rate_tables(db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    return _svc.list_rate_tables(db)

@router.post("/rate-tables", summary="Crear tabla de tarifas")
def create_rate_table(payload: RateTableIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.create_rate_table(payload.model_dump(), db)

@router.post("/rate-tables/{table_id}/entries", summary="Añadir tarifa")
def add_rate_entry(table_id: str, payload: RateEntryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.add_rate_entry(table_id, payload.model_dump(), db)

@router.patch("/rate-tables/{table_id}/entries/{entry_id}", summary="Actualizar tarifa")
def update_rate_entry(table_id: str, entry_id: str, payload: RateEntryIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_rate_entry(table_id, entry_id, payload.model_dump(), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.delete("/rate-tables/{table_id}/entries/{entry_id}", summary="Eliminar tarifa")
def delete_rate_entry(table_id: str, entry_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "rate_entry", entry_id, action="delete")
    try:
        return _svc.delete_rate_entry(table_id, entry_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.delete("/rate-tables/{table_id}", summary="Eliminar tabla de tarifas")
def delete_rate_table(table_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "rate_table", table_id, action="delete")
    try:
        return _svc.delete_rate_table(table_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))


# ── Vacation policies ─────────────────────────────────────────────────────────

@router.get("/vacation-policies", summary="Políticas de vacaciones")
def get_vacation_policies(db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    return _svc.list_vacation_policies(db)

@router.post("/vacation-policies", summary="Crear política de vacaciones")
def create_vacation_policy(payload: VacationPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.create_vacation_policy(payload.model_dump(), db)

@router.patch("/vacation-policies/{policy_id}", summary="Actualizar política")
def update_vacation_policy(policy_id: str, payload: VacationPolicyIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_vacation_policy(policy_id, payload.model_dump(), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.delete("/vacation-policies/{policy_id}", summary="Eliminar política")
def delete_vacation_policy(policy_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "vacation_policy", policy_id, action="delete")
    try:
        return _svc.delete_vacation_policy(policy_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.get("/vacation-balances", summary="Saldos de vacaciones del equipo")
def get_vacation_balances(year: int = Query(default=None), db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    return _svc.get_vacation_balances(year, db)

@router.patch("/vacation-balances/{user_id}", summary="Actualizar saldo de vacaciones")
def update_vacation_balance_endpoint(user_id: str, year: int = Query(...), days_entitled: float = Query(...), db: Session = Depends(get_db), _: User = Depends(require_admin_or_hr)):
    return _svc.update_vacation_balance(user_id, year, days_entitled, db)


# ── Offices ───────────────────────────────────────────────────────────────────

@router.get("/offices", summary="Sedes / oficinas")
def get_offices(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.list_offices(db)

@router.post("/offices", summary="Crear sede")
def create_office(payload: OfficeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.create_office(payload.model_dump(), db)

@router.patch("/offices/{office_id}", summary="Actualizar sede")
def update_office(office_id: str, payload: OfficeIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_office(office_id, payload.model_dump(), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.delete("/offices/{office_id}", summary="Eliminar sede")
def delete_office(office_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "office", office_id, action="delete")
    try:
        return _svc.delete_office(office_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))


# ── Numbering sequences ───────────────────────────────────────────────────────

@router.get("/numbering", summary="Secuencias de numeración")
def get_numbering(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.list_numbering(db)

@router.patch("/numbering/{entity}", summary="Actualizar numeración")
def update_numbering(entity: str, payload: NumberingIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    return _svc.update_numbering_seq(entity, payload.model_dump(), db)

@router.post("/numbering/{entity}/reset", summary="Resetear contador")
def reset_numbering(entity: str, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.reset_numbering_seq(entity, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))


# ── Custom fields ─────────────────────────────────────────────────────────────

@router.get("/custom-fields", summary="Campos personalizados")
def get_custom_fields(entity: Optional[str] = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.list_custom_fields(entity, db)

@router.post("/custom-fields", summary="Crear campo personalizado")
def create_custom_field(payload: CustomFieldIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.create_custom_field(payload.model_dump(), db)
    except ValueError as e:
        raise HTTPException(400, str(e))

@router.patch("/custom-fields/{field_id}", summary="Actualizar campo")
def update_custom_field(field_id: str, payload: CustomFieldIn, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    try:
        return _svc.update_custom_field(field_id, payload.model_dump(), db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.delete("/custom-fields/{field_id}", summary="Eliminar campo")
def delete_custom_field(field_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "custom_field", field_id, action="delete")
    try:
        return _svc.delete_custom_field(field_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.get("/custom-fields/values/{entity_id}", summary="Valores de campos personalizados")
def get_field_values(entity_id: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.get_custom_field_values(entity_id, db)

@router.post("/custom-fields/values/{entity_id}", summary="Guardar valores de campos")
def save_field_values(entity_id: str, values: dict, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.save_custom_field_values(entity_id, values, db)


# ── Project templates ─────────────────────────────────────────────────────────

@router.get("/templates", summary="Plantillas de proyecto")
def get_templates(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return _svc.list_templates(db)

@router.post("/templates", summary="Crear plantilla")
def create_template(payload: TemplateIn, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _svc.create_template(
        payload.model_dump(),
        str(current_user.id),
        current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        db,
    )

@router.delete("/templates/{template_id}", summary="Eliminar plantilla")
def delete_template(template_id: str, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    enforce_abac(db, user, "project_template", template_id, action="delete")
    try:
        return _svc.delete_template(template_id, db)
    except _svc.NotFoundError as e:
        raise HTTPException(404, str(e))

@router.post("/templates/{template_id}/apply/{project_id}", summary="Aplicar plantilla a proyecto")
def apply_template(template_id: str, project_id: str, start_date: Optional[str] = None,
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return _svc.apply_template_to_project(
        template_id, project_id, start_date, str(current_user.id),
        current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role),
        db,
    )
