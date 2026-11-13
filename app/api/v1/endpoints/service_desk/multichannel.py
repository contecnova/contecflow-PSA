"""Service Desk — Multi-channel Portal REST API.

Inbound webhooks (email, SMS), outbound notifications, and channel configuration.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_admin
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.user import User
from app.services.service_desk.multichannel_service import (
    get_channel_status,
    get_multichannel_config,
    notify_requester,
    procesar_correo_entrante,
    procesar_sms_entrante,
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
    _rol: User = Depends(require_admin),  # auditoria 2026-09: configuracion: la forma de la ruta manda sobre el fichero
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
        logging.getLogger(__name__).debug("inbound_email: excepcion ignorada", exc_info=True)
        payload = dict(await request.form())

    secret = x_inbound_secret or payload.get("token") or payload.get("signature")

    r = await run_db(procesar_correo_entrante, db, dict(payload), secret)
    return {"ticket_id": r.ticket_id, "ticket_number": r.numero, "status": r.accion,
            "reason": r.motivo, "source": "email"}


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
    to_phone = form.get("To", "")
    body = form.get("Body", "")

    # Auditoria 2026-11: la firma solo se miraba si venia la cabecera, asi que
    # sin ella cualquiera abria tickets. Ahora es obligatoria.
    # Segunda auditoría 2026-11 (#9): con el token de la organización del
    # número receptor (`To`), o el global si no tiene propio.
    if not await run_db(validate_twilio_signature, str(request.url), form, x_twilio_signature, db):
        from fastapi import HTTPException
        raise HTTPException(403, "Firma de Twilio ausente o inválida")

    return await run_db(procesar_sms_entrante, db, from_phone, body, to_phone)


# ── Outbound notification ─────────────────────────────────────────────────────

@router.post("/tickets/{ticket_id}/notify", summary="Enviar notificación al solicitante del ticket")
def notify_ticket_requester(
    ticket_id: str,
    payload: NotifyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    _rol: User = Depends(require_admin),  # auditoria 2026-09: dominio: canales de entrada
):
    return APIResponse.ok(data=notify_requester(db, ticket_id=ticket_id, message=payload.message, channels=payload.channels))
