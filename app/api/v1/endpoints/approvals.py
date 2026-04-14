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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


def _scope_request_query(q, db: Session, current_user: User):
    from app.models.billing_reports import ApprovalRequest
    if current_user.is_superadmin or not current_user.organization_id:
        return q
    org_user_ids = db.query(User.id).filter(
        User.organization_id == current_user.organization_id
    ).scalar_subquery()
    return q.filter(ApprovalRequest.requested_by.in_(org_user_ids))


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


def _find_default_workflow(entity_type: str, db: Session):
    from app.models.billing_reports import ApprovalWorkflow
    return db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.entity_type == entity_type,
        ApprovalWorkflow.is_default  == True,
        ApprovalWorkflow.is_active   == True,
    ).first()


def _notify_approver(request, step, db: Session, explicit_user_id: Optional[str] = None):
    """Crea notificación para el aprobador del paso actual."""
    try:
        from app.models.enterprise import Notification
        import uuid
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
                message=f"{request.entity_summary or request.entity_id} — Paso {step.step_order}: {step.name}",
                entity_type="approval_request",
                entity_id=request.id,
            ))
    except Exception:
        logger.warning("Failed to create approval notification", exc_info=True)
        # Notifications are non-critical; continue without raising


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
    q = _scope_request_query(q, db, current_user)
    if status:      q = q.filter(ApprovalRequest.status == status)
    if entity_type: q = q.filter(ApprovalRequest.entity_type == entity_type)
    if mine:        q = q.filter(ApprovalRequest.requested_by == current_user.id)
    return [_request_out(r) for r in q.order_by(ApprovalRequest.created_at.desc()).limit(100).all()]


