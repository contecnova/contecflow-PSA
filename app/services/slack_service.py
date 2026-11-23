"""Integracion con Slack: configuracion, envio y registro.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `mfa_service.py`, un
fichero de 1.435 lineas que contenia OCHO dominios sin relacion entre si —MFA,
organizaciones, Slack, presupuestos, planificacion asistida, escenarios, PDF y
tokens de BI— servidos ademas por un unico router llamado `mfa.py` con 38 rutas.

El reparto se pudo hacer mecanicamente porque los ocho dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.mfa import (
    SlackConfig, SlackNotificationLog,
)
from app.core.codigos_de_error import ErrorConCodigo

_logger = logging.getLogger(__name__)


def send_slack_message(config: SlackConfig, text: str, channel: str = None) -> tuple:
    """
    Send a message to Slack or Teams.
    Returns (success: bool, error: str|None)

    Auditoria 2026-11 (#35): las dos vias (API con bot token y webhook) salen
    por `entrega_saliente.enviar_a_webhook` (URL validada, `cliente_httpx`).
    """
    from app.services.entrega_saliente import enviar_a_webhook
    from app.services.textos_de_salida import nombre_de_marca

    ch = channel or config.default_channel or settings.SLACK_CANAL_POR_DEFECTO

    # 23-11-2026 (03 A-RZ2): el token se guarda cifrado; `decrypt_value` devuelve
    # tal cual los valores antiguos en claro hasta que se re-guarden o migren.
    from app.core.encryption import decrypt_value
    token = decrypt_value(config.bot_token) if config.bot_token else None
    if config.platform == "slack" and token:
        r = enviar_a_webhook(
            f"{settings.SLACK_API_BASE}/chat.postMessage",
            # 18-11-2026: firma con el nombre de la empresa (o el del producto), no «Contecflow» fijo.
            {"channel": ch, "text": text, "username": nombre_de_marca(None, getattr(config, "organization_id", None)),
             "icon_emoji": ":rocket:"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=5, campo="SLACK_API_BASE",
        )
        if r.ok:
            if (r.datos or {}).get("ok"):
                return True, None
            return False, (r.datos or {}).get("error", "Slack API error")
        _logger.warning("Fallo enviando mensaje vía Slack bot token: %s", r.error)
        if not config.webhook_url:
            return False, r.error or "slack_error"

    if config.webhook_url:
        body = {"text": text} if config.platform == "teams" else {"text": text, "channel": ch}
        r = enviar_a_webhook(config.webhook_url, body, timeout=5, estados_ok=(200, 201))
        if not r.ok:
            _logger.warning("Webhook delivery failed for platform=%s: %s", config.platform, r.error)
        return r.ok, r.error

    # Ronda 2 auditoría 2026-11-22: sin token ni webhook NO se ha enviado nada.
    # Antes devolvía éxito («SIMULATED») y la prueba de conexión salía verde.
    _logger.info("Slack/Teams sin token ni webhook (%s → %s): no se envía", config.platform, ch)
    return False, "slack_sin_configurar"


def get_slack_config(db: Session) -> list:
    configs = db.query(SlackConfig).all()
    return [{
        "id": c.id, "platform": c.platform,
        "workspace_name": c.workspace_name,
        "default_channel": c.default_channel,
        "is_active": c.is_active,
        "has_token": bool(c.bot_token),
        "subscriptions": json.loads(c.subscriptions or "[]"),
        "last_ping_at": str(c.last_ping_at)[:16] if c.last_ping_at else None,
    } for c in configs]


def _token_cifrado(payload_dict: dict, actual=None):
    """El `bot_token` a guardar: cifrado (03 A-RZ2). Sin la clave en el
    formulario se conserva el guardado (la pantalla nunca lo recibe de vuelta);
    cadena vacía lo borra."""
    if "bot_token" not in payload_dict:
        return actual
    nuevo = (payload_dict.get("bot_token") or "").strip()
    if not nuevo:
        return None
    from app.core.encryption import encrypt_value
    return encrypt_value(nuevo)


def create_or_update_slack_config(payload_dict: dict, db: Session, organization_id=None) -> dict:
    """Crea o actualiza la configuración de Slack/Teams de UNA organización.

    Auditoría 2026-08 §7 — aquí había dos fallos de tenencia:

    1. La búsqueda de la config existente se hacía solo por `platform`, sin acotar
       por organización, así que configurar Slack en la organización B **sobrescribía
       la de la A** (incluido su webhook y su bot_token).
    2. `organization_id` no se rellenaba al crear, pero `get_slack_webhook_url()` sí
       filtra por esa columna. Resultado: el webhook nunca se encontraba cuando se
       consultaba acotado por organización, y las notificaciones no salían.
    """
    platform = payload_dict.get("platform", "slack")
    subs = json.dumps(payload_dict.get("subscriptions") or ["task_overdue", "budget_alert", "ticket_sla"])
    q = db.query(SlackConfig).filter(SlackConfig.platform == platform)
    if organization_id:
        q = q.filter(SlackConfig.organization_id == organization_id)
    else:
        # Sin organización sólo se puede tocar la config que tampoco la tiene, para
        # no pisar la de un tenant concreto.
        q = q.filter(SlackConfig.organization_id.is_(None))
    existing = q.first()
    if existing:
        existing.workspace_name = payload_dict.get("workspace_name")
        existing.bot_token = _token_cifrado(payload_dict, existing.bot_token)
        existing.webhook_url = payload_dict.get("webhook_url")
        existing.default_channel = payload_dict.get("default_channel") or settings.SLACK_CANAL_POR_DEFECTO
        existing.subscriptions = subs
        existing.is_active = True
        db.commit()
        return {"ok": True, "id": existing.id, "updated": True}
    config = SlackConfig(
        platform=platform,
        organization_id=organization_id,
        workspace_name=payload_dict.get("workspace_name"),
        bot_token=_token_cifrado(payload_dict),
        webhook_url=payload_dict.get("webhook_url"),
        default_channel=payload_dict.get("default_channel") or settings.SLACK_CANAL_POR_DEFECTO,
        subscriptions=subs,
    )
    db.add(config); db.commit()
    return {"ok": True, "id": config.id, "updated": False}


def test_slack_config(config_id: str, message: str, channel: str, db: Session) -> dict:
    config = db.query(SlackConfig).filter(SlackConfig.id == config_id).first()
    if not config:
        raise ValueError("not_found")
    sent, error = send_slack_message(config, message, channel)
    log = SlackNotificationLog(
        config_id=config.id,
        channel=channel,
        event_type="test",
        message=message,
        status="sent" if sent else "failed",
        error=error,
    )
    db.add(log)
    if sent:
        config.last_ping_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": sent, "error": error, "platform": config.platform}


def notify_slack(event_type: str, message: str, channel: Optional[str], source_id: Optional[str], db: Session) -> dict:
    config = db.query(SlackConfig).filter(SlackConfig.is_active == True).first()
    if not config:
        raise ErrorConCodigo("integracion_no_configurada", detail="No hay integración Slack/Teams activa", nombre="Slack/Teams")
    subs = json.loads(config.subscriptions or "[]")
    if event_type not in subs and event_type != "manual":
        return {"ok": True, "skipped": True, "reason": f"Event '{event_type}' not subscribed"}
    sent, error = send_slack_message(config, message, channel or config.default_channel)
    db.add(SlackNotificationLog(
        config_id=config.id, channel=channel or config.default_channel,
        event_type=event_type, message=message[:500],
        status="sent" if sent else "failed", error=error, source_id=source_id,
    ))
    db.commit()
    return {"ok": sent, "error": error}

