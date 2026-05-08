"""
Background task queue abstraction.

Hoy: usa FastAPI BackgroundTasks o asyncio.create_task.
Mañana: NATS JetStream / Celery — basta con cambiar el backend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import traceback
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


class TaskQueue:
    """In-process async queue. Workers run as background tasks."""

    def __init__(self) -> None:
        self._q: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self._workers_started = False

    def _ensure_workers(self) -> None:
        if self._workers_started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return  # No loop yet — workers will start lazily on first publish from async context
        self._workers_started = True
        n = int(os.environ.get("COLLAB_QUEUE_WORKERS", "4"))
        for _ in range(n):
            loop.create_task(self._worker())

    async def _worker(self) -> None:
        while True:
            fn, args, kwargs = await self._q.get()
            try:
                if asyncio.iscoroutinefunction(fn):
                    await fn(*args, **kwargs)
                else:
                    fn(*args, **kwargs)
            except Exception:
                logger.error("collab queue task failed:\n%s", traceback.format_exc())
            finally:
                self._q.task_done()

    def enqueue(self, fn: Callable[..., Any] | Callable[..., Awaitable[Any]], *args, **kwargs) -> None:
        self._ensure_workers()
        try:
            self._q.put_nowait((fn, args, kwargs))
        except asyncio.QueueFull:
            logger.error("collab queue full; dropping task %s", getattr(fn, "__name__", "?"))

    async def join(self) -> None:
        await self._q.join()


task_queue = TaskQueue()
