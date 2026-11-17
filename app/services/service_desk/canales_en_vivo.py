"""Chat de los canales en tiempo real (17-11-2026).

Antes el portal y la bandeja de conversaciones sondeaban cada 5 s. Ahora van
por los WebSocket que ya existen:

- **Cliente del portal** (`/ws/portal-notifications`, clave `client:<id>`):
  recibe `{"type": "livechat", "event": ..., "conversation_id", ...}` SOLO de
  sus conversaciones (`client_user_id`). Manda `livechat_typing` y
  `livechat_read` de una conversacion suya (se comprueba con `del_cliente`).
- **Operadores** (`/ws/notifications`): quien tiene la bandeja abierta manda
  `{"type": "channel_watch"}` (latido); queda apuntado en la bandeja de SU
  empresa durante `TTL_DE_BANDEJA_S` y recibe
  `{"type": "sd_channel", "event": ..., "conversation_id", ...}` de las
  conversaciones de su empresa (las mismas que le ensena `GET /conversations`).
  Manda `channel_typing` y `channel_read` de una conversacion de su empresa.

Eventos: `message` (mensaje nuevo, ya en la forma que ve cada lado), `typing`
(escribiendo…), `read` (leido hasta) y `status` (traspaso a agente, cierre).

Se empuja DESPUES de confirmar (`db.commit()`): el otro lado puede pedir los
mensajes en cuanto le llega el aviso. Con Redis (`REDIS_URL`) llega a todos los
procesos por el canal de cada destinatario (`ws_manager.canal_de_usuario`);
sin Redis, a las conexiones de este proceso. Si el socket no esta, el portal y
la bandeja vuelven a su sondeo: nada depende de que el aviso llegue.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Segundos que un operador sigue apuntado a la bandeja sin latido.
TTL_DE_BANDEJA_S = 90
#: Tipos de mensaje que entiende cada WebSocket.
DEL_OPERADOR = ("channel_watch", "channel_typing", "channel_read")
DEL_PORTAL = ("livechat_typing", "livechat_read")

_bandejas: dict[str, dict[str, float]] = {}


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _clave_de_bandeja(org_id: str) -> str:
    return f"contecflow:sd:channels:inbox:{org_id}"


def clave_de_cliente(client_user_id: str) -> str:
    return f"client:{client_user_id}"


# ── Envio (desde codigo sincrono) ─────────────────────────────────────────────

_redis = None


def _redis_sincrono():
    """Cliente Redis sincrono compartido (con su pool), con esperas cortas: el aviso no frena."""
    global _redis
    if _redis is None:
        import redis as sync_redis
        _redis = sync_redis.from_url(settings.REDIS_URL, decode_responses=True, socket_timeout=2,
                                     socket_connect_timeout=2)
    return _redis


def _empujar(destinos: list[str], mensaje: dict) -> None:
    """Manda `mensaje` a cada destino. Nunca lanza: el aviso es un extra."""
    if not destinos:
        return
    if settings.REDIS_URL:
        try:
            from app.services.ws_manager import canal_de_usuario
            r = _redis_sincrono()
            texto = json.dumps(mensaje, default=str)
            for d in destinos:
                r.publish(canal_de_usuario(d), texto)
            return
        except Exception:
            logger.debug("canales en vivo: Redis no disponible; se entrega en este proceso", exc_info=True)
    try:
        import anyio.from_thread
        from app.services.ws_manager import manager

        async def _local():
            for d in destinos:
                await manager.send_to_user(d, mensaje)
        anyio.from_thread.run(_local)
    except Exception:
        # Sin bucle de eventos (worker) y sin Redis: el otro lado sondea.
        logger.debug("canales en vivo: sin entrega local", exc_info=True)


def operadores_en_bandeja(org_id: Optional[str]) -> list[str]:
    """Usuarios de la empresa con la bandeja abierta (latido reciente)."""
    if not org_id:
        return []
    limite = time.time() - TTL_DE_BANDEJA_S
    if settings.REDIS_URL:
        try:
            r = _redis_sincrono()
            filas = r.hgetall(_clave_de_bandeja(org_id))
            return [u for u, ts in filas.items() if float(ts) >= limite]
        except Exception:
            logger.debug("canales en vivo: bandeja sin Redis", exc_info=True)
    return [u for u, ts in _bandejas.get(org_id, {}).items() if ts >= limite]


def _a_operadores(conv, evento: str, datos: dict, excepto: Optional[str] = None) -> None:
    destinos = [u for u in operadores_en_bandeja(conv.organization_id) if u != excepto]
    _empujar(destinos, {"type": "sd_channel", "event": evento, "conversation_id": conv.id,
                        "channel": conv.channel, "ts": _ahora().isoformat(), **datos})


def _al_cliente(conv, evento: str, datos: dict) -> None:
    if conv.channel != "livechat" or not conv.client_user_id:
        return
    _empujar([clave_de_cliente(conv.client_user_id)], {
        "type": "livechat", "event": evento, "conversation_id": conv.id, "ts": _ahora().isoformat(), **datos})


def avisar_mensaje(db, conv, mensaje) -> None:
    """Mensaje nuevo: al cliente (como lo ve el) y a los operadores de la bandeja."""
    from app.services.service_desk import conversaciones
    try:
        _a_operadores(conv, "message", {"message": conversaciones.serializar_mensaje(mensaje),
                                        "conversation": conversaciones.serializar(db, conv)})
        if conv.channel == "livechat":
            para_cliente = conversaciones.serializar_mensaje(mensaje)
            if mensaje.author_type == "agent":
                from app.services.traduccion.salida import texto_para_cliente
                para_cliente["body"] = texto_para_cliente(db, conv.organization_id, "channel_message", mensaje.id,
                                                          mensaje.body)
            _al_cliente(conv, "message", {"message": para_cliente})
    except Exception:
        logger.debug("canales en vivo: aviso de mensaje no enviado", exc_info=True)


def avisar_estado(db, conv) -> None:
    """La conversacion cambio de estado (pide persona, la toma un agente, se cierra)."""
    from app.services.service_desk import conversaciones
    try:
        datos = conversaciones.serializar(db, conv)
        _a_operadores(conv, "status", {"conversation": datos})
        _al_cliente(conv, "status", {"conversation": {"id": conv.id, "status": conv.status,
                                                      "ticket_number": datos.get("ticket_number")}})
    except Exception:
        logger.debug("canales en vivo: aviso de estado no enviado", exc_info=True)


# ── Mensajes que llegan por los WebSocket ─────────────────────────────────────

EnSesion = Callable[..., Awaitable[Any]]


def _apuntar_en_bandeja(org_id: str, user_id: str) -> None:
    ahora = time.time()
    if settings.REDIS_URL:
        try:
            r = _redis_sincrono()
            clave = _clave_de_bandeja(org_id)
            r.hset(clave, user_id, ahora)
            r.expire(clave, TTL_DE_BANDEJA_S * 2)
            return
        except Exception:
            logger.debug("canales en vivo: bandeja en memoria", exc_info=True)
    filas = _bandejas.setdefault(org_id, {})
    filas[user_id] = ahora
    for u, ts in list(filas.items()):
        if ts < ahora - TTL_DE_BANDEJA_S:
            filas.pop(u, None)


def _es_operador(usuario) -> bool:
    from app.core.deps import require_internal_user
    return getattr(usuario, "role", None) in require_internal_user.roles and bool(
        getattr(usuario, "organization_id", None))


def _conv_de_la_empresa(db, conv_id: str, org_id):
    from app.models.service_desk import ChannelConversation
    return db.query(ChannelConversation).filter(ChannelConversation.id == conv_id,
                                                ChannelConversation.organization_id == org_id).first()


def _conv_del_cliente(db, conv_id: str, client_user_id: str):
    from app.models.service_desk import ChannelConversation
    return db.query(ChannelConversation).filter(ChannelConversation.id == conv_id,
                                                ChannelConversation.client_user_id == client_user_id).first()


def _operador(db, usuario, tipo: str, conv_id: Optional[str]) -> None:
    if tipo == "channel_watch":
        _apuntar_en_bandeja(usuario.organization_id, usuario.id)
        return
    conv = _conv_de_la_empresa(db, conv_id, usuario.organization_id) if conv_id else None
    if conv is None:
        return
    if tipo == "channel_typing":
        _al_cliente(conv, "typing", {"who": "agent"})
        _a_operadores(conv, "typing", {"who": "agent", "user_id": usuario.id, "name": usuario.full_name},
                      excepto=usuario.id)
    elif tipo == "channel_read":
        conv.agent_read_at = _ahora()
        db.commit()
        _al_cliente(conv, "read", {"by": "agent", "read_at": conv.agent_read_at.isoformat()})
        _a_operadores(conv, "read", {"by": "agent", "read_at": conv.agent_read_at.isoformat()},
                      excepto=usuario.id)


def _cliente(db, cliente, tipo: str, conv_id: Optional[str]) -> None:
    conv = _conv_del_cliente(db, conv_id, cliente.id) if conv_id else None
    if conv is None:
        return
    if tipo == "livechat_typing":
        _a_operadores(conv, "typing", {"who": "customer"})
    elif tipo == "livechat_read":
        conv.client_read_at = _ahora()
        db.commit()
        _a_operadores(conv, "read", {"by": "customer", "read_at": conv.client_read_at.isoformat()})


async def mensaje_del_operador(en_sesion: EnSesion, db, usuario, msg: dict) -> bool:
    """Atiende un mensaje del WebSocket de operadores. True si era de los canales."""
    tipo = msg.get("type")
    if tipo not in DEL_OPERADOR:
        return False
    if not _es_operador(usuario):
        return True
    conv_id = str(msg.get("conversation_id") or "")[:36] or None
    await en_sesion(_operador, db, usuario, tipo, conv_id)
    return True


async def mensaje_del_portal(en_sesion: EnSesion, db, cliente, msg: dict) -> bool:
    """Atiende un mensaje del WebSocket del portal. True si era del chat."""
    tipo = msg.get("type")
    if tipo not in DEL_PORTAL:
        return False
    conv_id = str(msg.get("conversation_id") or "")[:36] or None
    await en_sesion(_cliente, db, cliente, tipo, conv_id)
    return True
