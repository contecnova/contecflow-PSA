import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.models.service_desk import (
    AgentGroupMember, Ticket, TicketComment, TicketHistory,
)
from app.models.epics import ThreadedComment
from app.models.user import User
from app.services.service_desk.scoping import (
    get_scoped_ticket_or_404, scope_ticket_query,
)
from app.services.service_desk.status_compat import normalize_ticket_status, sanitize_legacy_ticket_statuses
from app.services.service_desk.ticket_query_service import build_ticket_list_query
from app.services.service_desk.dynamic_ticket_fields_service import get_ticket_dynamic_fields
import logging

logger = logging.getLogger(__name__)


def list_tickets_payload(
    db: Session,
    current_user: User,
    ticket_out,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    ticket_type: Optional[str] = None,
    assigned_to: Optional[str] = None,
    group_id: Optional[str] = None,
    project_id: Optional[str] = None,
    support_level: Optional[str] = None,
    sla_breached: Optional[bool] = None,
    search: Optional[str] = None,
    page: int = 1,
    page_size: int = 25,
) -> dict:
    sanitize_legacy_ticket_statuses(db)
    query = build_ticket_list_query(
        db=db,
        current_user=current_user,
        status=status,
        priority=priority,
        ticket_type=ticket_type,
        assigned_to=assigned_to,
        group_id=group_id,
        project_id=project_id,
        support_level=support_level,
        sla_breached=sla_breached,
        search=search,
    )

    total = query.count()
    tickets = query.order_by(Ticket.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "tickets": [
            {
                **ticket_out(ticket),
                "dynamic_fields": get_ticket_dynamic_fields(db, ticket.id),
            }
            for ticket in tickets
        ],
        "total": total,
        "page": page,
        "pages": math.ceil(total / page_size),
    }


def my_queue_payload(db: Session, current_user: User, ticket_out) -> list[dict]:
    sanitize_legacy_ticket_statuses(db)
    tickets = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.requester_user),
            joinedload(Ticket.requester_client),
            joinedload(Ticket.project),
        )
        .filter(
            Ticket.assigned_to_user_id == current_user.id,
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        )
        .order_by(Ticket.priority, Ticket.created_at)
        .all()
    )
    return [ticket_out(ticket) for ticket in tickets]


def _sla_risk_score(ticket: Ticket) -> float:
    if not ticket.sla_resolution_due or not ticket.created_at:
        return 0.0
    now = datetime.now(timezone.utc)
    created_at = ticket.created_at
    due_at = ticket.sla_resolution_due
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    if due_at.tzinfo is None:
        due_at = due_at.replace(tzinfo=timezone.utc)
    total = (due_at - created_at).total_seconds()
    if total <= 0:
        return 100.0
    elapsed = max((now - created_at).total_seconds(), 0.0)
    return min((elapsed / total) * 100.0, 100.0)


def _business_value_score(ticket: Ticket) -> float:
    priority_weights = {
        "p1_critical": 100.0,
        "p2_high": 75.0,
        "p3_medium": 45.0,
        "p4_low": 20.0,
    }
    p = str(ticket.priority)
    if "." in p:
        p = p.split(".", 1)[1]
    base = priority_weights.get(p, 40.0)
    if ticket.project_id:
        base += 10.0
    if ticket.contract_id:
        base += 8.0
    if ticket.client_id:
        base += 5.0
    return min(base, 100.0)


def my_queue_prioritized_payload(db: Session, current_user: User, ticket_out) -> list[dict]:
    sanitize_legacy_ticket_statuses(db)
    tickets = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.requester_user),
            joinedload(Ticket.requester_client),
            joinedload(Ticket.project),
        )
        .filter(
            Ticket.assigned_to_user_id == current_user.id,
            Ticket.status.notin_(["resolved", "closed", "cancelled"]),
        )
        .all()
    )

    rows = []
    for ticket in tickets:
        sla_risk = _sla_risk_score(ticket)
        business_value = _business_value_score(ticket)
        priority_score = round((sla_risk * 0.65) + (business_value * 0.35), 2)
        out = ticket_out(ticket)
        out["priority_score"] = priority_score
        out["sla_risk_score"] = round(sla_risk, 2)
        out["business_value_score"] = round(business_value, 2)
        rows.append(out)

    rows.sort(key=lambda r: r.get("priority_score", 0), reverse=True)
    return rows


