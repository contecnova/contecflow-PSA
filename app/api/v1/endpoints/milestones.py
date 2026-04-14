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
    # Calcular billing_amount desde pct si hace falta
    billing_amount = m.billing_amount
    if not billing_amount and m.billing_pct and db:
        from app.models.project import Project
        from app.models.pipeline import Contract
        proj = db.query(Project).filter(Project.id == m.project_id).first()
        if proj:
            total = db.query(func.sum(Contract.amount)).filter(
                Contract.project_id == proj.id
            ).scalar() or proj.budget_amount or 0
            billing_amount = round(total * m.billing_pct / 100, 2)

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
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    if m.billing_status not in ("pending", "rejected"):
        raise HTTPException(400, f"No se puede completar en estado '{m.billing_status}'")

    m.is_completed     = True
    m.completed_date   = date.today()
    m.completed_by     = current_user.id
    m.billing_status   = "completed"
    db.commit()
    return _ms_out(m, db)


@router.post("/{milestone_id}/uncomplete", summary="Revertir completado")
def uncomplete_milestone(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    if m.billing_status in ("approved", "invoiced"):
        raise HTTPException(400, "No se puede revertir un milestone aprobado o facturado")

    m.is_completed   = False
    m.completed_date = None
    m.completed_by   = None
    m.billing_status = "pending"
    db.commit()
    return _ms_out(m, db)


# ── Flujo: Solicitar Aprobación ────────────────────────────────────────────────
@router.post("/{milestone_id}/request-approval", summary="Solicitar aprobación del milestone")
def request_approval(
    milestone_id: str,
    payload: ApprovalRequestIn = Body(default=ApprovalRequestIn()),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    if m.billing_status != "completed":
        raise HTTPException(400, "El milestone debe estar completado antes de solicitar aprobación")

    m.billing_status          = "pending_approval"
    m.approval_requested_at   = datetime.now(timezone.utc)
    m.approval_requested_by   = current_user.id
    m.approved_at             = None
    m.rejected_at             = None
    m.rejection_reason        = None
    db.commit()

    # Notificar al manager del proyecto
    from app.models.project import Project as Proj
    proj = db.query(Proj).filter(Proj.id == m.project_id).first()
    if proj and proj.pm_id:
        try:
            notify_user(
                db, proj.pm_id,
                "system",
                f"Aprobación solicitada: {m.name}",
                f"{current_user.full_name} solicita aprobar el milestone '{m.name}' del proyecto {proj.code}."
                + (f" Nota: {payload.message}" if payload.message else ""),
                resource="milestones",
                resource_id=m.id,
            )
            db.commit()
        except Exception:
            db.rollback()  # notification failure must not roll back the approval state

    return {**_ms_out(m, db), "message": "Solicitud de aprobación enviada"}


# ── Flujo: Aprobar / Rechazar ──────────────────────────────────────────────────
@router.post("/{milestone_id}/approve", summary="Aprobar o rechazar milestone")
def approve_milestone(
    milestone_id: str,
    payload: ApprovalDecisionIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.financial import ProjectMilestone
    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    if m.billing_status != "pending_approval":
        raise HTTPException(400, f"El milestone no está pendiente de aprobación (estado: {m.billing_status})")

    if payload.approved:
        m.billing_status = "approved"
        m.approved_at    = datetime.now(timezone.utc)
        m.approved_by    = current_user.id
        m.rejected_at    = None
        m.rejection_reason = None
        db.commit()
        # Notificar al solicitante
        if m.approval_requested_by:
            try:
                notify_user(
                    db, m.approval_requested_by,
                    "expense_approved",
                    f"Milestone aprobado: {m.name}",
                    f"{current_user.full_name} ha aprobado el milestone. Ya puedes generar la factura.",
                    resource="milestones",
                    resource_id=m.id,
                )
                db.commit()
            except Exception:
                db.rollback()  # notification failure must not roll back approval
        return {**_ms_out(m, db), "message": "Milestone aprobado — puedes generar la factura"}
    else:
        if not payload.rejection_reason:
            raise HTTPException(400, "Indica el motivo del rechazo")
        m.billing_status   = "rejected"
        m.rejected_at      = datetime.now(timezone.utc)
        m.rejected_by      = current_user.id
        m.rejection_reason = payload.rejection_reason
        m.approved_at      = None
        db.commit()
        # Notificar al solicitante
        if m.approval_requested_by:
            try:
                notify_user(
                    db, m.approval_requested_by,
                    "expense_rejected",
                    f"Milestone rechazado: {m.name}",
                    f"{current_user.full_name} rechazó el milestone. Motivo: {payload.rejection_reason}",
                    resource="milestones",
                    resource_id=m.id,
                )
                db.commit()
            except Exception:
                db.rollback()  # notification failure must not roll back rejection
        return {**_ms_out(m, db), "message": "Milestone rechazado"}


# ── Flujo: Generar Factura ─────────────────────────────────────────────────────
@router.post("/{milestone_id}/generate-invoice", summary="Generar factura automáticamente para el milestone")
def generate_invoice(
    milestone_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    from app.models.financial import ProjectMilestone
    from app.models.billing_reports import Invoice, InvoiceLine
    from app.models.project import Project
    from app.models.pipeline import Contract
    import uuid

    m = db.query(ProjectMilestone).filter(ProjectMilestone.id == milestone_id).first()
    if not m: raise HTTPException(404)
    if m.billing_status != "approved":
        raise HTTPException(400, f"El milestone debe estar aprobado para facturar (estado: {m.billing_status})")
    if m.invoice_id:
        raise HTTPException(400, "Este milestone ya tiene una factura generada")

    proj = db.query(Project).filter(Project.id == m.project_id).first()
    if not proj: raise HTTPException(404, "Proyecto no encontrado")

    # Calcular importe
    amount = m.billing_amount
    if not amount and m.billing_pct:
        total_contract = db.query(func.sum(Contract.amount)).filter(
            Contract.project_id == proj.id
        ).scalar() or getattr(proj, 'budget_amount', 0) or 0
        amount = round(total_contract * m.billing_pct / 100, 2)

    if not amount or amount <= 0:
        raise HTTPException(400, "El milestone no tiene importe de facturación definido")

    # Número de factura — usa MAX para evitar race conditions con COUNT
    import re as _re
    from app.models.billing_reports import Invoice as Inv
    max_num_str = db.query(func.max(Inv.number)).scalar()
    if max_num_str:
        _m = _re.search(r"(\d+)$", max_num_str)
        next_num = (int(_m.group(1)) + 1) if _m else 1
    else:
        next_num = 1
    invoice_num = f"INV-{str(next_num).zfill(4)}"

    # Crear factura
    inv = Invoice(
        id=str(uuid.uuid4()),
        project_id=proj.id,
        client_id=getattr(proj, 'client_id', None),
        client_name=getattr(proj, 'client_name', ''),
        number=invoice_num,
        issue_date=date.today(),
        subtotal=amount,
        tax_rate=settings.DEFAULT_TAX_RATE,
        tax_amount=round(amount * settings.DEFAULT_TAX_RATE / 100, 2),
        total=round(amount * (1 + settings.DEFAULT_TAX_RATE / 100), 2),
        status="draft",
        notes=f"Factura por milestone: {m.name}",
        created_by=current_user.id,
    )
    db.add(inv)
    db.flush()

    # Línea de factura
    line = InvoiceLine(
        id=str(uuid.uuid4()),
        invoice_id=inv.id,
        description=f"Milestone: {m.name}",
        quantity=1.0,
        unit_price=amount,
        amount=amount,
        source_type="milestone",
        source_ids=f'["{m.id}"]',
    )
    db.add(line)

    # Actualizar milestone
    m.invoice_id     = inv.id
    m.is_billed      = True
    m.billed_at      = date.today()
    m.billing_status = "invoiced"

    db.commit()

    return {
        **_ms_out(m, db),
        "invoice": {
            "id": inv.id,
            "invoice_number": inv.number,
            "amount": inv.subtotal,
            "total_with_tax": inv.total,
            "status": inv.status,
        },
        "message": f"Factura {invoice_num} generada correctamente",
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
