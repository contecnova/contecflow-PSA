"""
approvals.py — Motor de aprobaciones multi-nivel configurables.

Soporta: timesheets, gastos, change requests, milestones, compras.
Flujo: request → step 1 → step 2 → ... → step N → decision final
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User, UserRole
from app.services.approval_engine import (
    log_financial_approval_event,
    scope_request_query,
    find_default_workflow,
    notify_approver,
    create_approval_request,
    decide_approval_request,
    get_pending_for_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

_FINANCIAL_ENTITY_TYPES = {"timesheet", "expense", "milestone", "purchase", "invoice"}


# ── Schemas ────────────────────────────────────────────────────────────────────
class WorkflowIn(BaseModel):
    name:        str
    description: Optional[str] = None
    entity_type: str   # timesheet | expense | change_request | milestone | purchase
    is_default:  bool  = False
    trigger_conditions: Optional[str] = "{}"

class StepIn(BaseModel):
    step_order:          int
    name:                str
    approver_type:       str   # role | user | manager | any_in_department
    approver_role:       Optional[str] = None
    approver_user_id:    Optional[str] = None
    approver_department: Optional[str] = None
    is_optional:         bool  = False
    timeout_hours:       int   = 72
    on_timeout:          str   = "escalate"
    escalate_to_user_id: Optional[str] = None

    # Coerce empty strings to None so FK constraints are never violated
    from pydantic import field_validator

    @field_validator("approver_user_id", "escalate_to_user_id", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        return None if v == "" else v

class ApprovalRequestIn(BaseModel):
    workflow_id:    Optional[str] = None   # si None, buscar el default para entity_type
    entity_type:    str
    entity_id:      str
    entity_summary: Optional[str] = None

class DecisionIn(BaseModel):
    decision: str        # approved | rejected | delegated
    note:     Optional[str] = None
    delegate_to: Optional[str] = None   # user_id si decision=delegated


# ── Helpers ────────────────────────────────────────────────────────────────────
def _step_out(s) -> dict:
    return {
        "id": s.id, "step_order": s.step_order, "name": s.name,
        "approver_type": s.approver_type, "approver_role": s.approver_role,
        "approver_user_id": s.approver_user_id,
        "approver_user_name": s.approver.full_name if s.approver else None,
        "is_optional": s.is_optional, "timeout_hours": s.timeout_hours,
        "on_timeout": s.on_timeout,
    }

def _workflow_out(w, include_steps=False) -> dict:
    d = {
        "id": w.id, "name": w.name, "description": w.description,
        "entity_type": w.entity_type, "is_active": w.is_active,
        "is_default": w.is_default,
        "trigger_conditions": w.trigger_conditions,
        "step_count": len(w.steps or []),
        "created_at": str(w.created_at)[:10] if w.created_at else None,
    }
    if include_steps:
        d["steps"] = [_step_out(s) for s in (w.steps or [])]
    return d

def _request_out(r) -> dict:
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



# ── CRUD Workflows ─────────────────────────────────────────────────────────────
@router.get("/workflows", summary="Listar flujos de aprobación")
def list_workflows(
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ApprovalWorkflow
    q = db.query(ApprovalWorkflow)
    if entity_type:
        q = q.filter(ApprovalWorkflow.entity_type == entity_type)
    return [_workflow_out(w, include_steps=True) for w in q.order_by(ApprovalWorkflow.entity_type).all()]


@router.post("/workflows", summary="Crear flujo de aprobación")
def create_workflow(
    payload: WorkflowIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import ApprovalWorkflow
    import uuid
    if payload.is_default:
        db.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.entity_type == payload.entity_type
        ).update({"is_default": False})
    w = ApprovalWorkflow(id=str(uuid.uuid4()), **payload.model_dump())
    db.add(w); db.commit(); db.refresh(w)
    return _workflow_out(w, include_steps=True)


@router.get("/workflows/{workflow_id}", summary="Detalle de flujo")
def get_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ApprovalWorkflow
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w: raise HTTPException(404)
    return _workflow_out(w, include_steps=True)


@router.patch("/workflows/{workflow_id}", summary="Actualizar flujo")
def update_workflow(
    workflow_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import ApprovalWorkflow
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w: raise HTTPException(404)
    allowed = ["name", "description", "is_active", "is_default", "trigger_conditions"]
    for k, v in payload.items():
        if k in allowed: setattr(w, k, v)
    db.commit()
    return _workflow_out(w, include_steps=True)


@router.delete("/workflows/{workflow_id}", summary="Eliminar flujo")
def delete_workflow(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import ApprovalWorkflow
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w: raise HTTPException(404)
    db.delete(w); db.commit()
    return {"ok": True}


# ── CRUD Steps ─────────────────────────────────────────────────────────────────
@router.post("/workflows/{workflow_id}/steps", summary="Añadir paso al flujo")
def add_step(
    workflow_id: str,
    payload: StepIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import ApprovalWorkflow, ApprovalStep
    import uuid
    w = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not w: raise HTTPException(404)
    s = ApprovalStep(id=str(uuid.uuid4()), workflow_id=workflow_id, **payload.model_dump())
    db.add(s); db.commit(); db.refresh(s)
    return _step_out(s)


@router.patch("/workflows/{workflow_id}/steps/{step_id}", summary="Actualizar paso")
def update_step(
    workflow_id: str, step_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import ApprovalStep
    s = db.query(ApprovalStep).filter(
        ApprovalStep.id == step_id, ApprovalStep.workflow_id == workflow_id
    ).first()
    if not s: raise HTTPException(404)
    allowed = ["name", "approver_type", "approver_role", "approver_user_id",
               "is_optional", "timeout_hours", "on_timeout", "step_order", "escalate_to_user_id"]
    _fk_fields = {"approver_user_id", "escalate_to_user_id"}
    for k, v in payload.items():
        if k in allowed:
            # Convert empty strings to None for FK fields
            setattr(s, k, None if (k in _fk_fields and v == "") else v)
    db.commit()
    return _step_out(s)


@router.delete("/workflows/{workflow_id}/steps/{step_id}", summary="Eliminar paso")
def delete_step(
    workflow_id: str, step_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    from app.models.billing_reports import ApprovalStep
    s = db.query(ApprovalStep).filter(
        ApprovalStep.id == step_id, ApprovalStep.workflow_id == workflow_id
    ).first()
    if not s: raise HTTPException(404)
    db.delete(s); db.commit()
    return {"ok": True}


# ── Requests ───────────────────────────────────────────────────────────────────
@router.get("/requests", summary="Solicitudes de aprobación — mis pendientes")
def list_requests(
    status:      Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    mine:        bool           = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ApprovalRequest
    # Non-managers can only query their own requests
    if not mine and current_user.role not in (UserRole.admin, UserRole.pm, UserRole.hr):
        raise HTTPException(403, "Acceso denegado: solo managers pueden ver todas las solicitudes")
    q = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.requester),
        joinedload(ApprovalRequest.decisions),
    )
    q = scope_request_query(q, db, current_user)
    if status:      q = q.filter(ApprovalRequest.status == status)
    if entity_type: q = q.filter(ApprovalRequest.entity_type == entity_type)
    if mine:        q = q.filter(ApprovalRequest.requested_by == current_user.id)
    return [_request_out(r) for r in q.order_by(ApprovalRequest.created_at.desc()).limit(100).all()]


@router.get("/requests/pending-my-action", summary="Solicitudes que yo debo aprobar ahora")
def pending_my_action(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pairs = get_pending_for_user(db, current_user)
    result = []
    for req, step in pairs:
        r = _request_out(req)
        r["step_name"] = step.name
        r["step_order"] = step.step_order
        result.append(r)
    return result


@router.post("/requests", summary="Crear solicitud de aprobación")
def create_request(
    payload: ApprovalRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = create_approval_request(payload, db, current_user)
    return _request_out(req)


@router.post("/requests/{request_id}/decide", summary="Aprobar, rechazar o delegar un paso")
def decide_request(
    request_id: str,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = decide_approval_request(
        request_id, payload.decision, payload.note, payload.delegate_to, db, current_user
    )
    return _request_out(req)


@router.post("/requests/{request_id}/cancel", summary="Cancelar solicitud")
def cancel_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ApprovalRequest
    req = scope_request_query(db.query(ApprovalRequest), db, current_user).filter(ApprovalRequest.id == request_id).first()
    if not req: raise HTTPException(404)
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
    return {"ok": True}


# ── Financial Audit Log ────────────────────────────────────────────────────────
@router.get(
    "/requests/{request_id}/financial-audit",
    summary="Audit trail inmutable de una solicitud financiera (SOX/ISAE 3402)",
)
def get_financial_audit_log(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ApprovalRequest, FinancialApprovalAuditLog

    req = scope_request_query(
        db.query(ApprovalRequest), db, current_user
    ).filter(ApprovalRequest.id == request_id).first()
    if not req:
        raise HTTPException(404, "Solicitud no encontrada")
    if req.entity_type not in _FINANCIAL_ENTITY_TYPES:
        raise HTTPException(
            404,
            f"Esta solicitud es de tipo '{req.entity_type}', que no es una entidad financiera. "
            "El audit log financiero sólo existe para: " + ", ".join(sorted(_FINANCIAL_ENTITY_TYPES)),
        )

    entries = (
        db.query(FinancialApprovalAuditLog)
        .filter(FinancialApprovalAuditLog.request_id == request_id)
        .order_by(FinancialApprovalAuditLog.created_at.asc())
        .all()
    )
    return {
        "request_id": request_id,
        "entity_type": req.entity_type,
        "entity_id": req.entity_id,
        "entries": [
            {
                "id": e.id,
                "action": e.action,
                "decision": e.decision,
                "actor_user_id": e.actor_user_id,
                "step_order": e.step_order,
                "note": e.note,
                "created_at": str(e.created_at) if e.created_at else None,
            }
            for e in entries
        ],
    }


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get("/stats", summary="Estadísticas de aprobaciones")
def approval_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ApprovalRequest
    q = scope_request_query(db.query(ApprovalRequest), db, current_user)
    total     = q.count()
    pending   = q.filter(ApprovalRequest.status == "pending").count()
    approved  = q.filter(ApprovalRequest.status == "approved").count()
    rejected  = q.filter(ApprovalRequest.status == "rejected").count()
    by_entity = q.with_entities(ApprovalRequest.entity_type, func.count(ApprovalRequest.id)).group_by(ApprovalRequest.entity_type).all()
    return {
        "total": total, "pending": pending,
        "approved": approved, "rejected": rejected,
        "by_entity_type": {e: c for e, c in by_entity},
    }