@router.get("/requests/pending-my-action", summary="Solicitudes que yo debo aprobar ahora")
def pending_my_action(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Devuelve solicitudes en estado 'pending' donde el aprobador del paso actual
    soy yo (por usuario directo, rol, o departamento).
    """
    from app.models.billing_reports import ApprovalRequest, ApprovalWorkflow

    pending = db.query(ApprovalRequest).filter(
        ApprovalRequest.status == "pending"
    ).options(
        joinedload(ApprovalRequest.requester),
        joinedload(ApprovalRequest.decisions),
    )
    pending = _scope_request_query(pending, db, current_user).all()

    if not pending:
        return []

    # Pre-load all workflows and their steps in one query (avoids N+1)
    wf_ids = list({req.workflow_id for req in pending if req.workflow_id})
    workflows = {
        wf.id: wf for wf in db.query(ApprovalWorkflow).options(
            joinedload(ApprovalWorkflow.steps)
        ).filter(ApprovalWorkflow.id.in_(wf_ids)).all()
    }

    result = []
    for req in pending:
        wf = workflows.get(req.workflow_id)
        if not wf: continue

        # Obtener el paso actual
        step = next(
            (s for s in wf.steps if s.step_order == req.current_step),
            None
        )
        if not step: continue

        # ¿Soy yo el aprobador?
        is_mine = False
        if step.approver_type == "user" and step.approver_user_id == current_user.id:
            is_mine = True
        elif step.approver_type == "role" and hasattr(current_user.role, "value"):
            is_mine = current_user.role.value == step.approver_role
        elif step.approver_type == "manager":
            # El manager del solicitante — current_user es el manager si el solicitante le reporta
            requester = req.requester or db.query(User).filter(User.id == req.requested_by).first()
            is_mine = bool(requester and requester.manager_id == current_user.id)
        elif step.approver_type == "any_in_department":
            is_mine = current_user.department == step.approver_department

        if is_mine:
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
    from app.models.billing_reports import ApprovalRequest, ApprovalWorkflow
    import uuid

    # Buscar workflow
    wf_id = payload.workflow_id
    if not wf_id:
        wf = _find_default_workflow(payload.entity_type, db)
        if not wf:
            raise HTTPException(404, f"No hay flujo de aprobación configurado para '{payload.entity_type}'")
        wf_id = wf.id
    else:
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == wf_id).first()
        if not wf: raise HTTPException(404, "Flujo no encontrado")

    # Crear request
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
    db.add(req); db.flush()

    # Notificar al aprobador del paso 1
    first_step = min(wf.steps, key=lambda s: s.step_order, default=None)
    if first_step:
        _notify_approver(req, first_step, db)

    db.commit(); db.refresh(req)
    return _request_out(req)


@router.post("/requests/{request_id}/decide", summary="Aprobar, rechazar o delegar un paso")
def decide_request(
    request_id: str,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ApprovalRequest, ApprovalWorkflow, ApprovalDecision
    import uuid

    req = db.query(ApprovalRequest).options(
        joinedload(ApprovalRequest.decisions)
    )
    req = _scope_request_query(req, db, current_user).filter(ApprovalRequest.id == request_id).first()
    if not req: raise HTTPException(404)
    if req.status != "pending":
        raise HTTPException(400, f"La solicitud ya está en estado '{req.status}'")

    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == req.workflow_id).first()
    if not wf: raise HTTPException(404, "Flujo no encontrado")

    steps = sorted(wf.steps, key=lambda s: s.step_order)

    # Verificar que el usuario actual es el aprobador del paso actual
    step = next((s for s in steps if s.step_order == req.current_step), None)
    if not step:
        raise HTTPException(400, "No se encontró el paso actual del flujo de aprobación")
    authorized = False
    if step.approver_type == "user" and step.approver_user_id == current_user.id:
        authorized = True
    elif step.approver_type == "role" and hasattr(current_user.role, "value"):
        authorized = current_user.role.value == step.approver_role
    elif step.approver_type == "manager":
        requester = db.query(User).filter(User.id == req.requested_by).first()
        authorized = bool(requester and requester.manager_id == current_user.id)
    elif step.approver_type == "any_in_department":
        authorized = current_user.department == step.approver_department
    # Admins can always act as approver
    if hasattr(current_user, 'role') and hasattr(current_user.role, 'value') and current_user.role.value == 'admin':
        authorized = True
    if not authorized:
        raise HTTPException(403, "No tienes permiso para aprobar este paso")

    # ── SoD: el solicitante no puede aprobar su propia solicitud ──────────────
    if req.requested_by == current_user.id:
        # Record the violation before blocking
        try:
            from app.api.v1.endpoints.grc import record_sod_violation
            from app.models.billing_reports import SodRule
            # Find matching SoD rule for this entity_type
            matching = db.query(SodRule).filter(
                SodRule.module_a == req.entity_type,
                SodRule.action_a == "crear",
                SodRule.module_b == req.entity_type,
                SodRule.action_b == "aprobar",
                SodRule.is_active == True,
            ).first()
            if matching:
                record_sod_violation(
                    db=db, rule_id=matching.id,
                    user_id=current_user.id, role=str(current_user.role),
                    context_type="approval_request", context_id=req.id,
                )
                db.flush()
        except Exception:
            pass
        raise HTTPException(
            403,
            "SoD: el solicitante no puede aprobar su propia solicitud "
            "(Segregación de Funciones — crear ≠ aprobar)"
        )

    # Registrar decisión
    decision = ApprovalDecision(
        id=str(uuid.uuid4()),
        request_id=request_id,
        step_order=req.current_step,
        approver_id=current_user.id,
        decision=payload.decision,
        note=payload.note,
    )
    db.add(decision)

    if payload.decision == "rejected":
        req.status         = "rejected"
        req.final_decision = "rejected"
        req.final_note     = payload.note
        req.completed_at   = datetime.now(timezone.utc)

    elif payload.decision == "delegated":
        if not payload.delegate_to:
            raise HTTPException(400, "Debes indicar delegate_to para delegar la aprobación")
        req.current_step = req.current_step
        req.status = "pending"
        req.final_note = f"Delegado a {payload.delegate_to} ({payload.note or 'sin nota'})"
        db.commit()
        # Notificar al delegado explícitamente fuera de la transacción crítica
        _notify_approver(req, next((s for s in steps if s.step_order == req.current_step), None), db, explicit_user_id=payload.delegate_to)
        db.commit()
        return _request_out(req)

    elif payload.decision == "approved":
        # Buscar el siguiente paso obligatorio (los pasos opcionales se saltan automáticamente)
        next_steps = [s for s in steps if s.step_order > req.current_step and not s.is_optional]

        if next_steps:
            req.current_step = next_steps[0].step_order
            db.commit()
            _notify_approver(req, next_steps[0], db)
            db.commit()
            return _request_out(req)
        else:
            # Todos los pasos completados → aprobado
            req.status         = "approved"
            req.final_decision = "approved"
            req.completed_at   = datetime.now(timezone.utc)
            db.commit()
            # Notificar al solicitante
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
            except Exception:
                pass
            db.commit()
            return _request_out(req)
    return _request_out(req)


@router.post("/requests/{request_id}/cancel", summary="Cancelar solicitud")
def cancel_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.billing_reports import ApprovalRequest
    req = _scope_request_query(db.query(ApprovalRequest), db, current_user).filter(ApprovalRequest.id == request_id).first()
    if not req: raise HTTPException(404)
    if req.requested_by != current_user.id and current_user.role.value not in ("admin", "pm"):
        raise HTTPException(403)
    req.status = "cancelled"
    req.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get("/stats", summary="Estadísticas de aprobaciones")
def approval_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.billing_reports import ApprovalRequest
    q = _scope_request_query(db.query(ApprovalRequest), db, current_user)
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
