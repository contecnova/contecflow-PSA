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

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional
from collections import defaultdict

from sqlalchemy.orm import Session, joinedload

from app.models.user import User
from app.models.billing_reports import FinancialApprovalAuditLog
from app.models.billing_reports import ApprovalRequest
from app.models.billing_reports import ApprovalWorkflow
from app.models.billing_reports import ApprovalDecision
from app.models.billing_reports import ApprovalStep
from app.models.billing_reports import ApprovalGroup
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import func

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
    w = get_workflow(db, workflow_id)
    if not w:
        raise HTTPException(404, "Flujo no encontrado")
    version_suffix = suffix or datetime.now(timezone.utc).strftime("v%Y%m%d%H%M")
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
    db.commit()
    db.refresh(cloned)
    return cloned


def create_workflow_from_template(db: Session, template_id: str, override_name: Optional[str] = None) -> ApprovalWorkflow:
    tpl = next((t for t in _WORKFLOW_TEMPLATES if t["id"] == template_id), None)
    if not tpl:
        raise HTTPException(404, "Plantilla no encontrada")
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
    db.commit()
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


def _parse_trigger_conditions(raw: Optional[str]) -> dict:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
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
        return False
    return True


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
            except (ValueError, TypeError):
                conditions = {}
            if conditions.get("category") == category:
                return wf

    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default == True,
        ApprovalWorkflow.is_active == True,
    ).first()


def find_document_workflow(db: Session, category: str):
    """Convenience wrapper — returns best workflow for a document category or None."""
    return find_default_workflow("document", db, category=category)


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


# ── Create request ─────────────────────────────────────────────────────────────

def create_approval_request(payload, db: Session, current_user: User) -> dict:
    """
    payload must have: workflow_id (optional), entity_type, entity_id, entity_summary (optional)
    Returns serialised ApprovalRequest dict (caller should use _request_out).
    Raises HTTPException if no workflow found.
    """

    wf_id = payload.workflow_id
    if not wf_id:
        category = getattr(payload, 'category', None)
        wf = find_default_workflow(payload.entity_type, db, category=category)
        if not wf:
            raise HTTPException(
                404, f"No hay flujo de aprobación configurado para '{payload.entity_type}'"
            )
        wf_id = wf.id
    else:
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == wf_id).first()
        if not wf:
            raise HTTPException(404, "Flujo no encontrado")

    # ── Auto-aprobación: comprobar reglas antes de crear la solicitud ──────────
    auto_result = _check_auto_approval(wf, payload)
    if auto_result:
        # Crear la solicitud ya aprobada directamente
        req = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=wf_id,
            entity_type=payload.entity_type,
            entity_id=payload.entity_id,
            entity_summary=getattr(payload, 'entity_summary', None),
            requested_by=current_user.id,
            current_step=1,
            status="approved",
            final_decision="approved",
            final_note=f"Auto-aprobado por regla: {auto_result}",
            completed_at=datetime.now(timezone.utc),
            step_started_at=datetime.now(timezone.utc),
        )
        db.add(req)
        db.flush()
        log_financial_approval_event(
            db=db, request_id=req.id, entity_type=req.entity_type,
            entity_id=req.entity_id, action="approved", decision="approved",
            actor_user_id=current_user.id, step_order=0,
            note=req.final_note,
        )
        _apply_entity_final_decision(req, "approved", current_user, db)
        db.commit()
        db.refresh(req)
        return req

    req = ApprovalRequest(
        id=str(uuid.uuid4()),
        workflow_id=wf_id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        entity_summary=getattr(payload, 'entity_summary', None),
        requested_by=current_user.id,
        current_step=1,
        status="pending",
        step_started_at=datetime.now(timezone.utc),
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
        note=getattr(payload, 'entity_summary', None),
    )

    # Skip steps whose condition is not met
    first_step = _first_active_step(wf.steps, req)
    if first_step:
        notify_approver(req, first_step, db)

    db.commit()
    db.refresh(req)
    from app.core.events import emit, EventType
    emit(db, EventType.APPROVAL_REQUESTED,
         {"entity_type": req.entity_type, "entity_id": req.entity_id,
          "summary": req.entity_summary, "workflow_id": req.workflow_id},
         resource_type="approval_request", resource_id=req.id)
    return req


