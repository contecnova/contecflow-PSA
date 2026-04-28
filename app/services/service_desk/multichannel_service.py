"""Multi-channel Service — Unified inbound/outbound message routing.

Routes inbound messages from any supported channel (email, SMS, web) to ticket
creation or updates, and dispatches outbound notifications via the requester's
preferred channel.

Supported channels:
  - email   — via inbound_email_service + notification_service (SMTP)
  - sms     — via sms_service (Twilio)
  - web     — native portal (no routing needed)

Configuration stored in AppSetting JSON blob key: sd.multichannel.config
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.settings import AppSetting
from app.services.notification_service import NotificationService
from app.services.service_desk.sms_service import (
    build_sms_ticket_notification,
    send_sms,
)

logger = logging.getLogger(__name__)

_CONFIG_KEY = "sd.multichannel.config"


# ── AppSetting helpers ────────────────────────────────────────────────────────

def get_multichannel_config(db: Session, org_id: Optional[str]) -> dict:
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == _CONFIG_KEY, AppSetting.organization_id == org_id)
        .first()
    )
    if not row or not row.value:
        return _default_config()
    try:
        return json.loads(row.value)
    except Exception:
        return _default_config()


def save_multichannel_config(db: Session, org_id: Optional[str], config: dict) -> dict:
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == _CONFIG_KEY, AppSetting.organization_id == org_id)
        .first()
    )
    payload = json.dumps(config, ensure_ascii=False)
    if not row:
        row = AppSetting(
            key=_CONFIG_KEY,
            organization_id=org_id,
            value=payload,
            description="Multi-channel portal configuration",
        )
        db.add(row)
    else:
        row.value = payload
    db.commit()
    return config


def _default_config() -> dict:
    return {
        "email": {"enabled": True, "inbound_secret": "", "auto_create_tickets": True},
        "sms": {"enabled": False, "inbound_webhook_enabled": False, "auto_create_tickets": True},
        "web": {"enabled": True},
        "default_notification_channel": "email",
    }


# ── Inbound SMS → ticket ──────────────────────────────────────────────────────

def process_inbound_sms(db: Session, from_phone: str, body: str) -> dict:
    """Convert an inbound SMS into a new service desk ticket.

    Looks up the sender in users/clients; creates ticket assigned to first
    available agent. Returns ticket summary dict.
    """
    from app.models.service_desk import (
        SLAPolicy, Ticket, TicketImpact, TicketPriority,
        TicketStatus, TicketType, TicketUrgency,
    )
    from app.models.user import User, UserRole

    now = datetime.now(timezone.utc)
    subject = body.strip()[:100] or "(SMS sin cuerpo)"
    description = f"Ticket creado vía SMS desde {from_phone}:\n\n{body[:2000]}"

    # First available agent
    agents = (
        db.query(User)
        .filter(User.role.in_([UserRole.admin, UserRole.pm]), User.is_active.is_(True))
        .order_by(User.created_at)
        .all()
    )
    assigned_to = agents[0].id if agents else None

    sla = db.query(SLAPolicy).filter(SLAPolicy.is_active.is_(True)).order_by(SLAPolicy.response_hours).first()

    ticket = Ticket(
        id=str(uuid.uuid4()),
        number=f"SMS-{uuid.uuid4().hex[:8].upper()}",
        ticket_type=TicketType.service_request,
        title=subject,
        description=description,
        status=TicketStatus.open,
        priority=TicketPriority.p3_medium,
        urgency=TicketUrgency.medium,
        impact=TicketImpact.user,
        source="sms",
        requester_name=from_phone,
        requester_phone=from_phone if hasattr(Ticket, "requester_phone") else None,
        assigned_to_user_id=assigned_to,
        sla_policy_id=sla.id if sla else None,
        sla_response_due=(
            datetime(now.year, now.month, now.day, now.hour, now.minute, now.second, tzinfo=timezone.utc)
            .__class__.fromtimestamp(
                now.timestamp() + sla.response_hours * 3600, tz=timezone.utc
            )
            if sla else None
        ),
        created_at=now,
    )
    db.add(ticket)
    db.flush()

    # Confirm receipt via SMS
    try:
        send_sms(
            from_phone,
            f"[ContecFlow] Ticket {ticket.number} creado. Seguimiento: https://app.contecflow.com/portal/tickets/{ticket.id}",
        )
    except Exception as exc:
        logger.warning("Could not send SMS confirmation to %s: %s", from_phone, exc)

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "source": "sms",
        "from_phone": from_phone,
    }


# ── Outbound notification routing ────────────────────────────────────────────

def notify_requester(
    db: Session,
    ticket_id: str,
    message: str,
    channels: Optional[list[str]] = None,
) -> dict:
    """Send a notification to the ticket requester via their preferred channel(s).

    Args:
        ticket_id: ID of the ticket to notify about.
        message:   Notification body.
        channels:  List of channels to use. If None, uses ticket source channel.

    Returns:
        Dict with per-channel send status.
    """
    from app.models.service_desk import Ticket

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        return {"error": "Ticket not found"}

    # Determine channels
    if channels is None:
        source = getattr(ticket, "source", "web") or "web"
        channels = [source] if source in ("email", "sms") else ["email"]

    results: dict[str, bool] = {}

    for channel in channels:
        try:
            if channel == "email" and getattr(ticket, "requester_email", None):
                ok = NotificationService.send_email(
                    to=ticket.requester_email,
                    subject=f"Actualización ticket {ticket.number}",
                    html_body=f"<p>{message}</p>",
                )
                results["email"] = ok
            elif channel == "sms":
                phone = getattr(ticket, "requester_phone", None)
                if phone:
                    sms_body = build_sms_ticket_notification(
                        ticket_number=ticket.number,
                        title=ticket.title or "",
                        status=str(ticket.status),
                    )
                    ok = send_sms(phone, sms_body)
                    results["sms"] = ok
                else:
                    results["sms"] = False
            else:
                results[channel] = False
        except Exception as exc:  # noqa: BLE001
            logger.warning("Notification via %s failed for ticket %s: %s", channel, ticket_id, exc)
            results[channel] = False

    return {"ticket_id": ticket_id, "notifications_sent": results}


def get_channel_status(db: Session, org_id: Optional[str]) -> list[dict]:
    """Return status of each configured notification channel."""
    config = get_multichannel_config(db, org_id)

    from app.core.config import settings

    channels = [
        {
            "channel": "email",
            "enabled": config.get("email", {}).get("enabled", True),
            "configured": bool(getattr(settings, "SMTP_HOST", None)),
            "inbound": config.get("email", {}).get("auto_create_tickets", False),
        },
        {
            "channel": "sms",
            "enabled": config.get("sms", {}).get("enabled", False),
            "configured": bool(getattr(settings, "TWILIO_ACCOUNT_SID", None)),
            "inbound": config.get("sms", {}).get("inbound_webhook_enabled", False),
        },
        {
            "channel": "web",
            "enabled": config.get("web", {}).get("enabled", True),
            "configured": True,
            "inbound": True,
        },
    ]
    return channels
