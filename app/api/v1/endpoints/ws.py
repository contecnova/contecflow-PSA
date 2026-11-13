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
  "contecflow:ws:<user_id>" y cada worker se suscribe para reenviarlos a sus
  conexiones locales. Sin Redis, funciona en modo in-memory (dev / single-worker).
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, Header, Cookie
from typing import Dict, List, Optional
import asyncio
import json
import logging
import secrets
import re
from datetime import datetime, timezone
from app.core.config import settings
from app.core.deps import get_current_user
from app.core.security import verify_client_token
import app.services.ws_service as _ws_svc
from app.db.session import publicar_contexto_de_tenant
from app.core.async_db import run_db

router = APIRouter(prefix="/ws", tags=["WebSocket"])
log    = logging.getLogger(__name__)

_REDIS_URL: Optional[str] = settings.REDIS_URL or ""
_IS_PRODUCTION_ENV = (settings.ENVIRONMENT or "development").lower() in {"production", "prod"}
if not _REDIS_URL:
    _missing_redis_msg = (
        "REDIS_URL no configurado: los tickets WS se almacenan en memoria del proceso. "
        "Con múltiples workers de Uvicorn los WebSockets fallarán aleatoriamente. "
        "Configura REDIS_URL para producción multi-worker."
    )
    if _IS_PRODUCTION_ENV:
        log.warning(_missing_redis_msg)
    else:
        log.info(_missing_redis_msg)

# ── WS Ticket Store (delegated to ws_service) ────────────────────────────────
_ws_tickets = _ws_svc._ws_tickets
_WS_TICKET_TTL = _ws_svc._WS_TICKET_TTL
_portal_ws_tickets = _ws_svc._portal_ws_tickets

_WS_TICKET_KEY_PREFIX = "contecflow:ws:ticket:user:"
_PORTAL_WS_TICKET_KEY_PREFIX = "contecflow:ws:ticket:portal:"
_SAFE_TICKET_RE = re.compile(r"^[A-Za-z0-9_-]{20,200}$")
_REDIS_ATOMIC_CONSUME_SCRIPT = "local v=redis.call('GET',KEYS[1]); if v then redis.call('DEL',KEYS[1]); end; return v"
_redis_fallback_warned: set[str] = set()

_issue_ws_ticket_local = _ws_svc.issue_ws_ticket_local
_consume_ws_ticket_local = _ws_svc.consume_ws_ticket_local
_issue_portal_ws_ticket_local = _ws_svc.issue_portal_ws_ticket_local
_consume_portal_ws_ticket_local = _ws_svc.consume_portal_ws_ticket_local


def _is_safe_ticket(ticket: str) -> bool:
    return bool(ticket and isinstance(ticket, str) and _SAFE_TICKET_RE.fullmatch(ticket))


def _warn_redis_fallback_once(key: str, template: str, exc: Exception) -> None:
    if key not in _redis_fallback_warned:
        _redis_fallback_warned.add(key)
        if _IS_PRODUCTION_ENV:
            log.warning(template, exc)
        else:
            log.info(template, exc)
    else:
        log.debug(template, exc)


#: Separa el usuario de la organización activa dentro del valor del ticket.
_SEPARADOR_DE_ORG = "|"


