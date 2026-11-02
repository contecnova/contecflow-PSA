"""Aprobacion de los servicios del catalogo.

Auditoria 2026-11: `ServiceItem.requires_approval` y `approval_user_id` se
guardaban y nada los comprobaba; una peticion «requiere aprobacion» se
atendia como cualquier otra. Ahora:

- el ticket de un servicio que la pide nace con `approval_status = pending` y
  una fila en `sd_ticket_approvals` para su aprobador, que recibe el aviso;
- mientras esta pendiente no se puede empezar, resolver ni cerrar (si
  cancelar);
- el aprobador —o un administrador— decide; rechazar cancela el ticket con el
  motivo, y el solicitante recibe la decision.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.service_desk import ServiceItem, Ticket, TicketApproval
from app.models.user import User, UserRole
from app.services.service_desk.ticket_events import registrar

PENDIENTE, APROBADO, RECHAZADO = "pending", "approved", "rejected"

#: Estados a los que no se puede pasar mientras la aprobacion esta pendiente.
BLOQUEADOS = {"in_progress", "resolved", "closed", "pending_client", "pending_third"}


def exigir_aprobador(db: Session, requires_approval: Optional[bool], approval_user_id: Optional[str]) -> None:
    """Un servicio que pide aprobacion tiene que decir quien aprueba."""
    if not requires_approval:
        return
    if not approval_user_id:
        raise HTTPException(422, "Un servicio que requiere aprobación necesita un aprobador")
    u = db.query(User).filter(User.id == approval_user_id, User.is_active == True).first()  # noqa: E712
    if u is None:
        raise HTTPException(422, "El aprobador no existe o no está activo")


def solicitar_si_hace_falta(db: Session, ticket: Ticket, service_item: Optional[ServiceItem]) -> Optional[TicketApproval]:
    """Si el servicio pide aprobacion, la deja pendiente y avisa al aprobador."""
    if service_item is None or not service_item.requires_approval:
        return None
    ticket.approval_status = PENDIENTE
    aprobacion = TicketApproval(
        organization_id=ticket.organization_id, ticket_id=ticket.id,
        approver_user_id=service_item.approval_user_id, status=PENDIENTE,
    )
    db.add(aprobacion)
    registrar(db, ticket, "approval_requested",
              {"approver_ids": [service_item.approval_user_id] if service_item.approval_user_id else [],
               "service": service_item.name})
    return aprobacion


def pendiente(db: Session, ticket_id: str) -> Optional[TicketApproval]:
    return db.query(TicketApproval).filter(
        TicketApproval.ticket_id == ticket_id, TicketApproval.status == PENDIENTE,
    ).first()


def exigir_aprobado(ticket: Ticket, nuevo_estado: Optional[str]) -> None:
    """No se trabaja un ticket cuya aprobacion sigue pendiente."""
    if ticket.approval_status == PENDIENTE and nuevo_estado in BLOQUEADOS:
        raise HTTPException(409, "El ticket está pendiente de aprobación")


def decidir(db: Session, ticket: Ticket, usuario: User, decision: str, comentario: Optional[str]) -> TicketApproval:
    """Aprueba o rechaza. Solo el aprobador o un administrador."""
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    if decision not in (APROBADO, RECHAZADO):
        raise HTTPException(422, "La decisión es approved o rejected")
    aprobacion = pendiente(db, ticket.id)
    if aprobacion is None:
        raise HTTPException(409, "El ticket no tiene ninguna aprobación pendiente")
    es_admin = getattr(usuario.role, "value", usuario.role) == UserRole.admin.value or usuario.is_superadmin
    if aprobacion.approver_user_id != usuario.id and not es_admin:
        raise HTTPException(403, "Solo el aprobador puede decidir")
    if decision == RECHAZADO and not (comentario or "").strip():
        raise HTTPException(422, "Rechazar pide el motivo: es lo que recibe el solicitante")

    aprobacion.status = decision
    aprobacion.comment = (comentario or "").strip() or None
    aprobacion.decided_by_user_id = usuario.id
    aprobacion.decided_at = datetime.now(timezone.utc)
    ticket.approval_status = decision
    if decision == RECHAZADO:
        ticket.resolution = aprobacion.comment
        apply_ticket_update(db, ticket, ticket.id, TicketUpdateIn(status="cancelled"),
                            current_user_id=usuario.id, old_assigned_to=ticket.assigned_to_user_id,
                            old_support_level=ticket.support_level)
    registrar(db, ticket, "approval_decided", {"decision": decision, "note": aprobacion.comment},
              actor_user_id=usuario.id)
    return aprobacion


def serializar(a: Optional[TicketApproval]) -> Optional[dict]:
    if a is None:
        return None
    return {
        "id": a.id, "status": a.status, "comment": a.comment,
        "approver_user_id": a.approver_user_id,
        "approver_name": a.approver.full_name if a.approver else None,
        "decided_by_name": a.decided_by.full_name if a.decided_by else None,
        "decided_at": a.decided_at.isoformat() if a.decided_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def ultima(db: Session, ticket_id: str) -> Optional[TicketApproval]:
    return (db.query(TicketApproval).filter(TicketApproval.ticket_id == ticket_id)
            .order_by(TicketApproval.created_at.desc()).first())


def mis_pendientes(db: Session, usuario: User) -> list[dict]:
    filas = (db.query(TicketApproval, Ticket)
             .join(Ticket, Ticket.id == TicketApproval.ticket_id)
             .filter(TicketApproval.status == PENDIENTE, TicketApproval.approver_user_id == usuario.id)
             .order_by(TicketApproval.created_at).all())
    return [{
        "approval_id": a.id, "ticket_id": t.id, "number": t.number, "title": t.title,
        "requester_name": (t.requester_client.full_name if t.requester_client else
                           t.requester_user.full_name if t.requester_user else t.requester_name),
        "service_item_name": t.service_item.name if t.service_item else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    } for a, t in filas]
