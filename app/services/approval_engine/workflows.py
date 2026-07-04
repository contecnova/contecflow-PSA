"""approval_engine.workflows — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalStep
from fastapi import HTTPException


from app.services.approval_engine._base import _WORKFLOW_TEMPLATES, _matches_conditions, _parse_trigger_conditions, find_default_workflow, serialize_workflow

def list_workflow_templates() -> list[dict]:
    return _WORKFLOW_TEMPLATES

def validate_workflow(db: Session, workflow_id: str) -> dict:
    w = get_workflow(db, workflow_id)
    if not w:
        raise HTTPException(404, "Flujo no encontrado")
    issues: list[str] = []
    warnings: list[str] = []
    steps = sorted(w.steps or [], key=lambda s: s.step_order)
    if not steps:
        issues.append("El flujo no tiene pasos.")
    seen_orders = set()
    for s in steps:
        if s.step_order in seen_orders:
            issues.append(f"Paso duplicado con orden {s.step_order}.")
        seen_orders.add(s.step_order)
        if s.approver_type == "role" and not s.approver_role:
            issues.append(f"Paso '{s.name}' requiere approver_role.")
        if s.approver_type == "user" and not s.approver_user_id:
            issues.append(f"Paso '{s.name}' requiere approver_user_id.")
        if s.timeout_hours and s.timeout_hours > 168:
            warnings.append(f"Paso '{s.name}' tiene timeout alto ({s.timeout_hours}h).")

    cond = _parse_trigger_conditions(w.trigger_conditions)
    if cond and not isinstance(cond, dict):
        issues.append("trigger_conditions debe ser un JSON objeto.")
    if isinstance(cond, dict) and cond.get("category") and w.entity_type != "document":
        warnings.append("Se ha definido category en trigger_conditions para una entidad no-document.")

    return {
        "workflow_id": w.id,
        "valid": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
    }

def publish_workflow(db: Session, workflow_id: str) -> ApprovalWorkflow:
    check = validate_workflow(db, workflow_id)
    if not check["valid"]:
        raise HTTPException(422, {"message": "El flujo no es publicable", "issues": check["issues"]})
    w = get_workflow(db, workflow_id)
    if not w:
        raise HTTPException(404, "Flujo no encontrado")
    w.is_active = True
    db.commit()
    db.refresh(w)
    return w

def clone_workflow_as_version(db: Session, workflow_id: str, suffix: Optional[str] = None) -> ApprovalWorkflow:
    # Audit #C8: wraps the workflow + N child steps insertion in a single
    # transaction. Without atomic(), a failure inside the steps loop would
    # leave an orphan workflow with partial steps (no rollback was issued).
    from app.db.transactions import atomic

    w = get_workflow(db, workflow_id)
    if not w:
        raise HTTPException(404, "Flujo no encontrado")
    version_suffix = suffix or datetime.now(timezone.utc).strftime("v%Y%m%d%H%M")
    with atomic(db):
        cloned = ApprovalWorkflow(
            id=str(uuid.uuid4()),
            name=f"{w.name} ({version_suffix})",
            description=w.description,
            entity_type=w.entity_type,
            is_active=False,
            is_default=False,
            trigger_conditions=w.trigger_conditions,
        )
        db.add(cloned)
        db.flush()
        for s in sorted(w.steps or [], key=lambda st: st.step_order):
            db.add(ApprovalStep(
                id=str(uuid.uuid4()),
                workflow_id=cloned.id,
                step_order=s.step_order,
                name=s.name,
                approver_type=s.approver_type,
                approver_role=s.approver_role,
                approver_user_id=s.approver_user_id,
                approver_department=s.approver_department,
                is_optional=s.is_optional,
                timeout_hours=s.timeout_hours,
                on_timeout=s.on_timeout,
                escalate_to_user_id=s.escalate_to_user_id,
            ))
    db.refresh(cloned)
    return cloned

def create_workflow_from_template(db: Session, template_id: str, override_name: Optional[str] = None) -> ApprovalWorkflow:
    # Audit #C8: workflow + steps must succeed atomically.
    from app.db.transactions import atomic

    tpl = next((t for t in _WORKFLOW_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        raise HTTPException(404, "Plantilla no encontrada")
    with atomic(db):
        w = ApprovalWorkflow(
            id=str(uuid.uuid4()),
            name=override_name or tpl["name"],
            description=tpl.get("description"),
            entity_type=tpl["entity_type"],
            is_active=False,
            is_default=False,
            trigger_conditions=json.dumps(tpl.get("trigger_conditions") or {}),
        )
        db.add(w)
        db.flush()
        for s in tpl.get("steps", []):
            db.add(ApprovalStep(id=str(uuid.uuid4()), workflow_id=w.id, **s))
    db.refresh(w)
    return w

def simulate_workflow(db: Session, entity_type: str, context: dict) -> dict:
    """Simulate workflow selection + step route without creating a request."""
    candidates = list_workflows(db, entity_type=entity_type)
    matches = []
    for w in candidates:
        cond = _parse_trigger_conditions(w.trigger_conditions)
        if _matches_conditions(cond, context):
            matches.append(w)
    # Prefer explicit condition matches, then default active flows
    chosen = None
    if matches:
        chosen = sorted(matches, key=lambda w: (not w.is_active, not w.is_default, w.created_at or datetime.now(timezone.utc)))[0]
    else:
        chosen = find_default_workflow(entity_type, db, category=context.get("category"))

    if not chosen:
        return {
            "matched": False,
            "reason": "No hay flujo activo/default que aplique al contexto.",
            "candidates": [],
        }

    steps = sorted(chosen.steps or [], key=lambda s: s.step_order)
    route = []
    total_timeout = 0
    for s in steps:
        resolved = _resolve_step_approver_preview(db, s, context)
        total_timeout += int(s.timeout_hours or 0)
        route.append({
            "step_order": s.step_order,
            "step_name": s.name,
            "approver_type": s.approver_type,
            "resolved_approver": resolved,
            "timeout_hours": s.timeout_hours,
            "on_timeout": s.on_timeout,
            "optional": s.is_optional,
        })

    return {
        "matched": True,
        "workflow": serialize_workflow(chosen, include_steps=False),
        "conditions": _parse_trigger_conditions(chosen.trigger_conditions),
        "estimated_total_timeout_hours": total_timeout,
        "route": route,
        "candidate_count": len(matches),
    }

def find_document_workflow(db: Session, category: str):
    """Convenience wrapper — returns best workflow for a document category or None."""
    return find_default_workflow("document", db, category=category)

def list_workflows(db: Session, entity_type: Optional[str] = None, include_inactive: bool = False):
    q = db.query(ApprovalWorkflow)
    if not include_inactive:
        q = q.filter(ApprovalWorkflow.is_active == True)
    if entity_type:
        q = q.filter(ApprovalWorkflow.entity_type == entity_type)
    return q.order_by(ApprovalWorkflow.entity_type).all()

def create_workflow(db: Session, payload_dict: dict):
    # Audit #61: validate auto_approval_rules JSON-as-Text on write.
    if payload_dict.get("auto_approval_rules"):
        from app.schemas.approvals import validate_auto_approval_rules
        try:
            payload_dict["auto_approval_rules"] = validate_auto_approval_rules(
                payload_dict["auto_approval_rules"]
            )
        except ValueError as exc:
            raise HTTPException(422, f"auto_approval_rules inválido: {exc}") from exc
    if payload_dict.get("is_default"):
        db.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.entity_type == payload_dict["entity_type"]
        ).update({"is_default": False})
    w = ApprovalWorkflow(id=str(uuid.uuid4()), **payload_dict)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w

def get_workflow(db: Session, workflow_id: str, include_inactive: bool = False):
    q = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id)
    if not include_inactive:
        q = q.filter(ApprovalWorkflow.is_active == True)
    return q.first()

def update_workflow(db: Session, workflow_id: str, payload_dict: dict):
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w:
        return None
    # Audit #61: validate auto_approval_rules JSON-as-Text on update too.
    if "auto_approval_rules" in payload_dict and payload_dict["auto_approval_rules"]:
        from app.schemas.approvals import validate_auto_approval_rules
        try:
            payload_dict["auto_approval_rules"] = validate_auto_approval_rules(
                payload_dict["auto_approval_rules"]
            )
        except ValueError as exc:
            raise HTTPException(422, f"auto_approval_rules inválido: {exc}") from exc
    allowed = [
        "name", "description", "is_active", "is_default", "trigger_conditions",
        # audit #61: expose auto_approval_rules on update so it can be edited.
        "auto_approval_rules", "chain_on_approval_workflow_id", "sla_block_on_breach",
    ]
    for k, v in payload_dict.items():
        if k in allowed:
            setattr(w, k, v)
    db.commit()
    return w

def delete_workflow(db: Session, workflow_id: str) -> bool:
    """Soft-delete: marca el workflow como inactivo y rompe encadenamientos.

    Soft en lugar de hard porque ApprovalRequest histórico mantiene FK al
    workflow para auditoría/trazabilidad. Las queries que listan workflows
    activos ya filtran por `is_active=True`.
    """
    w = db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.id == workflow_id,
        ApprovalWorkflow.is_active == True,
    ).first()
    if not w:
        return False
    # Romper encadenamientos a este workflow para que otros workflows no
    # apunten a un workflow inactivo.
    db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.chain_on_approval_workflow_id == workflow_id
    ).update({"chain_on_approval_workflow_id": None}, synchronize_session=False)
    w.is_active = False
    db.commit()
    return True

def add_workflow_step(db: Session, workflow_id: str, payload_dict: dict):
    w = get_workflow(db, workflow_id)
    if not w:
        return None
    s = ApprovalStep(id=str(uuid.uuid4()), workflow_id=workflow_id, **payload_dict)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s

def update_workflow_step(db: Session, workflow_id: str, step_id: str, payload_dict: dict):
    _fk_fields = {"approver_user_id", "escalate_to_user_id"}
    s = db.query(ApprovalStep).filter(
        ApprovalStep.id == step_id, ApprovalStep.workflow_id == workflow_id
    ).first()
    if not s:
        return None
    allowed = ["name", "approver_type", "approver_role", "approver_user_id",
               "is_optional", "timeout_hours", "on_timeout", "step_order", "escalate_to_user_id",
               # v2 enterprise
               "approver_group_id", "parallel_quorum", "required_approvals",
               "step_condition", "requires_attachment", "reminder_hours"]
    for k, v in payload_dict.items():
        if k in allowed:
            setattr(s, k, None if (k in _fk_fields and v == "") else v)
    db.commit()
    return s

def delete_workflow_step(db: Session, workflow_id: str, step_id: str):
    s = db.query(ApprovalStep).filter(
        ApprovalStep.id == step_id, ApprovalStep.workflow_id == workflow_id
    ).first()
    if not s:
        return None
    db.delete(s)
    db.commit()
    return s

def _resolve_step_approver_preview(db: Session, step: ApprovalStep, context: dict) -> Optional[str]:
    if step.approver_type == "user":
        if not step.approver_user_id:
            return None
        u = db.query(User).filter(User.id == step.approver_user_id).first()
        return u.full_name if u else f"user:{step.approver_user_id}"
    if step.approver_type == "role":
        u = db.query(User).filter(User.role == step.approver_role, User.is_active == True).first()
        return u.full_name if u else f"role:{step.approver_role} (sin usuario activo)"
    if step.approver_type == "manager":
        requester_id = context.get("requested_by_user_id")
        if not requester_id:
            return "manager:<requester requerido>"
        req_user = db.query(User).filter(User.id == requester_id).first()
        if not req_user or not req_user.manager_id:
            return "manager:<no asignado>"
        manager = db.query(User).filter(User.id == req_user.manager_id).first()
        return manager.full_name if manager else f"manager:{req_user.manager_id}"
    if step.approver_type == "any_in_department":
        if not step.approver_department:
            return "department:<no definido>"
        u = db.query(User).filter(User.department == step.approver_department, User.is_active == True).first()
        return u.full_name if u else f"department:{step.approver_department} (sin usuario activo)"
    return None