def client_my_tickets_payload(db: Session, client_id: str, ticket_out, status: Optional[str] = None) -> list[dict]:
    sanitize_legacy_ticket_statuses(db)
    query = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.assigned_to),
            joinedload(Ticket.assigned_group),
            joinedload(Ticket.project),
        )
        .filter(Ticket.requester_client_id == client_id)
    )
    normalized_status = normalize_ticket_status(status)
    if normalized_status:
        query = query.filter(Ticket.status == normalized_status)
    return [ticket_out(ticket) for ticket in query.order_by(Ticket.created_at.desc()).all()]


def client_ticket_detail_payload(db: Session, client_id: str, ticket_id: str, ticket_out) -> dict:
    sanitize_legacy_ticket_statuses(db)
    ticket = (
        db.query(Ticket)
        .options(
            joinedload(Ticket.requester_user),
            joinedload(Ticket.requester_client),
            joinedload(Ticket.assigned_to),
            joinedload(Ticket.assigned_group),
            joinedload(Ticket.project),
            joinedload(Ticket.service_item),
            joinedload(Ticket.comments).joinedload(TicketComment.author_user),
            joinedload(Ticket.comments).joinedload(TicketComment.author_client),
        )
        .filter(
            Ticket.id == ticket_id,
            Ticket.requester_client_id == client_id,
        )
        .first()
    )

    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")

    return {
        **ticket_out(ticket, include_comments=True),
        "dynamic_fields": get_ticket_dynamic_fields(db, ticket.id),
    }


def ticket_detail_payload(db: Session, current_user: User, ticket_id: str, ticket_out) -> dict:
    sanitize_legacy_ticket_statuses(db)
    query = db.query(Ticket).options(
        joinedload(Ticket.requester_user),
        joinedload(Ticket.requester_client),
        joinedload(Ticket.assigned_to),
        joinedload(Ticket.assigned_group),
        joinedload(Ticket.project),
        joinedload(Ticket.ci),
        joinedload(Ticket.service_item),
        joinedload(Ticket.comments).joinedload(TicketComment.author_user),
        joinedload(Ticket.comments).joinedload(TicketComment.author_client),
        joinedload(Ticket.history).joinedload(TicketHistory.changed_by),
        joinedload(Ticket.time_logs),
    )

    ticket = scope_ticket_query(query, db, current_user).filter(Ticket.id == ticket_id).first()
    if not ticket:
        raise HTTPException(404, "Ticket no encontrado")

    from app.services.service_desk import catalog_approval_service as _aprobacion
    payload = {
        **ticket_out(ticket, include_comments=True),
        "dynamic_fields": get_ticket_dynamic_fields(db, ticket.id),
        "approval": _aprobacion.serializar(_aprobacion.ultima(db, ticket.id)),
        "fulfillment_tasks": [{
            "id": h.id, "number": h.number, "title": h.title,
            "status": getattr(h.status, "value", h.status),
            "group_name": h.assigned_group.name if h.assigned_group else None,
            "assignee_name": h.assigned_to.full_name if h.assigned_to else None,
        } for h in db.query(Ticket).filter(Ticket.parent_ticket_id == ticket.id, Ticket.source == "fulfillment")
            .order_by(Ticket.created_at).all()],
        "parent": ({"id": ticket.parent_ticket_id,
                    "number": db.query(Ticket.number).filter(Ticket.id == ticket.parent_ticket_id).scalar()}
                   if ticket.parent_ticket_id else None),
    }

    # Merge threaded comments (Mentions page) so ticket detail shows the same
    # discussion history as the threaded comments module.
    threaded = (
        db.query(ThreadedComment)
        .filter(
            ThreadedComment.entity_type == "ticket",
            ThreadedComment.entity_id == ticket_id,
        )
        .order_by(ThreadedComment.created_at.asc())
        .all()
    )
    if threaded:
        comments = list(payload.get("comments") or [])
        for c in threaded:
            body = c.content if not c.parent_id else f"↳ {c.content}"
            comments.append(
                {
                    "id": c.id,
                    "body": body,
                    "is_public": True,
                    "is_solution": False,
                    "author_name": "Usuario",
                    "author_type": "agent",
                    "created_at": str(c.created_at)[:16],
                }
            )
        comments.sort(key=lambda x: x.get("created_at") or "")
        payload["comments"] = comments

    return payload


