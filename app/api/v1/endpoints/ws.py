"""
ws.py — WebSocket para notificaciones en tiempo real.

Endpoint: /ws/notifications?token=<jwt>
- El cliente se conecta con su JWT
- El servidor envía notificaciones cuando hay:
  * Nuevas alertas
  * Aprobaciones pendientes
  * Cambios en tareas asignadas al usuario
  * Menciones

Multi-worker support via Redis Pub/Sub:
  Cuando REDIS_URL está configurado, los mensajes se publican en el canal
  "clarive:ws:<user_id>" y cada worker se suscribe para reenviarlos a sus
  conexiones locales. Sin Redis, funciona en modo in-memory (dev / single-worker).
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, Header, Cookie
from typing import Dict, List, Optional
import asyncio
import json
import logging
import os
import secrets
import time
from datetime import datetime, timezone
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import verify_client_token
import app.services.ws_service as _ws_svc

router = APIRouter(prefix="/ws", tags=["WebSocket"])
log    = logging.getLogger(__name__)

_REDIS_URL: Optional[str] = settings.REDIS_URL or ""
if not _REDIS_URL:
    log.warning(
        "REDIS_URL no configurado: los tickets WS se almacenan en memoria del proceso. "
        "Con múltiples workers de Uvicorn los WebSockets fallarán aleatoriamente. "
        "Configura REDIS_URL para producción multi-worker."
    )

# ── WS Ticket Store ────────────────────────────────────────────────────────────
# Short-lived (60 s) one-time tickets so browser clients can authenticate the
# WebSocket connection without reading the httpOnly access token from JS.
# Production path uses Redis (shared across workers). In-memory is fallback-only.
_ws_tickets: Dict[str, tuple] = {}   # ticket → (user_id, expires_at)
_WS_TICKET_TTL = 60  # seconds
_portal_ws_tickets: Dict[str, tuple] = {}  # ticket → (client_id, expires_at)

_WS_TICKET_KEY_PREFIX = "clarive:ws:ticket:user:"
_PORTAL_WS_TICKET_KEY_PREFIX = "clarive:ws:ticket:portal:"


def _issue_ws_ticket_local(user_id: str) -> str:
    """Create a single-use WS ticket valid for _WS_TICKET_TTL seconds."""
    # Prune expired tickets lazily
    now = time.monotonic()
    expired = [t for t, (_, exp) in _ws_tickets.items() if exp < now]
    for t in expired:
        _ws_tickets.pop(t, None)
    ticket = secrets.token_urlsafe(24)
    _ws_tickets[ticket] = (user_id, now + _WS_TICKET_TTL)
    return ticket


def _consume_ws_ticket_local(ticket: str) -> Optional[str]:
    """Validate and consume a WS ticket, returning user_id or None."""
    entry = _ws_tickets.pop(ticket, None)
    if entry is None:
        return None
    user_id, expires_at = entry
    if time.monotonic() > expires_at:
        return None
    return user_id


def _issue_portal_ws_ticket_local(client_id: str) -> str:
    now = time.monotonic()
    expired = [t for t, (_, exp) in _portal_ws_tickets.items() if exp < now]
    for t in expired:
        _portal_ws_tickets.pop(t, None)
    ticket = secrets.token_urlsafe(24)
    _portal_ws_tickets[ticket] = (client_id, now + _WS_TICKET_TTL)
    return ticket


def _consume_portal_ws_ticket_local(ticket: str) -> Optional[str]:
    entry = _portal_ws_tickets.pop(ticket, None)
    if entry is None:
        return None
    client_id, expires_at = entry
    if time.monotonic() > expires_at:
        return None
    return client_id


async def _issue_ws_ticket(user_id: str) -> str:
    """Emit a one-time WS ticket.

    When REDIS_URL is configured, the ticket is stored in Redis so ANY worker
    can consume it.  Errors propagate to the caller (route handler converts them
    to HTTP 503).  Without Redis, the local in-memory store is used — only safe
    for single-worker / dev deployments.
    """
    ticket = secrets.token_urlsafe(24)
    if _REDIS_URL:
        # Do NOT fall back to in-memory on Redis errors: a ticket written to
        # worker-1's dict would be invisible to worker-2's consume call.
        r = await _get_redis()
        await r.setex(f"{_WS_TICKET_KEY_PREFIX}{ticket}", _WS_TICKET_TTL, user_id)
        return ticket
    return _issue_ws_ticket_local(user_id)


async def _consume_ws_ticket(ticket: str) -> Optional[str]:
    """Consume a one-time WS ticket, returning user_id or None."""
    if _REDIS_URL:
        try:
            r = await _get_redis()
            key = f"{_WS_TICKET_KEY_PREFIX}{ticket}"
            # Atomic single-use consume (GET + DEL in one server-side script).
            consumed = await r.eval(
                "local v=redis.call('GET',KEYS[1]); if v then redis.call('DEL',KEYS[1]); end; return v",
                1,
                key,
            )
            return consumed if consumed else None
        except Exception as exc:
            # Do NOT fall back to in-memory: reject the ticket to avoid
            # accepting unverified connections when Redis is unreachable.
            log.error("WS ticket Redis consume failed — rejecting ticket: %s", exc)
            return None
    return _consume_ws_ticket_local(ticket)


async def _issue_portal_ws_ticket(client_id: str) -> str:
    """Emit a one-time portal WS ticket (see _issue_ws_ticket for rationale)."""
    ticket = secrets.token_urlsafe(24)
    if _REDIS_URL:
        r = await _get_redis()
        await r.setex(f"{_PORTAL_WS_TICKET_KEY_PREFIX}{ticket}", _WS_TICKET_TTL, client_id)
        return ticket
    return _issue_portal_ws_ticket_local(client_id)


async def _consume_portal_ws_ticket(ticket: str) -> Optional[str]:
    """Consume a one-time portal WS ticket, returning client_id or None."""
    if _REDIS_URL:
        try:
            r = await _get_redis()
            key = f"{_PORTAL_WS_TICKET_KEY_PREFIX}{ticket}"
            consumed = await r.eval(
                "local v=redis.call('GET',KEYS[1]); if v then redis.call('DEL',KEYS[1]); end; return v",
                1,
                key,
            )
            return consumed if consumed else None
        except Exception as exc:
            log.error("Portal WS ticket Redis consume failed — rejecting ticket: %s", exc)
            return None
    return _consume_portal_ws_ticket_local(ticket)

# Shared async Redis client (initialised lazily on first use, reused thereafter)
_redis_client = None
_redis_client_lock = asyncio.Lock() if False else None   # replaced at runtime by actual lock


async def _get_redis():
    """Return the module-level shared Redis client, creating it once."""
    global _redis_client, _redis_client_lock
    if _redis_client_lock is None:
        _redis_client_lock = asyncio.Lock()
    async with _redis_client_lock:
        if _redis_client is None:
            import redis.asyncio as aioredis
            _redis_client = aioredis.from_url(_REDIS_URL, decode_responses=True)
    return _redis_client


# ── Connection Manager ─────────────────────────────────────────────────────────
class ConnectionManager:
    """Manages local WebSocket connections for this worker process.

    When Redis is available, uses Pub/Sub to forward messages published by
    any worker to all connected clients regardless of which worker they hit.
    Without Redis, messages only reach clients on the same worker (dev mode).
    """

    def __init__(self):
        self.connections: Dict[str, List[WebSocket]] = {}   # user_id → [ws, ...]
        self._redis_sub_task: Optional[asyncio.Task] = None

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(websocket)
        log.info(f"WS: {user_id} conectado ({len(self.connections[user_id])} sesiones)")
        # Start Redis subscriber on first connection if not already running
        if _REDIS_URL and self._redis_sub_task is None:
            self._redis_sub_task = asyncio.create_task(self._redis_subscriber())

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.connections:
            self.connections[user_id] = [ws for ws in self.connections[user_id] if ws != websocket]
            if not self.connections[user_id]:
                del self.connections[user_id]
        log.info(f"WS: {user_id} desconectado")

    async def send_to_user(self, user_id: str, message: dict):
        """Send a message to all active sessions of a user on this worker."""
        if user_id not in self.connections:
            return
        dead = []
        for ws in self.connections[user_id]:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections[user_id].remove(ws)

    async def publish(self, user_id: str, message: dict):
        """Publish a message for a user.

        With Redis: publishes to the shared channel so ALL workers deliver it.
        Without Redis: delivers locally (dev / single-worker).
        """
        if _REDIS_URL:
            try:
                r = await _get_redis()
                channel = f"clarive:ws:{user_id}"
                await r.publish(channel, json.dumps(message))
                return
            except Exception as exc:
                log.warning(f"Redis publish failed, falling back to local: {exc}")
        # Fallback: local delivery
        await self.send_to_user(user_id, message)

    async def broadcast(self, message: dict):
        """Send to all locally connected users."""
        for user_id in list(self.connections.keys()):
            await self.send_to_user(user_id, message)

    async def _redis_subscriber(self):
        """Background task: subscribe to per-user channels and forward to local WS connections."""
        try:
            r = await _get_redis()
            pubsub = r.pubsub()
            # Subscribe to a pattern matching all user channels for this app
            await pubsub.psubscribe("clarive:ws:*")
            log.info("WS: Redis Pub/Sub subscriber started (pattern=clarive:ws:*)")
            async for raw in pubsub.listen():
                if raw["type"] != "pmessage":
                    continue
                # channel = "clarive:ws:<user_id>"
                channel: str = raw.get("channel", "")
                user_id = channel.removeprefix("clarive:ws:")
                if not user_id or user_id not in self.connections:
                    continue
                try:
                    msg = json.loads(raw["data"])
                    await self.send_to_user(user_id, msg)
                except Exception as exc:
                    log.debug(f"WS Redis subscriber parse error: {exc}")
        except Exception as exc:
            log.warning(f"WS Redis subscriber crashed: {exc}")
            self._redis_sub_task = None  # Allow restart on next connection

    def connected_users(self) -> List[str]:
        return list(self.connections.keys())

    def total_connections(self) -> int:
        return sum(len(v) for v in self.connections.values())


# Instancia global — compartida entre todas las solicitudes de este worker
manager = ConnectionManager()


async def _validate_jwt(token: str, db) -> str:
    """Valida el token JWT y verifica que el usuario exista y esté activo en BD."""
    from app.core.security import decode_token
    from app.models.user import User
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        return None
    return user_id


async def _poll_and_send(websocket: WebSocket, user_id: str, db):
    """
    Sondea la BD cada 15s y envía notificaciones no leídas al cliente.
    En producción se reemplazaría por eventos de BD (pg_notify / Redis).
    """
    last_count = None
    while True:
        try:
            count, notifs = _ws_svc.get_unread_notifications(db, user_id)

            if count != last_count:
                last_count = count
                await websocket.send_text(json.dumps({
                    "type":  "notifications",
                    "count": count,
                    "items": [{
                        "id":           n.id,
                        "title":        n.title,
                        "message":      n.message,
                        "type":         n.type,
                        "entity_type":  n.entity_type,
                        "entity_id":    n.entity_id,
                        "created_at":   str(n.created_at)[:16] if n.created_at else None,
                    } for n in notifs],
                    "ts": datetime.now(timezone.utc).isoformat(),
                }))

        except WebSocketDisconnect:
            break
        except Exception as e:
            log.debug(f"WS poll error: {e}")
            break

        await asyncio.sleep(15)


async def _poll_and_send_client(websocket: WebSocket, client_id: str, db):
    """Poll client-facing updates (messages + tickets) and push via WS."""
    from app.models.client_portal import ClientMessage
    from app.models.service_desk import Ticket, TicketComment
    from sqlalchemy import func
        poll_data = _ws_svc.get_portal_poll_data(db, client_id)
            unread_messages = poll_data["unread_messages"]
            open_tickets = poll_data["open_tickets"]
            recent_public_comments = poll_data["recent_public_comments"]

            snapshot = (unread_messages, open_tickets, len(recent_public_comments))
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                await websocket.send_text(json.dumps({
                    "type": "portal_notifications",
                    "unread_messages": unread_messages,
                    "open_tickets": open_tickets,
                    "recent_ticket_replies": [{
                        "id": c.id,
                        "ticket_id": c.ticket_id,
                        "body": c.body,
                        "created_at": str(c.created_at)[:16] if c.created_at else None,
                    } for c in recent_public_comments],
                    "ts": datetime.now(timezone.utc).isoformat(),
                }))
        except WebSocketDisconnect:
            break
        except Exception as e:
            log.debug(f"Portal WS poll error: {e}")
            break

        await asyncio.sleep(10)


@router.get("/ticket", summary="Obtener ticket de un solo uso para conexión WebSocket")
async def get_ws_ticket(
    current_user=Depends(get_current_user),
):
    """Emite un ticket de corta duración (60 s) que el cliente puede usar como
    parámetro ?ticket= al abrir la conexión WebSocket.  Esto evita exponer el
    access token JWT en JavaScript (el token está sólo en una httpOnly cookie)."""
    try:
        ticket = await _issue_ws_ticket(str(current_user.id))
    except Exception as exc:
        log.error("No se pudo emitir WS ticket (Redis error): %s", exc)
        raise HTTPException(503, "Servicio no disponible temporalmente")
    return {"ticket": ticket, "expires_in": _WS_TICKET_TTL}


@router.get("/portal-ticket", summary="Obtener ticket WS de portal cliente")
async def get_portal_ws_ticket(
    authorization: Optional[str] = Header(None),
    portal_access_token: Optional[str] = Cookie(None),
):
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
    elif portal_access_token:
        token = portal_access_token
    if not token:
        raise HTTPException(401, "Autenticación requerida")

    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        client = verify_client_token(token, db)
        if not client or not getattr(client, "is_active", False):
            raise HTTPException(401, "Token de cliente inválido")
        try:
            ticket = await _issue_portal_ws_ticket(str(client.id))
        except Exception as exc:
            log.error("No se pudo emitir portal WS ticket (Redis error): %s", exc)
            raise HTTPException(503, "Servicio no disponible temporalmente")
        return {"ticket": ticket, "expires_in": _WS_TICKET_TTL}
    finally:
        db.close()


@router.websocket("/notifications")
async def ws_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    ticket: Optional[str] = Query(default=None),
):
    """
    WebSocket de notificaciones en tiempo real.
    Conectar: ws://localhost:8000/api/v1/ws/notifications?token=<jwt>
    """
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        # Accept either a short-lived one-shot ticket (preferred) or a raw JWT
        user_id: Optional[str] = None
        if ticket:
            user_id = await _consume_ws_ticket(ticket)
            if not user_id:
                await websocket.close(code=4001, reason="Ticket inválido o expirado")
                return
        elif token:
            user_id = await _validate_jwt(token, db)
            if not user_id:
                await websocket.close(code=4001, reason="Token inválido")
                return
        else:
            await websocket.close(code=4001, reason="Se requiere ticket o token")
            return

        await manager.connect(websocket, user_id)

        # Enviar estado inicial
        await websocket.send_text(json.dumps({
            "type":    "connected",
            "user_id": user_id,
            "ts":      datetime.now(timezone.utc).isoformat(),
        }))

        # Iniciar el loop de polling en background
        poll_task = asyncio.create_task(_poll_and_send(websocket, user_id, db))

        try:
            while True:
                # Escuchar mensajes del cliente (ping/pong, mark_read)
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    elif msg.get("type") == "mark_read" and msg.get("id"):
                        _ws_svc.mark_notification_read(db, msg["id"], user_id)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    logging.getLogger(__name__).warning(f"WS notifications malformed message: {e}")
                except Exception as e:
                    logging.getLogger(__name__).error(f"Unexpected error processing ws message: {e}")
        except WebSocketDisconnect:
            poll_task.cancel()
    finally:
        manager.disconnect(websocket, user_id if 'user_id' in locals() else 'unknown')
        db.close()


@router.websocket("/portal-notifications")
async def ws_portal_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    ticket: Optional[str] = Query(default=None),
):
    """WebSocket notifications for client portal users."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    client_id = None
    try:
        if ticket:
            client_id = await _consume_portal_ws_ticket(ticket)
            if not client_id:
                await websocket.close(code=4001, reason="Ticket inválido o expirado")
                return
        elif token:
            client = verify_client_token(token, db)
            client_id = str(client.id) if client else None
            if not client_id:
                await websocket.close(code=4001, reason="Token inválido")
                return
        else:
            await websocket.close(code=4001, reason="Se requiere ticket o token")
            return

        manager_key = f"client:{client_id}"
        await manager.connect(websocket, manager_key)
        await websocket.send_text(json.dumps({
            "type": "connected",
            "client_id": client_id,
            "ts": datetime.now(timezone.utc).isoformat(),
        }))
        poll_task = asyncio.create_task(_poll_and_send_client(websocket, client_id, db))

        try:
            while True:
                data = await websocket.receive_text()
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                except Exception:
                    pass
        except WebSocketDisconnect:
            poll_task.cancel()
    finally:
        if client_id:
            manager.disconnect(websocket, f"client:{client_id}")
        db.close()


