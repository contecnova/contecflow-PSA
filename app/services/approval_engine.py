"""
approval_engine.py — Motor de aprobaciones multi-nivel.

Funciones exportadas:
  log_financial_approval_event(...)
  scope_request_query(q, db, current_user)
  find_default_workflow(entity_type, db)
  notify_approver(request, step, db, explicit_user_id=None)
  create_approval_request(payload, db, current_user)
  decide_approval_request(request_id, payload, db, current_user)
  get_pending_for_user(db, current_user)
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.user import User, UserRole
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalRequest, ApprovalWorkflow
from app.models.billing_reports import ApprovalRequest, ApprovalWorkflow, ApprovalDecision
from app.models.billing_reports import ApprovalStep
from app.models.billing_reports import ApprovalRequest, FinancialApprovalAuditLog
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import func

logger = logging.getLogger(__name__)

_FINANCIAL_ENTITY_TYPES = {"timesheet", "expense", "milestone", "purchase", "invoice"}


# ── Audit log ──────────────────────────────────────────────────────────────────

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


# ── Scope / helpers ────────────────────────────────────────────────────────────

def scope_request_query(q, db: Session, current_user: User):
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(ApprovalRequest.requested_by.in_(org_user_ids))


def find_default_workflow(entity_type: str, db: Session):
    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default == True,
        ApprovalWorkflow.is_active == True,
    ).first()


def notify_approver(
    request,
    step,
    db: Session,
    explicit_user_id: Optional[str] = None,
) -> None:
    """Create an in-app notification for the current step's approver."""
    try:
        from app.models.enterprise import Notification
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
                type="approval_required",
                title=f"Aprobación requerida: {request.entity_type}",
                message=(
                    f"{request.entity_summary or request.entity_id} — "
                    f"Paso {step.step_order}: {step.name}"
                ),
                entity_type="approval_request",
                entity_id=request.id,
            ))
    except Exception:
        logger.warning("Failed to create approval notification", exc_info=True)


# ── Create request ─────────────────────────────────────────────────────────────

def create_approval_request(payload, db: Session, current_user: User) -> dict:
    """
    payload must have: workflow_id (optional), entity_type, entity_id, entity_summary (optional)
    Returns serialised ApprovalRequest dict (caller should use _request_out).
    Raises HTTPException if no workflow found.
    """

    wf_id = payload.workflow_id
    if not wf_id:
        wf = find_default_workflow(payload.entity_type, db)
        if not wf:
            raise HTTPException(
                404, f"No hay flujo de aprobación configurado para '{payload.entity_type}'"
            )
        wf_id = wf.id
    else:
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == wf_id).first()
        if not wf:
            raise HTTPException(404, "Flujo no encontrado")

    req = ApprovalRequest(
        id=str(uuid.uuid4()),
        workflow_id=wf_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_summary=payload.entity_summary,
        requested_by=current_user.id,
        current_step=1,
        status="pending",
    )
    db.add(req)
    db.flush()
    log_financial_approval_event(
        db=db,
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action="requested",
        actor_user_id=current_user.id,
        step_order=1,
        note=req.entity_summary,
    )

    first_step = min(wf.steps, key=lambda s: s.step_order, default=None)
    if first_step:
        notify_approver(req, first_step, db)

    db.commit()
    db.refresh(req)
    return req


# ── Decide ─────────────────────────────────────────────────────────────────────

