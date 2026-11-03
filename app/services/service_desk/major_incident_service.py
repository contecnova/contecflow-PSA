from datetime import datetime, timezone as tz
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.services.numbering import next_numbered_code

from app.models.service_desk import MajorIncident, Ticket
import logging

logger = logging.getLogger(__name__)


def build_major_incidents_query(db: Session, status: Optional[str]):
    q = db.query(MajorIncident).options(joinedload(MajorIncident.commander))
    if status:
        q = q.filter(MajorIncident.status == status)
    return q


def list_major_incidents_payload(db: Session, status: Optional[str]) -> list[dict]:
    query = build_major_incidents_query(db, status)
    major_incidents = query.order_by(MajorIncident.declared_at.desc()).all()
    return [serialize_major_incident(mi) for mi in major_incidents]


def serialize_major_incident(major_incident: MajorIncident) -> dict:
    return {
        "id": major_incident.id,
        "number": major_incident.number,
        "title": major_incident.title,
        "status": major_incident.status.value,
        "severity": major_incident.severity,
        "declared_at": str(major_incident.declared_at),
        "resolved_at": str(major_incident.resolved_at) if major_incident.resolved_at else None,
        "commander": major_incident.commander.full_name if major_incident.commander else None,
        "impact_statement": major_incident.impact_statement,
        "notifications_sent": major_incident.notifications_sent,
    }


def next_major_incident_number(db: Session) -> str:
    return next_numbered_code(db, "major_incident", prefix="MI", padding=4, separator="")


def build_major_incident(payload: dict, number: str, fallback_commander_id: str) -> MajorIncident:
    if not payload.get("title"):
        raise HTTPException(422, "title es obligatorio")

    return MajorIncident(
        number=number,
        title=payload["title"],
        severity=payload.get("severity", "P1"),
        impact_statement=payload.get("impact_statement"),
        incident_commander_id=payload.get("commander_id", fallback_commander_id),
        communication_lead_id=payload.get("comm_lead_id"),
    )


def declare_major_incident_record(db: Session, payload: dict, fallback_commander_id: str) -> MajorIncident:
    major_incident = build_major_incident(
        payload,
        number=next_major_incident_number(db),
        fallback_commander_id=fallback_commander_id,
    )
    db.add(major_incident)
    escalate_linked_tickets_to_major_incident(db, payload.get("ticket_ids", []))
    return major_incident


def get_major_incident_by_id(db: Session, mi_id: str):
    return db.query(MajorIncident).filter(MajorIncident.id == mi_id).first()


def get_major_incident_or_404(db: Session, mi_id: str) -> MajorIncident:
    major_incident = get_major_incident_by_id(db, mi_id)
    if not major_incident:
        raise HTTPException(404)
    return major_incident


def apply_major_incident_update(major_incident: MajorIncident, payload: dict) -> None:
    for field in (
        "title",
        "status",
        "impact_statement",
        "resolution_summary",
        "timeline",
        "notifications_sent",
    ):
        if field in payload:
            setattr(major_incident, field, payload[field])

    if payload.get("status") == "resolved":
        major_incident.resolved_at = datetime.now(tz.utc)


def update_major_incident_record(db: Session, mi_id: str, payload: dict) -> MajorIncident:
    major_incident = get_major_incident_or_404(db, mi_id)
    apply_major_incident_update(major_incident, payload)
    return major_incident


def escalate_linked_tickets_to_major_incident(db: Session, ticket_ids: list[str]) -> None:
    for tid in ticket_ids:
        ticket = db.query(Ticket).filter(Ticket.id == tid).first()
        if ticket:
            from app.services.service_desk.ticket_update_service import cambiar_prioridad
            cambiar_prioridad(db, ticket, "p1_critical")
            ticket.support_level = "l3"
