"""
milestones.py — Flujo completo SOW → Completado → Aprobación → Factura automática.

Estados del flujo:
  pending          → milestone creado, pendiente de completar
  completed        → equipo marca como completado, espera aprobación
  pending_approval → solicitud de aprobación enviada al cliente/manager
  approved         → aprobado, listo para facturar
  rejected         → rechazado, vuelve a pending con motivo
  invoiced         → factura generada automáticamente
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.services.milestone_service import (
    complete_milestone as svc_complete_milestone,
    uncomplete_milestone as svc_uncomplete_milestone,
    request_milestone_approval,
    decide_milestone_approval,
    generate_milestone_invoice,
    list_milestones_by_project as svc_list_milestones_by_project,
    create_milestone as svc_create_milestone,
    get_milestone_by_id as svc_get_milestone_by_id,
    update_milestone_fields as svc_update_milestone_fields,
    delete_milestone as svc_delete_milestone,
    get_pending_milestones_dashboard as svc_get_pending_milestones_dashboard,
    serialize_milestone,
)
from app.schemas.milestones import (
    MilestoneIn,
    MilestoneApprovalRequestIn as ApprovalRequestIn,
    MilestoneApprovalDecisionIn as ApprovalDecisionIn,
)

router = APIRouter(tags=["milestones"])


# ── Helper output ──────────────────────────────────────────────────────────────
# Delegate to service
_ms_out = serialize_milestone


# ── CRUD básico ────────────────────────────────────────────────────────────────
@router.get("/project/{project_id}", summary="Listar milestones de un proyecto")
def list_milestones(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ms = svc_list_milestones_by_project(db, project_id)
    return [_ms_out(m, db) for m in ms]


@router.post("/project/{project_id}", summary="Crear milestone")
def create_milestone(
    project_id: str,
    payload: MilestoneIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    m = svc_create_milestone(db, project_id, **payload.model_dump())
    return _ms_out(m, db)


@router.patch("/{milestone_id}", summary="Actualizar milestone")
def update_milestone(
    milestone_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    m = svc_get_milestone_by_id(db, milestone_id)
    if not m: raise HTTPException(404)
    allowed = ["name", "description", "due_date", "billing_amount", "billing_pct", "sort_order"]
    m = svc_update_milestone_fields(db, m, {k: v for k, v in payload.items() if k in allowed})
    return _ms_out(m, db)


@router.delete("/{milestone_id}", summary="Eliminar milestone")
def delete_milestone(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    m = svc_get_milestone_by_id(db, milestone_id)
    if not m: raise HTTPException(404)
    if m.invoice_id:
        raise HTTPException(400, "No se puede eliminar un milestone ya facturado")
    svc_delete_milestone(db, m)
    return {"ok": True}


# ── Flujo: Completar ───────────────────────────────────────────────────────────
@router.post("/{milestone_id}/complete", summary="Marcar milestone como completado")
def complete_milestone(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    m = svc_complete_milestone(milestone_id, current_user, db)
    return _ms_out(m, db)


@router.post("/{milestone_id}/uncomplete", summary="Revertir completado")
def uncomplete_milestone(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    m = svc_uncomplete_milestone(milestone_id, current_user, db)
    return _ms_out(m, db)


# ── Flujo: Solicitar Aprobación ────────────────────────────────────────────────
@router.post("/{milestone_id}/request-approval", summary="Solicitar aprobación del milestone")
def request_approval(
    milestone_id: str,
    payload: ApprovalRequestIn = Body(default=ApprovalRequestIn()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    m = request_milestone_approval(milestone_id, payload.message, current_user, db)
    return {**_ms_out(m, db), "message": "Solicitud de aprobación enviada"}


# ── Flujo: Aprobar / Rechazar ──────────────────────────────────────────────────
@router.post("/{milestone_id}/approve", summary="Aprobar o rechazar milestone")
def approve_milestone(
    milestone_id: str,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    m = decide_milestone_approval(
        milestone_id, payload.approved, payload.rejection_reason, current_user, db
    )
    msg = "Milestone aprobado — puedes generar la factura" if payload.approved else "Milestone rechazado"
    return {**_ms_out(m, db), "message": msg}


# ── Flujo: Generar Factura ─────────────────────────────────────────────────────
@router.post("/{milestone_id}/generate-invoice", summary="Generar factura automáticamente para el milestone")
def generate_invoice(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    invoice_data = generate_milestone_invoice(milestone_id, current_user, db)
    m = svc_get_milestone_by_id(db, milestone_id)
    return {
        **_ms_out(m, db),
        "invoice": {
            "id": invoice_data["invoice_id"],
            "invoice_number": invoice_data["invoice_number"],
            "amount": invoice_data["amount"],
            "total_with_tax": invoice_data["total_with_tax"],
            "status": invoice_data["status"],
        },
        "message": f"Factura {invoice_data['invoice_number']} generada correctamente",
    }


# ── Dashboard de milestones pendientes ────────────────────────────────────────
@router.get("/dashboard/pending", summary="Milestones pendientes de acción en todos los proyectos")
def pending_milestones_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    ms, projects_map = svc_get_pending_milestones_dashboard(db)

    result = []
    for m in ms:
        proj = projects_map.get(m.project_id)
        result.append({
            **_ms_out(m, db),
            "project_name": proj.name if proj else "—",
            "project_code": getattr(proj, "code", "—"),
            "next_action": {
                "completed":         "request-approval",
                "pending_approval":  "approve",
                "approved":          "generate-invoice",
            }.get(m.billing_status, "—"),
        })
    return result
