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

import hashlib
import secrets

from sqlalchemy import and_, or_
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
from app.core.codigos_de_error import error

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
        raise error(404, "no_encontrado", detail="Integración no encontrada", que="integracion")
    db.delete(fila)
    db.commit()


# ── Webhooks ────────────────────────────────────────────────────────────────

def enmascarar_secreto(secreto: str) -> str:
    """Lo único que se guarda del secreto (23-11-2026): sus 4 últimos caracteres,
    para reconocerlo. No sirve para autenticarse: la entrega va por la huella."""
    return "••••" + (secreto or "")[-4:] if secreto and len(secreto) > 8 else "••••"


def _dejar_sin_secreto_en_claro(db: Session, filas: list[CollaborationWebhook]) -> None:
    """Filas anteriores al 23-11-2026: guardaban el secreto en claro. Se calcula
    su huella (si falta) y el claro se sustituye por la máscara. Sin migración:
    se hace la primera vez que se listan, y la entrega sigue igual (por huella)."""
    cambiadas = False
    for f in filas:
        if f.secret_token and not f.secret_token.startswith("••••"):
            if not f.secret_token_hash:
                f.secret_token_hash = huella_del_secreto(f.secret_token)
            f.secret_token = enmascarar_secreto(f.secret_token)
            cambiadas = True
    if cambiadas:
        db.commit()


def list_webhooks(db: Session, user) -> list[CollaborationWebhook]:
    filas = (
        db.query(CollaborationWebhook)
        .filter(CollaborationWebhook.organization_id == _org(user))
        .all()
    )
    _dejar_sin_secreto_en_claro(db, filas)
    return filas


def create_webhook(
    db: Session, user, *, direction: str, name: str, url: str | None,
    target_channel_id: str | None, events: list | None,
) -> tuple[CollaborationWebhook, str]:
    """Crea un webhook con su secreto ya generado. Devuelve la fila y el secreto.

    23-11-2026 (auditoría 05, decisión): el secreto se enseña UNA sola vez, en
    la respuesta del alta. En la base solo queda su huella SHA-256 (la entrega
    busca por ella) y una máscara con los 4 últimos caracteres; si se pierde,
    se crea otro webhook.

    El secreto lo genera el servidor y no se acepta del cliente: es lo que
    autentica a quien empuja mensajes a un canal, y dejar elegirlo permitiría
    uno adivinable.

    Auditoría 22-11-2026 (fantasma 3 y A23):
    - los webhooks SALIENTES del chat se guardaban y nada los entregaba nunca;
      se retiran (422 `webhook_saliente_no_disponible`): los avisos hacia una
      URL externa son los webhooks salientes de la empresa (Integraciones →
      Webhooks, `enterprise_service.webhooks`, con reintentos y cortacircuitos);
    - el canal destino tiene que ser de la empresa (antes no se comprobaba).
    """
    from app.services.collaboration.workspaces import get_or_create_workspace

    if direction != "incoming":
        raise error(422, "webhook_saliente_no_disponible")
    if target_channel_id and not db.query(CollaborationChannel.id).filter(
        CollaborationChannel.id == target_channel_id,
        CollaborationChannel.organization_id == _org(user),
    ).first():
        raise error(404, "no_encontrado", que="canal")
    ws = get_or_create_workspace(db, user)
    secreto = secrets.token_urlsafe(BYTES_DE_SECRETO)
    fila = CollaborationWebhook(
        organization_id=_org(user), workspace_id=ws.id,
        direction=direction, name=name, url=url,
        secret_token=enmascarar_secreto(secreto), secret_token_hash=huella_del_secreto(secreto),
        target_channel_id=target_channel_id,
        events=events or [],
    )
    db.add(fila)
    db.commit()
    return fila, secreto


def huella_del_secreto(token: str) -> str:
    """SHA-256 del secreto del webhook (migración 196, A23). La entrega busca
    por la huella; desde el 23-11-2026 el secreto en claro ya no se guarda (solo
    se enseña al crearlo)."""
    return hashlib.sha256((token or "").encode()).hexdigest()


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
            # Filas sin huella (creadas por fuera del servicio): por el secreto.
            or_(CollaborationWebhook.secret_token_hash == huella_del_secreto(token),
                and_(CollaborationWebhook.secret_token_hash.is_(None),
                     CollaborationWebhook.secret_token == token)),
            CollaborationWebhook.is_active == True,  # noqa: E712
        )
        .first()
    )
    if not fila or fila.direction != "incoming" or not fila.target_channel_id:
        raise error(404, "webhook_no_autorizado", detail="Webhook inválido")
    # Segunda auditoría 2026-11 (#10): organización desactivada → 403.
    from app.db.session import exigir_organizacion_activa
    exigir_organizacion_activa(db, fila.organization_id)
    # 24-11-2026 (migración 208): ruta anónima; desde aquí, la empresa del
    # webhook (filtro y sellado del mensaje, sus avisos y su índice).
    from app.db.session import publicar_empresa
    publicar_empresa(db, fila.organization_id)

    cuota = consume_quota(
        db, scope="collab.webhook.incoming", tenant_id=fila.organization_id,
        subject=fila.id,
        limit=settings.COLLAB_WEBHOOK_INCOMING_PER_MIN,
        window_seconds=VENTANA_DE_CUOTA_SEGUNDOS,
    )
    if not cuota["allowed"]:
        raise error(429, "limite_webhook", detail=f"Webhook rate limit exceeded. Retry in {cuota['retry_after']}s", segundos=cuota['retry_after'])

    canal = (
        db.query(CollaborationChannel)
        .filter(CollaborationChannel.id == fila.target_channel_id,
                CollaborationChannel.organization_id == fila.organization_id)   # A23
        .first()
    )
    if not canal:
        raise error(404, "no_encontrado", detail="Canal del webhook no encontrado", que="canal")

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
