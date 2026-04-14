from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket
from app.models.user import User, UserRole


def build_ticket_list_query(
    db: Session,
    current_user: User,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    group_id: Optional[str] = None,
    project_id: Optional[str] = None,
    support_level: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    search: Optional[str] = None,
):
    """Build service-desk tickets query with scoping and all list filters."""
    q = db.query(Ticket).options(
        joinedload(Ticket.requester_user),
        joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
        joinedload(Ticket.ci),
        joinedload(Ticket.client),
    )

    if not current_user.is_superadmin:
        if current_user.role in (UserRole.employee, UserRole.subcontractor):
            q = q.filter(Ticket.requester_user_id == current_user.id)
        elif current_user.organization_id:
            org_user_ids = db.query(User.id).filter(
                User.organization_id == current_user.organization_id
            ).scalar_subquery()
            q = q.filter(
                or_(
                    Ticket.requester_user_id.in_(org_user_ids),
                    Ticket.assigned_to_user_id.in_(org_user_ids),
                )
            )

    if status:
        q = q.filter(Ticket.status == status)
    if priority:
        q = q.filter(Ticket.priority == priority)
    if ticket_type:
        q = q.filter(Ticket.ticket_type == ticket_type)
    if assigned_to:
        q = q.filter(Ticket.assigned_to_user_id == assigned_to)
    if group_id:
        q = q.filter(Ticket.assigned_group_id == group_id)
    if project_id:
        q = q.filter(Ticket.project_id == project_id)
    if support_level:
        q = q.filter(Ticket.support_level == support_level)
    if sla_breached:
        now = datetime.now(timezone.utc)
        q = q.filter(
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
            or_(Ticket.sla_response_due < now, Ticket.sla_resolution_due < now),
        )
    if search:
        q = q.filter(or_(Ticket.number.ilike(f"%{search}%"), Ticket.title.ilike(f"%{search}%")))

    return q
