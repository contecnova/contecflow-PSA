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

from sqlalchemy.orm import Session

from app.models.service_desk import ServiceItem, Ticket, TicketApproval
from app.models.user import User, UserRole
from app.services.service_desk.ticket_events import registrar
from app.core.errores import ErrorDeDominio
from app.core.codigos_de_error import error

PENDIENTE, APROBADO, RECHAZADO = "pending", "approved", "rejected"

#: Estados a los que no se puede pasar mientras la aprobacion esta pendiente.
BLOQUEADOS = {"in_progress", "resolved", "closed", "pending_client", "pending_third"}


def exigir_aprobador(db: Session, requires_approval: Optional[bool], approval_user_id: Optional[str]) -> None:
    """Un servicio que pide aprobacion tiene que decir quien aprueba."""
    if not requires_approval:
        return
    if not approval_user_id:
        raise error(422, "catalogo_servicio_sin_aprobador")
    u = db.query(User).filter(User.id == approval_user_id, User.is_active == True).first()  # noqa: E712
    if u is None:
        raise error(422, "aprobador_no_valido")


TIPO_EN_EL_MOTOR = "catalog_request"


def exigir_flujo(db: Session, workflow_id: Optional[str]) -> None:
    """Modo `engine`: el flujo elegido existe y esta activo, o hay uno por
    defecto activo para `catalog_request` (o politicas que pidan niveles)."""
    from app.models.billing_reports import ApprovalWorkflow
    if workflow_id:
        if db.query(ApprovalWorkflow.id).filter(ApprovalWorkflow.id == workflow_id,
                                                ApprovalWorkflow.is_active.is_(True)).first() is None:
            raise error(422, "flujo_aprobacion_no_valido")
        return
    if db.query(ApprovalWorkflow.id).filter(ApprovalWorkflow.entity_type == TIPO_EN_EL_MOTOR,
                                            ApprovalWorkflow.is_active.is_(True)).first() is None:
        raise error(422, "catalogo_sin_flujo_activo")


def _abrir_en_el_motor(db: Session, ticket: Ticket, item: ServiceItem) -> str:
    """Abre la solicitud de varios niveles. Devuelve `opened`, `auto_approved`
    o `not_opened` (sin solicitante interno o sin flujo que encaje).

    Se abre dentro de un punto de guardado: si el motor falla, el ticket se
    crea igual y la aprobacion cae en el aprobador del servicio.
    """
    import logging
    from app.schemas.approvals import ApprovalRequestIn
    from app.services.approval_engine.requests import create_approval_request

    solicitante = db.get(User, ticket.requester_user_id or ticket.created_by_user_id or "") \
        if (ticket.requester_user_id or ticket.created_by_user_id) else None
    if solicitante is None:
        return "not_opened"
    contexto = {
        "service_item_id": item.id, "service_item": item.name, "category": item.category_id,
        "priority": getattr(ticket.priority, "value", ticket.priority),
        "ticket_type": getattr(ticket.ticket_type, "value", ticket.ticket_type),
        "client_id": ticket.client_id, "department": solicitante.department,
    }
    evaluacion = None
    try:
        from app.services.politicas.motor import evaluar, resumen as resumen_de_politica
        evaluacion = evaluar(db, "catalogo", ticket, organization_id=ticket.organization_id)
        contexto = {**(evaluacion.get("contexto") or {}), **contexto,
                    "_politica": {**resumen_de_politica(evaluacion), "dominio": "catalogo"}}
    except ErrorDeDominio:
        raise
    except Exception:
        logging.getLogger(__name__).warning("politicas del catalogo no evaluadas", exc_info=True)
    resultado = (evaluacion or {}).get("resultado") or {}
    if resultado.get("decision") == "block":
        motivo = "; ".join(b.get("mensaje") or "" for b in resultado.get("bloqueos") or [])
        raise error(422, "bloqueado_por_politica", detail=motivo or "Lo impide una política del catálogo",
                    motivo=motivo)
    try:
        with db.begin_nested():
            req = create_approval_request(
                ApprovalRequestIn(entity_type=TIPO_EN_EL_MOTOR, entity_id=ticket.id,
                                  entity_summary=f"{ticket.number} · {item.name}"[:500], context=contexto,
                                  workflow_id=item.approval_workflow_id),
                db, solicitante, confirmar=False, politicas=resultado or None, de_confianza=True)
    except ErrorDeDominio:
        return "not_opened"
    estado = (req or {}).get("status") if isinstance(req, dict) else getattr(req, "status", None)
    return "auto_approved" if estado == APROBADO else "opened"


