"""Webhook de correo entrante (pasarelas tipo Mailgun, Postmark o SendGrid).

La logica de correo a ticket vive en `inbound_mail.py` y es la misma que usa
la lectura del buzon. Aqui solo se decide de que organizacion es el correo —por
la direccion de soporte que lo recibio (`SD_INBOUND_ADDRESS`)— y se comprueba
el secreto de la pasarela, el de esa organizacion o el del `.env`.
"""
import hmac
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.service_desk import inbound_mail


def parse_email_address(raw: Optional[str]) -> tuple[str, str]:
    from email.utils import parseaddr
    nombre, direccion = parseaddr(raw or "")
    return nombre.strip(), direccion.strip()


def _secreto(db: Session, org_id: Optional[str]) -> str:
    from app.services.integration_credentials_service import get_credential
    return get_credential(db, "webhooks", "inbound_email_secret", org_id=org_id) or ""


def _validate_inbound_secret(configured_secret: str, provided_secret: Optional[str]) -> None:
    if not configured_secret:
        raise HTTPException(403, "Email inbound deshabilitado: configura el secreto de la pasarela")
    if not hmac.compare_digest(provided_secret or "", configured_secret):
        raise HTTPException(403, "Firma inválida")


def process_inbound_email(db: Session, payload: dict, provided_secret: Optional[str]) -> inbound_mail.Resultado:
    """Comprueba el secreto y convierte el correo en ticket o comentario. No confirma."""
    correo = inbound_mail.desde_webhook(payload)
    org_id = inbound_mail.organizacion_por_direccion(db, correo.para)
    _validate_inbound_secret(_secreto(db, org_id), provided_secret)
    return inbound_mail.procesar(db, org_id, correo)
