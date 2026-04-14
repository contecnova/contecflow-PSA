from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import AgentGroup, AgentGroupMember, Ticket, TicketPriority, TicketStatus
from app.models.user import User


def get_group_with_members_or_404(db: Session, group_id: str) -> AgentGroup:
    group = db.query(AgentGroup).options(
        joinedload(AgentGroup.members).joinedload(AgentGroupMember.user)
    ).filter(AgentGroup.id == group_id).first()
    if not group:
        raise HTTPException(404)
    return group


def _count_open_tickets_for_user(db: Session, user_id: str) -> int:
    return db.query(func.count(Ticket.id)).filter(
        Ticket.assigned_to_user_id == user_id,
        Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
    ).scalar() or 0


def _count_p1_tickets_for_user(db: Session, user_id: str) -> int:
    return db.query(func.count(Ticket.id)).filter(
        Ticket.assigned_to_user_id == user_id,
        Ticket.priority == TicketPriority.p1_critical,
        Ticket.status.not_in([TicketStatus.resolved, TicketStatus.closed, TicketStatus.cancelled]),
    ).scalar() or 0


def build_group_workload_response(db: Session, group: AgentGroup, group_id: str) -> dict:
    result = []
    for member in group.members:
        open_count = _count_open_tickets_for_user(db, member.user_id)
        p1_count = _count_p1_tickets_for_user(db, member.user_id)
        result.append(
            {
                "user_id": member.user_id,
                "user_name": member.user.full_name if member.user else None,
                "is_lead": member.is_lead,
                "open_tickets": open_count,
                "p1_tickets": p1_count,
            }
        )

    result.sort(key=lambda x: x["open_tickets"])
    return {
        "group_id": group_id,
        "group_name": group.name,
        "agents": result,
        "recommended_assignee": result[0] if result else None,
    }


def get_group_workload_payload(db: Session, group_id: str) -> dict:
    group = get_group_with_members_or_404(db, group_id)
    return build_group_workload_response(db, group, group_id)


def get_ticket_for_auto_assign_or_404(db: Session, ticket_id: str) -> Ticket:
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404)
    if not ticket.assigned_group_id:
        raise HTTPException(400, "El ticket no tiene grupo asignado. Asigna un grupo primero.")
    return ticket


def get_group_members_or_400(db: Session, group_id: str):
    members = db.query(AgentGroupMember).filter(AgentGroupMember.group_id == group_id).all()
    if not members:
        raise HTTPException(400, "El grupo no tiene agentes")
    return members


def select_best_agent_id_by_open_load(db: Session, members) -> str:
    best_agent_id = None
    best_count = float("inf")
    for member in members:
        count = _count_open_tickets_for_user(db, member.user_id)
        if count < best_count:
            best_count = count
            best_agent_id = member.user_id
    return best_agent_id


def apply_auto_assignment(ticket: Ticket, best_agent_id: str):
    old_assignee = ticket.assigned_to_user_id
    ticket.assigned_to_user_id = best_agent_id
    if ticket.status == TicketStatus.new:
        ticket.status = TicketStatus.assigned
    return old_assignee


def prepare_auto_assignment(db: Session, ticket_id: str):
    ticket = get_ticket_for_auto_assign_or_404(db, ticket_id)
    members = get_group_members_or_400(db, ticket.assigned_group_id)
    best_agent_id = select_best_agent_id_by_open_load(db, members)
    old_assignee = apply_auto_assignment(ticket, best_agent_id)
    return ticket, old_assignee, best_agent_id


def get_user_name_by_id(db: Session, user_id: str):
    user = db.query(User).filter(User.id == user_id).first()
    return user.full_name if user else None