def decide_approval_request(
    request_id: str,
    decision: str,
    note: Optional[str],
    delegate_to: Optional[str],
    db: Session,
    current_user: User,
):
    """
    Apply an approval decision (approved | rejected | delegated).
    Returns the updated ApprovalRequest ORM object.
    Raises HTTPException on validation failures.
    """

    req = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.decisions)
    )
    req = scope_request_query(req, db, current_user).filter(
        ApprovalRequest.id == request_id
    ).first()
    if not req:
        raise HTTPException(404)
    if req.status != "pending":
        raise HTTPException(400, f"La solicitud ya está en estado '{req.status}'")

    wf = db.query(ApprovalWorkflow).options(
        joinedload(ApprovalWorkflow.steps)
    ).filter(ApprovalWorkflow.id == req.workflow_id).first()
    if not wf:
        raise HTTPException(404, "Flujo no encontrado")

    steps = sorted(wf.steps, key=lambda s: s.step_order)
    step = next((s for s in steps if s.step_order == req.current_step), None)
    if not step:
        raise HTTPException(400, "No se encontró el paso actual del flujo de aprobación")

    # Authorisation check
    authorized = _is_authorized(step, current_user, req.requested_by, db)
    if not authorized:
        raise HTTPException(403, "No tienes permiso para aprobar este paso")

    # SoD: requester cannot self-approve
    if req.requested_by == current_user.id:
        _record_sod_violation(req, current_user, db)
        raise HTTPException(
            403,
            "SoD: el solicitante no puede aprobar su propia solicitud "
            "(Segregación de Funciones — crear ≠ aprobar)",
        )

    db.add(ApprovalDecision(
        id=str(uuid.uuid4()),
        request_id=request_id,
        step_order=req.current_step,
        approver_id=current_user.id,
        decision=decision,
        note=note,
    ))
    log_financial_approval_event(
        db=db,
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action=decision,
        decision=decision,
        actor_user_id=current_user.id,
        step_order=req.current_step,
        note=note,
        metadata_=f"delegate_to={delegate_to}" if decision == "delegated" else None,
    )

    if decision == "rejected":
        req.status = "rejected"
        req.final_decision = "rejected"
        req.final_note = note
        req.completed_at = datetime.now(timezone.utc)

    elif decision == "delegated":
        if not delegate_to:
            raise HTTPException(400, "Debes indicar delegate_to para delegar la aprobación")
        req.final_note = f"Delegado a {delegate_to} ({note or 'sin nota'})"
        db.commit()
        notify_approver(
            req,
            next((s for s in steps if s.step_order == req.current_step), None),
            db,
            explicit_user_id=delegate_to,
        )

    elif decision == "approved":
        next_steps = [s for s in steps if s.step_order > req.current_step and not s.is_optional]
        if next_steps:
            req.current_step = next_steps[0].step_order
            db.commit()
            notify_approver(req, next_steps[0], db)
        else:
            req.status = "approved"
            req.final_decision = "approved"
            req.completed_at = datetime.now(timezone.utc)
            db.commit()
            _notify_requester_approved(req, db)

    db.commit()
    db.refresh(req)
    return req


def get_pending_for_user(db: Session, current_user: User) -> list:
    """Return all pending ApprovalRequests where the current user is the step approver."""

    pending_q = db.query(ApprovalRequest).filter(
        ApprovalRequest.status == "pending"
    ).options(
        joinedload(ApprovalRequest.requester),
        joinedload(ApprovalRequest.decisions),
    )
    pending = scope_request_query(pending_q, db, current_user).all()
    if not pending:
        return []

    wf_ids = list({req.workflow_id for req in pending if req.workflow_id})
    workflows = {
        wf.id: wf
        for wf in db.query(ApprovalWorkflow).options(
            joinedload(ApprovalWorkflow.steps)
        ).filter(ApprovalWorkflow.id.in_(wf_ids)).all()
    }

    result = []
    for req in pending:
        wf = workflows.get(req.workflow_id)
        if not wf:
            continue
        step = next((s for s in wf.steps if s.step_order == req.current_step), None)
        if not step:
            continue
        if _is_authorized(step, current_user, req.requested_by, db):
            result.append((req, step))

    return result


# ── Workflow CRUD ──────────────────────────────────────────────────────────────

def list_workflows(db: Session, entity_type: Optional[str] = None):
    q = db.query(ApprovalWorkflow)
    if entity_type:
        q = q.filter(ApprovalWorkflow.entity_type == entity_type)
    return q.order_by(ApprovalWorkflow.entity_type).all()


def create_workflow(db: Session, payload_dict: dict):
    if payload_dict.get("is_default"):
        db.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.entity_type == payload_dict["entity_type"]
        ).update({"is_default": False})
    w = ApprovalWorkflow(id=str(uuid.uuid4()), **payload_dict)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


def get_workflow(db: Session, workflow_id: str):
    return db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()


def update_workflow(db: Session, workflow_id: str, payload_dict: dict):
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w:
        return None
    allowed = ["name", "description", "is_active", "is_default", "trigger_conditions"]
    for k, v in payload_dict.items():
        if k in allowed:
            setattr(w, k, v)
    db.commit()
    return w


def delete_workflow(db: Session, workflow_id: str) -> bool:
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w:
        return False
    db.delete(w)
    db.commit()
    return True


# ── Step CRUD ──────────────────────────────────────────────────────────────────

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
               "is_optional", "timeout_hours", "on_timeout", "step_order", "escalate_to_user_id"]
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


