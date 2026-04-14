import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models.service_desk import Ticket
from app.models.user import User
from app.services.service_desk.scoping import scope_ticket_query as _scope_ticket_query
from app.services.sla_service import (
    PRIORITY_LABELS,
    STATUS_LABELS,
    TYPE_LABELS,
    aware as _aware,
)


def get_service_desk_stats(db: Session, current_user: User, days: int) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    now = datetime.now(timezone.utc)

    scoped_tickets = _scope_ticket_query(db.query(Ticket), db, current_user)

    total = scoped_tickets.filter(Ticket.created_at >= since).count()
    open_count = scoped_tickets.filter(Ticket.status.notin_(["resolved", "closed", "cancelled"])).count()
    resolved = scoped_tickets.filter(
        Ticket.created_at >= since,
        Ticket.status.in_(["resolved", "closed"]),
    ).count()

    sla_breached = scoped_tickets.filter(
        Ticket.created_at >= since,
        Ticket.status.notin_(["cancelled"]),
        or_(
            and_(Ticket.sla_resolution_due < now, Ticket.status.notin_(["resolved", "closed"])),
            and_(
                Ticket.resolved_at != None,
                Ticket.sla_resolution_due != None,
                Ticket.resolved_at > Ticket.sla_resolution_due,
            ),
        ),
    ).count()
    sla_compliance = round((1 - sla_breached / max(total, 1)) * 100, 1)

    resolved_tickets = scoped_tickets.filter(Ticket.created_at >= since, Ticket.resolved_at != None).all()
    mttr = 0
    if resolved_tickets:
        hours_list = []
        for ticket in resolved_tickets:
            if ticket.resolved_at and ticket.created_at:
                try:
                    hours = (_aware(ticket.resolved_at) - _aware(ticket.created_at)).total_seconds() / 3600
                    hours_list.append(hours)
                except Exception as exc:
                    logging.getLogger(__name__).warning(
                        "Skipping ticket %s MTTR calc due invalid timestamp: %s",
                        ticket.id,
                        exc,
                    )
        total_hours = sum(hours_list)
        mttr = round(total_hours / max(len(hours_list), 1), 1)

    csat_tickets = scoped_tickets.filter(Ticket.created_at >= since, Ticket.csat_score != None).all()
    avg_csat = (
        round(sum(t.csat_score for t in csat_tickets) / max(len(csat_tickets), 1), 1)
        if csat_tickets
        else None
    )

    fcr_count = scoped_tickets.filter(
        Ticket.created_at >= since,
        Ticket.status.in_(["resolved", "closed"]),
        Ticket.support_level == "l1",
    ).count()
    fcr_rate = round(fcr_count / max(resolved, 1) * 100, 1)

    by_priority = {}
    for pri in ["p1_critical", "p2_high", "p3_medium", "p4_low"]:
        count = scoped_tickets.filter(Ticket.created_at >= since, Ticket.priority == pri).count()
        by_priority[pri] = {
            "count": count,
            "label": PRIORITY_LABELS[pri]["label"],
            "color": PRIORITY_LABELS[pri]["color"],
        }

    by_type = {}
    for ttype in ["incident", "service_request", "change", "question"]:
        count = scoped_tickets.filter(Ticket.created_at >= since, Ticket.ticket_type == ttype).count()
        by_type[ttype] = {
            "count": count,
            "label": TYPE_LABELS[ttype]["label"],
            "icon": TYPE_LABELS[ttype]["icon"],
        }

    by_status = {}
    for st in ["new", "assigned", "in_progress", "pending_client", "resolved", "closed"]:
        count = scoped_tickets.filter(Ticket.status == st).count()
        by_status[st] = {
            "count": count,
            "label": STATUS_LABELS[st]["label"],
            "color": STATUS_LABELS[st]["color"],
        }

    agents = db.query(User.id, User.full_name, func.count(Ticket.id).label("count")).join(
        Ticket, Ticket.assigned_to_user_id == User.id
    )
    if not current_user.is_superadmin and current_user.organization_id:
        agents = agents.filter(User.organization_id == current_user.organization_id)
    agents = agents.filter(
        Ticket.status.notin_(["resolved", "closed", "cancelled"])
    ).group_by(User.id, User.full_name).all()

    trend = []
    for i in range(min(days, 30), 0, -1):
        d = date.today() - timedelta(days=i)
        count = scoped_tickets.filter(func.date(Ticket.created_at) == d).count()
        trend.append({"date": str(d)[5:], "count": count})

    sla_at_risk = scoped_tickets.filter(
        Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        Ticket.sla_resolution_due < now + timedelta(hours=2),
        Ticket.sla_resolution_due > now,
    ).count()
    sla_breached_now = scoped_tickets.filter(
        Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        Ticket.sla_resolution_due < now,
    ).count()

    return {
        "period_days": days,
        "summary": {
            "total": total,
            "open": open_count,
            "resolved": resolved,
            "sla_compliance_pct": sla_compliance,
            "sla_at_risk": sla_at_risk,
            "sla_breached_now": sla_breached_now,
            "mttr_hours": mttr,
            "avg_csat": avg_csat,
            "fcr_rate_pct": fcr_rate,
        },
        "by_priority": by_priority,
        "by_type": by_type,
        "by_status": by_status,
        "backlog_by_agent": [
            {"user_id": a.id, "user_name": a.full_name, "count": a.count}
            for a in agents
        ],
        "trend": trend,
    }
