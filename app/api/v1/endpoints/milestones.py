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
from sqlalchemy import func
from typing import Optional
from datetime import date, datetime, timezone
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user, require_any_manager
from app.models.user import User
from app.core.config import settings
from app.services.notifications import notify_user, notify_role
from app.services.milestone_service import (
    compute_billing_amount,
    complete_milestone as svc_complete_milestone,
    uncomplete_milestone as svc_uncomplete_milestone,
    request_milestone_approval,
    decide_milestone_approval,
    generate_milestone_invoice,
)

router = APIRouter(prefix="/milestones", tags=["milestones"])


# ── Schemas ────────────────────────────────────────────────────────────────────
class MilestoneIn(BaseModel):
    name:           str
    description:    Optional[str] = None
    due_date:       Optional[date] = None
    billing_amount: Optional[float] = None
    billing_pct:    Optional[float] = None
    sort_order:     int = 0

class ApprovalRequestIn(BaseModel):
    message: Optional[str] = None   # mensaje opcional al aprobador

class ApprovalDecisionIn(BaseModel):
    approved:         bool
    rejection_reason: Optional[str] = None


# ── Helper output ──────────────────────────────────────────────────────────────
def _ms_out(m, db=None) -> dict:
    billing_amount = compute_billing_amount(m, db) if db else m.billing_amount
    return {
        "id": m.id, "project_id": m.project_id,
        "name": m.name, "description": m.description,
        "due_date": str(m.due_date) if m.due_date else None,
        "sort_order": m.sort_order,
        "billing_status": m.billing_status or "pending",
        "is_completed": m.is_completed,
        "completed_date": str(m.completed_date) if m.completed_date else None,
        "billing_amount": billing_amount,
        "billing_pct": m.billing_pct,
        "is_billed": m.is_billed,
        "invoice_id": m.invoice_id,
        "approved_at": str(m.approved_at)[:16] if m.approved_at else None,
        "rejected_at": str(m.rejected_at)[:16] if m.rejected_at else None,
        "rejection_reason": m.rejection_reason,
        "approval_requested_at": str(m.approval_requested_at)[:16] if m.approval_requested_at else None,
    }


# ── CRUD básico ────────────────────────────────────────────────────────────────
@router.get("/project/{project_id}", summary="Listar milestones de un proyecto")
def list_milestones(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.financial import ProjectMilestone
    ms = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project_id
    ).order_by(ProjectMilestone.sort_order, ProjectMilestone.due_date).all()
    return [_ms_out(m, db) for m in ms]


@router.post("/project/{project_id}", summary="Crear milestone")
def create_milestone(
    project_id: str,
    payload: MilestoneIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.financial import ProjectMilestone
    import uuid
    m = ProjectMilestone(
        id=str(uuid.uuid4()),
        project_id=project_id,
        billing_status="pending",
        **payload.model_dump()
    )
    db.add(m); db.commit(); db.refresh(m)
    return _ms_out(m, db)


@router.patch("/{milestone_id}", summary="Actualizar milestone")
def update_milestone(
    milestone_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    allowed = ["name", "description", "due_date", "billing_amount", "billing_pct", "sort_order"]
    for k, v in payload.items():
        if k in allowed: setattr(m, k, v)
    db.commit()
    return _ms_out(m, db)


@router.delete("/{milestone_id}", summary="Eliminar milestone")
def delete_milestone(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    if m.invoice_id:
        raise HTTPException(400, "No se puede eliminar un milestone ya facturado")
    db.delete(m); db.commit()
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
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m:
        raise HTTPException(404)
    invoice_data = generate_milestone_invoice(milestone_id, current_user, db)
    db.refresh(m)
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
    from app.models.financial import ProjectMilestone
    from app.models.project import Project

    # Milestones que requieren acción
    ms = db.query(ProjectMilestone).filter(
        ProjectMilestone.billing_status.in_(["completed", "pending_approval", "approved"])
    ).order_by(ProjectMilestone.due_date).all()

    # Pre-load all projects in one query (avoids N+1)
    proj_ids = list({m.project_id for m in ms if m.project_id})
    projects_map = {
        p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()
    } if proj_ids else {}

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