# -- Los dos endpoints de IA sobre un ticket ---------------------------------
#
# Auditoria 2026-08 (hallazgo 22). Los dos buscaban el ticket asi:
#
#     ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
#
# Sin ambito de ninguna clase, mientras su vecino `ticket_detail_payload`, en
# este mismo modulo, usa `scope_ticket_query`. Es la asimetria de siempre: dos
# lecturas del mismo ticket por id, una comprobada y la otra no.
#
# Lo que se filtraba no era solo el ticket: `/ai-explain` devuelve ademas la
# lista de agentes candidatos con su puntuacion, es decir **los nombres y el
# rendimiento del equipo de soporte de otro cliente**, y cuelga de
# `get_current_user` a secas, no de un rol de gestion.
#
# Los miembros del grupo se buscan por `group_id` sin filtro de organizacion, y
# eso es correcto: el grupo sale de un ticket que ya se verifico, asi que el
# ambito llega por la clave padre.

#: Los pesos del score de asignacion, tal como los publica la API. Estaban en
#: duro en el cuerpo del endpoint.
PESOS_DEL_SCORE_DE_ASIGNACION = {
    "availability": "30%",
    "historical_speed": "35%",
    "historical_csat": "20%",
    "skill_match": "15%",
}

#: A partir de que confianza la auto-resolucion se considera fiable. Tambien
#: estaba en duro.
UMBRAL_DE_AUTO_RESOLUCION = 85

#: Cuantos candidatos se devuelven en la explicacion.
TOPE_DE_CANDIDATOS = 5


def candidatos_de_asignacion(
    db: Session, current_user: User, ticket_id: str
) -> dict:
    """Los agentes del grupo del ticket, ordenados por su score."""
    from app.services.service_desk.ml_routing_service import get_routing_candidates

    ticket = get_scoped_ticket_or_404(db, current_user, ticket_id)
    if not ticket.assigned_group_id:
        raise HTTPException(400, "El ticket no tiene grupo asignado")

    miembros = (
        db.query(AgentGroupMember)
        .filter(AgentGroupMember.group_id == ticket.assigned_group_id)
        .all()
    )
    return {
        "ticket_id": ticket_id,
        "ticket_number": ticket.number,
        "candidates": get_routing_candidates(db, ticket, miembros),
        "score_weights": PESOS_DEL_SCORE_DE_ASIGNACION,
    }


def explicacion_de_decision_de_ia(
    db: Session, current_user: User, ticket_id: str
) -> dict:
    """Confianza de la auto-resolucion y candidatos de asignacion del ticket.

    Devuelve `{"ok": False, ...}` en vez de lanzar un 404 porque es la forma
    que ya tenia la respuesta y no hay motivo para cambiarla de paso. Lo que si
    cambia es que ahora un ticket de otro cliente responde lo mismo que uno que
    no existe.
    """
    from app.services.service_desk.incident_intelligence_service import (
        score_auto_resolution,
    )
    from app.services.service_desk.workload_service import score_agent_for_ticket

    ticket = (
        scope_ticket_query(db.query(Ticket), db, current_user)
        .filter(Ticket.id == ticket_id)
        .first()
    )
    if not ticket:
        return {"ok": False, "error": "Ticket no encontrado"}

    candidatos = []
    if ticket.assigned_group_id:
        miembros = (
            db.query(AgentGroupMember)
            .filter(AgentGroupMember.group_id == ticket.assigned_group_id)
            .all()
        )
        candidatos = [
            {
                "user_id": m.user_id,
                "assignment_score": score_agent_for_ticket(db, m.user_id, ticket),
            }
            for m in miembros
        ]
        candidatos.sort(key=lambda c: c["assignment_score"], reverse=True)

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "auto_resolution": score_auto_resolution(db, ticket),
        "assignment_candidates": candidatos[:TOPE_DE_CANDIDATOS],
        "confidence_trace": {
            "auto_resolution_threshold": UMBRAL_DE_AUTO_RESOLUCION,
            "routing_method": "ml_score_v1",
        },
    }
