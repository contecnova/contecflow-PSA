"""
Event bus — abstraction over realtime distribution.

In dev: in-memory async queues per-subscriber.
In prod (future): swap implementation to Redis pub/sub or NATS JetStream
without callers caring.

Usage:
  await bus.publish('conversation:123', {'type': 'message.created', ...})
  async for event in bus.subscribe(['conversation:123', 'user:456']):
      ...
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from typing import Any, AsyncIterator, Iterable

logger = logging.getLogger(__name__)


class EventBus:
    """In-memory async pub/sub. Replace with RedisBus/NatsBus for prod."""

    def __init__(self) -> None:
        self._subs: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        # Snapshot to allow concurrent unsubscribes.
        async with self._lock:
            queues = list(self._subs.get(channel, ()))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("collaboration bus queue full on channel=%s", channel)

    async def subscribe(self, channels: Iterable[str], queue_size: int = 256) -> "Subscription":
        q: asyncio.Queue = asyncio.Queue(maxsize=queue_size)
        async with self._lock:
            for ch in channels:
                self._subs[ch].add(q)
        return Subscription(self, q, list(channels))

    async def _unsubscribe(self, queue: asyncio.Queue, channels: Iterable[str]) -> None:
        async with self._lock:
            for ch in channels:
                self._subs[ch].discard(queue)
                if not self._subs[ch]:
                    self._subs.pop(ch, None)


class Subscription:
    """Async iterator yielding events. Use as `async with` to auto-cleanup."""

    def __init__(self, bus: EventBus, queue: asyncio.Queue, channels: list[str]) -> None:
        self._bus = bus
        self._q = queue
        self._channels = channels
        self._closed = False

    async def __aenter__(self) -> "Subscription":
        return self

    async def __aexit__(self, *_exc) -> None:
        await self.close()

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        await self._bus._unsubscribe(self._q, self._channels)

    def __aiter__(self) -> AsyncIterator[dict[str, Any]]:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self._closed:
            raise StopAsyncIteration
        return await self._q.get()


# ── Channel name helpers (stable namespaces) ─────────────────────────────────
def conv_channel(conversation_id: str) -> str:
    return f"conv:{conversation_id}"


def user_channel(user_id: str) -> str:
    return f"user:{user_id}"


def client_user_channel(client_user_id: str) -> str:
    return f"client_user:{client_user_id}"


def workspace_channel(workspace_id: str) -> str:
    return f"workspace:{workspace_id}"


def org_channel(organization_id: str) -> str:
    return f"org:{organization_id}"


# ── Backend selection ────────────────────────────────────────────────────────
def _build_bus() -> EventBus:
    # env-driven backend selector: collaboration event bus implementation
    # (memory/redis/nats) is a deployment topology choice, not application config.
    backend = os.environ.get("COLLAB_BUS_BACKEND", "memory").lower()
    if backend == "memory":
        return EventBus()
    if backend == "redis":
        try:
            from app.services.collaboration._bus_redis import build_redis_bus
            return build_redis_bus()
        except Exception as exc:
            logger.warning("Redis bus unavailable, fallback memory: %s", exc)
            return EventBus()
    if backend == "nats":
        try:
            from app.services.collaboration._bus_nats import build_nats_bus
            return build_nats_bus()
        except Exception as exc:
            logger.warning("NATS bus unavailable, fallback memory: %s", exc)
            return EventBus()
    return EventBus()


bus: EventBus = _build_bus()
