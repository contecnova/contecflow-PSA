"""Tareas asíncronas de "lanzar y olvidar", con referencia fuerte.

Auditoría 2026-08 (hallazgo P2-15). Había cinco puntos con
`asyncio.create_task(...)` / `loop.create_task(...)` cuyo resultado se
descartaba. Es un fallo real, no de estilo: **asyncio sólo guarda una referencia
débil a la tarea**, así que el recolector de basura puede destruirla antes de que
termine. El síntoma es de los peores de diagnosticar — mensajes de chat y
notificaciones que se pierden a veces, sin error y sin patrón reproducible.

La documentación de asyncio lo dice explícitamente en `create_task`: hay que
conservar una referencia a la tarea mientras vive.

Los cinco sitios afectados eran:
  - api/v1/endpoints/collaboration/ws.py  (productor de eventos del WebSocket)
  - services/client_portal_service.py     (notificación al portal de cliente)
  - services/collaboration/_queue.py      (los 4 workers de la cola)
  - services/collaboration/bots.py        (publicación en tiempo real)
  - services/collaboration/messages.py    (publicación en tiempo real)

Uso:
    from app.core.background import spawn
    spawn(publish_user_notification(user_id, notif), name="portal-notif")
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Coroutine, Optional, Set

logger = logging.getLogger("contecflow.background")

# Conjunto a nivel de módulo: es la referencia fuerte que impide que el GC se
# lleve la tarea a medias. Cada tarea se descarta al terminar, así que no crece.
_TASKS: Set[asyncio.Task] = set()


def spawn(
    coro: Coroutine[Any, Any, Any],
    *,
    name: Optional[str] = None,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> Optional[asyncio.Task]:
    """Lanza `coro` en segundo plano conservando la referencia.

    Devuelve la tarea, o None si no hay bucle de eventos en marcha (caso típico
    en tests sincrónicos): en ese escenario la corrutina se cierra de forma
    limpia para no dejar un "coroutine was never awaited".

    Las excepciones de la tarea se registran en lugar de desaparecer. Antes, una
    tarea lanzada y olvidada que fallara no dejaba rastro: su excepción quedaba
    en un objeto que nadie consultaba.
    """
    try:
        target_loop = loop or asyncio.get_running_loop()
    except RuntimeError:
        # Sin bucle en marcha (p. ej. una función sincrónica en tests).
        coro.close()
        return None

    task = target_loop.create_task(coro, name=name)
    _TASKS.add(task)

    def _done(t: asyncio.Task) -> None:
        _TASKS.discard(t)
        if t.cancelled():
            return
        exc = t.exception()
        if exc is not None:
            logger.warning(
                "tarea en segundo plano '%s' terminó con error: %s",
                t.get_name(), exc, exc_info=exc,
            )

    task.add_done_callback(_done)
    return task


def pending_count() -> int:
    """Número de tareas en vuelo. Para diagnóstico y para tests."""
    return len(_TASKS)


__all__ = ("pending_count", "spawn")