# ── Decide ─────────────────────────────────────────────────────────────────────

def _load_request_and_workflow_for_decision(
    request_id: str, db: Session, current_user: User
):
    """Load request, workflow and current step for a decision, raising HTTPException on errors."""
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
    return req, wf, steps, step


def _validate_decision_authorization(
    req, step, decision: str, attachment_url: Optional[str], current_user: User, db: Session
) -> None:
    """Apply authorization / SoD / attachment / double-vote validations."""
    if not _is_authorized(step, current_user, req.requested_by, db):
        raise HTTPException(403, "No tienes permiso para aprobar este paso")

    if req.requested_by == current_user.id:
        _record_sod_violation(req, current_user, db)
        raise HTTPException(
            403,
            "SoD: el solicitante no puede aprobar su propia solicitud "
            "(Segregación de Funciones — crear ≠ aprobar)",
        )

    if step.requires_attachment and decision in ("approved", "rejected") and not attachment_url:
        raise HTTPException(400, "Este paso requiere adjuntar un documento para emitir la decisión")

    existing_vote = next(
        (d for d in (req.decisions or [])
         if d.step_order == req.current_step and d.approver_id == current_user.id),
        None
    )
    if existing_vote:
        raise HTTPException(400, "Ya has emitido tu voto en este paso")


def _record_decision_row(
    req, decision: str, note: Optional[str], delegate_to: Optional[str],
    attachment_url: Optional[str], current_user: User, db: Session
) -> None:
    """Persist the ApprovalDecision row and the audit log entry."""
    db.add(ApprovalDecision(
        id=str(uuid.uuid4()),
        request_id=req.id,
        step_order=req.current_step,
        approver_id=current_user.id,
        decision=decision,
        note=note,
        attachment_url=attachment_url,
    ))
    db.flush()
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
    db.refresh(req)


def _apply_rejected_decision(req, note: Optional[str], current_user: User, db: Session) -> None:
    req.status = "rejected"
    req.final_decision = "rejected"
    req.final_note = note
    req.completed_at = datetime.now(timezone.utc)
    _apply_entity_final_decision(req, "rejected", current_user, db)


def _apply_delegated_decision(
    req, steps, note: Optional[str], delegate_to: Optional[str], db: Session
) -> None:
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


def _quorum_satisfied(req, step) -> bool:
    """Return True if the parallel-quorum requirement of `step` is met by current votes."""
    if not step.parallel_quorum:
        return True
    step_approvals = [
        d for d in (req.decisions or [])
        if d.step_order == req.current_step and d.decision == "approved"
    ]
    required = step.required_approvals or 1
    return len(step_approvals) >= required


def _apply_approved_decision(
    req, wf, steps, step, current_user: User, db: Session
) -> bool:
    """Apply an approved decision. Returns True if the workflow stayed on the current
    step (waiting for more quorum votes) and the caller should return early."""
    if not _quorum_satisfied(req, step):
        db.commit()
        db.refresh(req)
        return True

    next_steps = [
        s for s in steps
        if s.step_order > req.current_step
        and not s.is_optional
        and _step_condition_met(s, req)
    ]
    if next_steps:
        req.current_step = next_steps[0].step_order
        req.step_started_at = datetime.now(timezone.utc)
        db.commit()
        notify_approver(req, next_steps[0], db)
    else:
        req.status = "approved"
        req.final_decision = "approved"
        req.completed_at = datetime.now(timezone.utc)
        db.commit()
        _notify_requester_approved(req, db)
        _apply_entity_final_decision(req, "approved", current_user, db)
        if wf.chain_on_approval_workflow_id:
            _trigger_chained_workflow(req, wf.chain_on_approval_workflow_id, current_user, db)
    return False


def _emit_decision_event(req, decision: str, note: Optional[str], current_user: User, db: Session) -> None:
    from app.core.events import emit, EventType
    event_type = (
        EventType.APPROVAL_APPROVED if req.final_decision == "approved"
        else EventType.APPROVAL_REJECTED if req.final_decision == "rejected"
        else EventType.APPROVAL_REQUESTED
    )
    emit(db, event_type,
         {"entity_type": req.entity_type, "entity_id": req.entity_id,
          "summary": req.entity_summary, "decision": decision, "note": note},
         resource_type="approval_request", resource_id=req.id,
         actor=current_user)


