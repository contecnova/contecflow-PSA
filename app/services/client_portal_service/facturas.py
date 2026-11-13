"""Facturas del cliente y enlaces publicos de estado del proyecto.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.models.billing_reports import Invoice
from app.models.billing_reports import InvoiceStatus
from app.models.client_portal import ClientMessage
from app.models.financial import ProjectMilestone
from app.models.project import Project as ProjectModel
from app.models.resources import Deliverable

from app.services.client_portal_service.autenticacion import (
    PORTAL_SHARE_LINK_EXPIRE_HOURS,
    create_portal_share_token,
    decode_portal_share_token,
)


# ── Invoices ──────────────────────────────────────────────────────────────────

# Revisión 2026-11. Medido antes: el portal enseñaba también los borradores
# (internos hasta emitirse) sin mirar `can_view_budget`, y aprobar un borrador
# desde el portal lo marcaba como enviado. Ahora el cliente sólo ve y decide
# sobre facturas emitidas, y sólo con ese permiso; su decisión no cambia el
# estado de la factura, queda en `client_approval_status` y en las notas.
_FACTURAS_DEL_CLIENTE = (InvoiceStatus.sent, InvoiceStatus.overdue, InvoiceStatus.paid)


def list_client_invoices(status: Optional[str], current_client, db: Session) -> list:

    accessible = current_client.get_project_ids()
    if not accessible or not current_client.can_view_budget:
        return []
    q = db.query(Invoice).filter(Invoice.project_id.in_(accessible), Invoice.status.in_(_FACTURAS_DEL_CLIENTE))
    if status:
        q = q.filter(Invoice.status == status)
    invoices = q.order_by(Invoice.issue_date.desc()).limit(200).all()
    return [{
        "id": i.id, "number": i.number, "project_id": i.project_id,
        "client_name": i.client_name, "status": i.status.value if hasattr(i.status, "value") else str(i.status),
        "subtotal": i.subtotal, "tax_amount": i.tax_amount, "total": i.total,
        "currency": i.currency,
        "issue_date": str(i.issue_date) if i.issue_date else None,
        "due_date": str(i.due_date) if i.due_date else None,
        "paid_date": str(i.paid_date) if i.paid_date else None,
        "notes": i.notes,
        # Auditoria 2026-11: la pantalla mostraba Aprobar/Rechazar solo con este
        # campo en «pending», y no existia: los botones no salian nunca.
        "client_approval_status": i.client_approval_status or (
            "pending" if getattr(i.status, "value", i.status) in ("sent", "overdue") else None),
    } for i in invoices]


def approve_client_invoice(invoice_id: str, approved: bool, reason: str, current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    if not accessible:
        raise ValueError("No hay proyectos asignados a este cliente")
    inv = db.query(Invoice).filter(
        Invoice.id == invoice_id,
        Invoice.project_id.in_(accessible),
        Invoice.status.in_((InvoiceStatus.sent, InvoiceStatus.overdue)),
    ).first()
    if not inv or not current_client.can_view_budget:
        raise ValueError("Factura no encontrada")

    action = "APROBADA" if approved else "RECHAZADA"
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    note_line = f"[{stamp}] Cliente {current_client.full_name} ({current_client.email}) {action}."
    if reason:
        note_line += f" Motivo: {reason}"

    existing = (inv.internal_notes or "").strip()
    inv.internal_notes = f"{existing}\n{note_line}".strip() if existing else note_line
    inv.client_approval_status = "approved" if approved else "rejected"

    db.add(ClientMessage(
        project_id=inv.project_id,
        subject=f"Factura {inv.number} {action.lower()}",
        body=note_line,
        sender_client_id=current_client.id,
        is_read_by_team=False,
        is_read_by_client=True,
    ))
    db.commit()
    return {
        "ok": True, "invoice_id": inv.id, "approved": approved,
        "status": inv.status.value if hasattr(inv.status, "value") else str(inv.status),
    }


# ── Share links ───────────────────────────────────────────────────────────────

def create_public_share_link(project_id: str, db: Session) -> dict:

    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    token = create_portal_share_token(project_id)
    return {
        "ok": True, "token": token,
        "url": f"/portal/view/{token}",
        "expires_in_hours": PORTAL_SHARE_LINK_EXPIRE_HOURS,
    }


def view_public_project_status(token: str, db: Session) -> dict:

    project_id = decode_portal_share_token(token)
    if not project_id:
        raise ValueError("Token inválido o expirado")
    project = db.query(ProjectModel).filter(ProjectModel.id == project_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    # Segunda auditoría 2026-11 (#10): organización desactivada → 403.
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, getattr(project, "organization_id", None))
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project.id
    ).order_by(ProjectMilestone.sort_order).all()
    deliverables = db.query(Deliverable).filter(
        Deliverable.project_id == project.id
    ).order_by(Deliverable.sort_order).all()
    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
        },
        "milestones": [{
            "id": m.id, "name": m.name,
            "due_date": str(m.due_date) if m.due_date else None,
            "is_completed": m.is_completed,
        } for m in milestones],
        "deliverables": [{
            "id": d.id, "name": d.name, "status": d.status,
            "planned_date": str(d.planned_date) if d.planned_date else None,
            "delivered_date": str(d.delivered_date) if d.delivered_date else None,
        } for d in deliverables],
    }
