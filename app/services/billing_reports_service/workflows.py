"""Flujos de automatizacion: alta, edicion, listado y serializacion.

Parte de `app.services.billing_reports_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.billing_reports import AutomationWorkflow, WorkflowStep, WorkflowStatus
from app.core.asignacion import es_asignable
from app.core.errores import ErrorDeDominio


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def create_workflow(payload, current_user: User, db: Session) -> dict:
    wf = AutomationWorkflow(
        name=payload.name, description=payload.description,
        project_id=payload.project_id, is_global=payload.is_global,
        trigger_type=payload.trigger_type,
        trigger_conditions=json.dumps(payload.trigger_conditions) if payload.trigger_conditions else None,
        status=WorkflowStatus.draft,
        created_by=current_user.id,
    )
    db.add(wf)
    db.flush()

    for i, step_data in enumerate(payload.steps):
        step = WorkflowStep(
            workflow_id=wf.id, order=i,
            step_type=step_data.get("step_type", "action"),
            name=step_data.get("name"),
            config=json.dumps(step_data.get("config", {})),
            next_step_yes=step_data.get("next_step_yes"),
            next_step_no=step_data.get("next_step_no"),
        )
        db.add(step)

    db.commit()
    wf = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)
    ).filter(AutomationWorkflow.id == wf.id).first()
    return serialize_workflow(wf)


def update_workflow(wf_id: str, payload: dict, db: Session) -> dict:
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == wf_id).first()
    if not wf:
        raise ErrorDeDominio(404)
    for k, v in payload.items():
        if k == "trigger_conditions" and v is not None:
            v = json.dumps(v)
        if es_asignable(wf, k):
            setattr(wf, k, v)
    if "steps" in payload:
        for s in wf.steps:
            db.delete(s)
        db.flush()
        for i, step_data in enumerate(payload["steps"]):
            step = WorkflowStep(
                workflow_id=wf.id, order=i,
                step_type=step_data.get("step_type", "action"),
                name=step_data.get("name"),
                config=json.dumps(step_data.get("config", {})),
                next_step_yes=step_data.get("next_step_yes"),
                next_step_no=step_data.get("next_step_no"),
            )
            db.add(step)
    db.commit()
    wf = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps), joinedload(AutomationWorkflow.project)
    ).filter(AutomationWorkflow.id == wf_id).first()
    return serialize_workflow(wf)


def list_workflows_all(db: Session) -> list:
    workflows = db.query(AutomationWorkflow).options(
        joinedload(AutomationWorkflow.steps),
        joinedload(AutomationWorkflow.project),
    ).order_by(AutomationWorkflow.created_at.desc()).all()
    return [serialize_workflow(w) for w in workflows]


def delete_workflow(wf_id: str, db: Session) -> dict:
    wf = db.query(AutomationWorkflow).filter(AutomationWorkflow.id == wf_id).first()
    if not wf:
        raise ErrorDeDominio(404)
    db.delete(wf)
    db.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# SERIALIZERS
# ═══════════════════════════════════════════════════════════════════════════════

def serialize_workflow(w: AutomationWorkflow) -> dict:
    return {
        "id": w.id, "name": w.name, "description": w.description,
        "project_id": w.project_id,
        "project_name": w.project.name if w.project else None,
        "is_global": w.is_global, "status": w.status,
        "trigger_type": w.trigger_type,
        "trigger_conditions": json.loads(w.trigger_conditions) if w.trigger_conditions else None,
        "steps": [{
            "id": s.id, "order": s.order, "step_type": s.step_type,
            "name": s.name,
            "config": json.loads(s.config) if s.config else {},
            "next_step_yes": s.next_step_yes,
            "next_step_no": s.next_step_no,
        } for s in w.steps],
        "run_count": w.run_count or 0,
        "success_count": w.success_count or 0,
        "error_count": w.error_count or 0,
        "last_run_at": str(w.last_run_at)[:16] if w.last_run_at else None,
    }