def decide_approval_request(
    request_id: str,
    decision: str,
    note: Optional[str],
    delegate_to: Optional[str],
    db: Session,
    current_user: User,
    attachment_url: Optional[str] = None,
):
    """
    Apply an approval decision (approved | rejected | delegated).
    Returns the updated ApprovalRequest ORM object.
    Raises HTTPException on validation failures.
    """
    req, wf, steps, step = _load_request_and_workflow_for_decision(request_id, db, current_user)
    _validate_decision_authorization(req, step, decision, attachment_url, current_user, db)
    _record_decision_row(req, decision, note, delegate_to, attachment_url, current_user, db)

    if decision == "rejected":
        _apply_rejected_decision(req, note, current_user, db)
    elif decision == "delegated":
        _apply_delegated_decision(req, steps, note, delegate_to, db)
    elif decision == "approved":
        early_return = _apply_approved_decision(req, wf, steps, step, current_user, db)
        if early_return:
            return req

    db.commit()
    db.refresh(req)
    _emit_decision_event(req, decision, note, current_user, db)
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

def list_workflows(db: Session, entity_type: Optional[str] = None, include_inactive: bool = False):
    q = db.query(ApprovalWorkflow)
    if not include_inactive:
        q = q.filter(ApprovalWorkflow.is_active == True)
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


def get_workflow(db: Session, workflow_id: str, include_inactive: bool = False):
    q = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id)
    if not include_inactive:
        q = q.filter(ApprovalWorkflow.is_active == True)
    return q.first()


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
    if req.requested_by != current_user.id and current_user.role not in ("admin", "pm"):
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
    from app.core.events import emit, EventType
    emit(db, EventType.APPROVAL_REJECTED,
         {"entity_type": req.entity_type, "entity_id": req.entity_id,
          "summary": req.entity_summary, "action": "cancelled"},
         resource_type="approval_request", resource_id=req.id,
         actor=current_user)
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


def _empty_bottleneck_row() -> dict:
    return {
        "workflow_id": None,
        "workflow_name": None,
        "step_order": None,
        "step_name": None,
        "step_timeout_hours": None,
        "decisions_total": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "delegated_count": 0,
        "decision_time_sum_hours": 0.0,
        "decision_time_count": 0,
        "pending_count": 0,
        "pending_age_sum_hours": 0.0,
    }


def _stamp_bottleneck_row(row: dict, wf, step, step_order: int) -> None:
    row["workflow_id"] = wf.id
    row["workflow_name"] = wf.name
    row["step_order"] = step_order
    row["step_name"] = step.name if step else f"Step {step_order}"
    row["step_timeout_hours"] = step.timeout_hours if step else None


def _aggregate_bottleneck_decisions(stats: dict, req, wf, step_map: dict, now: datetime) -> None:
    ordered_decisions = sorted(req.decisions or [], key=lambda d: (d.step_order, d.decided_at or now))
    prev_ts = req.created_at
    for d in ordered_decisions:
        step = step_map.get(d.step_order)
        key = (req.workflow_id, d.step_order)
        row = stats[key]
        _stamp_bottleneck_row(row, wf, step, d.step_order)

        row["decisions_total"] += 1
        if d.decision == "approved":
            row["approved_count"] += 1
        elif d.decision == "rejected":
            row["rejected_count"] += 1
        elif d.decision == "delegated":
            row["delegated_count"] += 1

        if d.decided_at and prev_ts:
            delta_h = max(0.0, (d.decided_at - prev_ts).total_seconds() / 3600.0)
            row["decision_time_sum_hours"] += delta_h
            row["decision_time_count"] += 1
        if d.decided_at:
            prev_ts = d.decided_at


def _aggregate_bottleneck_pending(stats: dict, req, wf, step_map: dict, now: datetime) -> None:
    if not (req.status == "pending" and req.current_step):
        return
    step = step_map.get(req.current_step)
    key = (req.workflow_id, req.current_step)
    row = stats[key]
    _stamp_bottleneck_row(row, wf, step, req.current_step)
    row["pending_count"] += 1
    if req.step_started_at:
        age_h = max(0.0, (now - req.step_started_at).total_seconds() / 3600.0)
        row["pending_age_sum_hours"] += age_h


