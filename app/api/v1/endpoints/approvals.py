"""
approvals.py — Motor de aprobaciones multi-nivel configurables.

Soporta: timesheets, gastos, change requests, milestones, compras.
Flujo: request → step 1 → step 2 → ... → step N → decision final
"""
from fastapi import APIRouter, Depends, HTTPException, Body, Query
from sqlalchemy.orm import Session
from typing import Optional
import logging

from app.core.abac_enforce import enforce_abac
from app.db.session import get_db
from app.core.deps import get_current_user, require_admin, require_any_manager
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
    list_workflow_templates,
    create_workflow_from_template,
    simulate_workflow,
    validate_workflow,
    publish_workflow,
    clone_workflow_as_version,
    get_workflow_bottlenecks,
    get_approver_load,
    list_approval_groups,
    get_approval_group,
    create_approval_group,
    update_approval_group,
    delete_approval_group,
    serialize_approval_group as _group_out,
    serialize_step as _step_out,
    serialize_workflow as _workflow_out,
    serialize_approval_request as _request_out,
)
from app.schemas.approvals import WorkflowIn, StepIn, ApprovalRequestIn, DecisionIn
from app.core.responses import APIListResponse, APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])

_FINANCIAL_ENTITY_TYPES = {
    "timesheet", "expense", "milestone", "purchase", "invoice",
    "contract", "budget", "leave", "deliverable", "proposal",
    "subcontractor", "scope_change", "hire", "price_change",
}



