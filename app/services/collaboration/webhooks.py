"""Integraciones y webhooks de colaboración: alta, baja y entrega entrante.

Auditoría 2026-08 (hallazgo 22). Estas operaciones vivían en
`endpoints/collaboration/bots.py` con **11 puntos de acceso directo a base**.

Y un valor que estaba en duro y la regla de «no hardcodear nada» no permite
dejar: el tope de peticiones de un webhook entrante —120 por minuto— estaba
escrito en el endpoint. Es el caudal que un sistema externo puede empujar dentro
de un canal, así que quien despliega tiene que poder ajustarlo sin tocar código:
ahora es `COLLAB_WEBHOOK_INCOMING_PER_MIN`.
"""
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.timeutil import utcnow
from app.models.collaboration import (
    CollaborationBotApp,
    CollaborationChannel,
    CollaborationIntegration,
    CollaborationWebhook,
)
from app.services.collaboration._permissions import _org
from app.services.traffic_control_service import consume_quota
from app.core.errores import ErrorDeDominio

#: Ventana del tope del webhook entrante, en segundos.
VENTANA_DE_CUOTA_SEGUNDOS = 60

#: Longitud en bytes del secreto de un webhook. 32 bytes en base64url dan 43
#: caracteres: es el secreto con el que un sistema externo se autentica para
#: escribir en un canal, así que no puede ser corto.
BYTES_DE_SECRETO = 32

#: El bot con el que se firman los mensajes que entran por webhook. Si la
#: organización no lo tiene sembrado, el mensaje entra sin bot en vez de fallar.
HANDLE_DEL_BOT_PUENTE = "bridge"

#: Lo que se publica cuando el sistema externo no manda texto. Mejor un mensaje
#: visible y vacío que un mensaje en blanco que parezca un fallo de la interfaz.
TEXTO_SI_VIENE_VACIO = "(sin contenido)"


# ── Bots ────────────────────────────────────────────────────────────────────

def list_bots(db: Session, user) -> list[CollaborationBotApp]:
    return (
        db.query(CollaborationBotApp)
        .filter(CollaborationBotApp.organization_id == _org(user))
        .all()
    )


# ── Integraciones ───────────────────────────────────────────────────────────

def list_integrations(db: Session, user) -> list[CollaborationIntegration]:
    return (
        db.query(CollaborationIntegration)
        .filter(CollaborationIntegration.organization_id == _org(user))
        .all()
    )


def create_integration(db: Session, user, *, kind: str, name: str, config: dict | None) -> CollaborationIntegration:
    from app.services.collaboration.workspaces import get_or_create_workspace

    ws = get_or_create_workspace(db, user)
    fila = CollaborationIntegration(
        organization_id=_org(user), workspace_id=ws.id,
        kind=kind, name=name, config=config or {}, created_by=user.id,
    )
    db.add(fila)
    db.commit()
    return fila


def delete_integration(db: Session, user, integration_id: str) -> None:
    fila = (
        db.query(CollaborationIntegration)
        .filter(
            CollaborationIntegration.id == integration_id,
            CollaborationIntegration.organization_id == _org(user),
        )
        .first()
    )
    if not fila:
        raise ErrorDeDominio(404, "Integración no encontrada")
    db.delete(fila)
    db.commit()


# ── Webhooks ────────────────────────────────────────────────────────────────

def list_webhooks(db: Session, user) -> list[CollaborationWebhook]:
    return (
        db.query(CollaborationWebhook)
        .filter(CollaborationWebhook.organization_id == _org(user))
        .all()
    )


def create_webhook(
    db: Session, user, *, direction: str, name: str, url: str | None,
    target_channel_id: str | None, events: list | None,
) -> CollaborationWebhook:
    """Crea un webhook con su secreto ya generado.

    El secreto lo genera el servidor y no se acepta del cliente: es lo que
    autentica a quien empuja mensajes a un canal, y dejar elegirlo permitiría
    uno adivinable.
    """
    from app.services.collaboration.workspaces import get_or_create_workspace

    ws = get_or_create_workspace(db, user)
    fila = CollaborationWebhook(
        organization_id=_org(user), workspace_id=ws.id,
        direction=direction, name=name, url=url,
        secret_token=secrets.token_urlsafe(BYTES_DE_SECRETO),
        target_channel_id=target_channel_id,
        events=events or [],
    )
    db.add(fila)
    db.commit()
    return fila


def deliver_incoming(db: Session, token: str, payload: dict) -> None:
    """Entrega en su canal un mensaje empujado por un sistema externo.

    Todas las comprobaciones son necesarias y ninguna revela por qué falla más
    de lo debido: un token que no existe, uno que no es entrante y uno sin canal
    destino dan **el mismo 404**, para no convertir este endpoint en un oráculo
    de tokens válidos.
    """
    from app.models.user import User
    from app.services.collaboration.messages import send_message

    fila = (
        db.query(CollaborationWebhook)
        .filter(
            CollaborationWebhook.secret_token == token,
            CollaborationWebhook.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not fila or fila.direction != "incoming" or not fila.target_channel_id:
        raise ErrorDeDominio(404, "Webhook inválido")
    # Segunda auditoría 2026-11 (#10): organización desactivada → 403.
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, fila.organization_id)

    cuota = consume_quota(
        db, scope="collab.webhook.incoming", tenant_id=fila.organization_id,
        subject=fila.id,
        limit=settings.COLLAB_WEBHOOK_INCOMING_PER_MIN,
        window_seconds=VENTANA_DE_CUOTA_SEGUNDOS,
    )
    if not cuota["allowed"]:
        raise ErrorDeDominio(
            status_code=429,
            detail=f"Webhook rate limit exceeded. Retry in {cuota['retry_after']}s",
        )

    canal = (
        db.query(CollaborationChannel)
        .filter(CollaborationChannel.id == fila.target_channel_id)
        .first()
    )
    if not canal:
        raise ErrorDeDominio(404, "Canal del webhook no encontrado")

    bot = (
        db.query(CollaborationBotApp)
        .filter(
            CollaborationBotApp.organization_id == fila.organization_id,
            CollaborationBotApp.handle == HANDLE_DEL_BOT_PUENTE,
        )
        .first()
    )
    # Autor sintético: el mensaje no lo escribe una persona, y `send_message`
    # necesita un sujeto con organización para acotar por tenant.
    autor = User(id="webhook", organization_id=fila.organization_id)
    send_message(
        db, autor,
        body=(payload or {}).get("text") or TEXTO_SI_VIENE_VACIO,
        channel_id=canal.id, type="bot",
        metadata_json={"card": "webhook", "source": fila.name, "raw": payload},
        bot_id=bot.id if bot else None,
    )
    fila.last_called_at = utcnow()
    db.commit()
