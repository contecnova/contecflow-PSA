"""
approvals.py — Motor de aprobaciones multi-nivel configurables.

Soporta: timesheets, gastos, change requests, milestones, compras.
Flujo: request → step 1 → step 2 → ... → step N → decision final
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager, require_admin
from app.models.user import User, UserRole
from app.services.approval_engine import (
    create_approval_request,
    decide_approval_request,
    get_pending_for_user,
    list_workflows,
    create_workflow,
    get_workflow,
    update_workflow,
    delete_workflow,
    add_workflow_step,
    update_workflow_step,
    delete_workflow_step,
    list_approval_requests,
    cancel_approval_request,
    get_financial_audit_entries,
    get_approval_stats,
    process_approval_timeouts,
    serialize_step as _step_out,
    serialize_workflow as _workflow_out,
    serialize_approval_request as _request_out,
)
from app.schemas.approvals import WorkflowIn, StepIn, ApprovalRequestIn, DecisionIn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

_FINANCIAL_ENTITY_TYPES = {"timesheet", "expense", "milestone", "purchase", "invoice"}



# ── CRUD Workflows ─────────────────────────────────────────────────────────────
@router.get("/workflows", summary="Listar flujos de aprobación")
def list_workflows_endpoint(
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_workflow_out(w, include_steps=True) for w in list_workflows(db, entity_type=entity_type)]


@router.post("/workflows", summary="Crear flujo de aprobación")
def create_workflow_endpoint(
    payload: WorkflowIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    w = create_workflow(db, payload.model_dump())
    return _workflow_out(w, include_steps=True)


@router.get("/workflows/{workflow_id}", summary="Detalle de flujo")
def get_workflow_endpoint(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    w = get_workflow(db, workflow_id)
    if not w:
        raise HTTPException(404)
    return _workflow_out(w, include_steps=True)


@router.patch("/workflows/{workflow_id}", summary="Actualizar flujo")
def update_workflow_endpoint(
    workflow_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    w = update_workflow(db, workflow_id, payload)
    if not w:
        raise HTTPException(404)
    return _workflow_out(w, include_steps=True)


@router.delete("/workflows/{workflow_id}", summary="Eliminar flujo")
def delete_workflow_endpoint(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not delete_workflow(db, workflow_id):
        raise HTTPException(404)
    return {"ok": True}


# ── CRUD Steps ─────────────────────────────────────────────────────────────────
@router.post("/workflows/{workflow_id}/steps", summary="Añadir paso al flujo")
def add_step(
    workflow_id: str,
    payload: StepIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    s = add_workflow_step(db, workflow_id, payload.model_dump())
    if not s:
        raise HTTPException(404)
    return _step_out(s)


@router.patch("/workflows/{workflow_id}/steps/{step_id}", summary="Actualizar paso")
def update_step(
    workflow_id: str, step_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    s = update_workflow_step(db, workflow_id, step_id, payload)
    if not s:
        raise HTTPException(404)
    return _step_out(s)


@router.delete("/workflows/{workflow_id}/steps/{step_id}", summary="Eliminar paso")
def delete_step(
    workflow_id: str, step_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    if not delete_workflow_step(db, workflow_id, step_id):
        raise HTTPException(404)
    return {"ok": True}


# ── Requests ───────────────────────────────────────────────────────────────────
@router.get("/requests", summary="Solicitudes de aprobación — mis pendientes")
def list_requests_endpoint(
    status:      Optional[str] = Query(None),
    entity_type: Optional[str] = Query(None),
    mine:        bool           = Query(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Non-managers can only query their own requests
    if not mine and current_user.role not in (UserRole.admin, UserRole.pm, UserRole.hr):
        raise HTTPException(403, "Acceso denegado: solo managers pueden ver todas las solicitudes")
    return [_request_out(r) for r in list_approval_requests(db, current_user, status=status, entity_type=entity_type, mine=mine)]


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
    cancel_approval_request(db, request_id, current_user)
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
    req, entries = get_financial_audit_entries(db, request_id, current_user)
    if not req:
        raise HTTPException(404, "Solicitud no encontrada")
    if req.entity_type not in _FINANCIAL_ENTITY_TYPES:
        raise HTTPException(
            404,
            f"Esta solicitud es de tipo '{req.entity_type}', que no es una entidad financiera. "
            "El audit log financiero sólo existe para: " + ", ".join(sorted(_FINANCIAL_ENTITY_TYPES)),
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


# ── Timeout job ───────────────────────────────────────────────────────────────
@router.post(
    "/process-timeouts",
    summary="Procesar timeouts de aprobaciones vencidas (job manual/cron)",
)
def run_approval_timeouts(
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """
    Evalúa todas las solicitudes pendientes y aplica la acción configurada
    (escalar, auto-aprobar o rechazar) para los pasos que superaron su timeout.
    En producción lo ejecuta el scheduler periódicamente cada hora.
    """
    result = process_approval_timeouts(db)
    return result


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get("/stats", summary="Estadísticas de aprobaciones")
def approval_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return get_approval_stats(db, current_user)
