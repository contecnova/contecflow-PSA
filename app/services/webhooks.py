"""
webhooks.py — Outbound webhook delivery service.

Usage:
    from app.services.webhooks import fire_webhook
    fire_webhook(db, "task.status_changed", {"task_id": t.id, "status": "done"}, project_id=t.project_id)

Delivery is asynchronous when Celery/Redis is available (deliver_webhook_task).
Falls back to synchronous delivery if the task broker is unreachable (dev/test).
"""
import json
import hmac
import hashlib
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from app.models.enterprise import Webhook, WebhookDelivery
from app.core.encryption import decrypt_value

logger = logging.getLogger(__name__)


def _sign_payload(secret: str, payload: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _deliver_single(db: Session, hook: Webhook, body: str, event: str) -> bool:
    """Deliver *body* to a single webhook synchronously. Returns True on HTTP 2xx.

    All exceptions are caught and recorded in WebhookDelivery so a single
    failing endpoint never raises into the caller.
    """
    status_code = None
    response_text = None
    success = False
    error = None
    duration_ms = None

    try:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Contecflow-Webhooks/1.0",
            "X-Contecflow-Event": event,
        }
        if hook.secret:
            secret = decrypt_value(hook.secret) or hook.secret
            headers["X-Contecflow-Signature"] = _sign_payload(secret, body)

        start = time.time()
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(hook.url, content=body, headers=headers)
        duration_ms = int((time.time() - start) * 1000)
        status_code = resp.status_code
        response_text = resp.text[:500]
        success = 200 <= resp.status_code < 300

    except Exception as exc:
        error = str(exc)[:500]
        logger.warning("Webhook %s delivery error: %s", hook.id, error)

    delivery = WebhookDelivery(
        webhook_id=hook.id,
        event=event,
        payload=body[:10000],
        status_code=status_code,
        response=response_text,
        success=success,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(delivery)

    hook.total_deliveries = (hook.total_deliveries or 0) + 1
    if not success:
        hook.failed_deliveries = (hook.failed_deliveries or 0) + 1
    hook.last_triggered_at = datetime.now(timezone.utc)

    db.commit()
    return success


def fire_webhook(
    db: Session,
    event: str,
    payload: dict,
    project_id: Optional[str] = None,
) -> int:
    """Find matching active webhooks and dispatch the event payload.

    When Celery is available each delivery is enqueued as an async task so the
    calling request is never blocked by slow or unresponsive webhook endpoints.
    Falls back to synchronous delivery (_deliver_single) when the broker is
    unreachable (development without Redis).

    Returns the number of webhooks triggered.
    """
    hooks = db.query(Webhook).filter(Webhook.is_active == True).all()
    triggered = 0

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

        enqueued = False
        try:
            from app.worker import deliver_webhook_task
            deliver_webhook_task.apply_async(args=[hook.id, body, event])
            enqueued = True
        except Exception as exc:
            logger.debug("Celery unavailable, delivering webhook %s synchronously: %s", hook.id, exc)

        if not enqueued:
            _deliver_single(db, hook, body, event)

        triggered += 1

    return triggered
