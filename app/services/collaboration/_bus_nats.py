"""NATS-backed EventBus.

Requiere: pip install nats-py

Variables:
  NATS_URL=nats://localhost:4222
  NATS_TLS=0|1
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


class NatsBus(EventBus):
    def __init__(self, url: str | None = None) -> None:
        super().__init__()
        self._url = url or os.environ.get("NATS_URL", "nats://localhost:4222")
        self._nc = None
        self._subs_by_channel: dict[str, Any] = {}

    async def _ensure(self):
        if self._nc:
            return
        try:
            import nats  # type: ignore
        except Exception as exc:
            raise RuntimeError("nats-py no instalado") from exc
        self._nc = await nats.connect(servers=[self._url], allow_reconnect=True)

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        await self._ensure()
        await self._nc.publish(channel, json.dumps(event, default=str).encode())
        await super().publish(channel, event)

    async def subscribe(self, channels: Iterable[str], queue_size: int = 256) -> Subscription:
        await self._ensure()
        chs = list(channels)
        sub = await super().subscribe(chs, queue_size=queue_size)
        for ch in chs:
            if ch not in self._subs_by_channel:
                async def cb(msg, _channel=ch):
                    try:
                        event = json.loads(msg.data)
                    except Exception:
                        return
                    queues = list(self._subs.get(_channel, ()))
                    for q in queues:
                        try:
                            q.put_nowait(event)
                        except asyncio.QueueFull:
                            pass
                self._subs_by_channel[ch] = await self._nc.subscribe(ch, cb=cb)
        return sub


def build_nats_bus() -> EventBus:
    return NatsBus()
