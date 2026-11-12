"""Disparadores por webhook entrante: alta, rotacion del slug, registro y ejecucion del flujo.

Parte de `app.services.cab_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy.orm import Session, joinedload
from app.models.cab import WebhookTrigger, WebhookTriggerLog
from app.db.session import SessionLocal
from app.models.bookings import WorkflowQueueItem
from app.core.errores import ErrorDeDominio

from app.services.cab_service._comun import logger


def trigger_out(t: WebhookTrigger) -> dict:
    return {
        "id": t.id, "name": t.name, "slug": t.slug,
        "workflow_id": t.workflow_id,
        "is_active": t.is_active,
        "fire_count": t.fire_count or 0,
        "last_fired_at": str(t.last_fired_at)[:16] if t.last_fired_at else None,
        "slug_rotated_at": str(t.slug_rotated_at)[:19] if t.slug_rotated_at else None,
        "slug_expires_at": str(t.slug_expires_at)[:19] if t.slug_expires_at else None,
        "endpoint": f"/api/v1/webhooks/fire/{t.slug}",
    }


# ─── Webhook background task ──────────────────────────────────────────────────

def execute_workflow_from_webhook(workflow_id: str, context: dict) -> None:
    """Background task: enqueue workflow triggered by incoming webhook."""
    bg_db = SessionLocal()
    try:
        item = WorkflowQueueItem(
            workflow_id=workflow_id,
            trigger_data=json.dumps(context),
            execute_at=datetime.now(timezone.utc),
            status="pending",
        )
        bg_db.add(item); bg_db.commit()
    except Exception as e:
        bg_db.rollback()
        logger.error(f"Failed to create webhook trigger: {e}", exc_info=True)
    finally:
        bg_db.close()


# ─── Webhook CRUD ─────────────────────────────────────────────────────────────

def list_webhook_triggers(db: Session) -> list:
    triggers = db.query(WebhookTrigger).options(joinedload(WebhookTrigger.workflow)).all()
    return [trigger_out(t) for t in triggers]


def create_webhook_trigger(payload, current_user_id: str, db: Session) -> dict:
    import secrets as _secrets
    existing = db.query(WebhookTrigger).filter(WebhookTrigger.slug == payload.slug).first()
    if existing:
        raise ValueError(f"Slug '{payload.slug}' ya está en uso")
    secret = payload.secret or _secrets.token_hex(32)
    t = WebhookTrigger(
        name=payload.name, slug=payload.slug,
        secret=secret,
        workflow_id=payload.workflow_id,
        rule_id=payload.rule_id,
        field_mapping=json.dumps(payload.field_mapping) if payload.field_mapping else None,
        created_by=current_user_id,
    )
    db.add(t); db.commit()
    return {"ok": True, "id": t.id, "secret": secret,
            "endpoint": f"/api/v1/webhooks/fire/{t.slug}"}


def log_webhook_fire(trigger, payload_str: str, headers_str: str, db: Session) -> None:
    log = WebhookTriggerLog(
        trigger_id=trigger.id,
        payload=payload_str[:2000],
        headers=headers_str[:1000],
        status="ok",
    )
    db.add(log)
    trigger.fire_count = (trigger.fire_count or 0) + 1
    trigger.last_fired_at = datetime.now(timezone.utc)
    db.commit()


def get_active_webhook_trigger_by_slug(db: Session, slug: str) -> WebhookTrigger:
    trigger = db.query(WebhookTrigger).filter(
        WebhookTrigger.slug == slug,
        WebhookTrigger.is_active == True,
    ).first()
    if not trigger:
        raise ErrorDeDominio(404, "Webhook trigger no encontrado")
    if trigger.slug_expires_at and trigger.slug_expires_at < datetime.now(timezone.utc):
        raise ErrorDeDominio(410, "Webhook trigger slug expirado — rota el slug para reactivarlo")
    return trigger


def rotate_webhook_trigger_slug(trigger_id: str, expires_in_days: int | None, db: Session) -> dict:
    """Generate a new random slug for the trigger, invalidating the old one immediately.

    expires_in_days: if provided, sets slug_expires_at that many days from now.
                     Pass None (or omit) for a non-expiring slug.
    """
    import secrets as _secrets
    t = db.query(WebhookTrigger).filter(WebhookTrigger.id == trigger_id).first()
    if not t:
        raise ValueError("Trigger no encontrado")
    new_slug = _secrets.token_urlsafe(16)
    # Ensure uniqueness (collision extremely unlikely but guard anyway)
    while db.query(WebhookTrigger).filter(WebhookTrigger.slug == new_slug).first():
        new_slug = _secrets.token_urlsafe(16)
    t.slug = new_slug
    t.slug_rotated_at = datetime.now(timezone.utc)
    if expires_in_days is not None:
        from datetime import timedelta
        t.slug_expires_at = t.slug_rotated_at + timedelta(days=expires_in_days)
    else:
        t.slug_expires_at = None
    db.commit()
    return {
        "ok": True, "id": t.id, "slug": t.slug,
        "slug_rotated_at": str(t.slug_rotated_at)[:19],
        "slug_expires_at": str(t.slug_expires_at)[:19] if t.slug_expires_at else None,
        "endpoint": f"/api/v1/webhooks/fire/{t.slug}",
    }


def get_webhook_logs(trigger_id: str, db: Session) -> list:
    logs = db.query(WebhookTriggerLog).filter(
        WebhookTriggerLog.trigger_id == trigger_id
    ).order_by(WebhookTriggerLog.received_at.desc()).limit(50).all()
    return [{
        "id": l.id, "status": l.status, "error": l.error,
        "received_at": str(l.received_at)[:16],
        "payload_preview": (l.payload or "")[:200],
    } for l in logs]


def delete_webhook_trigger(trigger_id: str, db: Session) -> dict:
    t = db.query(WebhookTrigger).filter(WebhookTrigger.id == trigger_id).first()
    if not t:
        raise ValueError("Trigger no encontrado")
    db.delete(t); db.commit()
    return {"ok": True}
