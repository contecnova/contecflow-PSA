"""Scheduler de mensajes programados.

El campo CollaborationMessage.scheduled_for marca un mensaje como "programado".
Estos mensajes se persisten al crearse pero NO se notifican ni publican vía bus
hasta que llega su hora.

Este scheduler:
  - Se arranca con la app (lifespan).
  - Cada N segundos busca mensajes con scheduled_for <= now y status=visible
    cuyo notification fan-out aún no se ejecutó (lo trackeamos con un flag en
    metadata_json["_scheduled_delivered"]).
  - Para cada uno: dispara fan-out de notificaciones, publica al bus realtime,
    indexa en search.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS = 30


async def _tick():
    from app.db.session import SessionLocal
    from app.models.collaboration import (
        CollaborationConversation, CollaborationMention,
        CollaborationMessage, CollaborationNotification,
    )
    from app.services.collaboration import bus
    from app.services.collaboration._bus import (
        client_user_channel, conv_channel, user_channel,
    )
    from app.services.collaboration._search import search_engine
    from app.services.collaboration.messages import _notify_recipients, _serialize_message

    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        # SQLite guarda datetime sin tz; Postgres con tz. Usamos un margen
        # generoso (now + 0) y filtramos en Python si hace falta para evitar
        # tropezar con comparaciones naive vs aware.
        rows = (
            db.query(CollaborationMessage)
            .filter(
                CollaborationMessage.scheduled_for.isnot(None),
                CollaborationMessage.status == "visible",
            )
            .all()
        )
        rows = [r for r in rows if r.scheduled_for and (r.scheduled_for.replace(tzinfo=timezone.utc) if r.scheduled_for.tzinfo is None else r.scheduled_for) <= now]
        for msg in rows:
            meta = dict(msg.metadata_json or {})
            if meta.get("_scheduled_delivered"):
                continue
            conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == msg.conversation_id).first()
            if not conv:
                meta["_scheduled_delivered"] = True
                msg.metadata_json = meta
                db.commit()
                continue
            mentions = db.query(CollaborationMention).filter(CollaborationMention.message_id == msg.id).all()
            _notify_recipients(db, organization_id=msg.organization_id, conv=conv, message=msg, mentions=mentions)
            meta["_scheduled_delivered"] = True
            msg.metadata_json = meta
            conv.last_activity_at = now
            conv.last_message_id = msg.id
            db.commit()
            search_engine.index(db, msg.id)

            # Realtime publish
            event = {
                "type": "message.created",
                "conversation_id": conv.id,
                "message_id": msg.id,
                "payload": _serialize_message(db, msg),
            }
            await bus.publish(conv_channel(conv.id), event)
            for n in db.query(CollaborationNotification).filter(CollaborationNotification.message_id == msg.id).all():
                if n.user_id:
                    await bus.publish(user_channel(n.user_id), {"type": "notification.new", "payload": {"id": n.id}})
                if n.client_user_id:
                    await bus.publish(client_user_channel(n.client_user_id), {"type": "notification.new", "payload": {"id": n.id}})
    except Exception as exc:
        logger.warning("scheduled-msg tick failed: %s", exc)
    finally:
        db.close()


_loop_task: asyncio.Task | None = None


_DAILY_TASKS_INTERVAL = 24 * 60 * 60  # 24h
_last_daily_run: float = 0.0


def _maybe_run_daily_tasks() -> None:
    """Tareas que se ejecutan a baja frecuencia (1/día):
        - Purga de signed-URL tokens expirados (defensivo).
        - Limpieza de push subscriptions inactivas viejas.
    """
    global _last_daily_run
    import time
    now = time.time()
    if now - _last_daily_run < _DAILY_TASKS_INTERVAL:
        return
    _last_daily_run = now
    try:
        from app.services.collaboration._storage import _purge_expired_signed_tokens
        _purge_expired_signed_tokens()
    except Exception as exc:
        logger.warning("signed-token purge failed: %s", exc)
    from app.db.session import SessionLocal as _SessionLocal
    db = _SessionLocal()
    try:
        from app.services.collaboration._push import purge_stale_subscriptions
        n = purge_stale_subscriptions(db, days=30)
        if n:
            logger.info("collaboration: purged %s stale push subscriptions", n)
    except Exception as exc:
        logger.warning("push-sub purge failed: %s", exc)
    finally:
        db.close()


def _tick_workflow_engine() -> None:
    """Despierta runs en estado `waiting` cuyos timers (`wake_at`) hayan expirado."""
    try:
        from app.db.session import SessionLocal as _SessionLocal
        from app.services.service_desk import workflow_engine as _engine
        db = _SessionLocal()
        try:
            n = _engine.tick_waiting(db)
            if n:
                logger.info("workflow engine: %s run(s) reanudados desde wait", n)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("workflow engine tick failed: %s", exc)


async def _run_forever(interval: int):
    while True:
        try:
            await _tick()
            _tick_workflow_engine()
            _maybe_run_daily_tasks()
        except Exception as exc:
            logger.warning("scheduler tick error: %s", exc)
        await asyncio.sleep(interval)


def start(interval: int = DEFAULT_INTERVAL_SECONDS):
    global _loop_task
    if _loop_task and not _loop_task.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _loop_task = loop.create_task(_run_forever(interval))
        logger.info("collaboration scheduled-msg loop started (interval=%ss)", interval)
    # intentional: best-effort fallback, log noise outweighs diagnostic value
    except RuntimeError:
        # No loop yet (eg test sync). Will be started on first FastAPI startup.
        pass


def stop():
    global _loop_task
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
    _loop_task = None
