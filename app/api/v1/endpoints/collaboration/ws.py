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
from app.services.ws_service import consume_ws_ticket_local, get_active_user_by_id
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
    user_id = consume_ws_ticket_local(ticket)
    if not user_id:
        # try redis-backed tickets (best-effort)
        try:
            from app.api.v1.endpoints.ws import _validate_jwt  # not used here, only to ensure env loaded
            del _validate_jwt
        except Exception:
            pass
        await websocket.close(code=4401)
        return

    db: Session = SessionLocal()
    try:
        user = get_active_user_by_id(db, user_id)
        if not user:
            await websocket.close(code=4403)
            return
        ws_obj = get_or_create_workspace(db, user)
        await websocket.accept()

        # Subscribe to user's channels
        conv_list = list_conversations_for_user(db, user)
        channels = [
            org_channel(user.organization_id),
            workspace_channel(ws_obj.id),
            user_channel(user.id),
        ] + [conv_channel(c["id"]) for c in conv_list]

        sub = await bus.subscribe(channels)

        async def producer():
            async for event in sub:
                try:
                    await websocket.send_text(json.dumps(event, default=str))
                except Exception:
                    return

        async def consumer():
            bucket = _bucket_for(user.id)
            sustained_breach = 0
            while True:
                try:
                    raw = await websocket.receive_text()
                except WebSocketDisconnect:
                    return
                try:
                    payload = json.loads(raw)
                except Exception:
                    continue
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

        try:
            await asyncio.gather(producer(), consumer())
        except Exception as exc:
            log.warning("collab ws closed: %s", exc)
        finally:
            await sub.close()
    finally:
        db.close()
