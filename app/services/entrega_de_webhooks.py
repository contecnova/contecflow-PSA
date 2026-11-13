"""Entrega de un webhook saliente: lo que ejecuta `app.worker.deliver_webhook`.

Segunda auditoria 2026-11 (#37): eran 136 lineas dentro de la tarea de Celery
mas el cortacircuitos. La decision de reintentar se devuelve
(`reintentar_en`); quien llama a `self.retry` es la tarea, que es lo unico de
Celery.

(#33) La entrega corre en la organizacion del webhook: la fila de
`WebhookDelivery` y el aviso `webhook.suspended` quedan en esa organizacion.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

#: Esperas entre intentos (1 -> 2 -> 3) ante fallos transitorios.
ESPERAS_DE_REINTENTO = (60, 300, 1800)
ESTADOS_TRANSITORIOS = frozenset({408, 425, 429, 500, 502, 503, 504})


def aplicar_cortacircuitos(hook) -> None:
    """Suspende un webhook tras N fallos seguidos, y avisa a los administradores.

    Auditoria 2026-09 (hallazgo 18). Suspender no es tirar la configuracion: el
    webhook queda inactivo con su `suspended_at` y se reactiva desde el panel.
    El aviso usa **su propia sesion** porque la de la entrega puede estar a
    medias de una transaccion.
    """
    umbral = getattr(settings, "WEBHOOK_CB_THRESHOLD", 5)
    if hook.consecutive_failures < umbral or not hook.is_active:
        return

    hook.is_active = False
    hook.suspended_at = datetime.now(timezone.utc)
    logger.error(
        "Circuit breaker: webhook %s (%s) suspended after %d consecutive "
        "failures. Re-enable via the admin panel once the endpoint is fixed.",
        hook.id, hook.url, hook.consecutive_failures,
    )
    try:
        from app.core.events import emit_event
        from app.db import session as _sesion
        from app.services.service_desk.ticket_events import como_organizacion

        with _sesion.worker_db_session() as _db, como_organizacion(_db, getattr(hook, "organization_id", None)):
            emit_event(_db, "webhook.suspended", {
                "webhook_id": hook.id,
                "webhook_name": hook.name,
                "url": hook.url,
                "consecutive_failures": hook.consecutive_failures,
            })
    except Exception:
        # El aviso es cortesia: no debe impedir la suspension.
        logger.warning("No se pudo emitir webhook.suspended", exc_info=True)


def entregar_webhook(webhook_id, body: str, event: str, intento: int = 0) -> dict:
    """Un intento de entrega. Cada intento queda en `WebhookDelivery`.

    Devuelve el resultado; si el fallo es transitorio, el webhook sigue activo y
    quedan intentos, trae `reintentar_en` (segundos) y `motivo` (la excepcion).
    """
    import httpx

    from app.core.encryption import decrypt_value
    from app.db import session as _sesion
    from app.models.enterprise import Webhook, WebhookDelivery
    from app.services.enterprise_service import _validate_webhook_url
    from app.services.service_desk.ticket_events import como_organizacion
    from app.services.webhooks import _sign_payload

    with _sesion.worker_db_session() as db:
        hook = db.query(Webhook).filter(Webhook.id == webhook_id, Webhook.is_active == True).first()  # noqa: E712
        if not hook:
            return {"skipped": True, "reason": "webhook not found or inactive"}

        with como_organizacion(db, getattr(hook, "organization_id", None)):
            # SSRF: se revalida justo antes de salir (DNS rebinding / TOCTOU).
            try:
                _validate_webhook_url(hook.url)
            except ValueError as exc:
                logger.warning("Webhook delivery blocked by SSRF guard: hook_id=%s url=%r reason=%s",
                               hook.id, hook.url, exc)
                db.add(WebhookDelivery(
                    webhook_id=hook.id, event=event, payload=body[:10000],
                    status_code=None, response=None, success=False,
                    error=f"blocked: unsafe destination ({exc})"[:500],
                ))
                try:
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
                return {"skipped": True, "blocked": True, "reason": "unsafe_destination"}

            status_code: Optional[int] = None
            response_text = error = None
            duration_ms = None
            http_exc: Optional[Exception] = None
            success = False
            try:
                headers = {
                    "Content-Type": "application/json",
                    "User-Agent": "Contecflow-Webhooks/1.0",
                    "X-Contecflow-Event": event,
                }
                if hook.secret:
                    secret = decrypt_value(hook.secret) or hook.secret
                    headers["X-Contecflow-Signature"] = _sign_payload(secret, body)
                inicio = time.time()
                from app.services.settings_service import outbound_http_timeout
                with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as client:
                    resp = client.post(hook.url, content=body, headers=headers)
                duration_ms = int((time.time() - inicio) * 1000)
                status_code = resp.status_code
                response_text = resp.text[:500]
                success = 200 <= resp.status_code < 300
            except httpx.HTTPError as exc:
                error = str(exc)[:500]
                http_exc = exc
            except Exception as exc:
                logger.warning("Webhook %s: error inesperado al entregar", webhook_id, exc_info=True)
                error = str(exc)[:500]

            db.add(WebhookDelivery(
                webhook_id=hook.id, event=event, payload=body[:10000],
                status_code=status_code, response=response_text, success=success,
                error=error, duration_ms=duration_ms,
            ))
            hook.total_deliveries = (hook.total_deliveries or 0) + 1
            hook.last_triggered_at = datetime.now(timezone.utc)
            if success:
                hook.consecutive_failures = 0
            else:
                hook.failed_deliveries = (hook.failed_deliveries or 0) + 1
                hook.consecutive_failures = (hook.consecutive_failures or 0) + 1
                aplicar_cortacircuitos(hook)
            db.commit()

            resultado = {"success": success, "status_code": status_code, "suspended": not hook.is_active}
            transitorio = http_exc is not None or status_code in ESTADOS_TRANSITORIOS
            if hook.is_active and transitorio:
                if intento < len(ESPERAS_DE_REINTENTO):
                    resultado["reintentar_en"] = ESPERAS_DE_REINTENTO[intento]
                    resultado["motivo"] = http_exc or RuntimeError(f"HTTP {status_code}")
                    logger.warning("Webhook %s transient failure (attempt %d/%d), retrying in %ds: %s",
                                   webhook_id, intento + 1, len(ESPERAS_DE_REINTENTO) + 1,
                                   resultado["reintentar_en"], resultado["motivo"])
                else:
                    logger.error("Webhook %s transient failure exhausted retries (attempt %d/%d). "
                                 "Last status=%s error=%s", webhook_id, intento + 1,
                                 len(ESPERAS_DE_REINTENTO) + 1, status_code, error)
            return resultado
