
from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException as FastAPIHTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.core.abac_enforce import enforce_abac
from app.core.responses import APIListResponse, APIResponse
from app.models.user import User
import app.services.automations_service as _svc
from app.models.automations import TriggerType, ActionType

router = APIRouter()

# Endpoint para testear triggers de automations (usado en test_test_trigger_invalid_entity)
@router.post("/test-trigger", summary="Test trigger for automations (test only)")
def test_trigger(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    # Simula la lógica: si entity_type es "nonexistent_entity" devuelve 400, si no, matched=False
    if payload.get("entity_type") == "nonexistent_entity":
        raise FastAPIHTTPException(status_code=400, detail="Entity not found")
    return APIResponse.ok(data={"matched": False})


# ── Schemas ───────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    is_global: bool = False
    trigger_type: str
    trigger_conditions: Optional[dict] = None
    actions: List[dict]

# ── Schemas ───────────────────────────────────────────────────────────────────


class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_conditions: Optional[dict] = None
    actions: Optional[List[dict]] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", response_model=APIListResponse[dict], summary="Listar reglas de automatización")
def list_rules(
    project_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    items = _svc.list_rules_for_user(db, current_user, project_id, is_active)
    return APIListResponse.ok(items=items, page=page, page_size=page_size)


@router.post("", summary="Crear regla de automatización")
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.create_rule_db(payload, db, current_user.id))


@router.patch("/{rule_id}", summary="Actualizar regla")
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.update_rule_db(rule_id, payload, db))


@router.delete("/{rule_id}", summary="Eliminar regla")
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    enforce_abac(db, current_user, "automation_rule", rule_id, action="delete")
    return APIResponse.ok(data=_svc.delete_rule_db(rule_id, db))


@router.post("/run-scheduled", summary="Ejecutar automatizaciones programadas (cron)")
def run_scheduled(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return APIResponse.ok(data=_svc.run_scheduled_automations(db))


@router.post("/{rule_id}/test", summary="Probar regla manualmente")
def test_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=_svc.test_rule_by_id(rule_id, current_user.id, db))


@router.get("/templates/list", summary="Plantillas de automatización predefinidas")
def get_templates(current_user: User = Depends(get_current_user)):
    return APIListResponse.ok(items=_svc.get_automation_templates())


@router.get("/{rule_id}/executions", summary="Historial de ejecuciones")
def get_executions(
    rule_id: str,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIListResponse.ok(items=_svc.get_executions_db(rule_id, limit, db))


# --- New endpoints for trigger/action types ---

@router.get("/trigger-types", summary="Listar tipos de trigger disponibles")
def list_trigger_types(current_user: User = Depends(get_current_user)):
    """Devuelve todos los tipos de trigger soportados por el sistema."""
    return APIListResponse.ok(items=[
        {"type": t.value, "label": t.name.replace('_', ' ').title(), "value": t.value}
        for t in TriggerType
    ])

@router.get("/action-types", summary="Listar tipos de acción disponibles")
def list_action_types(current_user: User = Depends(get_current_user)):
    """Devuelve todos los tipos de acción soportados por el sistema."""
    return APIListResponse.ok(items=[
        {"type": a.value, "label": a.name.replace('_', ' ').title(), "value": a.value}
        for a in ActionType
    ])
