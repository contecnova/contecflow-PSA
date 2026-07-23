"""WebSocket gateway for collaboration realtime events.

Subscribes a connected user to:
  - org:<org_id>             (org-wide broadcasts)
  - workspace:<ws_id>        (workspace updates)
  - user:<user_id>           (personal notifications)
  - conv:<conversation_id>   (joined dynamically per the conversations the user can see)

Auth: same WS ticket scheme used by the rest of the app.

Rate limit: token bucket por usuario sobre eventos *enviados desde* el cliente
(typing, presence, ping). Default 60 eventos / 30 s. Se cierra el socket si
se excede de forma sostenida.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services.ws_service import get_active_user_by_id
from app.api.v1.endpoints.ws import _consume_ws_ticket
from app.services.collaboration._bus import (
    bus, conv_channel, org_channel, user_channel, workspace_channel,
)
from app.services.collaboration.workspaces import (
    get_or_create_workspace, list_conversations_for_user,
)

router = APIRouter(tags=["Collaboration"])
log = logging.getLogger(__name__)


# ── Per-user token bucket ────────────────────────────────────────────────────
class _Bucket:
    __slots__ = ("tokens", "max", "last", "rate")

    def __init__(self, capacity: int = 60, refill_per_second: float = 2.0):
        self.tokens = float(capacity)
        self.max = float(capacity)
        self.last = time.monotonic()
        self.rate = refill_per_second

    def take(self, n: float = 1.0) -> bool:
        now = time.monotonic()
        self.tokens = min(self.max, self.tokens + (now - self.last) * self.rate)
        self.last = now
        if self.tokens >= n:
            self.tokens -= n
            return True
        return False


_buckets: dict[str, _Bucket] = {}


def _bucket_for(user_id: str) -> _Bucket:
    b = _buckets.get(user_id)
    if not b:
        b = _Bucket()
        _buckets[user_id] = b
    return b


@router.websocket("/ws")
async def collaboration_ws(
    websocket: WebSocket,
    ticket: Optional[str] = Query(default=None),
):
    if not ticket:
        await websocket.close(code=4401)
        return
    user_id = await _consume_ws_ticket(ticket)
    if not user_id:
        await websocket.close(code=4401)
        return

    db: Session = SessionLocal()
    try:
        user = get_active_user_by_id(db, user_id)
        if not user:
            await websocket.close(code=4403)
            return
        # Si el usuario no pertenece a una organización (p.ej. superadmin global)
        # no puede operar en el módulo de chat: cerramos el handshake limpiamente
        # con 4403 en lugar de propagar HTTPException → 500.
        if not getattr(user, "organization_id", None):
            log.info("collab ws: user=%s sin organización — chat no disponible", user_id)
            await websocket.accept()
            await websocket.close(code=4403)
            return
        try:
            ws_obj = get_or_create_workspace(db, user)
        except Exception as exc:
            log.warning("collab ws: get_or_create_workspace falló para user=%s: %s", user_id, exc)
            await websocket.accept()
            await websocket.close(code=4403)
            return
        await websocket.accept()

        # Subscribe to user's channels
        def _channels_for() -> list[str]:
            conv_list = list_conversations_for_user(db, user)
            return [
                org_channel(user.organization_id),
                workspace_channel(ws_obj.id),
                user_channel(user.id),
            ] + [conv_channel(c["id"]) for c in conv_list]

        channels = _channels_for()
        sub = await bus.subscribe(channels)

        async def producer():
            async for event in sub:
                try:
                    await websocket.send_text(json.dumps(event, default=str))
                except Exception:
                    return

        async def _ensure_user_still_active() -> bool:
            revalidated_user = get_active_user_by_id(db, user_id)
            if not revalidated_user or not revalidated_user.is_active:
                log.warning("collab ws closing user=%s: access revoked", user_id)
                try:
                    await websocket.close(code=4403)
                except Exception:
                    pass
                return False
            return True

        async def resync_subscriptions():
            """Re-suscribe a las conversations actuales del usuario.
            Útil tras crear/unirse a un nuevo grupo/canal mientras está conectado."""
            nonlocal sub, channels
            new_channels = _channels_for()
            if set(new_channels) == set(channels):
                return
            await sub.close()
            channels = new_channels
            sub = await bus.subscribe(channels)
            asyncio.create_task(producer())

        async def consumer():
            bucket = _bucket_for(user.id)
            sustained_breach = 0
            revalidate_counter = 0
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue

                # Revalidación cada 10 mensajes del cliente (más watchdog cada 30s)
                revalidate_counter += 1
                if revalidate_counter >= 10:
                    if not await _ensure_user_still_active():
                        return
                    revalidate_counter = 0

                t = payload.get("type")
                # Rate limit (excluye pong de servidor; ping cuenta como 1 token)
                if not bucket.take(1.0):
                    sustained_breach += 1
                    try:
                        await websocket.send_text(json.dumps({"type": "rate_limited"}))
                    except Exception:
                        return
                    if sustained_breach > 5:
                        log.warning("collab ws closing user=%s for sustained rate-limit breaches", user.id)
                        try: await websocket.close(code=4429)
                        except Exception: pass
                        return
                    await asyncio.sleep(0.5)
                    continue
                else:
                    sustained_breach = 0
                # Client-side messages: ping, typing, presence
                if t == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif t == "typing":
                    cid = payload.get("conversation_id")
                    if cid:
                        await bus.publish(conv_channel(cid), {
                            "type": "typing", "conversation_id": cid,
                            "payload": {"user_id": user.id, "active": bool(payload.get("active", True))},
                        })
                elif t == "presence":
                    status = payload.get("status", "online")
                    await bus.publish(org_channel(user.organization_id), {
                        "type": "presence.updated",
                        "payload": {"user_id": user.id, "status": status},
                    })
                elif t == "resync":
                    # Cliente acaba de crear/unirse a una conversación nueva
                    await resync_subscriptions()

        async def revocation_watchdog():
            # Revalidación periódica incluso si el cliente está idle.
            while True:
                await asyncio.sleep(30)
                if not await _ensure_user_still_active():
                    return

        # Lanzamos las tres tasks y, en cuanto cualquiera termine (cliente
        # desconecta / revocación / error), cancelamos las otras para que el
        # producer no quede vivo consumiendo del bus tras un disconnect del
        # cliente (resource leak).
        tasks = [
            asyncio.create_task(producer()),
            asyncio.create_task(consumer()),
            asyncio.create_task(revocation_watchdog()),
        ]
        try:
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            # Drenar excepciones para que no se logueen como "Task exception was never retrieved"
            for t in done:
                exc = t.exception()
                if exc:
                    log.debug("collab ws task ended: %s", exc)
            for t in pending:
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        finally:
            try:
                await sub.close()
            except Exception:
                pass
    finally:
        db.close()