def _compute_bottleneck_item(row: dict) -> dict:
    decisions_total = row["decisions_total"]
    decision_time_count = row["decision_time_count"]
    pending_count = row["pending_count"]
    reject_rate = (row["rejected_count"] / decisions_total * 100.0) if decisions_total else 0.0
    avg_decision_h = (row["decision_time_sum_hours"] / decision_time_count) if decision_time_count else 0.0
    avg_pending_h = (row["pending_age_sum_hours"] / pending_count) if pending_count else 0.0

    timeout_h = row["step_timeout_hours"] or 0
    sla_risk_pct = (avg_pending_h / timeout_h * 100.0) if timeout_h > 0 else 0.0
    bottleneck_score = avg_decision_h * (1.0 + pending_count * 0.35) * (1.0 + reject_rate / 100.0)

    return {
        "workflow_id": row["workflow_id"],
        "workflow_name": row["workflow_name"],
        "step_order": row["step_order"],
        "step_name": row["step_name"],
        "step_timeout_hours": row["step_timeout_hours"],
        "decisions_total": decisions_total,
        "approved_count": row["approved_count"],
        "rejected_count": row["rejected_count"],
        "delegated_count": row["delegated_count"],
        "rejection_rate_pct": round(reject_rate, 2),
        "avg_decision_time_hours": round(avg_decision_h, 2),
        "pending_count": pending_count,
        "avg_pending_age_hours": round(avg_pending_h, 2),
        "sla_risk_pct": round(sla_risk_pct, 2),
        "bottleneck_score": round(bottleneck_score, 3),
    }


def _compute_weekly_trend(requests) -> list:
    weekly = defaultdict(lambda: {"decisions": 0, "rejected": 0})
    for req in requests:
        for d in (req.decisions or []):
            if not d.decided_at:
                continue
            week_key = d.decided_at.astimezone(timezone.utc).strftime("%G-W%V")
            weekly[week_key]["decisions"] += 1
            if d.decision == "rejected":
                weekly[week_key]["rejected"] += 1

    weekly_trend = []
    for week_key in sorted(weekly.keys()):
        row = weekly[week_key]
        decisions = row["decisions"]
        reject_rate = (row["rejected"] / decisions * 100.0) if decisions else 0.0
        weekly_trend.append({
            "week": week_key,
            "decisions": decisions,
            "rejected": row["rejected"],
            "rejection_rate_pct": round(reject_rate, 2),
        })
    return weekly_trend


def _compute_top_workflows(items: list) -> list:
    top_workflow_map = defaultdict(lambda: {
        "workflow_id": None,
        "workflow_name": None,
        "steps_analyzed": 0,
        "avg_bottleneck_score": 0.0,
        "max_sla_risk_pct": 0.0,
        "pending_total": 0,
    })
    for it in items:
        wf_row = top_workflow_map[it["workflow_id"]]
        wf_row["workflow_id"] = it["workflow_id"]
        wf_row["workflow_name"] = it["workflow_name"]
        wf_row["steps_analyzed"] += 1
        wf_row["avg_bottleneck_score"] += it["bottleneck_score"]
        wf_row["max_sla_risk_pct"] = max(wf_row["max_sla_risk_pct"], it["sla_risk_pct"])
        wf_row["pending_total"] += it["pending_count"]

    top_workflows = []
    for wf in top_workflow_map.values():
        wf["avg_bottleneck_score"] = round(
            wf["avg_bottleneck_score"] / max(1, wf["steps_analyzed"]),
            3,
        )
        top_workflows.append(wf)
    top_workflows.sort(
        key=lambda x: (x["avg_bottleneck_score"], x["max_sla_risk_pct"], x["pending_total"]),
        reverse=True,
    )
    return top_workflows


