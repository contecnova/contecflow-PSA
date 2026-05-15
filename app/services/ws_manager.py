"""WebSocket connection manager — extraído de `app/api/v1/endpoints/ws.py`
para romper la dependencia inversa `services → endpoints`.

Tanto el endpoint `ws.py` como otros servicios (`realtime_notifications.py`)
deben importar la instancia singleton `manager` desde aquí.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional

from app.core.config import settings

log = logging.getLogger(__name__)

_REDIS_URL: str = settings.REDIS_URL or ""

# ── Redis client (perezoso) ──────────────────────────────────────────────────
_redis_client = None
_redis_client_lock: Optional[asyncio.Lock] = None


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


# ── Connection Manager ───────────────────────────────────────────────────────
class ConnectionManager:
    """Manages local WebSocket connections for this worker process.

    When Redis is available, uses Pub/Sub to forward messages published by
    any worker to all connected clients regardless of which worker they hit.
    Without Redis, messages only reach clients on the same worker (dev mode).
    """

    def __init__(self) -> None:
        self.connections: Dict[str, List] = {}   # user_id → [WebSocket, ...]
        self._redis_sub_task: Optional[asyncio.Task] = None
        self._redis_sub_retry_after: float = 0.0

    async def connect(self, websocket, user_id: str) -> None:
        await websocket.accept()
        if user_id not in self.connections:
            self.connections[user_id] = []
        self.connections[user_id].append(websocket)
        log.info("WS: %s conectado (%s sesiones)", user_id, len(self.connections[user_id]))
        if _REDIS_URL and self._redis_sub_task is None and time.monotonic() >= self._redis_sub_retry_after:
            self._redis_sub_task = asyncio.create_task(self._redis_subscriber())

    def disconnect(self, websocket, user_id: str) -> None:
        if user_id in self.connections:
            self.connections[user_id] = [ws for ws in self.connections[user_id] if ws != websocket]
            if not self.connections[user_id]:
                del self.connections[user_id]
        log.info("WS: %s desconectado", user_id)

    async def send_to_user(self, user_id: str, message: dict) -> None:
        """Send a message to all active sessions of a user on this worker."""
        if user_id not in self.connections:
            return
        dead = []
        for ws in self.connections[user_id]:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                log.debug("WS send_text failed for user=%s; marking connection dead", user_id, exc_info=True)
                dead.append(ws)
        for ws in dead:
            self.connections[user_id].remove(ws)

    async def publish(self, user_id: str, message: dict) -> None:
        """Publish a message for a user.

        With Redis: publishes to the shared channel so ALL workers deliver it.
        Without Redis: delivers locally (dev / single-worker).
        """
        if _REDIS_URL:
            try:
                r = await _get_redis()
                channel = f"contecflow:ws:{user_id}"
                await r.publish(channel, json.dumps(message))
                return
            except Exception as exc:
                log.warning("Redis publish failed, falling back to local: %s", exc)
        await self.send_to_user(user_id, message)

    async def broadcast(self, message: dict) -> None:
        """Send to all locally connected users."""
        for user_id in list(self.connections.keys()):
            await self.send_to_user(user_id, message)

    async def _redis_subscriber(self) -> None:
        """Background task: subscribe to per-user channels and forward to local WS connections."""
        try:
            r = await _get_redis()
            pubsub = r.pubsub()
            await pubsub.psubscribe("contecflow:ws:*")
            log.info("WS: Redis Pub/Sub subscriber started (pattern=contecflow:ws:*)")
            async for raw in pubsub.listen():
                if raw["type"] != "pmessage":
                    continue
                channel: str = raw.get("channel", "")
                user_id = channel.removeprefix("contecflow:ws:")
                if not user_id or user_id not in self.connections:
                    continue
                try:
                    msg = json.loads(raw["data"])
                    await self.send_to_user(user_id, msg)
                except Exception as exc:
                    log.debug("WS Redis subscriber parse error: %s", exc)
        except Exception as exc:
            self._redis_sub_retry_after = time.monotonic() + 30.0
            log.warning("WS Redis subscriber crashed: %s. Reintentando en 30s", exc)
            self._redis_sub_task = None

    def connected_users(self) -> List[str]:
        return list(self.connections.keys())

    def total_connections(self) -> int:
        return sum(len(v) for v in self.connections.values())


# Singleton compartido a nivel de proceso
manager = ConnectionManager()
