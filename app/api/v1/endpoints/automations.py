"""
Automation rules router — thin delegate to automations_service.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
import app.services.automations_service as _svc

router = APIRouter()


# ── Schemas ───────────────────────────────────────────────────────────────────

class RuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    project_id: Optional[str] = None
    is_global: bool = False
    trigger_type: str
    trigger_conditions: Optional[dict] = None
    actions: List[dict]

class RuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None
    trigger_type: Optional[str] = None
    trigger_conditions: Optional[dict] = None
    actions: Optional[List[dict]] = None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("", summary="Listar reglas de automatización")
def list_rules(
    project_id: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.list_rules_for_user(db, current_user, project_id, is_active)


@router.post("", summary="Crear regla de automatización")
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.create_rule_db(payload, db, current_user.id)


@router.patch("/{rule_id}", summary="Actualizar regla")
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.update_rule_db(rule_id, payload, db)


@router.delete("/{rule_id}", summary="Eliminar regla")
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.delete_rule_db(rule_id, db)


@router.post("/run-scheduled", summary="Ejecutar automatizaciones programadas (cron)")
def run_scheduled(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return _svc.run_scheduled_automations(db)


@router.post("/{rule_id}/test", summary="Probar regla manualmente")
def test_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.test_rule_by_id(rule_id, current_user.id, db)


@router.get("/templates/list", summary="Plantillas de automatización predefinidas")
def get_templates(current_user: User = Depends(get_current_user)):
    return _svc.get_automation_templates()


@router.get("/{rule_id}/executions", summary="Historial de ejecuciones")
def get_executions(
    rule_id: str,
    limit: int = Query(20, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return _svc.get_executions_db(rule_id, limit, db)