@router.get("/notifications/stats", summary="Estadísticas de conexiones WebSocket activas")
async def ws_stats(token: str = Query(...)):
    """Requiere token JWT de acceso válido para evitar exponer usuarios conectados."""
    from app.core.security import decode_token
    from fastapi import HTTPException
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token inválido")
    return {
        "connected_users":   manager.connected_users(),
        "total_connections": manager.total_connections(),
    }


@router.get("/token", summary="Obtener token de corta duración para WebSocket")
def get_ws_token(current_user=Depends(get_current_user)):
    """Returns a short-lived JWT (5 min) to authenticate WebSocket connections."""
    from datetime import timedelta
    from app.core.security import create_access_token
    token = create_access_token(
        subject=current_user.id,
        extra={"ws": True},
        expires_delta=timedelta(minutes=5),
    )
    return {"token": token}


# ── Wiki document real-time collaboration ─────────────────────────────────────
# Implements a simple broadcast hub: every update sent by one client is
# forwarded to all other clients editing the same document.  This is
# protocol-agnostic so it works with both plain-text diffs and binary Yjs
# awareness/update messages sent as base64 JSON envelopes.

_doc_rooms: Dict[str, List[WebSocket]] = {}   # doc_id → [ws, ...] (local worker)
_doc_rooms_lock = asyncio.Lock()
_doc_redis_sub_task: Optional[asyncio.Task] = None