# ── CRUD Workflows ─────────────────────────────────────────────────────────────
@router.get("/workflows", summary="Listar flujos de aprobación")
def list_workflows_endpoint(
    entity_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = [_workflow_out(w, include_steps=True) for w in list_workflows(db, entity_type=entity_type)]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/workflows", summary="Crear flujo de aprobación")
def create_workflow_endpoint(
    payload: WorkflowIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    w = create_workflow(db, payload.model_dump())
    return APIResponse.ok(data=_workflow_out(w, include_steps=True))


@router.get("/workflow-templates", summary="Listar plantillas de flujos")
def list_workflow_templates_endpoint(
    current_user: User = Depends(get_current_user),
):
    items = list_workflow_templates()
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/workflows/from-template", summary="Crear flujo desde plantilla")
def create_workflow_from_template_endpoint(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    template_id = payload.get("template_id")
    name = payload.get("name")
    if not template_id:
        raise HTTPException(400, "template_id es obligatorio")
    w = create_workflow_from_template(db, template_id, override_name=name)
    return APIResponse.ok(data=_workflow_out(w, include_steps=True))


@router.get("/workflows/{workflow_id}", summary="Detalle de flujo")
def get_workflow_endpoint(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    w = get_workflow(db, workflow_id)
    if not w:
        raise HTTPException(404)
    return APIResponse.ok(data=_workflow_out(w, include_steps=True))


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
    return APIResponse.ok(data=_workflow_out(w, include_steps=True))


@router.get("/workflows/{workflow_id}/validate", summary="Validar flujo")
def validate_workflow_endpoint(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=validate_workflow(db, workflow_id))


@router.post("/workflows/{workflow_id}/publish", summary="Publicar flujo")
def publish_workflow_endpoint(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    w = publish_workflow(db, workflow_id)
    return APIResponse.ok(data=_workflow_out(w, include_steps=True))


@router.post("/workflows/{workflow_id}/clone-version", summary="Clonar flujo como nueva versión")
def clone_workflow_version_endpoint(
    workflow_id: str,
    payload: dict = Body(default={}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    suffix = payload.get("suffix")
    w = clone_workflow_as_version(db, workflow_id, suffix=suffix)
    return APIResponse.ok(data=_workflow_out(w, include_steps=True))


@router.post("/simulate", summary="Simular selección y ruta de flujo")
def simulate_workflow_endpoint(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: sus hermanas del fichero usan esa guarda
):
    entity_type = payload.get("entity_type")
    context = payload.get("context") or {}
    if not entity_type:
        raise HTTPException(400, "entity_type es obligatorio")
    return APIResponse.ok(data=simulate_workflow(db, entity_type=entity_type, context=context))


@router.delete("/workflows/{workflow_id}", summary="Eliminar flujo")
def delete_workflow_endpoint(
    workflow_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "approval_workflow", workflow_id, action="delete")
    if not delete_workflow(db, workflow_id):
        raise HTTPException(404)
    return APIResponse.ok(data={"ok": True})


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
    return APIResponse.ok(data=_step_out(s))


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
    return APIResponse.ok(data=_step_out(s))


@router.delete("/workflows/{workflow_id}/steps/{step_id}", summary="Eliminar paso")
def delete_step(
    workflow_id: str, step_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "approval_workflow_step", step_id, action="delete")
    if not delete_workflow_step(db, workflow_id, step_id):
        raise HTTPException(404)
    return APIResponse.ok(data={"ok": True})


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
    items = [_request_out(r) for r in list_approval_requests(db, current_user, status=status, entity_type=entity_type, mine=mine)]
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/requests/pending-my-action", summary="Solicitudes que yo debo aprobar ahora")
def pending_my_action(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        pairs = get_pending_for_user(db, current_user)
        result = []
        for req, step in pairs:
            r = _request_out(req)
            r["step_name"] = step.name
            r["step_order"] = step.step_order
            result.append(r)
        return APIListResponse.ok(items=result, total=len(result))
    except Exception:
        logger.exception("pending-my-action failed for user_id=%s", getattr(current_user, "id", None))
        return APIListResponse.ok(items=[], total=0)


@router.post("/requests", summary="Crear solicitud de aprobación")
def create_request(
    payload: ApprovalRequestIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = create_approval_request(payload, db, current_user)
    return APIResponse.ok(data=_request_out(req))


@router.post("/requests/{request_id}/decide", summary="Aprobar, rechazar o delegar un paso")
def decide_request(
    request_id: str,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = decide_approval_request(
        request_id, payload.decision, payload.note, payload.delegate_to,
        db, current_user,
        attachment_url=getattr(payload, "attachment_url", None),
    )
    return APIResponse.ok(data=_request_out(req))


@router.post("/requests/{request_id}/cancel", summary="Cancelar solicitud")
def cancel_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cancel_approval_request(db, request_id, current_user)
    return APIResponse.ok(data={"ok": True})


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
    return APIResponse.ok(data={
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
    })


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
    return APIResponse.ok(data=result)


# ── Stats ──────────────────────────────────────────────────────────────────────
@router.get("/stats", summary="Estadísticas de aprobaciones")
def approval_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=get_approval_stats(db, current_user))


@router.get("/analytics/bottlenecks", summary="Cuellos de botella por flujo/paso")
def approval_bottlenecks(
    workflow_id: Optional[str] = Query(None),
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=get_workflow_bottlenecks(db, current_user, workflow_id=workflow_id, days=days))


@router.get("/analytics/approver-load", summary="Carga de trabajo por aprobador")
def approver_load_endpoint(
    days: int = Query(90, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    return APIResponse.ok(data=get_approver_load(db, current_user, days=days))


# ── Approver Groups ──────────────────────────────────────────────────────────────
@router.get("/groups", summary="Listar grupos de aprobadores")
def list_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = [_group_out(g) for g in list_approval_groups(db)]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/groups", summary="Crear grupo de aprobadores")
def create_group(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    g = create_approval_group(
        db,
        name=payload.get("name", "Nuevo grupo"),
        description=payload.get("description"),
        member_ids=payload.get("member_ids", []),
        created_by=current_user.id,
    )
    return APIResponse.ok(data=_group_out(g))


@router.get("/groups/{group_id}", summary="Detalle de grupo")
def get_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    g = get_approval_group(db, group_id)
    if not g:
        raise HTTPException(404)
    return APIResponse.ok(data=_group_out(g))


@router.patch("/groups/{group_id}", summary="Actualizar grupo")
def update_group(
    group_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    g = update_approval_group(
        db, group_id,
        name=payload.get("name"),
        description=payload.get("description"),
        member_ids=payload.get("member_ids"),
    )
    if not g:
        raise HTTPException(404)
    return APIResponse.ok(data=_group_out(g))


@router.delete("/groups/{group_id}", summary="Eliminar grupo")
def delete_group(
    group_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    enforce_abac(db, current_user, "approval_group", group_id, action="delete")
    if not delete_approval_group(db, group_id):
        raise HTTPException(404)
    return APIResponse.ok(data={"ok": True})
