"""Herramientas de tickets de service desk."""
from __future__ import annotations

from app.models.service_desk._enums import ESTADOS_DE_TICKET_EN_CURSO
from app.models.service_desk import Ticket
from app.services.ai_chat.tool_execution.politica import buscar_persona


def _get_open_tickets(tool_input, db, user, now, is_financial_role):
    # Segunda auditoría 2026-11: los tickets que ve el usuario (`scope_ticket_query`).
    from app.services.service_desk.scoping import scope_ticket_query
    q = scope_ticket_query(db.query(Ticket), db, user).filter(Ticket.status.in_(ESTADOS_DE_TICKET_EN_CURSO))
    if tool_input.get("priority"): q = q.filter(Ticket.priority == tool_input["priority"])
    if tool_input.get("assignee_id"): q = q.filter(Ticket.assigned_to_user_id == tool_input["assignee_id"])
    tickets = q.order_by(Ticket.created_at.asc()).limit(tool_input.get("limit", 15)).all()
    return {"tickets": [{
        "id": t.id, "number": t.number, "title": t.title,
        "status": t.status, "priority": t.priority,
        "assignee_id": t.assigned_to_user_id,
        "created_at": str(t.created_at)[:10] if t.created_at else None,
    } for t in tickets]}


def _actualizar_ticket(db, user, ticket, **cambios) -> None:
    """El mismo camino que `PATCH /sd/tickets/{id}` (`apply_ticket_update`)."""
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update
    apply_ticket_update(
        db=db, ticket=ticket, ticket_id=ticket.id, payload=TicketUpdateIn(**cambios),
        current_user_id=user.id, old_assigned_to=ticket.assigned_to_user_id,
        old_support_level=ticket.support_level, organization_id=getattr(user, "organization_id", None),
    )
    db.flush()


def _update_ticket_status(tool_input, db, user, now, is_financial_role):
    # Segunda auditoría 2026-11: solo un ticket que ve (`get_scoped_ticket_or_404`)
    # y por el servicio del endpoint; antes, cualquiera de la empresa.
    from app.services.service_desk.scoping import get_scoped_ticket_or_404
    ticket = get_scoped_ticket_or_404(db, user, tool_input["ticket_id"])
    cambios = {}
    if tool_input.get("status"): cambios["status"] = tool_input["status"]
    if tool_input.get("assignee_name"):
        agente = buscar_persona(db, user, tool_input["assignee_name"])
        if agente: cambios["assigned_to_user_id"] = agente.id
    _actualizar_ticket(db, user, ticket, **cambios)
    return {"ok": True, "ticket_id": ticket.id, "new_status": ticket.status}


def _reassign_tickets(tool_input, db, user, now, is_financial_role):
    from app.services.service_desk.scoping import scope_ticket_query
    from_user = buscar_persona(db, user, tool_input["from_user_name"])
    to_user   = buscar_persona(db, user, tool_input["to_user_name"])
    if not from_user: return {"error": f"Usuario no encontrado: {tool_input['from_user_name']}"}
    if not to_user:   return {"error": f"Usuario no encontrado: {tool_input['to_user_name']}"}
    tickets = scope_ticket_query(db.query(Ticket), db, user).filter(
        Ticket.assigned_to_user_id == from_user.id, Ticket.status.in_(ESTADOS_DE_TICKET_EN_CURSO)
    ).all()
    for t in tickets:
        _actualizar_ticket(db, user, t, assigned_to_user_id=to_user.id)
    return {"ok": True, "reassigned_count": len(tickets),
            "from": from_user.full_name, "to": to_user.full_name}


HANDLERS = {
    "get_open_tickets": _get_open_tickets,
    "update_ticket_status": _update_ticket_status,
    "reassign_tickets": _reassign_tickets,
}