async def _ensure_doc_redis_sub() -> None:
    """Start the Redis pub/sub subscriber for doc collab once per worker."""
    global _doc_redis_sub_task
    if not _REDIS_URL:
        return
    if _doc_redis_sub_task is not None and not _doc_redis_sub_task.done():
        return
    _doc_redis_sub_task = asyncio.create_task(_doc_redis_subscriber())


async def _doc_redis_subscriber() -> None:
    """Forward Redis doc collab messages to locally connected clients."""
    global _doc_redis_sub_task
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(_REDIS_URL, decode_responses=True)
        pubsub = r.pubsub()
        await pubsub.psubscribe("clarive:doc:*")
        log.info("WS: Doc collab Redis pub/sub subscriber started")
        async for raw in pubsub.listen():
            if raw["type"] != "pmessage":
                continue
            channel: str = raw.get("channel", "")
            doc_id = channel.removeprefix("clarive:doc:")
            if not doc_id or doc_id not in _doc_rooms:
                continue
            try:
                msg = json.loads(raw["data"])
                await _broadcast_doc_local(doc_id, msg)
            except Exception as exc:
                log.debug("Doc Redis subscriber parse error: %s", exc)
    except Exception as exc:
        log.warning("Doc collab Redis subscriber crashed: %s", exc)
        _doc_redis_sub_task = None  # Allow restart on next connection


