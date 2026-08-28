"""
milestone_service.py — Lógica de negocio para el flujo SOW → Completado → Factura.

Funciones exportadas:
  complete_milestone(milestone_id, current_user, db)
  uncomplete_milestone(milestone_id, current_user, db)
  request_milestone_approval(milestone_id, message, current_user, db)
  decide_milestone_approval(milestone_id, approved, rejection_reason, current_user, db)
  generate_milestone_invoice(milestone_id, current_user, db)
  compute_billing_amount(milestone, db) -> float | None
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.numbering import next_numbered_code

from app.core.config import settings
from app.db.transactions import atomic
from app.models.user import User
from app.models.billing_reports import Invoice, InvoiceLine
from app.models.financial import ProjectMilestone
from app.models.pipeline import Contract
from app.models.project import Project
from app.models.project import Project as Proj
from app.services.notifications import notify_user
from app.core import timeutil

logger = logging.getLogger(__name__)
from fastapi import HTTPException


# ── CRUD helpers ──────────────────────────────────────────────────────────────

def list_milestones_by_project(db: Session, project_id: str):
    return (
        db.query(ProjectMilestone)
        .filter(ProjectMilestone.project_id == project_id, ProjectMilestone.is_active == True)
        .order_by(ProjectMilestone.sort_order, ProjectMilestone.due_date)
        .all()
    )


def create_milestone(db: Session, project_id: str, **kwargs):
    m = ProjectMilestone(
        id=str(uuid.uuid4()),
        project_id=project_id,
        billing_status="pending",
        **kwargs,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return m


def get_milestone_by_id(db: Session, milestone_id: str):
    return db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.is_active == True,
    ).first()


def update_milestone_fields(db: Session, m, fields: dict):
    for k, v in fields.items():
        setattr(m, k, v)
    db.commit()
    return m


def delete_milestone(db: Session, m) -> None:
    m.is_active = False
    db.commit()


def get_pending_milestones_dashboard(db: Session):
    ms = (
        db.query(ProjectMilestone)
        .filter(
            ProjectMilestone.is_active == True,
            ProjectMilestone.billing_status.in_(["completed", "pending_approval", "approved"]),
        )
        .order_by(ProjectMilestone.due_date)
        .all()
    )
    proj_ids = list({m.project_id for m in ms if m.project_id})
    projects_map = (
        {p.id: p for p in db.query(Project).filter(Project.id.in_(proj_ids)).all()}
        if proj_ids else {}
    )
    return ms, projects_map


# ── Amount helper ──────────────────────────────────────────────────────────────

def compute_billing_amount(milestone, db: Session) -> Optional[float]:
    if milestone.billing_amount:
        return milestone.billing_amount
    if milestone.billing_pct:
        proj = db.query(Project).filter(Project.id == milestone.project_id).first()
        if proj:
            total = (
                db.query(func.sum(Contract.amount)).filter(
                    Contract.project_id == proj.id
                ).scalar()
                or getattr(proj, "budget_amount", None)
                or 0
            )
            return round(total * milestone.billing_pct / 100, 2)
    return None


# ── Complete ───────────────────────────────────────────────────────────────────

def complete_milestone(milestone_id: str, current_user: User, db: Session):

    m = db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.is_active == True,
    ).first()
    if not m:
        raise HTTPException(404)
    if m.billing_status not in ("pending", "rejected"):
        raise HTTPException(400, f"No se puede completar en estado '{m.billing_status}'")

    m.is_completed = True
    m.completed_date = timeutil.today()
    m.completed_by = current_user.id
    m.billing_status = "completed"
    db.commit()

    # ASC 606: trigger revenue recognition for milestone-method contracts
    try:
        from app.services.revenue_service import recognize_on_milestone
        recognize_on_milestone(db, milestone_id, current_user.id)
    except Exception:
        logger.warning("Revenue recognition failed (non-blocking) for milestone=%s user=%s", milestone_id, current_user.id, exc_info=True)

    return m


def uncomplete_milestone(milestone_id: str, current_user: User, db: Session):

    m = db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.is_active == True,
    ).first()
    if not m:
        raise HTTPException(404)
    if m.billing_status in ("approved", "invoiced"):
        raise HTTPException(400, "No se puede revertir un milestone aprobado o facturado")

    m.is_completed = False
    m.completed_date = None
    m.completed_by = None
    m.billing_status = "pending"
    db.commit()
    return m


# ── Request approval ───────────────────────────────────────────────────────────

def request_milestone_approval(
    milestone_id: str,
    message: Optional[str],
    current_user: User,
    db: Session,
):

    m = db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.is_active == True,
    ).first()
    if not m:
        raise HTTPException(404)
    if m.billing_status != "completed":
        raise HTTPException(400, "El milestone debe estar completado antes de solicitar aprobación")

    m.billing_status = "pending_approval"
    m.approval_requested_at = datetime.now(timezone.utc)
    m.approval_requested_by = current_user.id
    m.approved_at = None
    m.rejected_at = None
    m.rejection_reason = None
    db.commit()

    _notify_pm_approval_requested(m, message, current_user, db)
    return m


# ── Approve / reject ───────────────────────────────────────────────────────────

def decide_milestone_approval(
    milestone_id: str,
    approved: bool,
    rejection_reason: Optional[str],
    current_user: User,
    db: Session,
):

    m = db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.is_active == True,
    ).first()
    if not m:
        raise HTTPException(404)
    if m.billing_status != "pending_approval":
        raise HTTPException(400, f"El milestone no está pendiente de aprobación (estado: {m.billing_status})")

    if approved:
        m.billing_status = "approved"
        m.approved_at = datetime.now(timezone.utc)
        m.approved_by = current_user.id
        m.rejected_at = None
        m.rejection_reason = None
        db.commit()
        _notify_requester_approved(m, current_user, db)
    else:
        if not rejection_reason:
            raise HTTPException(400, "Indica el motivo del rechazo")
        m.billing_status = "rejected"
        m.rejected_at = datetime.now(timezone.utc)
        m.rejected_by = current_user.id
        m.rejection_reason = rejection_reason
        m.approved_at = None
        db.commit()
        _notify_requester_rejected(m, rejection_reason, current_user, db)

    return m


# ── Generate invoice ───────────────────────────────────────────────────────────

def generate_milestone_invoice(milestone_id: str, current_user: User, db: Session) -> dict:

    # Lock the milestone row to prevent a double-invoice race (two concurrent
    # callers both passing the check-then-act on m.invoice_id). On Postgres this
    # serializes the requests via SELECT ... FOR UPDATE; sqlite ignores the lock
    # but the defensive re-check below still guards single-process test runs.
    m = db.query(ProjectMilestone).filter(
        ProjectMilestone.id == milestone_id,
        ProjectMilestone.is_active == True,
    ).with_for_update().first()
    if not m:
        raise HTTPException(404)
    if m.billing_status != "approved":
        raise HTTPException(400, f"El milestone debe estar aprobado para facturar (estado: {m.billing_status})")
    # Re-check under the lock: if a concurrent transaction already invoiced this
    # milestone, bail out idempotently.
    if m.invoice_id:
        raise HTTPException(400, "Este milestone ya tiene una factura generada")

    proj = db.query(Project).filter(Project.id == m.project_id).first()
    if not proj:
        raise HTTPException(404, "Proyecto no encontrado")

    amount = compute_billing_amount(m, db)
    if not amount or amount <= 0:
        raise HTTPException(400, "El milestone no tiene importe de facturación definido")

    invoice_num = _next_invoice_number(db)

    # Atomic: invoice header + line + milestone status flip must all land or none
    # do — a partial write would leave a milestone marked invoiced with no/empty
    # invoice (or vice versa). atomic() commits on success, rolls back on error.
    with atomic(db):
        inv = Invoice(
            id=str(uuid.uuid4()),
            project_id=proj.id,
            client_id=getattr(proj, "client_id", None),
            client_name=getattr(proj, "client_name", ""),
            number=invoice_num,
            issue_date=timeutil.today(),
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

        m.invoice_id = inv.id
        m.is_billed = True
        m.billed_at = timeutil.today()
        m.billing_status = "invoiced"

    return {
        "invoice_id": inv.id,
        "invoice_number": inv.number,
        "amount": inv.subtotal,
        "total_with_tax": inv.total,
        "status": inv.status,
    }


# ── Private helpers ────────────────────────────────────────────────────────────

def _next_invoice_number(db: Session) -> str:
    return next_numbered_code(
        db,
        "invoice",
        prefix="INV",
        padding=4,
        include_year=True,
        reset_yearly=True,
        year_separator="-",
    )


def _notify_pm_approval_requested(m, message, current_user, db: Session) -> None:

    try:
        proj = db.query(Proj).filter(Proj.id == m.project_id).first()
        if proj and proj.pm_id:
            notify_user(
                db,
                proj.pm_id,
                "system",
                f"Aprobación solicitada: {m.name}",
                (
                    f"{current_user.full_name} solicita aprobar el milestone '{m.name}' "
                    f"del proyecto {proj.code}."
                    + (f" Nota: {message}" if message else "")
                ),
                resource="milestones",
                resource_id=m.id,
            )
            db.commit()
    except Exception:
        logger.warning("Failed to notify approver(s) for milestone=%s", m.id, exc_info=True)
        db.rollback()


def _notify_requester_approved(m, current_user, db: Session) -> None:

    if m.approval_requested_by:
        try:
            notify_user(
                db,
                m.approval_requested_by,
                "expense_approved",
                f"Milestone aprobado: {m.name}",
                f"{current_user.full_name} ha aprobado el milestone. Ya puedes generar la factura.",
                resource="milestones",
                resource_id=m.id,
            )
            db.commit()
        except Exception:
            logger.warning("Failed to notify requester of approval for milestone=%s", m.id, exc_info=True)
            db.rollback()


def _notify_requester_rejected(m, rejection_reason: str, current_user, db: Session) -> None:

    if m.approval_requested_by:
        try:
            notify_user(
                db,
                m.approval_requested_by,
                "expense_rejected",
                f"Milestone rechazado: {m.name}",
                f"{current_user.full_name} rechazó el milestone. Motivo: {rejection_reason}",
                resource="milestones",
                resource_id=m.id,
            )
            db.commit()
        except Exception:
            logger.warning("Failed to notify requester of rejection for milestone=%s", m.id, exc_info=True)
            db.rollback()


# ── Serialization helper ───────────────────────────────────────────────────

def serialize_milestone(m, db=None) -> dict:
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
