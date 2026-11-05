from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

from app.core.deps import get_current_user, get_db, require_any_manager
from app.models.user import User
import app.services.integrations as _svc

router = APIRouter(tags=["Notifications", "Slack"])
logger = logging.getLogger(__name__)


# Una sola tarjeta: la del servicio (aqui habia una copia muerta, sobrescrita
# justo debajo, con los enlaces de aprobacion rotos).
_build_block_kit_message = _svc.build_block_kit_message


@router.post("/notifications/slack/block-kit", summary="Send rich Slack Block Kit notification")
def send_slack_block_kit(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_manager),
):
    import httpx

    event_type = payload.get("event_type", "custom")
    data = payload.get("data", {})

    block_kit = _build_block_kit_message(event_type, data)
    if payload.get("channel"):
        block_kit["channel"] = payload["channel"]

    webhook_url = payload.get("webhook_url")
    if not webhook_url:
        org_id = getattr(current_user, "organization_id", None)
        webhook_url = _svc.get_slack_webhook_url(db, org_id)

    if not webhook_url:
        raise HTTPException(
            status_code=503,
            detail="No Slack webhook URL configured. Set it in Settings -> Integrations -> Slack.",
        )

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(webhook_url, json=block_kit)
            resp.raise_for_status()
    except Exception as exc:
        logger.warning("Slack block kit delivery failed: %s", exc)
        raise HTTPException(status_code=502, detail="Slack delivery failed")

    return {"ok": True, "event_type": event_type, "blocks_count": len(block_kit.get("blocks", []))}


@router.get("/notifications/slack/block-kit/preview", summary="Preview Block Kit message for a given event type")
def preview_block_kit(
    event_type: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    sample_data = {
        "task_overdue": {"task_title": "API Integration", "project_name": "CRM Relaunch", "due_date": "2026-04-01", "assignee": "Alice Smith", "task_id": "xxx"},
        "invoice_paid": {"invoice_number": "INV-2026-042", "amount": 12500.0, "currency": "EUR", "client_name": "Acme Corp", "paid_at": "2026-04-11"},
        "approval_required": {"entity_type": "expense", "submitter": "Bob Jones", "amount": "€850", "project_name": "Digital Transformation", "request_id": "req-001"},
    }
    data = sample_data.get(event_type, {"message": f"Sample {event_type} event"})
    return _build_block_kit_message(event_type, data)
