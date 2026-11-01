"""Herramientas de tickets de service desk."""
from __future__ import annotations

from app.models.service_desk import Ticket
from app.models.user import User


def _get_open_tickets(tool_input, db, user, now, is_financial_role):
    q = db.query(Ticket).filter(Ticket.status.in_(["new","assigned","in_progress"]))
    if tool_input.get("priority"): q = q.filter(Ticket.priority == tool_input["priority"])
    if tool_input.get("assignee_id"): q = q.filter(Ticket.assigned_to_user_id == tool_input["assignee_id"])
    tickets = q.order_by(Ticket.created_at.asc()).limit(tool_input.get("limit", 15)).all()
    return {"tickets": [{
        "id": t.id, "number": t.number, "title": t.title,
        "status": t.status, "priority": t.priority,
        "assignee_id": t.assigned_to_user_id,
        "created_at": str(t.created_at)[:10] if t.created_at else None,
    } for t in tickets]}


def _update_ticket_status(tool_input, db, user, now, is_financial_role):
    ticket = db.query(Ticket).filter(Ticket.id == tool_input["ticket_id"]).first()
    if not ticket: return {"error": "Ticket no encontrado"}
    if tool_input.get("status"): ticket.status = tool_input["status"]
    if tool_input.get("assignee_name"):
        agent = db.query(User).filter(
            User.full_name.ilike(f"%{tool_input['assignee_name']}%")
        ).first()
        if agent: ticket.assigned_to_user_id = agent.id
    db.flush()
    return {"ok": True, "ticket_id": ticket.id, "new_status": ticket.status}


def _reassign_tickets(tool_input, db, user, now, is_financial_role):
    from_user = db.query(User).filter(User.full_name.ilike(f"%{tool_input['from_user_name']}%")).first()
    to_user   = db.query(User).filter(User.full_name.ilike(f"%{tool_input['to_user_name']}%")).first()
    if not from_user: return {"error": f"Usuario no encontrado: {tool_input['from_user_name']}"}
    if not to_user:   return {"error": f"Usuario no encontrado: {tool_input['to_user_name']}"}
    tickets = db.query(Ticket).filter(
        Ticket.assigned_to_user_id == from_user.id, Ticket.status.in_(["new","assigned","in_progress"])
    ).all()
    for t in tickets: t.assigned_to_user_id = to_user.id
    db.flush()
    return {"ok": True, "reassigned_count": len(tickets),
            "from": from_user.full_name, "to": to_user.full_name}


HANDLERS = {
    "get_open_tickets": _get_open_tickets,
    "update_ticket_status": _update_ticket_status,
    "reassign_tickets": _reassign_tickets,
}