# ── Request queries ────────────────────────────────────────────────────────────

def list_approval_requests(
    db: Session,
    current_user: User,
    status: Optional[str] = None,
    entity_type: Optional[str] = None,
    mine: bool = True,
):
    q = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.requester),
        joinedload(ApprovalRequest.decisions),
    )
    q = scope_request_query(q, db, current_user)
    if status:
        q = q.filter(ApprovalRequest.status == status)
    if entity_type:
        q = q.filter(ApprovalRequest.entity_type == entity_type)
    if mine:
        q = q.filter(ApprovalRequest.requested_by == current_user.id)
    return q.order_by(ApprovalRequest.created_at.desc()).limit(100).all()


def cancel_approval_request(db: Session, request_id: str, current_user: User):
    req = scope_request_query(
        db.query(ApprovalRequest), db, current_user
    ).filter(ApprovalRequest.id == request_id).first()
    if not req:
        raise HTTPException(404)
    if req.requested_by != current_user.id and current_user.role.value not in ("admin", "pm"):
        raise HTTPException(403)
    req.status = "cancelled"
    req.completed_at = datetime.now(timezone.utc)
    log_financial_approval_event(
        db=db,
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action="cancelled",
        actor_user_id=current_user.id,
        step_order=req.current_step,
    )
    db.commit()
    return req


def get_financial_audit_entries(db: Session, request_id: str, current_user: User):
    req = scope_request_query(
        db.query(ApprovalRequest), db, current_user
    ).filter(ApprovalRequest.id == request_id).first()
    if not req:
        return None, None
    entries = (
        db.query(FinancialApprovalAuditLog)
        .filter(FinancialApprovalAuditLog.request_id == request_id)
        .order_by(FinancialApprovalAuditLog.created_at.asc())
        .all()
    )
    return req, entries


