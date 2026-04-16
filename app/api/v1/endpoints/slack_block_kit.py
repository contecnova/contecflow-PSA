from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.deps import get_current_user, get_db, require_any_manager
from app.models.user import User
import app.services.integrations as _svc

router = APIRouter(tags=["Notifications", "Slack"])


def _build_block_kit_message(event_type: str, payload: dict) -> dict:
    base_url = settings.FRONTEND_URL or "http://localhost:3000"

    if event_type == "task_overdue":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "⚠️ Task Overdue"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Task:*\n{payload.get('task_title', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Project:*\n{payload.get('project_name', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Due Date:*\n{payload.get('due_date', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Assignee:*\n{payload.get('assignee', 'N/A')}"},
                ]},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "View Task"},
                     "url": f"{base_url}/tasks/{payload.get('task_id', '')}",
                     "style": "primary"},
                    {"type": "button", "text": {"type": "plain_text", "text": "Update Status"},
                     "url": f"{base_url}/tasks/{payload.get('task_id', '')}?action=update"},
                ]},
            ]
        }
    if event_type == "invoice_paid":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "✅ Invoice Paid"}},
                {"type": "section", "fields": [
                    {"type": "mrkdwn", "text": f"*Invoice:*\n{payload.get('invoice_number', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Amount:*\n{payload.get('currency', 'EUR')} {payload.get('amount', 0):,.2f}"},
                    {"type": "mrkdwn", "text": f"*Client:*\n{payload.get('client_name', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Paid At:*\n{payload.get('paid_at', 'N/A')}"},
                ]},
            ]
        }
    if event_type == "approval_required":
        return {
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🔔 Approval Required"}},
                {"type": "section", "text": {
                    "type": "mrkdwn",
                    "text": f"*{payload.get('entity_type', 'Item').title()}* submitted by "
                            f"*{payload.get('submitter', 'Unknown')}* requires your approval.",
                }},
                {"type": "actions", "elements": [
                    {"type": "button", "text": {"type": "plain_text", "text": "✅ Approve"},
                     "style": "primary",
                     "url": f"{base_url}/approvals/{payload.get('request_id', '')}?action=approve"},
                    {"type": "button", "text": {"type": "plain_text", "text": "❌ Reject"},
                     "style": "danger",
                     "url": f"{base_url}/approvals/{payload.get('request_id', '')}?action=reject"},
                ]},
            ]
        }

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
        raise HTTPException(status_code=502, detail=f"Slack delivery failed: {exc}")

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
