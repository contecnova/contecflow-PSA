"""Service Desk metrics: tickets_by_status, tickets_by_type, tickets_by_agent,
tickets_by_priority, ticket_resolution_time, ticket_sla_compliance, ticket_volume_trend, ticket_csat."""
from datetime import date
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.service_desk import Ticket
from sqlalchemy import case
from . import register_metric


STATUS_LABELS = {
    "new": "Nuevo",
    "assigned": "Asignado",
    "in_progress": "En proceso",
    "pending_client": "Pendiente cliente",
    "resolved": "Resuelto",
    "closed": "Cerrado"
}

TYPE_LABELS = {
    "incident": "Incidencia",
    "request": "Solicitud",
    "question": "Consulta",
    "problem": "Problema",
    "change": "Cambio"
}

PRIO_LABELS = {
    "p1_critical": "P1 Crítica",
    "p2_high": "P2 Alta",
    "p3_medium": "P3 Media",
    "p4_low": "P4 Baja"
}


@register_metric("tickets_by_status")
def metric_tickets_by_status(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de tickets por estado."""
    q = db.query(Ticket.status, func.count(Ticket.id).label("n")).group_by(Ticket.status)
    if project_ids is not None:
        q = q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Ticket.project_id == project_id)

    rows = [
        {"label": STATUS_LABELS.get(r.status, r.status), "value": r.n}
        for r in q.all()
    ]
    return rows, {}


@register_metric("tickets_by_type")
def metric_tickets_by_type(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de tickets por tipo."""
    q = db.query(Ticket.ticket_type, func.count(Ticket.id).label("n")).group_by(Ticket.ticket_type)
    if project_ids is not None:
        q = q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Ticket.project_id == project_id)

    rows = [
        {"label": TYPE_LABELS.get(str(r.ticket_type).replace("TicketType.", ""), str(r.ticket_type)), "value": r.n}
        for r in q.all()
    ]
    return rows, {}


@register_metric("tickets_by_priority")
def metric_tickets_by_priority(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Distribución de tickets por prioridad."""
    q = db.query(Ticket.priority, func.count(Ticket.id).label("n")).group_by(Ticket.priority)
    if project_ids is not None:
        q = q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Ticket.project_id == project_id)

    rows = [
        {"label": PRIO_LABELS.get(str(r.priority).replace("TicketPriority.", ""), str(r.priority)), "value": r.n}
        for r in q.all()
    ]
    return rows, {}


@register_metric("tickets_by_agent")
def metric_tickets_by_agent(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Carga de tickets por agente asignado."""

    q = db.query(
        User.full_name,
        func.count(Ticket.id).label("count"),
        func.sum(case((Ticket.status == "closed", 1), else_=0)).label("closed")
    ).join(
        Ticket,
        Ticket.assigned_to_user_id == User.id
    ).filter(
        Ticket.status.notin_(["closed", "resolved"])
    )
    if project_ids is not None:
        q = q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Ticket.project_id == project_id)

    q = q.group_by(
        User.full_name
    ).order_by(
        func.count(Ticket.id).desc()
    ).limit(top_n)

    rows = [
        {"label": r.full_name or "Sin asignar", "value": r.count, "closed": r.closed or 0}
        for r in q.all()
    ]
    return rows, {}