def _compute_bottleneck_recommendations(items: list) -> list:
    recommendations: list = []
    worst = items[0] if items else None
    if worst and worst["sla_risk_pct"] >= 80:
        recommendations.append({
            "priority": "high",
            "title": f"Mitigar riesgo SLA en '{worst['workflow_name']}' paso {worst['step_order']}",
            "action": "Reducir timeout o activar escalado automatico con fallback a rol.",
            "why": f"Riesgo SLA {worst['sla_risk_pct']}% con {worst['pending_count']} pendientes.",
        })

    high_reject = next((it for it in items if it["rejection_rate_pct"] >= 25), None)
    if high_reject:
        recommendations.append({
            "priority": "medium",
            "title": f"Bajar rechazo en '{high_reject['workflow_name']}' paso {high_reject['step_order']}",
            "action": "Añadir checklist previo y validaciones automaticas antes de enviar a aprobacion.",
            "why": f"Tasa de rechazo {high_reject['rejection_rate_pct']}%.",
        })

    slow = next((it for it in items if it["avg_decision_time_hours"] >= 24), None)
    if slow:
        recommendations.append({
            "priority": "medium",
            "title": f"Acelerar ciclo en '{slow['workflow_name']}' paso {slow['step_order']}",
            "action": "Usar aprobador de respaldo o regla any_in_department para evitar bloqueo por ausencia.",
            "why": f"Tiempo medio de decision {slow['avg_decision_time_hours']}h.",
        })
    return recommendations


def _load_bottleneck_requests(db: Session, current_user: User, workflow_id: Optional[str], since: datetime) -> list:
    rq = db.query(ApprovalRequest).options(joinedload(ApprovalRequest.decisions)).filter(
        ApprovalRequest.created_at >= since
    )
    if workflow_id:
        rq = rq.filter(ApprovalRequest.workflow_id == workflow_id)
    rq = scope_request_query(rq, db, current_user)
    return rq.all()


def _load_workflows_by_ids(db: Session, workflow_ids: list) -> dict:
    if not workflow_ids:
        return {}
    return {
        w.id: w
        for w in db.query(ApprovalWorkflow).options(joinedload(ApprovalWorkflow.steps)).filter(
            ApprovalWorkflow.id.in_(workflow_ids)
        ).all()
    }


