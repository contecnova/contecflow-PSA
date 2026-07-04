"""
async_db.py — helper para usar el ORM síncrono dentro de endpoints `async def`.

Audit #C7 — endpoints async con `Depends(get_db)` ejecutaban queries síncronas
en el event loop, bloqueando todas las requests concurrentes. La regla canónica
(documentada en `app/db/session.py:get_db`) es:

  • Si el endpoint NO necesita features async (await request.body(), httpx,
    websocket, SSE asíncrono), declárese como `def` y FastAPI lo correrá en el
    threadpool. Las queries síncronas son seguras allí.

  • Si el endpoint DEBE ser `async def` (webhook que necesita el body raw para
    HMAC, integración con httpx, streaming SSE), entonces toda operación que
    toque la BD síncrona se envuelve con `await run_db(callable, *args)`. Esto
    delega la ejecución al threadpool de Starlette en lugar del event loop.

Uso típico::

    @router.post("/webhooks/fire/{slug}")
    async def fire_webhook(slug: str, request: Request, db: Session = Depends(get_db)):
        body = await request.body()         # legítimamente async
        trigger = await run_db(_svc.get_active_webhook_trigger_by_slug, db, slug)
        await run_db(_svc.log_webhook_fire, trigger, body, dict(request.headers), db)
        return {"ok": True}
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from starlette.concurrency import run_in_threadpool

T = TypeVar("T")


async def run_db(func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Run a synchronous DB-bound callable in the Starlette threadpool.

    Mirrors how FastAPI itself executes plain `def` endpoints. Use inside
    `async def` handlers so SQLAlchemy queries never run on the event loop.
    """
    return await run_in_threadpool(lambda: func(*args, **kwargs))


__all__ = ["run_db"]
