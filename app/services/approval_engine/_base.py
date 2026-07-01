"""approval_engine._base — extracted from the former 1827-LOC god-file."""

from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session, joinedload
from app.models.user import User
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalGroup


logger = logging.getLogger(__name__)

_FINANCIAL_ENTITY_TYPES = {
    "timesheet", "expense", "milestone", "purchase", "invoice",
    "contract", "budget", "leave", "deliverable", "proposal",
    "subcontractor", "scope_change", "hire", "price_change",
}

_WORKFLOW_TEMPLATES = [
    {
        "id": "legal_strict_v1",
        "name": "Legal - Strict Review",
        "description": "Aprobacion legal multi-nivel para documentos sensibles.",
        "entity_type": "document",
        "trigger_conditions": {"category": "legal", "amount_gt": 0},
        "steps": [
            {"step_order": 1, "name": "Legal Lead", "approver_type": "role", "approver_role": "pm", "timeout_hours": 48, "on_timeout": "escalate"},
            {"step_order": 2, "name": "Finance Review", "approver_type": "role", "approver_role": "admin", "timeout_hours": 48, "on_timeout": "escalate"},
        ],
    },
    {
        "id": "engineering_delivery_v1",
        "name": "Engineering Deliverable",
        "description": "Flujo para entregables de ingenieria con validacion tecnica y de negocio.",
        "entity_type": "document",
        "trigger_conditions": {"category": "deliverable"},
        "steps": [
            {"step_order": 1, "name": "Team Lead", "approver_type": "role", "approver_role": "team_lead", "timeout_hours": 36, "on_timeout": "escalate"},
            {"step_order": 2, "name": "Project Manager", "approver_type": "role", "approver_role": "pm", "timeout_hours": 36, "on_timeout": "escalate"},
        ],
    },
    {
        "id": "expense_high_amount_v1",
        "name": "Expense - High Amount",
        "description": "Aprobacion escalonada para gastos altos.",
        "entity_type": "expense",
        "trigger_conditions": {"amount_gt": 1000},
        "steps": [
            {"step_order": 1, "name": "Direct Manager", "approver_type": "manager", "timeout_hours": 24, "on_timeout": "escalate"},
            {"step_order": 2, "name": "Finance", "approver_type": "role", "approver_role": "admin", "timeout_hours": 24, "on_timeout": "escalate"},
        ],
    },
]

def scope_request_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(ApprovalRequest.requested_by.in_(org_user_ids))

def log_financial_approval_event(
    db: Session,
    request_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    actor_user_id: Optional[str],
    step_order: Optional[int] = None,
    decision: Optional[str] = None,
    note: Optional[str] = None,
    metadata_: Optional[str] = None,
) -> None:
    if entity_type not in _FINANCIAL_ENTITY_TYPES:
        return
    db.add(FinancialApprovalAuditLog(
        id=str(uuid.uuid4()),
        request_id=request_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        decision=decision,
        actor_user_id=actor_user_id,
        step_order=step_order,
        note=note,
        metadata_=metadata_,
    ))

def notify_approver(
    request,
    step,
    db: Session,
    explicit_user_id: Optional[str] = None,
) -> None:
    """Create an in-app notification for the current step's approver."""
    try:
        from app.models.enterprise import Notification, NotificationType
        approver_id = explicit_user_id
        if not approver_id:
            if step.approver_type == "user" and step.approver_user_id:
                approver_id = step.approver_user_id
            elif step.approver_type == "role" and step.approver_role:
                approver = db.query(User).filter(
                    User.role == step.approver_role, User.is_active == True
                ).first()
                if approver:
                    approver_id = approver.id

        if approver_id:
            db.add(Notification(
                id=str(uuid.uuid4()),
                user_id=approver_id,
                type=NotificationType.system,
                title=f"Aprobación requerida: {request.entity_type}",
                body=(
                    f"{request.entity_summary or request.entity_id} — "
                    f"Paso {step.step_order}: {step.name}"
                ),
                resource="approval_request",
                resource_id=request.id,
            ))
    except Exception:
        logger.warning("Failed to create approval notification", exc_info=True)