def solicitar_si_hace_falta(db: Session, ticket: Ticket, service_item: Optional[ServiceItem]):
    """Si el servicio pide aprobacion, la deja pendiente y avisa al aprobador.

    Modo `engine` (mejoras de mercado 16-11-2026): la aprobacion de varios
    niveles es la del motor comun (bandeja de Aprobaciones); su decision final
    vuelve aqui por `aplicar_decision_del_motor`. Si el motor no la abre, cae
    en el aprobador del servicio o, sin el, en los administradores.
    """
    if service_item is None or not service_item.requires_approval:
        return None
    if (service_item.approval_mode or "single") == "engine":
        ticket.approval_status = PENDIENTE
        db.flush()
        resultado = _abrir_en_el_motor(db, ticket, service_item)
        if resultado == "auto_approved":
            ticket.approval_status = APROBADO
            return None
        if resultado == "opened":
            registrar(db, ticket, "approval_requested",
                      {"approver_ids": [], "service": service_item.name, "engine": True})
            # No es None: quien llama no crea las tareas hasta que se apruebe.
            return PENDIENTE
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
        raise error(409, "ticket_pendiente_aprobacion")


def decidir(db: Session, ticket: Ticket, usuario: User, decision: str, comentario: Optional[str]) -> TicketApproval:
    """Aprueba o rechaza. Solo el aprobador o un administrador."""
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    if decision not in (APROBADO, RECHAZADO):
        raise error(422, "decision_aprobada_o_rechazada", detail="La decisión es approved o rejected")
    aprobacion = pendiente(db, ticket.id)
    if aprobacion is None:
        raise error(409, "ticket_sin_aprobacion_pendiente")
    es_admin = getattr(usuario.role, "value", usuario.role) == UserRole.admin.value or usuario.is_superadmin
    if aprobacion.approver_user_id != usuario.id and not es_admin:
        raise error(403, "solo_aprobador_decide")
    # Segunda auditoría 2026-11: quien pide el servicio no se lo aprueba (SoD),
    # tampoco un administrador.
    from app.services.approval_engine._base import exigir_que_no_sea_suyo
    exigir_que_no_sea_suyo(db, ticket.requester_user_id, usuario, "catalog_request", ticket.id)
    if decision == RECHAZADO and not (comentario or "").strip():
        raise error(422, "motivo_de_rechazo_obligatorio", detail="Rechazar pide el motivo: es lo que recibe el solicitante")

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
    if decision == APROBADO:
        from app.services.service_desk.fulfillment_service import crear_tareas
        crear_tareas(db, ticket, db.get(ServiceItem, ticket.service_item_id) if ticket.service_item_id else None)
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


def aplicar_decision_del_motor(db: Session, ticket_id: str, decision: str, actor, nota: Optional[str]) -> None:
    """Decision final del motor de aprobaciones sobre una peticion del catalogo
    (`approval_engine.fuentes.aplicar`, tipo `catalog_request`).

    Aprobada: se libera y nacen sus tareas. Rechazada: se cancela con el motivo.
    Solo si sigue pendiente (si se cancelo antes, no se toca).
    """
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    ticket = db.get(Ticket, ticket_id)
    if ticket is None or ticket.approval_status != PENDIENTE:
        return
    aprobado = decision == APROBADO
    ticket.approval_status = APROBADO if aprobado else RECHAZADO
    if not aprobado:
        ticket.resolution = (nota or "").strip() or None
        apply_ticket_update(db, ticket, ticket.id, TicketUpdateIn(status="cancelled"),
                            current_user_id=getattr(actor, "id", None), old_assigned_to=ticket.assigned_to_user_id,
                            old_support_level=ticket.support_level)
    registrar(db, ticket, "approval_decided", {"decision": ticket.approval_status, "note": nota, "engine": True},
              actor_user_id=getattr(actor, "id", None))
    if aprobado:
        from app.services.service_desk.fulfillment_service import crear_tareas
        crear_tareas(db, ticket, db.get(ServiceItem, ticket.service_item_id) if ticket.service_item_id else None)
    db.commit()