def get_approval_stats(db: Session, current_user: User) -> dict:
    q = scope_request_query(db.query(ApprovalRequest), db, current_user)
    total    = q.count()
    pending  = q.filter(ApprovalRequest.status == "pending").count()
    approved = q.filter(ApprovalRequest.status == "approved").count()
    rejected = q.filter(ApprovalRequest.status == "rejected").count()
    by_entity = (
        q.with_entities(ApprovalRequest.entity_type, func.count(ApprovalRequest.id))
        .group_by(ApprovalRequest.entity_type)
        .all()
    )
    return {
        "total": total,
        "pending": pending,
        "approved": approved,
        "rejected": rejected,
        "by_entity_type": {e: c for e, c in by_entity},
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _is_authorized(step, current_user: User, requested_by: str, db: Session) -> bool:
    if step.approver_type == "user" and step.approver_user_id == current_user.id:
        return True
    if step.approver_type == "role" and hasattr(current_user.role, "value"):
        if current_user.role.value == step.approver_role:
            return True
    if step.approver_type == "manager":
        requester = db.query(User).filter(User.id == requested_by).first()
        if requester and requester.manager_id == current_user.id:
            return True
    if step.approver_type == "any_in_department":
        if current_user.department == step.approver_department:
            return True
    return False


def _record_sod_violation(req, current_user: User, db: Session) -> None:
    try:
        from app.api.v1.endpoints.grc import record_sod_violation
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
        pass


def _notify_requester_approved(req, db: Session) -> None:
    try:
        from app.models.enterprise import Notification
        db.add(Notification(
            id=str(uuid.uuid4()),
            user_id=req.requested_by,
            type="approval_completed",
            title="Solicitud aprobada",
            message=f"{req.entity_summary or req.entity_id} ha sido aprobada",
            entity_type="approval_request",
            entity_id=req.id,
        ))
        db.commit()
    except Exception:
        pass


# ── Serialization helpers ───────────────────────────────────────────────────

def serialize_step(s) -> dict:
    return {
        "id": s.id, "step_order": s.step_order, "name": s.name,
        "approver_type": s.approver_type, "approver_role": s.approver_role,
        "approver_user_id": s.approver_user_id,
        "approver_user_name": s.approver.full_name if s.approver else None,
        "is_optional": s.is_optional, "timeout_hours": s.timeout_hours,
        "on_timeout": s.on_timeout,
    }


def serialize_workflow(w, include_steps: bool = False) -> dict:
    d = {
        "id": w.id, "name": w.name, "description": w.description,
        "entity_type": w.entity_type, "is_active": w.is_active,
        "is_default": w.is_default,
        "trigger_conditions": w.trigger_conditions,
        "step_count": len(w.steps or []),
        "created_at": str(w.created_at)[:10] if w.created_at else None,
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
                "decided_at": str(d.decided_at)[:16] if d.decided_at else None,
            }
            for d in (r.decisions or [])
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# TIMEOUT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def process_approval_timeouts(db: Session) -> dict:
    """Process timed-out approval steps: escalate, auto-approve or reject."""

    now = datetime.now(timezone.utc)
    pending = db.query(ApprovalRequest).filter(
        ApprovalRequest.status == "pending",
        ApprovalRequest.step_started_at.isnot(None),
    ).all()

    processed = escalated = auto_approved = rejected = 0

    for req in pending:
        step = (
            db.query(ApprovalStep)
            .filter(
                ApprovalStep.workflow_id == req.workflow_id,
                ApprovalStep.step_order == req.current_step,
            )
            .first()
        )
        if not step:
            continue

        timeout_hours = step.timeout_hours or 72
        deadline = req.step_started_at + timedelta(hours=timeout_hours)
        if now < deadline:
            continue

        processed += 1
        on_timeout = step.on_timeout or "escalate"

        if on_timeout == "auto_approve":
            req.status = "approved"
            req.final_decision = "approved"
            req.final_note = f"Auto-aprobado por timeout ({timeout_hours}h)"
            req.completed_at = now
            auto_approved += 1
        elif on_timeout == "reject":
            req.status = "rejected"
            req.final_decision = "rejected"
            req.final_note = f"Rechazado por timeout ({timeout_hours}h)"
            req.completed_at = now
            rejected += 1
        else:
            if step.escalate_to_user_id:
                req.step_started_at = now
                try:
                    notify_approver(req, step, db, explicit_user_id=step.escalate_to_user_id)
                except Exception:
                    pass
            escalated += 1

    db.commit()
    return {"processed": processed, "escalated": escalated, "auto_approved": auto_approved, "rejected": rejected}


# ═══════════════════════════════════════════════════════════════════════════════
# TIMEOUT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def process_approval_timeouts(db: Session) -> dict:
    """
    Scan all pending ApprovalRequests and apply the configured on_timeout action
    (escalate | auto_approve | reject) for every step that has exceeded its
    timeout_hours budget.  Returns a summary dict.
    """

    now = datetime.now(timezone.utc)
    pending = (
        db.query(ApprovalRequest)
        .filter(
            ApprovalRequest.status == "pending",
            ApprovalRequest.step_started_at.isnot(None),
        )
        .all()
    )

    processed = escalated = auto_approved = rejected = 0

    for req in pending:
        step = (
            db.query(ApprovalStep)
            .filter(
                ApprovalStep.workflow_id == req.workflow_id,
                ApprovalStep.step_order == req.current_step,
            )
            .first()
        )
        if not step:
            continue

        timeout_hours = step.timeout_hours or 72
        deadline = req.step_started_at + timedelta(hours=timeout_hours)
        if now < deadline:
            continue

        processed += 1
        action = step.on_timeout or "escalate"

        if action == "auto_approve":
            wf = db.query(ApprovalWorkflow).options(
                joinedload(ApprovalWorkflow.steps)
            ).filter(ApprovalWorkflow.id == req.workflow_id).first()
            next_steps = []
            if wf:
                next_steps = sorted(
                    [s for s in wf.steps if s.step_order > req.current_step and not s.is_optional],
                    key=lambda s: s.step_order,
                )
            if next_steps:
                req.current_step = next_steps[0].step_order
                req.step_started_at = now
            else:
                req.status = "approved"
                req.final_decision = "approved"
                req.completed_at = now
            auto_approved += 1

        elif action == "reject":
            req.status = "rejected"
            req.final_decision = "rejected"
            req.final_note = f"Auto-rejected: step {req.current_step} timed out after {timeout_hours}h"
            req.completed_at = now
            rejected += 1

        else:  # escalate (default)
            if step.escalate_to_user_id:
                req.step_started_at = now
                notify_approver(req, step, db, explicit_user_id=step.escalate_to_user_id)
            else:
                req.status = "rejected"
                req.final_decision = "rejected"
                req.final_note = (
                    f"Auto-rejected: step {req.current_step} timed out and no escalatee configured"
                )
                req.completed_at = now
            escalated += 1

    db.commit()
    return {
        "processed": processed,
        "escalated": escalated,
        "auto_approved": auto_approved,
        "rejected": rejected,
    }
