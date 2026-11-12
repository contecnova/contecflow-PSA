"""Redis-backed implementation of EventBus.

Cross-process pub/sub via redis.asyncio.PubSub. Cada worker FastAPI
crea su propio cliente; al publicar va a Redis y todos los suscriptores
(de cualquier worker) reciben el evento.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from collections import defaultdict
from typing import Any, Iterable

from app.services.collaboration._bus import EventBus, Subscription

logger = logging.getLogger(__name__)


class RedisBus(EventBus):
    def __init__(self, url: str | None = None) -> None:
        super().__init__()
        try:
            import redis.asyncio as aioredis  # noqa: F401
            self._url = url or os.environ.get("REDIS_URL", "redis://localhost:6379/0")
            self._client = None  # lazy
            self._listener_task: asyncio.Task | None = None
            self._pubsub = None
            self._channel_index: dict[str, set[asyncio.Queue]] = defaultdict(set)
        except Exception as exc:
            logger.error("redis.asyncio unavailable: %s", exc)
            raise

    async def _ensure(self):
        if self._client:
            return
        import redis.asyncio as aioredis
        self._client = aioredis.from_url(self._url, decode_responses=True)
        self._pubsub = self._client.pubsub()
        # Listener pump
        self._listener_task = asyncio.create_task(self._listen())

    async def _listen(self):
        try:
            while True:
                message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if not message:
                    await asyncio.sleep(0.05)
                    continue
                channel = message["channel"]
                try:
                    event = json.loads(message["data"])
                except Exception:  # noqa: S112
                    logger.debug("_listen: excepcion ignorada", exc_info=True)
                    continue
                queues = list(self._channel_index.get(channel, ()))
                for q in queues:
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        pass
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.warning("redis bus listener died: %s", exc)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        await self._ensure()
        await self._client.publish(channel, json.dumps(event, default=str))
        # Also dispatch locally so single-worker dev still works without round-trip
        await super().publish(channel, event)

    async def subscribe(self, channels: Iterable[str], queue_size: int = 256) -> Subscription:
        await self._ensure()
        chs = list(channels)
        # Local fan-out so the parent's logic still works
        sub = await super().subscribe(chs, queue_size=queue_size)
        # Mirror those queues into our redis listener index so cross-process events arrive too
        # (super already added the queue to self._subs via parent class code)
        for ch in chs:
            self._channel_index[ch].update(self._subs.get(ch, set()))
            await self._pubsub.subscribe(ch)
        return sub

    async def _unsubscribe(self, queue: asyncio.Queue, channels: Iterable[str]) -> None:
        await super()._unsubscribe(queue, channels)
        try:
            for ch in channels:
                if not self._subs.get(ch):
                    await self._pubsub.unsubscribe(ch)
                    self._channel_index.pop(ch, None)
        except Exception:
            logger.debug("_unsubscribe: fallo best-effort ignorado", exc_info=True)


def build_redis_bus() -> EventBus:
    return RedisBus()
