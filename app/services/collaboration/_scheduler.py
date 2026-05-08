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
        rows = (
            db.query(CollaborationMessage)
            .filter(
                CollaborationMessage.scheduled_for.isnot(None),
                CollaborationMessage.scheduled_for <= now,
                CollaborationMessage.status == "visible",
            )
            .all()
        )
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


async def _run_forever(interval: int):
    while True:
        try:
            await _tick()
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
    except RuntimeError:
        # No loop yet (eg test sync). Will be started on first FastAPI startup.
        pass


def stop():
    global _loop_task
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
    _loop_task = None
