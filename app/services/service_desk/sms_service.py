"""SMS Service — Twilio-based SMS notifications and inbound handling.

Requires optional Twilio dependency. Install with:
    pip install twilio>=8.0.0

Configuration via AppSetting or environment variables:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER  (E.164 format, e.g. +34600000000)
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
from typing import Optional
from app.core.constantes import NOMBRE_DEL_PRODUCTO

logger = logging.getLogger(__name__)

try:
    from twilio.rest import Client as TwilioClient  # type: ignore
    _TWILIO_AVAILABLE = True
except ImportError:
    _TWILIO_AVAILABLE = False
    logger.info("Twilio not installed — SMS features disabled. Run: pip install twilio>=8.0.0")


def _get_twilio_config() -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (account_sid, auth_token, from_number) from settings or env."""
    try:
        from app.core.config import settings
        sid = getattr(settings, "TWILIO_ACCOUNT_SID", None)
        token = getattr(settings, "TWILIO_AUTH_TOKEN", None)
        from_num = getattr(settings, "TWILIO_FROM_NUMBER", None)
        return sid, token, from_num
    except Exception:
        logger.debug("_get_twilio_config: excepcion ignorada", exc_info=True)
        return None, None, None


def send_sms(to: str, body: str) -> bool:
    """Send an SMS message via Twilio.

    Args:
        to:   Recipient phone number in E.164 format (e.g. +34612345678).
        body: Message text (≤160 characters for single SMS segment).

    Returns:
        True if sent successfully, False otherwise.
    """
    if not _TWILIO_AVAILABLE:
        logger.warning("SMS send skipped — Twilio not installed")
        return False

    sid, token, from_num = _get_twilio_config()
    if not all([sid, token, from_num]):
        logger.warning("SMS send skipped — Twilio credentials not configured (TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER)")
        return False

    try:
        from app.core.metrics import track_external_call

        client = TwilioClient(sid, token)
        with track_external_call("twilio"):
            message = client.messages.create(body=body[:1600], from_=from_num, to=to)
        logger.info("SMS sent to %s — SID: %s", to, message.sid)
        return True
    except Exception as exc:
        logger.error("SMS send failed to %s: %s", to, exc)
        return False


def twilio_auth_token_para(db, to_phone: Optional[str]) -> Optional[str]:
    """El auth token con el que se verifica un SMS que llego a `to_phone`.

    Segunda auditoria 2026-11 (#9): la organizacion sale del numero receptor
    (credencial `twilio.from_number`); se usa su token propio (credencial
    cifrada `twilio.auth_token` o ajuste `TWILIO_AUTH_TOKEN` de esa
    organizacion) y, si no tiene, el global `TWILIO_AUTH_TOKEN`.
    """
    _, global_token, _ = _get_twilio_config()
    if db is None:
        return global_token
    from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
    from app.services.service_desk.multichannel_service import _organizacion_por_numero

    org_id = _organizacion_por_numero(db, to_phone)
    propio = secreto_propio_de_la_organizacion(
        db, "twilio", "auth_token", "TWILIO_AUTH_TOKEN", org_id) if org_id else None
    return propio or global_token


def validate_twilio_signature(url: str, params: dict, signature: Optional[str], db=None) -> bool:
    """Si la peticion viene de Twilio de verdad.

    Auditoria 2026-11: fallaba ABIERTA —sin la libreria de Twilio, sin token o
    sin cabecera de firma se aceptaba—, asi que cualquiera podia abrir tickets
    por SMS. Ahora sin token o sin firma se rechaza. El algoritmo es el
    documentado por Twilio (HMAC-SHA1 de la URL y los parametros ordenados, en
    base64) y no necesita la libreria.

    Con `db`, el token es el de la organizacion del numero receptor (`To`).
    """
    token = twilio_auth_token_para(db, (params or {}).get("To"))
    if not token or not signature:
        return False
    datos = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    esperada = base64.b64encode(hmac.new(token.encode(), datos.encode(), hashlib.sha1).digest()).decode()
    return hmac.compare_digest(esperada, signature)


def build_sms_ticket_notification(ticket_number: str, title: str, status: str) -> str:
    """Format a short SMS notification for a ticket status update."""
    return (
        f"[{NOMBRE_DEL_PRODUCTO}] Ticket {ticket_number}: {title[:60]}\n"
        f"Estado: {status}\n"
        "Responde a este mensaje para actualizar el ticket."
    )
