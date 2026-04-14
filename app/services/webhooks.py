"""
webhooks.py — Outbound webhook delivery service.

Usage:
    from app.services.webhooks import fire_webhook
    fire_webhook(db, "task.status_changed", {"task_id": t.id, "status": "done"}, project_id=t.project_id)
"""
import json
import hmac
import hashlib
import logging

logger = logging.getLogger(__name__)
import httpx
import time
from typing import Optional
from sqlalchemy.orm import Session
from app.models.enterprise import Webhook, WebhookDelivery
from app.core.encryption import decrypt_value


def _sign_payload(secret: str, payload: str) -> str:
    """Generate HMAC-SHA256 signature for webhook payload."""
    return "sha256=" + hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def fire_webhook(
    db: Session,
    event: str,
    payload: dict,
    project_id: Optional[str] = None,
) -> int:
    """
    Fire an event to all matching active webhooks.
    Returns number of webhooks triggered.
    Non-blocking — failures are logged but don't raise.
    """
    # Find all active webhooks that subscribe to this event
    hooks = db.query(Webhook).filter(Webhook.is_active == True).all()
    triggered = 0

    for hook in hooks:
        # Check project scope
        if hook.project_id and hook.project_id != project_id:
            continue

        # Check event subscription
        try:
            subscribed_events = json.loads(hook.events)
        except Exception as e:
            logger.warning(f"Failed to parse webhook events for hook {hook.id}: {e}")
            continue
        if event not in subscribed_events and "*" not in subscribed_events:
            continue

        # Build payload
        body = json.dumps({
            "event": event,
            "timestamp": int(time.time()),
            "data": payload,
        }, default=str)

        # Deliver
        status_code = None
        response_text = None
        success = False
        error = None
        duration_ms = None

        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Clarive-Webhooks/11.0",
                "X-Clarive-Event": event,
            }
            if hook.secret:
                secret = decrypt_value(hook.secret) or hook.secret
                headers["X-Clarive-Signature"] = _sign_payload(secret, body)

            start = time.time()
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(hook.url, content=body, headers=headers)
            duration_ms = int((time.time() - start) * 1000)
            status_code = resp.status_code
            response_text = resp.text[:500]
            success = 200 <= resp.status_code < 300

        except Exception as e:
            error = str(e)[:500]

        # Log delivery
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

        # Update hook stats
        hook.total_deliveries = (hook.total_deliveries or 0) + 1
        if not success:
            hook.failed_deliveries = (hook.failed_deliveries or 0) + 1
        from datetime import datetime, timezone
        hook.last_triggered_at = datetime.now(timezone.utc)

        triggered += 1

    if triggered > 0:
        db.commit()

    return triggered