@register_metric("ticket_resolution_time")
def metric_ticket_resolution_time(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tiempo medio de resolución por tipo de ticket."""

    type_labels = {
        "incident": "Incidencia",
        "request": "Solicitud",
        "question": "Consulta",
        "change": "Cambio"
    }

    if is_postgres():
        _avg_days = (func.extract("epoch", func.avg(Ticket.resolved_at - Ticket.created_at)) / 86400).label("avg_days")
    else:
        _avg_days = func.avg(func.julianday(Ticket.resolved_at) - func.julianday(Ticket.created_at)).label("avg_days")

    rows_raw = db.query(
        Ticket.ticket_type,
        func.count(Ticket.id).label("n"),
        _avg_days
    ).filter(
        Ticket.resolved_at.isnot(None),
        Ticket.created_at.isnot(None)
    )
    if project_ids is not None:
        rows_raw = rows_raw.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        rows_raw = rows_raw.filter(Ticket.project_id == project_id)
    rows_raw = rows_raw.group_by(Ticket.ticket_type).all()

    rows = [
        {
            "label": type_labels.get(str(r.ticket_type).replace("TicketType.", ""), str(r.ticket_type)),
            "value": round((r.avg_days or 0) * 24, 1),
            "count": r.n
        }
        for r in rows_raw
    ]
    return rows, {}


@register_metric("ticket_sla_compliance")
def metric_ticket_sla_compliance(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Cumplimiento de SLA por mes."""

    monthly = {}
    q = db.query(
        Ticket.created_at,
        Ticket.sla_response_status,
        Ticket.sla_resolution_status
    ).filter(Ticket.created_at.isnot(None))
    if project_ids is not None:
        q = q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        q = q.filter(Ticket.project_id == project_id)

    for t in q.all():
        if t.created_at:
            key = str(t.created_at)[:7]
            if key not in monthly:
                monthly[key] = {"total": 0, "ok_resp": 0, "ok_res": 0}
            monthly[key]["total"] += 1
            if str(t.sla_response_status) in ("ok", "SLAStatus.ok"):
                monthly[key]["ok_resp"] += 1
            if str(t.sla_resolution_status) in ("ok", "SLAStatus.ok"):
                monthly[key]["ok_res"] += 1

    rows = []
    for k in sorted(monthly.keys())[-12:]:
        m = monthly[k]
        pct = round(m["ok_res"] / m["total"] * 100, 1) if m["total"] > 0 else 0
        rows.append({
            "label": k,
            "value": pct,
            "total": m["total"],
            "ok": m["ok_res"]
        })

    return rows, {}


@register_metric("ticket_volume_trend")
def metric_ticket_volume_trend(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Tendencia de volumen: apertura vs cierre de tickets."""

    monthly = {}

    # Count opened tickets
    opened_q = db.query(Ticket.created_at).filter(Ticket.created_at.isnot(None))
    if project_ids is not None:
        opened_q = opened_q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        opened_q = opened_q.filter(Ticket.project_id == project_id)

    for t in opened_q.all():
        k = str(t.created_at)[:7]
        if k not in monthly:
            monthly[k] = {"opened": 0, "closed": 0}
        monthly[k]["opened"] += 1

    # Count closed tickets
    closed_q = db.query(Ticket.resolved_at).filter(Ticket.resolved_at.isnot(None))
    if project_ids is not None:
        closed_q = closed_q.filter(Ticket.project_id.in_(project_ids))
    if project_id:
        closed_q = closed_q.filter(Ticket.project_id == project_id)

    for t in closed_q.all():
        k = str(t.resolved_at)[:7]
        if k not in monthly:
            monthly[k] = {"opened": 0, "closed": 0}
        monthly[k]["closed"] += 1

    rows = [
        {"label": k, "opened": m["opened"], "closed": m["closed"], "value": m["opened"]}
        for k, m in sorted(monthly.items())[-12:]
    ]
    return rows, {}


@register_metric("ticket_csat")
def metric_ticket_csat(
    db: Session,
    d_from: date,
    d_to: date,
    top_n: int,
    project_id: Optional[str] = None,
    user_id: Optional[str] = None,
    project_ids: Optional[list[str]] = None,
    **kwargs
) -> tuple[list[dict], dict]:
    """Satisfacción del cliente (CSAT) por agente."""

    users_data = db.query(User).filter(User.is_active == True).all()
    rows = []
    for u in users_data[:top_n]:
        ratings = db.query(Ticket.csat_score).filter(
            Ticket.assigned_to_user_id == u.id,
            Ticket.csat_score.isnot(None)
        )
        if project_ids is not None:
            ratings = ratings.filter(Ticket.project_id.in_(project_ids))
        if project_id:
            ratings = ratings.filter(Ticket.project_id == project_id)
        ratings = ratings.all()
        if ratings:
            avg = sum(r.csat_score for r in ratings) / len(ratings)
            rows.append({
                "label": u.full_name,
                "value": round(avg, 2),
                "count": len(ratings)
            })

    rows.sort(key=lambda x: -x["value"])
    return rows, {}


# Import case for conditional sum
from sqlalchemy import case
from app.db.session import is_postgres
from app.models.service_desk import Ticket
from sqlalchemy import desc