async def _broadcast_doc_local(doc_id: str, message: dict, exclude: WebSocket = None) -> None:
    """Send to all locally-connected clients in a doc room."""
    room = list(_doc_rooms.get(doc_id, []))
    text = json.dumps(message)
    for ws in room:
        if ws is exclude:
            continue
        try:
            await ws.send_text(text)
        except Exception:
            pass


@router.websocket("/doc/{doc_id}")
async def ws_doc_collab(
    websocket: WebSocket,
    doc_id: str,
    token: str = Query(...),
):
    """
    Wiki document collaboration WebSocket.
    Connect: ws://.../api/v1/ws/doc/<doc_id>?token=<jwt>

    Protocol (JSON messages):
      Client → Server:
        { "type": "update",  "data": "<base64 Yjs update>" }
        { "type": "awareness", "data": "<base64 Yjs awareness update>" }
        { "type": "ping" }

      Server → Client:
        { "type": "update",    "data": "...", "from": "<user_id>" }
        { "type": "awareness", "data": "...", "from": "<user_id>" }
        { "type": "joined",    "user_id": "...", "peers": <count> }
        { "type": "left",      "user_id": "...", "peers": <count> }
        { "type": "pong" }
    """
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        user_id = await _validate_jwt(token, db)
        if not user_id:
            await websocket.close(code=4001, reason="Token inválido")
            return

        await websocket.accept()

        async with _doc_rooms_lock:
            if doc_id not in _doc_rooms:
                _doc_rooms[doc_id] = []
            _doc_rooms[doc_id].append(websocket)

        await _ensure_doc_redis_sub()

        peer_count = len(_doc_rooms.get(doc_id, []))
        await websocket.send_text(json.dumps({
            "type": "joined", "user_id": user_id, "peers": peer_count,
        }))

        # Notify others
        await _broadcast_doc(doc_id, {"type": "joined", "user_id": user_id, "peers": peer_count}, exclude=websocket)

        try:
            while True:
                raw = await websocket.receive_text()
                try:
                    msg = json.loads(raw)
                    msg_type = msg.get("type")

                    if msg_type == "ping":
                        await websocket.send_text(json.dumps({"type": "pong"}))
                    elif msg_type in ("update", "awareness"):
                        # Broadcast to all other editors of this document
                        out = {"type": msg_type, "data": msg.get("data"), "from": user_id}
                        await _broadcast_doc(doc_id, out, exclude=websocket)
                except Exception:
                    pass
        except WebSocketDisconnect:
            pass
    finally:
        async with _doc_rooms_lock:
            room = _doc_rooms.get(doc_id, [])
            if websocket in room:
                room.remove(websocket)
            if not room:
                _doc_rooms.pop(doc_id, None)

        peer_count = len(_doc_rooms.get(doc_id, []))
        await _broadcast_doc(doc_id, {"type": "left", "user_id": locals().get("user_id", "?"), "peers": peer_count})
        db.close()


async def _broadcast_doc(doc_id: str, message: dict, exclude: WebSocket = None) -> None:
    """Send a message to all clients editing a document.

    With Redis: publishes to the shared channel so all workers deliver it.
    Without Redis: local delivery only (dev / single-worker).
    Note: Redis path cannot honour `exclude` across workers; clients should
    de-duplicate their own updates by checking the `from` field.
    """
    if _REDIS_URL:
        try:
            import redis.asyncio as aioredis
            r = aioredis.from_url(_REDIS_URL, decode_responses=True)
            await r.publish(f"clarive:doc:{doc_id}", json.dumps(message))
            await r.aclose()
            return
        except Exception as exc:
            log.warning("Doc Redis publish failed, falling back to local: %s", exc)
    await _broadcast_doc_local(doc_id, message, exclude=exclude)

