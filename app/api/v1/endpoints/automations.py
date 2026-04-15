"""
Automation rules router — thin delegate to automations_service.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from typing import Optional, List
from pydantic import BaseModel
import json

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User
from app.models.automations import AutomationRule, AutomationExecution
from app.models.project import Project
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
    q = db.query(AutomationRule).options(joinedload(AutomationRule.project))
    if not current_user.is_superadmin and current_user.organization_id:
        org_user_ids = db.query(User.id).filter(
            User.organization_id == current_user.organization_id
        ).scalar_subquery()
        org_project_ids = db.query(Project.id).filter(
            Project.organization_id == current_user.organization_id
        ).scalar_subquery()
        q = q.filter(
            or_(
                AutomationRule.project_id.in_(org_project_ids),
                AutomationRule.created_by.in_(org_user_ids),
            )
        )
    if project_id:
        q = q.filter((AutomationRule.project_id == project_id) | (AutomationRule.is_global == True))
    if is_active is not None:
        q = q.filter(AutomationRule.is_active == is_active)
    return [_svc.serialize_rule(r) for r in q.order_by(AutomationRule.created_at.desc()).all()]


@router.post("", summary="Crear regla de automatización")
def create_rule(
    payload: RuleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    rule = AutomationRule(
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id,
        is_global=payload.is_global,
        trigger_type=payload.trigger_type,
        trigger_conditions=json.dumps(payload.trigger_conditions) if payload.trigger_conditions else None,
        actions=json.dumps(payload.actions),
        created_by=current_user.id,
    )
    db.add(rule); db.commit(); db.refresh(rule)
    rule = db.query(AutomationRule).options(joinedload(AutomationRule.project)).filter(AutomationRule.id == rule.id).first()
    return _svc.serialize_rule(rule)


@router.patch("/{rule_id}", summary="Actualizar regla")
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404, "Regla no encontrada")
    data = payload.model_dump(exclude_unset=True)
    if "trigger_conditions" in data:
        data["trigger_conditions"] = json.dumps(data["trigger_conditions"]) if data["trigger_conditions"] else None
    if "actions" in data:
        data["actions"] = json.dumps(data["actions"])
    for k, v in data.items():
        setattr(rule, k, v)
    db.commit()
    rule = db.query(AutomationRule).options(joinedload(AutomationRule.project)).filter(AutomationRule.id == rule_id).first()
    return _svc.serialize_rule(rule)


@router.delete("/{rule_id}", summary="Eliminar regla")
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    db.delete(rule); db.commit()
    return {"ok": True}


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
    rule = db.query(AutomationRule).filter(AutomationRule.id == rule_id).first()
    if not rule:
        raise HTTPException(404)
    return _svc.test_automation_rule(rule, current_user.id, db)


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
    executions = db.query(AutomationExecution).filter(
        AutomationExecution.rule_id == rule_id
    ).order_by(AutomationExecution.executed_at.desc()).limit(limit).all()
    return [{
        "id": e.id,
        "trigger_context": json.loads(e.trigger_context) if e.trigger_context else None,
        "actions_taken": json.loads(e.actions_taken) if e.actions_taken else None,
        "success": e.success,
        "error": e.error,
        "executed_at": str(e.executed_at)[:16],
    } for e in executions]
