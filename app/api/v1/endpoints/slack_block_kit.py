from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session
import logging

from app.core.deps import get_current_user, get_db, requiere_capacidad
from app.models.user import User
import app.services.integrations as _svc
from app.core.codigos_de_error import error_http

router = APIRouter(tags=["Notifications", "Slack"])
logger = logging.getLogger(__name__)


# Una sola tarjeta: la del servicio (aqui habia una copia muerta, sobrescrita
# justo debajo, con los enlaces de aprobacion rotos).
_build_block_kit_message = _svc.build_block_kit_message


@router.post("/notifications/slack/block-kit", summary="Send rich Slack Block Kit notification")
def send_slack_block_kit(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(requiere_capacidad("integraciones.responsables")),
):
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
        raise error_http(503, "slack_sin_webhook", detail="No Slack webhook URL configured. Set it in Settings -> Integrations -> Slack.")

    # Auditoria 2026-11 (#35): `httpx` directo, sin validar la URL que llega en
    # el cuerpo (SSRF). Ahora la URL se valida (400 si es interna) y el envio
    # sale por `entrega_saliente.enviar_a_webhook`, el emisor comun.
    from app.core.outbound_url import validate_outbound_url
    from app.services.entrega_saliente import enviar_a_webhook

    validate_outbound_url(webhook_url, field="webhook_url")
    resultado = enviar_a_webhook(webhook_url, block_kit)
    if not resultado.ok:
        logger.warning("Slack block kit delivery failed: %s", resultado.error)
        raise error_http(502, "webhook_entrega_fallida", detail="Slack delivery failed", servicio="Slack")

    return {"ok": True, "event_type": event_type, "blocks_count": len(block_kit.get("blocks", []))}


@router.get("/notifications/slack/block-kit/preview", summary="Preview Block Kit message for a given event type")
def preview_block_kit(
    event_type: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    # 19-11-2026: sin nombres de demo (Alice Smith, Acme Corp…): la vista previa
    # usa a quien la pide, la moneda de su empresa y textos neutros de ejemplo.
    from app.core.timeutil import utcnow
    from app.services.settings_service import por_empresa as _pe
    hoy = utcnow().date().isoformat()
    quien = getattr(current_user, "full_name", None) or getattr(current_user, "email", "")
    moneda = _pe.moneda_de_empresa(None, current_user.organization_id)
    sample_data = {
        "task_overdue": {"task_title": "Tarea de ejemplo", "project_name": "Proyecto de ejemplo", "due_date": hoy, "assignee": quien, "task_id": "ejemplo"},
        "invoice_paid": {"invoice_number": "FAC-EJEMPLO", "amount": 1000.0, "currency": moneda, "client_name": "Cliente de ejemplo", "paid_at": hoy},
        "approval_required": {"entity_type": "expense", "submitter": quien, "amount": f"100 {moneda}", "project_name": "Proyecto de ejemplo", "request_id": "ejemplo"},
    }
    data = sample_data.get(event_type, {"message": f"Sample {event_type} event"})
    return _build_block_kit_message(event_type, data)
