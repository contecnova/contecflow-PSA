"""Correo del Service Desk: el que sale (avisos) con las credenciales de la organizacion.

Las credenciales SMTP se editan en Admin (proveedor `smtp` de
`integration_credentials_service`), por organizacion y con el `.env` de
respaldo. `NotificationService.send_email` lee solo el `.env`, asi que una
organizacion que configurase su SMTP en la pantalla no enviaba con el suyo.
"""
from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class ResultadoEnvio:
    enviado: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


def configuracion_smtp(db: Session, org_id: Optional[str]) -> dict:
    from app.services.integration_credentials_service import get_provider_config
    return get_provider_config(db, "smtp", org_id=org_id)


def enviar(
    db: Session,
    org_id: Optional[str],
    para: str,
    asunto: str,
    html: str,
    texto: str,
    *,
    responder_a: Optional[str] = None,
) -> ResultadoEnvio:
    """Envia un correo y dice si salio. No lanza: el fallo vuelve en el resultado."""
    cfg = configuracion_smtp(db, org_id)
    host, puerto = cfg.get("host"), int(cfg.get("port") or 587)
    usuario, clave = cfg.get("user"), cfg.get("password")
    remitente = cfg.get("from") or usuario
    if not host or not remitente:
        return ResultadoEnvio(False, error="SMTP sin configurar (host y remitente)")

    msg = EmailMessage()
    msg["Subject"] = asunto
    msg["From"] = remitente
    msg["To"] = para
    if responder_a:
        msg["Reply-To"] = responder_a
    dominio = remitente.rpartition("@")[2] or None
    msg["Message-ID"] = make_msgid(domain=dominio)
    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    try:
        if puerto == 465:
            servidor = smtplib.SMTP_SSL(host, puerto, timeout=20)
        else:
            servidor = smtplib.SMTP(host, puerto, timeout=20)
        with servidor:
            servidor.ehlo()
            if puerto not in (25, 465) and servidor.has_extn("starttls"):
                servidor.starttls()
                servidor.ehlo()
            if usuario and clave:
                servidor.login(usuario, clave)
            servidor.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("correo no enviado a @%s: %s", para.rpartition("@")[2], exc)
        return ResultadoEnvio(False, error=str(exc)[:500])
    return ResultadoEnvio(True, message_id=msg["Message-ID"])