def separar_identidad(identidad: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """(user_id, organización activa) de lo que guarda el ticket WS.

    Segunda auditoría 2026-11 (#7): el ticket lleva la empresa ACTIVA de la
    sesión que lo pidió; un ticket sin ella (emitido antes) da `None` y la
    conexión usa la de ficha, como siempre.
    """
    if not identidad:
        return None, None
    usuario, _, org = identidad.partition(_SEPARADOR_DE_ORG)
    return usuario or None, org or None


async def _issue_ws_ticket(user_id: str, organization_id: Optional[str] = None) -> str:
    """Emit a one-time WS ticket.

    When REDIS_URL is configured and Redis is reachable, the ticket is stored
    in Redis so any worker can consume it.  If Redis is unreachable (e.g. local
    dev without a running Redis), falls back to the in-memory store — safe for
    single-worker deployments.

    `organization_id` es la empresa activa de la petición (claim `org`); el
    socket la publica al abrirse, revalidando la pertenencia.
    """
    if organization_id:
        user_id = f"{user_id}{_SEPARADOR_DE_ORG}{organization_id}"
    ticket = secrets.token_urlsafe(24)
    if _REDIS_URL:
        try:
            r = await _get_redis()
            await r.setex(f"{_WS_TICKET_KEY_PREFIX}{ticket}", _WS_TICKET_TTL, user_id)
            return ticket
        except Exception as exc:
            log.debug("_issue_ws_ticket: excepcion ignorada", exc_info=True)
            _warn_redis_fallback_once(
                "ws_issue",
                "Redis unreachable, falling back to in-memory WS ticket store: %s",
                exc,
            )
    return _issue_ws_ticket_local(user_id)


async def _consume_ws_ticket(ticket: str) -> Optional[str]:
    """Consume a one-time WS ticket, returning user_id or None."""
    if not _is_safe_ticket(ticket):
        log.warning("WS ticket rechazado por formato inválido")
        return None
    if _REDIS_URL:
        try:
            r = await _get_redis()
            key = f"{_WS_TICKET_KEY_PREFIX}{ticket}"
            # Atomic single-use consume (GET + DEL in one server-side script).
            consumed = await r.eval(
                _REDIS_ATOMIC_CONSUME_SCRIPT,
                1,
                key,
            )
            if consumed:
                return consumed
            # Redis reachable but ticket not found — fall through to in-memory
            # in case it was issued during a prior Redis outage.
        except Exception as exc:
            log.debug("_consume_ws_ticket: excepcion ignorada", exc_info=True)
            _warn_redis_fallback_once(
                "ws_consume",
                "Redis unreachable during WS ticket consume, falling back to in-memory: %s",
                exc,
            )
    return _consume_ws_ticket_local(ticket)


async def _issue_portal_ws_ticket(client_id: str) -> str:
    """Emit a one-time portal WS ticket (see _issue_ws_ticket for rationale)."""
    ticket = secrets.token_urlsafe(24)
    if _REDIS_URL:
        try:
            r = await _get_redis()
            await r.setex(f"{_PORTAL_WS_TICKET_KEY_PREFIX}{ticket}", _WS_TICKET_TTL, client_id)
            return ticket
        except Exception as exc:
            log.debug("_issue_portal_ws_ticket: excepcion ignorada", exc_info=True)
            _warn_redis_fallback_once(
                "portal_issue",
                "Redis unreachable, falling back to in-memory portal WS ticket store: %s",
                exc,
            )
    return _issue_portal_ws_ticket_local(client_id)


async def _consume_portal_ws_ticket(ticket: str) -> Optional[str]:
    """Consume a one-time portal WS ticket, returning client_id or None."""
    if not _is_safe_ticket(ticket):
        log.warning("Portal WS ticket rechazado por formato inválido")
        return None
    if _REDIS_URL:
        try:
            r = await _get_redis()
            key = f"{_PORTAL_WS_TICKET_KEY_PREFIX}{ticket}"
            consumed = await r.eval(
                _REDIS_ATOMIC_CONSUME_SCRIPT,
                1,
                key,
            )
            return consumed if consumed else None
        except Exception as exc:
            log.warning("Portal WS ticket Redis consume failed — falling back to in-memory: %s", exc)
            # Redis unavailable (e.g. local dev without Redis) — use in-memory store
            return _consume_portal_ws_ticket_local(ticket)
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
# Movido a `app/services/ws_manager.py` para romper la dependencia
# `services → endpoints`. Re-exportamos aquí para mantener retrocompatibilidad
# con cualquier importador externo que hiciera `from app.api.v1.endpoints.ws import manager`.
from app.services.ws_manager import ConnectionManager, manager  # noqa: F401


async def _validate_jwt(token: str, db) -> str:
    """Valida el token JWT y verifica que el usuario exista y esté activo en BD."""
    from app.core.security import decode_token
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    user = await run_db(_ws_svc.get_active_user_by_id, db, user_id)
    if not user:
        return None
    org = payload.get("org")
    return f"{user_id}{_SEPARADOR_DE_ORG}{org}" if org else user_id


def usuario_en_su_organizacion_activa(db, user, org: Optional[str]):
    """Fija en memoria la empresa activa del ticket si sigue perteneciendo.

    Segunda auditoría 2026-11 (#7). Sin pertenencia vigente vuelve a la de
    ficha (igual que una petición HTTP con un `org` retirado).
    """
    from app.services.entrada_service import fijar_organizacion_activa

    if user is not None and org:
        fijar_organizacion_activa(db, user, org)
    return user


async def _en_sesion(cerrojo: Optional[asyncio.Lock], fn, *args):
    """Ejecuta `fn(*args)` (consultas sincronas) en el pool de hilos.

    Auditoria 2026-11: el sondeo y los mensajes del cliente consultaban la BD
    dentro del bucle de eventos, cada 10-15 s por conexion abierta. En el pool
    de hilos, el sondeo y `mark_read` podrian usar la MISMA sesion a la vez desde
    dos hilos (una `Session` no es thread-safe): el cerrojo de la conexion los
    pone en fila.
    """
    if cerrojo is None:
        return await run_db(fn, *args)
    async with cerrojo:
        return await run_db(fn, *args)


async def _poll_and_send(websocket: WebSocket, user_id: str, db, cerrojo: Optional[asyncio.Lock] = None):
    """
    Sondea la BD cada 15s y envía notificaciones no leídas al cliente.
    En producción se reemplazaría por eventos de BD (pg_notify / Redis).
    """
    last_count = None
    while True:
        try:
            count, notifs, team_poll = await _en_sesion(
                cerrojo, _sondeo_de_usuario, db, user_id)
            governed_unread = team_poll["governed_unread"]
            pending_reviews = team_poll["pending_reviews"]
            assigned_overdue = team_poll["assigned_overdue"]

            snapshot = (count, governed_unread, pending_reviews, assigned_overdue)
            if snapshot != last_count:
                last_count = snapshot
                await websocket.send_text(json.dumps({
                    "type":  "notifications",
                    "count": count,
                    "governed_unread": governed_unread,
                    "pending_conversation_reviews": pending_reviews,
                    "conversation_sla_overdue": assigned_overdue,
                    "items": [{
                        "id":           n.id,
                        "title":        n.title,
                        "message":      n.body,
                        "type":         n.type,
                        "entity_type":  n.resource,
                        "entity_id":    n.resource_id,
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


def _sondeo_de_usuario(db, user_id: str):
    """Las dos consultas del sondeo, juntas: un solo salto al pool de hilos.

    `items` se serializa en el bucle de eventos despues; los atributos de las
    notificaciones ya vienen cargados de la consulta.
    """
    count, notifs = _ws_svc.get_unread_notifications(db, user_id)
    return count, notifs, _ws_svc.get_team_poll_data(db, user_id)


async def _poll_and_send_client(websocket: WebSocket, client_id: str, db, cerrojo: Optional[asyncio.Lock] = None):
    """Poll client-facing updates (messages + tickets) and push via WS."""
    last_snapshot = None
    while True:
        try:
            poll_data = await _en_sesion(cerrojo, _ws_svc.get_portal_poll_data, db, client_id)
            unread_messages = poll_data["unread_messages"]
            governed_unread = poll_data["governed_unread"]
            open_tickets = poll_data["open_tickets"]
            recent_public_comments = poll_data["recent_public_comments"]

            snapshot = (unread_messages, governed_unread, open_tickets, len(recent_public_comments))
            if snapshot != last_snapshot:
                last_snapshot = snapshot
                await websocket.send_text(json.dumps({
                    "type": "portal_notifications",
                    "unread_messages": unread_messages,
                    "governed_unread": governed_unread,
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
        # `get_current_user` ya dejó en `organization_id` la empresa ACTIVA
        # (claim `org`, validada): es la que viaja en el ticket.
        ticket = await _issue_ws_ticket(
            str(current_user.id), getattr(current_user, "organization_id", None))
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
        client = await run_db(verify_client_token, token, db)
        if not client or not getattr(client, "is_active", False):
            raise HTTPException(401, "Token de cliente inválido")
        # Auditoria 2026-08 (hallazgo 22): sesion creada a mano. Aqui solo se
        # emite un ticket y no hay mas consultas, pero el contexto se publica
        # igual: una sesion autenticada sin contexto es la forma exacta en la
        # que aparecio este defecto tres veces.
        publicar_contexto_de_tenant(db, client, es_cliente=True)
        try:
            ticket = await _issue_portal_ws_ticket(str(client.id))
        except Exception as exc:
            log.error("No se pudo emitir portal WS ticket (Redis error): %s", exc)
            raise HTTPException(503, "Servicio no disponible temporalmente")
        return {"ticket": ticket, "expires_in": _WS_TICKET_TTL}
    finally:
        db.close()


async def _identidad_de_la_conexion(
    websocket: WebSocket,
    db,
    *,
    ticket: Optional[str],
    token: Optional[str],
    portal: bool = False,
) -> Optional[str]:
    """El id autenticado de esta conexión, o `None` si ya se cerró.

    Auditoría 2026-08 (hallazgo 18). Este preámbulo estaba **copiado tres
    veces** —notificaciones de usuario, notificaciones de portal y colaboración
    en documentos— con seis ramas cada uno: ticket de un solo uso, o JWT en la
    URL si no estamos en producción, y un cierre distinto por cada forma de
    fallar. Entre las tres sumaban dieciocho ramas que hacen lo mismo.

    Devolver `None` **después de haber cerrado el socket** es lo que permite que
    cada WebSocket se quede en dos líneas: pedir la identidad y volver si no
    hay. La alternativa —devolver un motivo y que cada uno cierre— repartiría
    otra vez las mismas ramas por los tres sitios.

    La política del token en la URL se conserva verbatim, y su razón merece
    quedar aquí: un JWT en el `query string` **queda registrado por cada proxy y
    en el historial del navegador**, y sigue siendo reutilizable hasta que
    caduca. En producción y en preproducción no se acepta; en local sí, para no
    obligar a montar el flujo del ticket sólo para desarrollar.
    """
    if ticket:
        consumir = _consume_portal_ws_ticket if portal else _consume_ws_ticket
        identidad = await consumir(ticket)
        if not identidad:
            await websocket.close(code=4001, reason="Ticket inválido o expirado")
            return None
        return identidad

    ruta_del_ticket = "/ws/portal-ticket" if portal else "/ws/ticket"

    if token:
        if settings.ENVIRONMENT in {"production", "staging"}:
            await websocket.close(
                code=4003,
                reason=(
                    "Token en URL no permitido en production. "
                    f"Usa ?ticket= (GET {ruta_del_ticket})."
                ),
            )
            return None
        if portal:
            cliente = await run_db(verify_client_token, token, db)
            identidad = str(cliente.id) if cliente else None
        else:
            identidad = await _validate_jwt(token, db)
        if not identidad:
            await websocket.close(code=4001, reason="Token inválido")
            return None
        return identidad

    await websocket.close(
        code=4001,
        reason=f"Se requiere ?ticket= (obtener via GET {ruta_del_ticket})",
    )
    return None


@router.websocket("/notifications")
async def ws_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    ticket: Optional[str] = Query(default=None),
):
    """
    WebSocket de notificaciones en tiempo real.
    Conectar: ws://host/api/v1/ws/notifications?ticket=<one-time-ticket>

    Obtener el ticket previo: GET /api/v1/ws/ticket (requiere cookie de sesión).
    El parámetro ?token=<JWT> está deshabilitado en production/staging — los JWT
    en URLs quedan registrados en logs de proxy y en el historial del navegador.
    """
    from app.db.session import SessionLocal

    user_id: Optional[str] = None
    with SessionLocal() as db:
        try:
            user_id, org_activa = separar_identidad(await _identidad_de_la_conexion(
                websocket, db, ticket=ticket, token=token))
            if not user_id:
                return

            # Auditoria 2026-08 (hallazgo 22). Esta sesion vive lo que dure la
            # conexion y sobre ella corren `_poll_and_send` —en bucle— y
            # `mark_notification_read`, que **leen y escriben** datos del
            # usuario. Sin contexto, `TenantSession` la trata como «no
            # inicializada» y no filtra nada.
            #
            # Hasta aqui solo se tiene el `user_id` que venia del ticket, asi
            # que hay que cargar al usuario. Es una consulta por conexion, no
            # por mensaje.
            usuario = await run_db(_ws_svc.get_active_user_by_id, db, user_id)
            if not usuario:
                await websocket.close(code=4001, reason="Usuario no encontrado")
                return
            await run_db(usuario_en_su_organizacion_activa, db, usuario, org_activa)
            publicar_contexto_de_tenant(db, usuario)

            await manager.connect(websocket, user_id)

            # Enviar estado inicial
            await websocket.send_text(json.dumps({
                "type":    "connected",
                "user_id": user_id,
                "ts":      datetime.now(timezone.utc).isoformat(),
            }))

            # Iniciar el loop de polling en background
            cerrojo = asyncio.Lock()
            poll_task = asyncio.create_task(_poll_and_send(websocket, user_id, db, cerrojo))

            try:
                while True:
                    # Escuchar mensajes del cliente (ping/pong, mark_read)
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                        if msg.get("type") == "ping":
                            await websocket.send_text(json.dumps({"type": "pong"}))
                        elif msg.get("type") == "mark_read" and msg.get("id"):
                            await _en_sesion(cerrojo, _ws_svc.mark_notification_read,
                                             db, msg["id"], user_id)
                    except (json.JSONDecodeError, KeyError, TypeError) as e:
                        logging.getLogger(__name__).warning(f"WS notifications malformed message: {e}")
                    except Exception as e:
                        logging.getLogger(__name__).error(f"Unexpected error processing ws message: {e}")
            except (WebSocketDisconnect, RuntimeError):
                # Auditoria 2026-11: si el cliente cierra mientras el sondeo
                # escribe, Starlette da RuntimeError («not connected») y no
                # WebSocketDisconnect: salia como traza en el log.
                pass
            finally:
                poll_task.cancel()
        finally:
            manager.disconnect(websocket, user_id if user_id else 'unknown')


@router.websocket("/portal-notifications")
async def ws_portal_notifications(
    websocket: WebSocket,
    token: Optional[str] = Query(default=None),
    ticket: Optional[str] = Query(default=None),
):
    """WebSocket notifications for client portal users."""
    from app.db.session import SessionLocal

    client_id = None
    with SessionLocal() as db:
        try:
            client_id = await _identidad_de_la_conexion(
                websocket, db, ticket=ticket, token=token, portal=True)
            if not client_id:
                return

            # Ver la nota del WebSocket de notificaciones de arriba:
            # `_poll_and_send_client` corre en bucle sobre esta sesion.
            from app.services.client_portal_service import (
                get_active_client_by_id as _cliente_activo,
            )

            cliente = await run_db(_cliente_activo, db, client_id)
            if not cliente:
                await websocket.close(code=4001, reason="Cliente no encontrado")
                return
            publicar_contexto_de_tenant(db, cliente, es_cliente=True)

            manager_key = f"client:{client_id}"
            await manager.connect(websocket, manager_key)
            await websocket.send_text(json.dumps({
                "type": "connected",
                "client_id": client_id,
                "ts": datetime.now(timezone.utc).isoformat(),
            }))
            poll_task = asyncio.create_task(
                _poll_and_send_client(websocket, client_id, db, asyncio.Lock()))

            try:
                while True:
                    data = await websocket.receive_text()
                    try:
                        msg = json.loads(data)
                        if msg.get("type") == "ping":
                            await websocket.send_text(json.dumps({"type": "pong"}))
                    except Exception:
                        log.debug("Portal WS received non-JSON or malformed message", exc_info=True)
            except WebSocketDisconnect:
                poll_task.cancel()
        finally:
            if client_id:
                manager.disconnect(websocket, f"client:{client_id}")


@router.get("/notifications/stats", summary="Estadísticas de conexiones WebSocket activas")
async def ws_stats(current_user=Depends(get_current_user)):
    """Requiere sesión autenticada (header/cookie), no token en query string."""
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
        await pubsub.psubscribe("contecflow:doc:*")
        log.info("WS: Doc collab Redis pub/sub subscriber started")
        async for raw in pubsub.listen():
            if raw["type"] != "pmessage":
                continue
            channel: str = raw.get("channel", "")
            doc_id = channel.removeprefix("contecflow:doc:")
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
            log.debug("Doc collab broadcast send_text failed for doc=%s", doc_id, exc_info=True)


async def _bucle_de_documento(
    websocket: WebSocket, doc_id: str, user_id: str
) -> None:
    """Recibe mensajes de un editor y los reparte al resto de la sala.

    Auditoría 2026-08 (hallazgo 18). Esto estaba dentro de `ws_doc_collab`, que
    con ello llegaba a complejidad 17 —la más alta del backend—. Y no es que
    fuese larga: es que mezclaba **dos cosas distintas**, el ciclo de vida de la
    conexión (autenticar, permisos sobre el documento, entrar y salir de la
    sala) y el protocolo que se habla por dentro. Sacar el protocolo deja la
    otra mitad legible sin tocar ni una rama.

    El tope de 2 MB por mensaje se conserva y su porqué también: un `update` de
    Yjs de un documento normal son kilobytes, así que un mensaje de megabytes es
    un cliente roto o un intento de agotar la memoria del proceso — y como
    `receive_text()` ya materializó la cadena, el único remedio honesto es
    cerrar la conexión, no ignorar el mensaje.

    El `except Exception` de dentro es a propósito y se queda: un mensaje
    malformado de **un** editor no puede tirar la sesión de los demás.
    """
    MAX_MSG_SIZE = 2 * 1024 * 1024  # 2 MB
    try:
        while True:
            raw = await websocket.receive_text()
            if len(raw) > MAX_MSG_SIZE:
                await websocket.close(code=4009, reason="Mensaje demasiado grande")
                break
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
                log.debug("Doc collab WS received malformed message for doc=%s user=%s", doc_id, user_id, exc_info=True)
    # intentional: cleanup path, logging would cascade
    except WebSocketDisconnect:
        pass


@router.websocket("/doc/{doc_id}")
async def ws_doc_collab(
    websocket: WebSocket,
    doc_id: str,
    ticket: Optional[str] = Query(default=None),
    token: Optional[str] = Query(default=None),
):
    """
    Wiki document collaboration WebSocket.
    Connect: ws://.../api/v1/ws/doc/<doc_id>?ticket=<one-time-ticket>

    Obtain the ticket first: GET /api/v1/ws/ticket (requires session cookie).
    ?token=<JWT> is disabled in production/staging — see /ws/notifications.

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
    from app.services.documents_service import get_document_or_404, check_document_access

    user_id: Optional[str] = None
    with SessionLocal() as db:
        try:
            user_id, org_activa = separar_identidad(await _identidad_de_la_conexion(
                websocket, db, ticket=ticket, token=token))
            if not user_id:
                return

            # Obtener usuario y documento
            user = await run_db(_ws_svc.get_active_user_by_id, db, user_id)
            await run_db(usuario_en_su_organizacion_activa, db, user, org_activa)
            # Auditoria 2026-08 (hallazgo 22): el contexto va **entre** las dos
            # llamadas, y no es casualidad. `get_active_user_by_id` busca por id
            # sin saber todavia de que organizacion es, asi que tiene que correr
            # sin filtrar; `get_document_or_404` si tiene que estar acotada.
            if user:
                publicar_contexto_de_tenant(db, user)
            doc = await run_db(get_document_or_404, db, doc_id, user)
            try:
                check_document_access(doc, user, required_level=None)  # viewer mínimo
            except Exception:
                log.info("Doc WS access denied for user=%s doc=%s", user_id, doc_id, exc_info=True)
                await websocket.close(code=4003, reason="Sin permiso para acceder al documento")
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

            await _bucle_de_documento(websocket, doc_id, user_id)
        finally:
            async with _doc_rooms_lock:
                room = _doc_rooms.get(doc_id, [])
                if websocket in room:
                    room.remove(websocket)
                if not room:
                    _doc_rooms.pop(doc_id, None)

            peer_count = len(_doc_rooms.get(doc_id, []))
            await _broadcast_doc(doc_id, {"type": "left", "user_id": user_id or "?", "peers": peer_count})


async def _broadcast_doc(doc_id: str, message: dict, exclude: WebSocket = None) -> None:
    """Send a message to all clients editing a document.

    With Redis: publishes to the shared channel so all workers deliver it.
    Without Redis: local delivery only (dev / single-worker).
    Note: Redis path cannot honour `exclude` across workers; clients should
    de-duplicate their own updates by checking the `from` field.
    """
    if _REDIS_URL:
        try:
            r = await _get_redis()
            await r.publish(f"contecflow:doc:{doc_id}", json.dumps(message))
            return
        except Exception as exc:
            log.warning("Doc Redis publish failed, falling back to local: %s", exc)
    await _broadcast_doc_local(doc_id, message, exclude=exclude)

