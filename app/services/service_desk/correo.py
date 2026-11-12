"""Correo del Service Desk: el que sale (avisos) con las credenciales de la organizacion.

Las credenciales SMTP se editan en Admin (proveedor `smtp` de
`integration_credentials_service`), por organizacion y con el `.env` de
respaldo. `NotificationService.send_email` lee solo el `.env`, asi que una
organizacion que configurase su SMTP en la pantalla no enviaba con el suyo.

Auditoria 2026-11 (hallazgo 20): la conexion SMTP ya no se abre aqui; la abre
`notification_service.enviar_correo`, el unico emisor de la aplicacion.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.services.notification_service import ResultadoEnvio, ServidorSmtp, enviar_correo

__all__ = ["ResultadoEnvio", "enviar"]


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
    servidor = ServidorSmtp.de_organizacion(db, org_id, timeout=20.0)
    remitente = servidor.remitente or servidor.user
    if not servidor.host or not remitente:
        return ResultadoEnvio(False, error="SMTP sin configurar (host y remitente)")
    return enviar_correo(
        para, asunto, html, texto=texto, remitente=remitente, responder_a=responder_a,
        servidor=servidor, con_message_id=True,
    )