def get_workflow_bottlenecks(
    db: Session,
    current_user: User,
    workflow_id: Optional[str] = None,
    days: int = 90,
) -> dict:
    """Compute bottleneck metrics per workflow step based on historical decisions.

    Metrics per step:
      - decisions_total
      - rejection_rate_pct
      - avg_decision_time_hours
      - pending_count
      - avg_pending_age_hours
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(days, 365)))

    requests = _load_bottleneck_requests(db, current_user, workflow_id, since)
    workflow_ids = sorted({r.workflow_id for r in requests if r.workflow_id})
    workflows = _load_workflows_by_ids(db, workflow_ids)

    stats = defaultdict(_empty_bottleneck_row)
    for req in requests:
        wf = workflows.get(req.workflow_id)
        if not wf:
            continue
        step_map = {s.step_order: s for s in (wf.steps or [])}
        _aggregate_bottleneck_decisions(stats, req, wf, step_map, now)
        _aggregate_bottleneck_pending(stats, req, wf, step_map, now)

    items = [_compute_bottleneck_item(row) for row in stats.values()]
    items.sort(key=lambda x: x["bottleneck_score"], reverse=True)

    weekly_trend = _compute_weekly_trend(requests)
    top_workflows = _compute_top_workflows(items)
    recommendations = _compute_bottleneck_recommendations(items)

    critical_steps = [
        it for it in items
        if it["sla_risk_pct"] >= 80 or it["pending_count"] >= 3 or it["rejection_rate_pct"] >= 25
    ]
    pending_total = sum(it["pending_count"] for it in items)
    avg_decision_time = round(
        (sum(it["avg_decision_time_hours"] for it in items) / len(items)) if items else 0.0,
        2,
    )

    return {
        "since": since.isoformat(),
        "days": days,
        "workflow_id": workflow_id,
        "count": len(items),
        "items": items,
        "top_bottlenecks": items[:10],
        "summary": {
            "steps_analyzed": len(items),
            "critical_steps": len(critical_steps),
            "pending_total": pending_total,
            "avg_decision_time_hours": avg_decision_time,
        },
        "top_workflows": top_workflows[:5],
        "weekly_trend": weekly_trend[-12:],
        "recommendations": recommendations,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

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
                pass
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
        pass


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
        pass


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


# ── Serialization helpers ───────────────────────────────────────────────────

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

# ═══════════════════════════════════════════════════════════════════════════════
# TIMEOUT PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════

def _handle_timeout_escalate(req, step, now: datetime, info: dict, db: Session) -> str:
    """Apply 'escalate' timeout action. Returns counter bucket name."""
    if step.escalate_to_user_id:
        db.add(ApprovalDecision(
            request_id=req.id,
            step_order=step.step_order,
            approver_id=step.escalate_to_user_id,
            decision="delegated",
            note="Escalado automáticamente por timeout",
            decided_at=now,
        ))
        req.current_step += 1
        req.step_started_at = now
        info["escalated_to"] = step.escalate_to_user_id
        return "escalated"
    req.status = "rejected"
    req.final_decision = "rejected"
    req.final_note = "Rechazado automáticamente por timeout (sin escalado)"
    req.completed_at = now
    info["rejected"] = True
    return "rejected"


def _handle_timeout_auto_approve(req, step, now: datetime, info: dict, db: Session) -> str:
    db.add(ApprovalDecision(
        request_id=req.id,
        step_order=step.step_order,
        approver_id=step.approver_user_id,
        decision="approved",
        note="Aprobado automáticamente por timeout",
        decided_at=now,
    ))
    req.current_step += 1
    req.step_started_at = now
    info["auto_approved"] = True
    return "auto_approved"


def _handle_timeout_reject(req, step, now: datetime, info: dict, db: Session) -> str:
    req.status = "rejected"
    req.final_decision = "rejected"
    req.final_note = "Rechazado automáticamente por timeout"
    req.completed_at = now
    info["rejected"] = True
    return "rejected"


def _log_timeout_audit_event(req, step, action: str, now: datetime, db: Session) -> None:
    if req.entity_type not in _FINANCIAL_ENTITY_TYPES:
        return
    db.add(FinancialApprovalAuditLog(
        request_id=req.id,
        entity_type=req.entity_type,
        entity_id=req.entity_id,
        action="timeout",
        decision=action,
        actor_user_id=None,
        step_order=step.step_order,
        note=f"Acción automática por timeout: {action}",
        created_at=now,
    ))


def _step_is_expired(step, req, now: datetime) -> bool:
    if not step or not step.timeout_hours or not req.step_started_at:
        return False
    timeout_at = req.step_started_at + timedelta(hours=step.timeout_hours)
    return now >= timeout_at


def process_approval_timeouts(db: Session) -> dict:
    """
    Procesa todas las solicitudes de aprobación pendientes y aplica la acción configurada
    (escalar, auto-aprobar o rechazar) para los pasos que superaron su timeout.
    Devuelve un resumen de las acciones realizadas.
    """
    now = datetime.now(timezone.utc)
    counters = {"escalated": 0, "auto_approved": 0, "rejected": 0}
    updated = 0
    details: list = []

    requests = db.query(ApprovalRequest).filter(ApprovalRequest.status == "pending").all()
    for req in requests:
        step = (
            db.query(ApprovalStep)
            .filter(
                ApprovalStep.workflow_id == req.workflow_id,
                ApprovalStep.step_order == req.current_step,
            )
            .first()
        )
        if not _step_is_expired(step, req, now):
            continue

        action = (step.on_timeout or "escalate").lower()
        info = {"request_id": req.id, "step": step.step_order, "action": action}

        if action == "escalate":
            bucket = _handle_timeout_escalate(req, step, now, info, db)
        elif action == "auto_approve":
            bucket = _handle_timeout_auto_approve(req, step, now, info, db)
        elif action == "reject":
            bucket = _handle_timeout_reject(req, step, now, info, db)
        else:
            continue

        counters[bucket] = counters.get(bucket, 0) + 1
        _log_timeout_audit_event(req, step, action, now, db)
        updated += 1
        details.append(info)

    db.commit()
    return {
        "updated": updated,
        "escalated": counters["escalated"],
        "auto_approved": counters["auto_approved"],
        "rejected": counters["rejected"],
        "details": details,
    }


# ── Enterprise v2: helpers ─────────────────────────────────────────────────────

def _check_auto_approval(wf, payload) -> Optional[str]:
    """Return rule label if auto-approval applies, else None."""
    if not wf.auto_approval_rules:
        return None
    try:
        rules = json.loads(wf.auto_approval_rules)
    except Exception:
        return None
    ctx = {}
    if hasattr(payload, 'context') and payload.context:
        ctx = payload.context if isinstance(payload.context, dict) else {}
    for rule in (rules or []):
        if rule.get("action") != "auto_approve":
            continue
        conds = rule.get("conditions", {})
        if not conds:
            continue
        match = True
        if "amount_lt" in conds:
            try:
                if float(ctx.get("amount", 0)) >= float(conds["amount_lt"]):
                    match = False
            except Exception:
                match = False
        if "amount_gt" in conds:
            try:
                if float(ctx.get("amount", 0)) <= float(conds["amount_gt"]):
                    match = False
            except Exception:
                match = False
        if "department" in conds:
            if ctx.get("department") != conds["department"]:
                match = False
        if "category" in conds:
            if ctx.get("category") != conds["category"]:
                match = False
        if match:
            return rule.get("label", "auto-rule")
    return None


def _first_active_step(steps, req):
    """Return first step whose condition is met (or first step if no conditions)."""
    ordered = sorted(steps, key=lambda s: s.step_order)
    for s in ordered:
        if not s.is_optional and _step_condition_met(s, req):
            return s
    return ordered[0] if ordered else None


def _step_condition_met(step, req) -> bool:
    """Evaluate step.step_condition JSON against the request context."""
    if not step.step_condition:
        return True
    try:
        cond = json.loads(step.step_condition)
    except Exception:
        return True
    ctx = {}
    try:
        ctx = json.loads(req.entity_summary or "{}")
    except Exception:
        pass
    if "amount_gt" in cond:
        try:
            if float(ctx.get("amount", 0)) <= float(cond["amount_gt"]):
                return False
        except Exception:
            pass
    if "amount_lt" in cond:
        try:
            if float(ctx.get("amount", 0)) >= float(cond["amount_lt"]):
                return False
        except Exception:
            pass
    if "department" in cond:
        if ctx.get("department") != cond["department"]:
            return False
    if "category" in cond:
        if ctx.get("category") != cond["category"]:
            return False
    return True


def _trigger_chained_workflow(req, chain_wf_id: str, actor, db: Session) -> None:
    """Create a new approval request for the chained workflow."""
    try:
        chain_wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == chain_wf_id).first()
        if not chain_wf or not chain_wf.is_active:
            return
        chained = ApprovalRequest(
            id=str(uuid.uuid4()),
            workflow_id=chain_wf_id,
            entity_type=req.entity_type,
            entity_id=req.entity_id,
            entity_summary=f"[Encadenado de {req.id[:8]}] {req.entity_summary or ''}",
            requested_by=req.requested_by,
            current_step=1,
            status="pending",
            step_started_at=datetime.now(timezone.utc),
        )
        db.add(chained)
        db.commit()
        first = _first_active_step(chain_wf.steps or [], chained)
        if first:
            notify_approver(chained, first, db)
    except Exception:
        logger.warning("_trigger_chained_workflow failed", exc_info=True)


# ── Enterprise v2: Approver Groups CRUD ───────────────────────────────────────

def list_approval_groups(db: Session) -> list:
    return db.query(ApprovalGroup).order_by(ApprovalGroup.name).all()


def get_approval_group(db: Session, group_id: str):
    return db.query(ApprovalGroup).filter(ApprovalGroup.id == group_id).first()


def create_approval_group(db: Session, name: str, description: Optional[str], member_ids: list, created_by: str):
    g = ApprovalGroup(
        id=str(uuid.uuid4()),
        name=name,
        description=description,
        member_ids=json.dumps(member_ids),
        created_by=created_by,
    )
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


def update_approval_group(db: Session, group_id: str, name: Optional[str], description: Optional[str], member_ids: Optional[list]):
    g = db.query(ApprovalGroup).filter(ApprovalGroup.id == group_id).first()
    if not g:
        return None
    if name is not None:
        g.name = name
    if description is not None:
        g.description = description
    if member_ids is not None:
        g.member_ids = json.dumps(member_ids)
    db.commit()
    db.refresh(g)
    return g


def delete_approval_group(db: Session, group_id: str) -> bool:
    g = db.query(ApprovalGroup).filter(ApprovalGroup.id == group_id).first()
    if not g:
        return False
    db.delete(g)
    db.commit()
    return True


def serialize_approval_group(g) -> dict:
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "member_ids": json.loads(g.member_ids or "[]"),
        "created_by": g.created_by,
        "created_at": str(g.created_at)[:16] if g.created_at else None,
    }


# ── Enterprise v2: Approver Load Analytics ────────────────────────────────────

def _empty_approver_load_row() -> dict:
    return {
        "user_id": None,
        "decisions_total": 0,
        "approved_count": 0,
        "rejected_count": 0,
        "decision_time_sum_hours": 0.0,
        "decision_time_count": 0,
        "pending_count": 0,
        "avg_pending_age_hours": 0.0,
    }


def _aggregate_decisions_per_user(decisions, user_stats: dict) -> None:
    for d in decisions:
        row = user_stats[d.approver_id]
        row["user_id"] = d.approver_id
        row["decisions_total"] += 1
        if d.decision == "approved":
            row["approved_count"] += 1
        elif d.decision == "rejected":
            row["rejected_count"] += 1


def _resolve_pending_responsible_user(step, db: Session) -> Optional[str]:
    uid = step.approver_user_id
    if uid:
        return uid
    if step.approver_group_id:
        try:
            g = db.query(ApprovalGroup).filter(ApprovalGroup.id == step.approver_group_id).first()
            members = json.loads(g.member_ids or "[]") if g else []
            return members[0] if members else None
        except Exception:
            return None
    return None


def _aggregate_pending_per_user(
    pending_requests, workflows: dict, user_stats: dict, now: datetime, db: Session
) -> None:
    for req in pending_requests:
        wf = workflows.get(req.workflow_id)
        if not wf:
            continue
        step = next((s for s in (wf.steps or []) if s.step_order == req.current_step), None)
        if not step:
            continue
        age_h = max(0.0, (now - req.step_started_at).total_seconds() / 3600.0) if req.step_started_at else 0.0
        uid = _resolve_pending_responsible_user(step, db)
        if uid:
            user_stats[uid]["user_id"] = uid
            user_stats[uid]["pending_count"] += 1
            user_stats[uid]["avg_pending_age_hours"] = (
                user_stats[uid]["avg_pending_age_hours"] + age_h
            )


def _build_approver_load_item(uid: str, row: dict, db: Session) -> dict:
    total = row["decisions_total"]
    reject_rate = round(row["rejected_count"] / total * 100, 2) if total else 0.0
    avg_response = round(row["decision_time_sum_hours"] / row["decision_time_count"], 2) if row["decision_time_count"] else 0.0
    pending = row["pending_count"]
    avg_age = round(row["avg_pending_age_hours"] / pending, 2) if pending else 0.0
    load_score = round(pending * 1.5 + avg_response * 0.1, 2)
    user_obj = db.query(User).filter(User.id == uid).first()
    return {
        "user_id": uid,
        "user_name": user_obj.full_name if user_obj else uid,
        "user_email": user_obj.email if user_obj else None,
        "decisions_total": total,
        "approved_count": row["approved_count"],
        "rejected_count": row["rejected_count"],
        "rejection_rate_pct": reject_rate,
        "avg_response_hours": avg_response,
        "pending_count": pending,
        "avg_pending_age_hours": avg_age,
        "load_score": load_score,
    }


def get_approver_load(db: Session, current_user, days: int = 90) -> dict:
    """Compute per-user approval load: pending, decided, avg response time, rejection rate."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=max(1, min(days, 365)))

    decisions = (
        db.query(ApprovalDecision)
        .filter(ApprovalDecision.decided_at >= since)
        .all()
    )

    pending_requests = (
        db.query(ApprovalRequest)
        .filter(ApprovalRequest.status == "pending")
        .all()
    )

    user_stats = defaultdict(_empty_approver_load_row)
    _aggregate_decisions_per_user(decisions, user_stats)

    wf_ids = list({r.workflow_id for r in pending_requests if r.workflow_id})
    workflows = _load_workflows_by_ids(db, wf_ids)
    _aggregate_pending_per_user(pending_requests, workflows, user_stats, now, db)

    items = [
        _build_approver_load_item(uid, row, db)
        for uid, row in user_stats.items()
        if uid
    ]

    items.sort(key=lambda x: x["load_score"], reverse=True)
    overloaded = [it for it in items if it["pending_count"] >= 5 or it["avg_pending_age_hours"] >= 48]
    return {
        "days": days,
        "since": since.isoformat(),
        "count": len(items),
        "items": items,
        "overloaded_approvers": overloaded,
    }