def find_default_workflow(entity_type: str, db: Session, category: Optional[str] = None):
    """Find the best-matching workflow for an entity type.

    For documents, first tries a category-specific workflow (trigger_conditions contains
    the category key), then falls back to the generic document default.
    """
    if entity_type == "document" and category:
        # Look for workflows whose trigger_conditions specify this category
        candidates = db.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.entity_type == "document",
            ApprovalWorkflow.is_active == True,
        ).all()
        for wf in sorted(candidates, key=lambda w: (not w.is_default)):
            try:
                conditions = json.loads(wf.trigger_conditions or "{}")
            # intentional: best-effort fallback, log noise outweighs diagnostic value
            except (ValueError, TypeError):
                conditions = {}
            if conditions.get("category") == category:
                return wf

    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default == True,
        ApprovalWorkflow.is_active == True,
    ).first()

def _is_authorized(step, current_user: User, requested_by: str, db: Session) -> bool:
    # Group authorisation
    if step.approver_group_id:
        group = db.query(ApprovalGroup).filter(ApprovalGroup.id == step.approver_group_id).first()
        if group:
            try:
                members = json.loads(group.member_ids or "[]")
                if current_user.id in members:
                    return True
            except Exception:
                logger.warning("Failed to parse approval group member_ids for group=%s", group.id, exc_info=True)
    if step.approver_type == "group" and step.approver_group_id:
        return False  # already checked above
    # Solo autoriza si el usuario está explícitamente configurado como aprobador
    if step.approver_type == "user" and step.approver_user_id == current_user.id:
        return True
    if step.approver_type == "role" and current_user.role == step.approver_role:
        return True
    if step.approver_type == "manager":
        requester = db.query(User).filter(User.id == requested_by).first()
        if requester and requester.manager_id == current_user.id:
            return True
    if step.approver_type == "any_in_department":
        if current_user.department == step.approver_department:
            return True
    # No bypass para admin: debe estar configurado explícitamente
    return False

