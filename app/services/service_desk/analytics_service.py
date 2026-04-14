from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import Ticket
from app.models.user import User
from app.services.service_desk.metrics_service import compute_itil_metrics


def _parse_range(date_from: Optional[str], date_to: Optional[str]):
    d_from = (
        datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
        if date_from
        else datetime.now(timezone.utc) - timedelta(days=30)
    )
    d_to = (
        datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc)
        if date_to
        else datetime.now(timezone.utc)
    )
    return d_from, d_to


def get_itil_metrics_payload(
    db: Session,
    date_from: Optional[str],
    date_to: Optional[str],
    client_id: Optional[str],
) -> dict:
    d_from, d_to = _parse_range(date_from, date_to)

    q = db.query(Ticket).options(joinedload(Ticket.comments)).filter(
        Ticket.created_at.between(d_from, d_to)
    )
    if client_id:
        q = q.filter(Ticket.client_id == client_id)
    tickets = q.all()

    total = len(tickets)
    resolved = [t for t in tickets if t.resolved_at]
    open_t = [t for t in tickets if t.status.value not in ("resolved", "closed", "cancelled")]
    breached = [
        t
        for t in tickets
        if t.sla_resolution_status and t.sla_resolution_status.value == "breached"
    ]

    metrics = compute_itil_metrics(tickets)

    sla_compliant = [
        t
        for t in resolved
        if t.sla_resolution_status and t.sla_resolution_status.value == "ok"
    ]
    sla_pct = round(len(sla_compliant) / len(resolved) * 100, 1) if resolved else 100.0

    by_type = {}
    for t in tickets:
        key = t.ticket_type.value
        by_type[key] = by_type.get(key, 0) + 1

    by_priority = {}
    for t in tickets:
        key = t.priority.value
        by_priority[key] = by_priority.get(key, 0) + 1

    csat_scores = [t.csat_score for t in tickets if t.csat_score]
    avg_csat = round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None

    breach_by_priority = {}
    for t in breached:
        key = t.priority.value
        breach_by_priority[key] = breach_by_priority.get(key, 0) + 1

    return {
        "period": {"from": str(d_from.date()), "to": str(d_to.date())},
        "volume": {
            "total": total,
            "open": len(open_t),
            "resolved": len(resolved),
            "breached_sla": len(breached),
        },
        "sla_compliance_pct": sla_pct,
        "mttr_minutes": metrics["mttr_minutes"],
        "mttr_hours": metrics["mttr_hours"],
        "fcr_percent": metrics["fcr_percent"],
        "avg_csat": avg_csat,
        "by_type": by_type,
        "by_priority": by_priority,
        "breach_by_priority": breach_by_priority,
    }


def get_agent_performance_payload(
    db: Session,
    date_from: Optional[str],
    date_to: Optional[str],
) -> list[dict]:
    d_from, d_to = _parse_range(date_from, date_to)

    agents = db.query(User).filter(User.is_active == True).all()
    result = []

    for agent in agents:
        agent_tickets = db.query(Ticket).filter(
            Ticket.assigned_to_user_id == agent.id,
            Ticket.created_at.between(d_from, d_to),
        ).all()
        if not agent_tickets:
            continue

        resolved = [t for t in agent_tickets if t.resolved_at and t.created_at]
        mttr = 0
        if resolved:
            def _safe_dt(dt):
                return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

            mttr = round(
                sum(
                    (_safe_dt(t.resolved_at) - _safe_dt(t.created_at)).total_seconds() / 60
                    for t in resolved
                )
                / len(resolved),
                0,
            )

        csat_scores = [t.csat_score for t in agent_tickets if t.csat_score]
        breached = sum(
            1
            for t in agent_tickets
            if t.sla_resolution_status and t.sla_resolution_status.value == "breached"
        )

        result.append(
            {
                "agent_id": agent.id,
                "agent_name": agent.full_name,
                "total": len(agent_tickets),
                "resolved": len(resolved),
                "open": len(agent_tickets) - len(resolved),
                "mttr_minutes": mttr,
                "avg_csat": round(sum(csat_scores) / len(csat_scores), 2) if csat_scores else None,
                "sla_breaches": breached,
            }
        )

    result.sort(key=lambda x: -x["resolved"])
    return result
