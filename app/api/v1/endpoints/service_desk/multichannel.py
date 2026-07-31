"""Service Desk — Multi-channel Portal REST API.

Inbound webhooks (email, SMS), outbound notifications, and channel configuration.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.inbound_email_service import process_inbound_email
from app.services.service_desk.multichannel_service import (
    get_channel_status,
    get_multichannel_config,
    notify_requester,
    process_inbound_sms,
    save_multichannel_config,
)
from app.services.service_desk.sms_service import validate_twilio_signature

router = APIRouter(prefix="/multichannel", tags=["Multi-channel Portal"])


# ── Pydantic schemas ───────────────────────────────────────────────────────────

class MultichannelConfigIn(BaseModel):
    email: Optional[dict] = None
    sms: Optional[dict] = None
    web: Optional[dict] = None
    default_notification_channel: Optional[str] = "email"


class NotifyIn(BaseModel):
    message: str
    channels: Optional[list[str]] = None


# ── Configuration endpoints ────────────────────────────────────────────────────

@router.get("/config", summary="Configuración de canales de comunicación")
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIResponse.ok(data=get_multichannel_config(db, org_id))


@router.put("/config", summary="Guardar configuración de canales de comunicación")
def put_config(
    payload: MultichannelConfigIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    current = get_multichannel_config(db, org_id)
    # Merge provided fields only
    data = payload.model_dump(exclude_unset=True)
    current.update(data)
    return APIResponse.ok(data=save_multichannel_config(db, org_id, current))


@router.get("/channels", summary="Estado de los canales configurados")
def list_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    org_id = getattr(current_user, "organization_id", None)
    return APIListResponse.ok(items=get_channel_status(db, org_id))


# ── Inbound webhooks ───────────────────────────────────────────────────────────

@router.post(
    "/inbound/email",
    summary="Webhook para correo entrante (Mailgun / Postmark / SendGrid format)",
    include_in_schema=True,
)
async def inbound_email(
    request: Request,
    db: Session = Depends(get_db),
    x_inbound_secret: Optional[str] = Header(None, alias="X-Inbound-Secret"),
):
    """Accept inbound email webhook and create/update a ticket.

    Supports Mailgun, Postmark, and SendGrid payload formats.
    Authenticates via X-Inbound-Secret header or ``token`` field in body.
    """
    # Audit #C7: async required for await request.json/form; DB to threadpool.
    from app.core.async_db import run_db

    try:
        payload = await request.json()
    except Exception:
        payload = dict(await request.form())

    secret = x_inbound_secret or payload.get("token") or payload.get("signature")

    def _process_and_commit():
        ticket, requester_email = process_inbound_email(db, dict(payload), provided_secret=secret)
        db.commit()
        return ticket, requester_email

    ticket, requester_email = await run_db(_process_and_commit)
    return {
        "ticket_id": ticket.id,
        "ticket_number": ticket.number,
        "requester_email": requester_email,
        "source": "email",
    }


@router.post(
    "/inbound/sms",
    summary="Webhook de Twilio para SMS entrante",
    include_in_schema=True,
)
async def inbound_sms(
    request: Request,
    db: Session = Depends(get_db),
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature"),
):
    """Accept inbound SMS from Twilio webhook and create a ticket.

    Validates Twilio signature when TWILIO_AUTH_TOKEN is configured.
    Twilio sends form-encoded POST with fields: From, Body, etc.
    """
    # Audit #C7: same pattern as inbound_email above.
    from app.core.async_db import run_db

    form = dict(await request.form())
    from_phone = form.get("From", "")
    body = form.get("Body", "")

    # Validate Twilio signature (non-blocking in dev if token not configured)
    if x_twilio_signature:
        is_valid = validate_twilio_signature(str(request.url), form, x_twilio_signature)
        if not is_valid:
            from fastapi import HTTPException
            raise HTTPException(403, "Invalid Twilio signature")

    def _process_and_commit():
        result = process_inbound_sms(db, from_phone=from_phone, body=body)
        db.commit()
        return result

    return await run_db(_process_and_commit)


# ── Outbound notification ─────────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/notify", summary="Enviar notificación al solicitante del ticket")
def notify_ticket_requester(
    ticket_id: str,
    payload: NotifyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return APIResponse.ok(data=notify_requester(db, ticket_id=ticket_id, message=payload.message, channels=payload.channels))