def _parse_trigger_conditions(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        logger.warning("Failed to parse approval trigger conditions JSON", exc_info=True)
        return {}

def _matches_conditions(conditions: dict, context: dict) -> bool:
    if not conditions:
        return True
    category = context.get("category")
    department = context.get("department")
    amount = context.get("amount")

    if conditions.get("category") and category != conditions.get("category"):
        return False
    if conditions.get("department") and department != conditions.get("department"):
        return False
    try:
        if conditions.get("amount_gt") is not None and float(amount or 0) <= float(conditions["amount_gt"]):
            return False
        if conditions.get("amount_gte") is not None and float(amount or 0) < float(conditions["amount_gte"]):
            return False
        if conditions.get("amount_lt") is not None and float(amount or 0) >= float(conditions["amount_lt"]):
            return False
        if conditions.get("amount_lte") is not None and float(amount or 0) > float(conditions["amount_lte"]):
            return False
    except Exception:
        logger.warning("Failed to evaluate amount conditions for approval (amount=%r)", amount, exc_info=True)
        return False
    return True

def serialize_step(s) -> dict:
    return {
        "id": s.id, "step_order": s.step_order, "name": s.name,
        "approver_type": s.approver_type, "approver_role": s.approver_role,
        "approver_user_id": s.approver_user_id,
        "approver_user_name": s.approver.full_name if s.approver else None,
        "approver_group_id": getattr(s, "approver_group_id", None),
        "is_optional": s.is_optional, "timeout_hours": s.timeout_hours,
        "on_timeout": s.on_timeout,
        # v2 enterprise
        "parallel_quorum": getattr(s, "parallel_quorum", False),
        "required_approvals": getattr(s, "required_approvals", 1),
        "step_condition": getattr(s, "step_condition", None),
        "requires_attachment": getattr(s, "requires_attachment", False),
        "reminder_hours": getattr(s, "reminder_hours", None),
    }

def serialize_workflow(w, include_steps: bool = False) -> dict:
    d = {
        "id": w.id, "name": w.name, "description": w.description,
        "entity_type": w.entity_type, "is_active": w.is_active,
        "is_default": w.is_default,
        "trigger_conditions": w.trigger_conditions,
        "step_count": len(w.steps or []),
        "created_at": str(w.created_at)[:10] if w.created_at else None,
        # v2 enterprise
        "chain_on_approval_workflow_id": getattr(w, "chain_on_approval_workflow_id", None),
        "sla_block_on_breach": getattr(w, "sla_block_on_breach", False),
        "auto_approval_rules": getattr(w, "auto_approval_rules", None),
    }
    if include_steps:
        d["steps"] = [serialize_step(s) for s in (w.steps or [])]
    return d

def serialize_approval_request(r) -> dict:
    return {
        "id": r.id, "workflow_id": r.workflow_id,
        "entity_type": r.entity_type, "entity_id": r.entity_id,
        "entity_summary": r.entity_summary,
        "requested_by": r.requested_by,
        "requester_name": r.requester.full_name if r.requester else None,
        "current_step": r.current_step,
        "status": r.status,
        "final_decision": r.final_decision,
        "final_note": r.final_note,
        "completed_at": str(r.completed_at)[:16] if r.completed_at else None,
        "created_at": str(r.created_at)[:16] if r.created_at else None,
        "decisions": [
            {
                "step_order": d.step_order,
                "approver_id": d.approver_id,
                "approver_name": d.approver.full_name if d.approver else None,
                "decision": d.decision,
                "note": d.note,
                "attachment_url": getattr(d, "attachment_url", None),
                "decided_at": str(d.decided_at)[:16] if d.decided_at else None,
            }
            for d in (r.decisions or [])
        ],
        "escalated": getattr(r, "escalated", False),
        "auto_approved": getattr(r, "auto_approved", False),
        "rejected": getattr(r, "rejected", False),
    }

def _load_workflows_by_ids(db: Session, workflow_ids: list) -> dict:
    if not workflow_ids:
        return {}
    return {
        w.id: w
        for w in db.query(ApprovalWorkflow).options(joinedload(ApprovalWorkflow.steps)).filter(
            ApprovalWorkflow.id.in_(workflow_ids)
        ).all()
    }

def _record_sod_violation(req, current_user: User, db: Session) -> None:
    try:
        from app.services.grc_sod import record_sod_violation
        from app.models.billing_reports import SodRule
        matching = db.query(SodRule).filter(
            SodRule.module_a == req.entity_type,
            SodRule.action_a == "crear",
            SodRule.module_b == req.entity_type,
            SodRule.action_b == "aprobar",
            SodRule.is_active == True,
        ).first()
        if matching:
            record_sod_violation(
                db=db,
                rule_id=matching.id,
                user_id=current_user.id,
                role=str(current_user.role),
                context_type="approval_request",
                context_id=req.id,
            )
            db.flush()
    except Exception:
        logger.warning("Failed to record SoD violation for approval request=%s user=%s", req.id, current_user.id, exc_info=True)

def _notify_requester_approved(req, db: Session) -> None:
    try:
        from app.models.enterprise import Notification, NotificationType
        db.add(Notification(
            id=str(uuid.uuid4()),
            user_id=req.requested_by,
            type=NotificationType.system,
            title="Solicitud aprobada",
            body=f"{req.entity_summary or req.entity_id} ha sido aprobada",
            resource="approval_request",
            resource_id=req.id,
        ))
        db.commit()
    except Exception:
        logger.warning("Failed to notify requester of approved request=%s", req.id, exc_info=True)

def _apply_entity_final_decision(req, final_decision: str, actor, db: Session) -> None:
    """Propagate the final approval decision back to the source entity.

    Currently handles:
      - entity_type == "document": updates Document.approval_status, approved_by, approved_at
    """
    if req.entity_type != "document":
        return
    try:
        from app.models.documents import Document, ApprovalStatus
        doc = db.query(Document).filter(Document.id == req.entity_id).first()
        if not doc:
            return
        if final_decision == "approved":
            doc.approval_status = ApprovalStatus.approved
            doc.approved_by = actor.id
            doc.approved_at = datetime.now(timezone.utc)
        elif final_decision == "rejected":
            doc.approval_status = ApprovalStatus.rejected
        db.add(doc)
        db.commit()
    except Exception:
        logger.warning("_apply_entity_final_decision failed for document %s", req.entity_id, exc_info=True)
