"""
webhooks.py — Outbound webhook delivery service.

Usage:
    from app.services.webhooks import fire_webhook
    fire_webhook(db, "task.status_changed", {"task_id": t.id, "status": "done"}, project_id=t.project_id)

Delivery is always asynchronous via Celery task enqueue (deliver_webhook_task).
No synchronous network I/O is performed in the request path.
"""
import json
import hmac
import hashlib
import logging
import time
from typing import Optional

from sqlalchemy.orm import Session

from app.models.enterprise import Webhook

logger = logging.getLogger(__name__)


def _sign_payload(secret: str, payload: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def fire_webhook(
    db: Session,
    event: str,
    payload: dict,
    project_id: Optional[str] = None,
) -> int:
    """Find matching active webhooks and dispatch the event payload.

    Each matching delivery is enqueued as an async Celery task so the
    calling request is never blocked by slow or unresponsive webhook endpoints.
    If the broker is unavailable, the enqueue is skipped and logged.

    Returns the number of webhook tasks successfully enqueued.
    """
    hooks = db.query(Webhook).filter(Webhook.is_active == True).all()
    enqueued_count = 0

    for hook in hooks:
        if hook.project_id and hook.project_id != project_id:
            continue

        try:
            subscribed_events = json.loads(hook.events)
        except Exception as exc:
            logger.warning("Failed to parse webhook events for hook %s: %s", hook.id, exc)
            continue

        if event not in subscribed_events and "*" not in subscribed_events:
            continue

        body = json.dumps(
            {"event": event, "timestamp": int(time.time()), "data": payload},
            default=str,
        )

        try:
            from app.worker import deliver_webhook_task
            deliver_webhook_task.apply_async(args=[hook.id, body, event])
            enqueued_count += 1
        except Exception as exc:
            logger.warning(
                "Webhook %s not enqueued because Celery broker is unavailable: %s",
                hook.id,
                exc,
            )

    return enqueued_count
