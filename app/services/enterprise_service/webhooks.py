"""Webhooks salientes: validacion de destino (sin redes internas), alta, edicion, entregas y prueba.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from app.core.encryption import encrypt_value
from app.models.enterprise import Webhook
from app.models.enterprise import WebhookDelivery
from app.services.audit import audit_log
from sqlalchemy.orm import joinedload
from typing import TYPE_CHECKING
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.services.settings_service import outbound_http_timeout
from app.core.codigos_de_error import ErrorConCodigo
if TYPE_CHECKING:
    from app.models.enterprise import (
        Webhook,
    )


logger = logging.getLogger("app.services.enterprise_service")

# Auditoría 22-11-2026 (01 M7, 02 A27): aquí había un segundo validador SSRF con
# su propia lista de redes, divergente del central. Ahora delega en
# `app.core.outbound_url` (un único guardia: IP global, metadatos de nube, CGN,
# NAT64...). Los nombres se conservan porque el paquete los reexporta.
from app.core.outbound_url import es_red_prohibida as _es_red_prohibida
from app.core.outbound_url import ConexionBloqueada
from app.core.outbound_url import validar_url_o_valueerror as _validar_url

_BLOCKED_NETWORKS: list = []      # obsoleto: la política vive en outbound_url
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset()


def _rechazar_si_es_interna(ip_str: str) -> None:
    """Levanta si esta IP no es un destino saliente aceptable (delegado)."""
    if _es_red_prohibida(ip_str):
        raise ErrorConCodigo("url_red_no_permitida", campo="Webhook")


def _validate_webhook_url(url: str) -> None:
    """Levanta `ErrorConCodigo` (un `ValueError`) si *url* no es un destino seguro.

    HTTPS obligatorio y el guardia central (`validate_outbound_url`). La entrega
    usa además `cliente_httpx`, que comprueba la IP conectada (DNS rebinding).
    """
    _validar_url(url, field="Webhook", require_https=True)


# ── Serializers ───────────────────────────────────────────────────────────────

def serialize_webhook(h) -> dict:
    import json
    return {
        "id": h.id, "name": h.name, "url": h.url,
        "has_secret": bool(h.secret),
        "events": json.loads(h.events) if h.events else [],
        "is_active": h.is_active,
        # Auditoría 22-11-2026 (A44): suspendido por el cortacircuitos (no borrado).
        "suspended": bool(not h.is_active and getattr(h, "suspended_at", None)),
        "suspended_at": str(h.suspended_at)[:16] if getattr(h, "suspended_at", None) else None,
        "consecutive_failures": getattr(h, "consecutive_failures", 0) or 0,
        "project_id": h.project_id,
        "project_name": h.project.name if h.project else None,
        "total_deliveries": h.total_deliveries or 0,
        "failed_deliveries": h.failed_deliveries or 0,
        "last_triggered_at": str(h.last_triggered_at)[:16] if h.last_triggered_at else None,
        "created_at": str(h.created_at)[:10] if h.created_at else None,
    }


def test_webhook_delivery(hook, current_user) -> dict:
    """Send a test payload to a webhook URL and return result.

    The destination URL is validated against SSRF risks before the request
    is made.  Blocked attempts are logged as warnings for audit purposes.
    """
    import httpx
    import json
    import time

    # ── SSRF guard — must happen before any network I/O ──────────────────────
    try:
        _validate_webhook_url(hook.url)
    except ValueError as exc:
        actor = getattr(current_user, "email", "unknown")
        logger.warning(
            "Webhook SSRF attempt blocked: actor=%s hook_id=%s url=%r reason=%s",
            actor,
            getattr(hook, "id", "?"),
            hook.url,
            exc,
        )
        return {"ok": False, "blocked": True, "error": f"URL no permitida: {exc}"}

    test_payload = {
        "event": "test",
        "message": f"This is a test delivery from {NOMBRE_DEL_PRODUCTO}",
        "triggered_by": current_user.full_name,
    }
    try:
        body = json.dumps({"event": "test", "data": test_payload}, default=str)
        start = time.time()
        from app.core.outbound_url import cliente_httpx
        with cliente_httpx(timeout=outbound_http_timeout(default=10.0)) as client:
            resp = client.post(
                hook.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "User-Agent": "Contecflow-Test/11.0",
                },
            )
        return {
            "ok": resp.status_code < 400,
            "status_code": resp.status_code,
            "duration_ms": int((time.time() - start) * 1000),
        }
    except httpx.TimeoutException as exc:
        logger.warning("Webhook delivery timeout: url=%r error=%s", hook.url, exc)
        return {"ok": False, "error": "Timeout al conectar con el destino del webhook"}
    except httpx.RequestError as exc:
        logger.warning("Webhook delivery network error: url=%r error=%s", hook.url, exc)
        return {"ok": False, "error": "Error de red al conectar con el destino del webhook"}
    except ConexionBloqueada as exc:
        logger.warning("Webhook SSRF blocked at connect: url=%r error=%s", hook.url, exc)
        return {"ok": False, "blocked": True, "error": "URL no permitida: el destino resuelve a una red interna"}


# ── Webhooks ──────────────────────────────────────────────────────────────────

def _vivo():
    """Activo o suspendido por el cortacircuitos (A44): borrado = inactivo SIN `suspended_at`.

    Antes el cortacircuitos ponía `is_active=False` y la lista y la edición
    filtraban `is_active == True`: un webhook suspendido desaparecía y no se
    podía reactivar ni borrar."""
    from sqlalchemy import or_
    return or_(Webhook.is_active == True, Webhook.suspended_at.isnot(None))  # noqa: E712


def list_webhooks(db: Session) -> list:
    hooks = db.query(Webhook).options(joinedload(Webhook.project)).filter(
        _vivo()
    ).order_by(Webhook.created_at.desc()).all()
    return [serialize_webhook(h) for h in hooks]


def reactivar_webhook(hook_id: str, current_user, db: Session) -> dict:
    """Reactiva un webhook suspendido por el cortacircuitos (A44): contador a 0."""
    hook = db.query(Webhook).filter(Webhook.id == hook_id, _vivo()).first()
    if not hook:
        raise ValueError("not_found")
    antes = {"is_active": bool(hook.is_active), "suspended_at": str(hook.suspended_at) if hook.suspended_at else None,
             "consecutive_failures": hook.consecutive_failures}
    hook.is_active = True
    hook.suspended_at = None
    hook.consecutive_failures = 0
    audit_log(db, current_user, "REACTIVATE", "webhooks", hook.id, hook.name, old_values=antes,
              new_values={"is_active": True})
    db.commit()
    return serialize_webhook(hook)


def create_webhook(payload, current_user, db: Session) -> dict:
    import json as _json
    # SSRF guard at the source: never persist a webhook pointing at an internal
    # or non-HTTPS destination. Raises ValueError → mapped to 400 by the router.
    _validate_webhook_url(payload.url)
    hook = Webhook(
        name=payload.name, url=payload.url,
        secret=encrypt_value(payload.secret) if payload.secret else None,
        events=_json.dumps(payload.events),
        project_id=payload.project_id,
        created_by=current_user.id,
    )
    db.add(hook)
    audit_log(db, current_user, "CREATE", "webhooks", hook.id, hook.name)
    db.commit()
    return serialize_webhook(hook)


def update_webhook(hook_id: str, payload, current_user, db: Session) -> dict:
    import json as _json
    hook = db.query(Webhook).filter(Webhook.id == hook_id, _vivo()).first()
    if not hook:
        raise ValueError("not_found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("url"):
        _validate_webhook_url(data["url"])
    if "events" in data:
        data["events"] = _json.dumps(data["events"])
    if "secret" in data and data["secret"]:
        data["secret"] = encrypt_value(data["secret"])
    # M85 (auditoría 22-11-2026): el cambio queda auditado (sin el secreto).
    antes = {k: (getattr(hook, k, None) if k != "secret" else "***") for k in data}
    for k, v in data.items():
        setattr(hook, k, v)
    audit_log(db, current_user, "UPDATE", "webhooks", hook.id, getattr(hook, "name", None) or hook.url,
              old_values=antes, new_values={k: (v if k != "secret" else "***") for k, v in data.items()})
    db.commit()
    return serialize_webhook(hook)


def delete_webhook(hook_id: str, current_user, db: Session) -> dict:
    hook = db.query(Webhook).filter(Webhook.id == hook_id, _vivo()).first()
    if not hook:
        raise ValueError("not_found")
    audit_log(db, current_user, "DELETE", "webhooks", hook.id, hook.name)
    hook.is_active = False
    hook.suspended_at = None   # borrado, no suspendido
    db.commit()
    return {"ok": True, "message": "Webhook eliminado correctamente"}


def get_webhook_deliveries(hook_id: str, limit: int, db: Session) -> list:
    deliveries = db.query(WebhookDelivery).filter(
        WebhookDelivery.webhook_id == hook_id
    ).order_by(WebhookDelivery.created_at.desc()).limit(limit).all()
    return [{
        "id": d.id, "event": d.event, "status_code": d.status_code,
        "success": d.success, "error": d.error, "duration_ms": d.duration_ms,
        "created_at": str(d.created_at)[:19],
    } for d in deliveries]


def list_all_webhook_deliveries(
    db: Session, *, webhook_id: str | None = None, event: str | None = None,
    success: bool | None = None, page: int = 1, page_size: int = 50,
) -> dict:
    """Entregas de todos los webhooks de la empresa en una sola consulta (segunda auditoria 2026-11, #22).

    Sustituye a la pagina que pedia `/webhooks/{id}/...` una vez por webhook (N+1).
    El aislamiento por empresa lo pone la sesion; el join solo trae nombre y URL.
    """
    q = (db.query(WebhookDelivery, Webhook.name, Webhook.url)
         .join(Webhook, Webhook.id == WebhookDelivery.webhook_id))
    if webhook_id:
        q = q.filter(WebhookDelivery.webhook_id == webhook_id)
    if event:
        q = q.filter(WebhookDelivery.event == event)
    if success is not None:
        q = q.filter(WebhookDelivery.success == success)
    total = q.count()
    filas = (q.order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id)
              .offset((page - 1) * page_size).limit(page_size).all())
    items = [{
        "id": d.id, "webhook_id": d.webhook_id, "webhook_name": nombre, "webhook_url": url,
        "event": d.event, "status_code": d.status_code, "success": bool(d.success),
        "error": d.error, "duration_ms": d.duration_ms, "attempt": d.attempt,
        "payload": d.payload, "response": (d.response or "")[:500] or None,
        "created_at": str(d.created_at)[:19] if d.created_at else None,
    } for d, nombre, url in filas]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def get_webhook_for_test(hook_id: str, db: Session):
    return db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()
