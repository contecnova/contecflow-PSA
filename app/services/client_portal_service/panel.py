"""Panel del cliente, actividad reciente, ficha del proyecto y estadisticas del portal.

Parte de `app.services.client_portal_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models.client_portal import ClientMessage
from app.models.client_portal import ClientUser, client_user_projects
from app.models.client_portal import UATSession, UATStatus, FeatureRequest, FeatureRequestStatus
from app.models.client_portal import ClientSurvey
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.project import Project as ProjectModel
from app.models.resources import Deliverable, DeliverableStatus
from app.models.service_desk import Ticket, TicketStatus
from sqlalchemy import func
from app.core import timeutil


# ── Serializers ───────────────────────────────────────────────────────────────

def get_recent_activity(project_id: str, db: Session) -> list:

    activity = []
    msgs = db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.is_internal == False,
        ClientMessage.sender_user_id != None,
    ).order_by(ClientMessage.created_at.desc()).limit(3).all()
    for m in msgs:
        name = m.sender_user.full_name if m.sender_user else "Equipo"
        activity.append({
            "type": "message",
            "text": f"Mensaje de {name}: {m.body[:60]}...",
            "date": str(m.created_at)[:10],
        })

    dels = db.query(Deliverable).filter(
        Deliverable.project_id == project_id,
        Deliverable.status.in_([DeliverableStatus.delivered, DeliverableStatus.accepted])
    ).order_by(Deliverable.updated_at.desc()).limit(2).all()
    for d in dels:
        activity.append({
            "type": "deliverable",
            "text": f"Entregable disponible: {d.name}",
            "date": str(d.updated_at or d.created_at)[:10],
        })

    activity.sort(key=lambda x: x["date"], reverse=True)
    return activity[:5]


# ── Dashboard ─────────────────────────────────────────────────────────────────

_OPEN_TICKET_STATUSES = [
    TicketStatus.new,
    TicketStatus.assigned,
    TicketStatus.in_progress,
    TicketStatus.pending_client,
    TicketStatus.pending_third,
]


def _resolve_dashboard_project(project_id: Optional[str], current_client, db: Session):
    """Resolve which project the dashboard should target.

    Returns a tuple (early_response, project). When early_response is not None,
    the dashboard endpoint must short-circuit and return it directly.
    """
    accessible_ids = current_client.get_project_ids()
    if len(accessible_ids) > 1 and not project_id:
        projs = db.query(ProjectModel).filter(ProjectModel.id.in_(accessible_ids)).all()
        return {
            "needs_project_selection": True,
            "projects": [{"id": p.id, "name": p.name, "code": p.code, "status": p.status} for p in projs],
        }, None
    effective_id = project_id or (accessible_ids[0] if accessible_ids else None)
    if effective_id and accessible_ids and effective_id not in accessible_ids:
        raise ValueError("No tienes acceso a este proyecto")
    if not effective_id:
        return {"project": None, "no_project": True,
                "message": "Este usuario del portal no tiene ningún proyecto asignado."}, None
    project = db.query(ProjectModel).filter(ProjectModel.id == effective_id).first()
    if not project:
        return {"project": None, "no_project": True,
                "message": "El proyecto asignado no existe."}, None
    return None, project


def _dashboard_budget_and_milestones(project, db: Session):
    total_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.project_id == project.id
    ).scalar() or 0
    budget_pct = round(total_hours / project.budget_hours * 100, 1) if project.budget_hours else None
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project.id
    ).order_by(ProjectMilestone.sort_order).all()
    return total_hours, budget_pct, milestones


def _dashboard_deliverables_and_uat(project, db: Session) -> dict:
    deliverables = db.query(Deliverable).filter(Deliverable.project_id == project.id).all()
    uat_sessions = db.query(UATSession).filter(UATSession.project_id == project.id).all()
    return {
        "deliverables_total": len(deliverables),
        "del_accepted": sum(1 for d in deliverables if d.status == DeliverableStatus.accepted),
        "del_pending_uat": sum(1 for d in deliverables if d.status == DeliverableStatus.delivered),
        "uat_total": len(uat_sessions),
        "uat_passed": sum(1 for s in uat_sessions if s.status in [UATStatus.passed, UATStatus.conditional]),
        "uat_pending": sum(1 for s in uat_sessions if s.status in [UATStatus.pending, UATStatus.in_progress]),
    }


def _dashboard_fr_and_unread(project, db: Session):
    fr_open = db.query(FeatureRequest).filter(
        FeatureRequest.project_id == project.id,
        FeatureRequest.status.in_([
            FeatureRequestStatus.new,
            FeatureRequestStatus.reviewing,
            FeatureRequestStatus.estimated
        ])
    ).count()
    unread = db.query(ClientMessage).filter(
        ClientMessage.project_id == project.id,
        ClientMessage.is_read_by_client == False,
        ClientMessage.sender_client_id == None,
        ClientMessage.is_internal == False,
    ).count()
    return fr_open, unread


def _dashboard_ticket_counts(ticket_query) -> dict:
    return {
        "tickets_open": ticket_query.filter(Ticket.status.in_(_OPEN_TICKET_STATUSES)).count(),
        "tickets_pending_client": ticket_query.filter(Ticket.status == TicketStatus.pending_client).count(),
        "tickets_resolved": ticket_query.filter(
            Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed])
        ).count(),
    }


def _dashboard_sla_stats(project, current_client, ticket_query, db: Session) -> dict:
    avg_first_response_minutes = db.query(func.avg(Ticket.first_response_minutes)).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
        Ticket.first_response_minutes.isnot(None),
        Ticket.first_response_minutes > 0,
    ).scalar()
    avg_resolution_minutes = db.query(func.avg(Ticket.resolution_minutes)).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
        Ticket.resolution_minutes.isnot(None),
        Ticket.resolution_minutes > 0,
    ).scalar()
    resolved_ticket_count = ticket_query.filter(
        Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed]),
        Ticket.resolution_minutes.isnot(None),
    ).count()
    breached_ticket_count = ticket_query.filter(
        Ticket.status.in_([TicketStatus.resolved, TicketStatus.closed]),
        Ticket.sla_resolution_breached == True,
    ).count()
    response_breached_open = ticket_query.filter(
        Ticket.status.in_(_OPEN_TICKET_STATUSES),
        Ticket.sla_response_breached == True,
    ).count()
    resolution_breached_open = ticket_query.filter(
        Ticket.status.in_(_OPEN_TICKET_STATUSES),
        Ticket.sla_resolution_breached == True,
    ).count()
    csat_avg = db.query(func.avg(Ticket.csat_score)).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
        Ticket.csat_score.isnot(None),
    ).scalar()
    sla_compliance_pct = (
        round(((resolved_ticket_count - breached_ticket_count) / resolved_ticket_count) * 100, 1)
        if resolved_ticket_count else None
    )
    return {
        "avg_first_response_minutes": round(float(avg_first_response_minutes), 1) if avg_first_response_minutes is not None else None,
        "avg_resolution_minutes": round(float(avg_resolution_minutes), 1) if avg_resolution_minutes is not None else None,
        "sla_compliance_pct": sla_compliance_pct,
        "response_breached_open": response_breached_open,
        "resolution_breached_open": resolution_breached_open,
        "csat_avg": round(float(csat_avg), 1) if csat_avg is not None else None,
    }


def _dashboard_progress_pct(project) -> float:
    days_elapsed = (timeutil.today() - project.start_date).days if project.start_date else 0
    days_total = (
        (project.end_date_planned - project.start_date).days
        if project.end_date_planned and project.start_date else None
    )
    progress_pct = round(days_elapsed / days_total * 100, 1) if days_total and days_total > 0 else 0
    return min(progress_pct, 100)


def _dashboard_next_milestone(milestones) -> Optional[dict]:
    nm = next((m for m in milestones if not m.is_completed and m.due_date), None)
    if not nm:
        return None
    return {
        "name": nm.name,
        "title": nm.name,
        "due_date": str(nm.due_date),
        "days_remaining": (nm.due_date - timeutil.today()).days,
    }


def get_client_dashboard(project_id: Optional[str], current_client, db: Session) -> dict:
    early, project = _resolve_dashboard_project(project_id, current_client, db)
    if early is not None:
        return early

    total_hours, budget_pct, milestones = _dashboard_budget_and_milestones(project, db)
    milestones_done = sum(1 for m in milestones if m.is_completed)
    del_uat = _dashboard_deliverables_and_uat(project, db)
    fr_open, unread = _dashboard_fr_and_unread(project, db)

    ticket_query = db.query(Ticket).filter(
        Ticket.requester_client_id == current_client.id,
        Ticket.project_id == project.id,
    )
    ticket_counts = _dashboard_ticket_counts(ticket_query)
    sla = _dashboard_sla_stats(project, current_client, ticket_query, db)

    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
            "progress_pct": _dashboard_progress_pct(project),
        },
        "kpis": {
            "budget_hours": project.budget_hours,
            "hours_consumed": round(total_hours, 1),
            "budget_pct": budget_pct,
            "budget_total": project.budget_hours,
            "budget_spent": round(total_hours, 1),
            "milestones_total": len(milestones),
            "milestones_done": milestones_done,
            "deliverables_accepted": del_uat["del_accepted"],
            "deliverables_approved": del_uat["del_accepted"],
            "deliverables_total": del_uat["deliverables_total"],
            "deliverables_pending_uat": del_uat["del_pending_uat"],
            "uat_total": del_uat["uat_total"],
            "uat_passed": del_uat["uat_passed"],
            "uat_pending": del_uat["uat_pending"],
            "feature_requests_open": fr_open,
            "tickets_open": ticket_counts["tickets_open"],
            "tickets_pending_client": ticket_counts["tickets_pending_client"],
            "tickets_resolved": ticket_counts["tickets_resolved"],
            "unread_messages": unread,
        },
        "service_desk": {
            "tickets_open": ticket_counts["tickets_open"],
            "tickets_pending_client": ticket_counts["tickets_pending_client"],
            "tickets_resolved": ticket_counts["tickets_resolved"],
            **sla,
        },
        "next_milestone": _dashboard_next_milestone(milestones),
        "recent_activity": get_recent_activity(project.id, db),
    }


# ── Project info ──────────────────────────────────────────────────────────────

def get_project_info(project_id: Optional[str], current_client, db: Session) -> dict:

    accessible = current_client.get_project_ids()
    if not accessible:
        raise ValueError("No hay proyectos asignados a este cliente")
    effective_id = project_id or accessible[0]
    if accessible and effective_id and effective_id not in accessible:
        raise ValueError("No tienes acceso a ese proyecto")
    project = db.query(ProjectModel).filter(ProjectModel.id == effective_id).first()
    if not project:
        raise ValueError("Proyecto no encontrado")
    milestones = db.query(ProjectMilestone).filter(
        ProjectMilestone.project_id == project.id
    ).order_by(ProjectMilestone.sort_order).all()
    deliverables = db.query(Deliverable).filter(
        Deliverable.project_id == project.id
    ).order_by(Deliverable.sort_order).all()
    total_hours = db.query(func.sum(Imputation.hours)).filter(
        Imputation.project_id == project.id
    ).scalar() or 0
    return {
        "project": {
            "id": project.id, "code": project.code, "name": project.name,
            "description": project.description, "status": project.status,
            "start_date": str(project.start_date) if project.start_date else None,
            "end_date_planned": str(project.end_date_planned) if project.end_date_planned else None,
            "client_name": project.client_name,
        },
        "milestones": [{
            "id": m.id, "name": m.name,
            "due_date": str(m.due_date) if m.due_date else None,
            "is_completed": m.is_completed,
            "completed_date": str(m.completed_date) if m.completed_date else None,
            "billing_pct": m.billing_pct,
        } for m in milestones],
        "deliverables": [{
            "id": d.id, "code": d.code, "name": d.name, "format": d.format,
            "status": d.status,
            "planned_date": str(d.planned_date) if d.planned_date else None,
            "delivered_date": str(d.delivered_date) if d.delivered_date else None,
            "accepted_date": str(d.accepted_date) if d.accepted_date else None,
        } for d in deliverables],
        "budget": {
            "hours_budget": project.budget_hours, "hours_consumed": round(total_hours, 1),
            "pct_consumed": round(total_hours / project.budget_hours * 100, 1) if project.budget_hours else None,
        } if current_client.can_view_budget else None,
    }


# ── Stats ─────────────────────────────────────────────────────────────────────

def _portal_stats_client_count(project_id: str, db: Session) -> int:
    import sqlalchemy as sa
    legacy_ids = {r[0] for r in db.execute(
        sa.select(ClientUser.id).where(ClientUser.project_id == project_id)
    ).fetchall()}
    m2m_ids = {r[0] for r in db.execute(
        sa.select(client_user_projects.c.client_user_id).where(
            client_user_projects.c.project_id == project_id
        )
    ).fetchall()}
    return len(legacy_ids | m2m_ids)


def _portal_stats_survey_aggregates(surveys) -> dict:
    if not surveys:
        return {"survey_count": 0, "avg_nps": None, "avg_satisfaction": None}
    n = max(len(surveys), 1)
    return {
        "survey_count": len(surveys),
        "avg_nps": round(sum(s.nps_score for s in surveys if s.nps_score) / n, 1),
        "avg_satisfaction": round(
            sum(s.overall_satisfaction for s in surveys if s.overall_satisfaction) / n, 1
        ),
    }


def get_portal_stats(project_id: str, db: Session) -> dict:
    clients = _portal_stats_client_count(project_id, db)
    unread_from_client = db.query(ClientMessage).filter(
        ClientMessage.project_id == project_id,
        ClientMessage.sender_client_id != None,
        ClientMessage.is_read_by_team == False,
    ).count()
    fr_pending = db.query(FeatureRequest).filter(
        FeatureRequest.project_id == project_id,
        FeatureRequest.status.in_(["new", "reviewing"]),
    ).count()
    uat_pending = db.query(UATSession).filter(
        UATSession.project_id == project_id,
        UATSession.status.in_(["pending", "in_progress"]),
    ).count()
    surveys = db.query(ClientSurvey).filter(
        ClientSurvey.project_id == project_id,
        ClientSurvey.status == "completed",
    ).all()
    survey_stats = _portal_stats_survey_aggregates(surveys)
    return {
        "client_count": clients,
        "unread_messages": unread_from_client,
        "fr_pending_review": fr_pending,
        "uat_pending": uat_pending,
        **survey_stats,
    }
