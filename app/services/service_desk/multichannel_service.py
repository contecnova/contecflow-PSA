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
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import settings
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
        logger.debug("get_multichannel_config: excepcion ignorada", exc_info=True)
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

def _organizacion_por_numero(db: Session, to_phone: Optional[str]) -> Optional[str]:
    """La organizacion cuyo numero de Twilio (`from_number`) recibio el SMS."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import IntegrationCredential

    if not to_phone:
        return None
    with sin_filtro_de_tenant(db):
        fila = db.query(IntegrationCredential).filter(
            IntegrationCredential.provider == "twilio",
            IntegrationCredential.key == "from_number",
            IntegrationCredential.value == to_phone.strip(),
        ).first()
    return fila.organization_id if fila else None


def process_inbound_sms(db: Session, from_phone: str, body: str, to_phone: Optional[str] = None) -> dict:
    """Un SMS entrante abre un ticket, con las mismas reglas que el resto de canales.

    Auditoria 2026-11: el ticket se montaba a mano (`SMS-xxxx` fuera de la
    numeracion, el primer administrador como agente, sin organizacion). Ahora
    la organizacion sale del numero que lo recibio y quien escribe se reconoce
    por su telefono si es contacto del portal o usuario.
    """
    from app.models.client_portal import ClientUser
    from app.models.user import User
    from app.services.service_desk.ticket_creation_service import build_channel_ticket
    from app.services.service_desk.ticket_events import como_organizacion

    org_id = _organizacion_por_numero(db, to_phone)
    with como_organizacion(db, org_id):
        cliente = db.query(ClientUser).filter(ClientUser.phone == from_phone,
                                              ClientUser.is_active == True).first()  # noqa: E712
        usuario = None if cliente else db.query(User).filter(
            User.phone == from_phone, User.is_active == True).first()  # noqa: E712
        nombre = (cliente.full_name if cliente else usuario.full_name if usuario else from_phone)
        ticket = build_channel_ticket(
            db, org_id=org_id, titulo=body.strip()[:100] or "(SMS sin cuerpo)",
            descripcion=f"SMS de {nombre} ({from_phone}):\n\n{body[:2000]}", source="sms",
            requester_user=usuario, requester_client=cliente, requester_name=nombre,
            requester_email=cliente.email if cliente else (usuario.email if usuario else None),
            requester_phone=from_phone,
        )


    # Confirm receipt via SMS
    try:
        send_sms(
            from_phone,
            f"[ContecFlow] Ticket {ticket.number} creado. Seguimiento: "
            f"{settings.FRONTEND_URL.rstrip('/')}/portal?ticket={ticket.id}",
        )
    except Exception as exc:
        logger.warning("Could not send SMS confirmation to %s: %s", from_phone, exc)

    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "source": "sms",
        "from_phone": from_phone,
    }


# ── Lo que confirman los webhooks de entrada ─────────────────────────────────

def procesar_sms_entrante(db: Session, from_phone: str, body: str, to_phone: Optional[str] = None) -> dict:
    """`process_inbound_sms` y confirma (webhook de Twilio)."""
    result = process_inbound_sms(db, from_phone=from_phone, body=body, to_phone=to_phone)
    db.commit()
    return result


def procesar_correo_entrante(db: Session, payload: dict, provided_secret: Optional[str]):
    """`process_inbound_email` y confirma (webhook de correo entrante)."""
    from app.services.service_desk.inbound_email_service import process_inbound_email

    r = process_inbound_email(db, payload, provided_secret=provided_secret)
    db.commit()
    return r


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
        except Exception as exc:
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
