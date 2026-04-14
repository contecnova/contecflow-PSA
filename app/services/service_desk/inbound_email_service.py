import hmac
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.service_desk import (
    SLAPolicy,
    SupportLevel,
    Ticket,
    TicketImpact,
    TicketPriority,
    TicketStatus,
    TicketType,
    TicketUrgency,
)
from app.models.user import User, UserRole


def parse_email_address(raw: Optional[str]) -> Tuple[str, str]:
    if not raw:
        return "", ""
    raw = raw.strip()
    if "<" in raw and ">" in raw:
        name = raw[: raw.index("<")].strip().strip('"')
        email = raw[raw.index("<") + 1 : raw.index(">")].strip()
    else:
        name, email = "", raw
    return name, email


def _validate_inbound_secret(configured_secret: str, provided_secret: Optional[str]) -> None:
    if not configured_secret:
        raise HTTPException(403, "Email inbound deshabilitado: configura INBOUND_EMAIL_SECRET")
    if not hmac.compare_digest(provided_secret or "", configured_secret):
        raise HTTPException(403, "Firma inválida")


def build_inbound_ticket(db: Session, payload: dict, configured_secret: str, provided_secret: Optional[str]):
    _validate_inbound_secret(configured_secret, provided_secret)

    raw_from = payload.get("from") or payload.get("From") or payload.get("sender") or ""
    req_name, req_email = parse_email_address(raw_from)

    description = (
        payload.get("stripped-text")
        or payload.get("body-plain")
        or payload.get("text")
        or payload.get("html")
        or "(Sin cuerpo)"
    )[:4000]

    subject = (payload.get("subject") or "(Sin asunto)").strip()[:255]

    agents = db.query(User).filter(
        User.role.in_([UserRole.admin, UserRole.pm]),
        User.is_active.is_(True),
    ).order_by(User.created_at).all()
    assigned_to = agents[0].id if agents else None

    sla = db.query(SLAPolicy).filter(SLAPolicy.is_active.is_(True)).order_by(SLAPolicy.response_hours).first()

    now = datetime.now(timezone.utc)
    ticket = Ticket(
        id=str(uuid.uuid4()),
        number=f"EML-{uuid.uuid4().hex[:8].upper()}",
        ticket_type=TicketType.service_request,
        title=subject,
        description=description,
        status=TicketStatus.open,
        priority=TicketPriority.p3_medium,
        urgency=TicketUrgency.medium,
        impact=TicketImpact.user,
        support_level=SupportLevel.l1,
        source="email",
        requester_name=req_name or req_email or "Email",
        requester_email=req_email or None,
        assigned_to_user_id=assigned_to,
        sla_policy_id=sla.id if sla else None,
        sla_response_due=now + timedelta(hours=sla.response_hours) if sla else None,
        sla_resolution_due=now + timedelta(hours=sla.resolution_hours) if sla else None,
        created_at=now,
    )

    db.add(ticket)
    return ticket, req_email


def process_inbound_email(db: Session, payload: dict, provided_secret: Optional[str]):
    configured_secret = settings.INBOUND_EMAIL_SECRET if hasattr(settings, "INBOUND_EMAIL_SECRET") else ""
    return build_inbound_ticket(db, payload, configured_secret, provided_secret)
