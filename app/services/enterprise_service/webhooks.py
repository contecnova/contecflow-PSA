"""Webhooks salientes: validacion de destino (sin redes internas), alta, edicion, entregas y prueba.

Parte de `app.services.enterprise_service` (auditoria 2026-11, #24): se partio por responsabilidad
sin cambiar el codigo. El paquete reexporta todos los nombres.
"""
from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.parse as _urlparse
from sqlalchemy.orm import Session
from app.core.encryption import encrypt_value
from app.models.enterprise import Webhook
from app.models.enterprise import WebhookDelivery
from app.services.audit import audit_log
from sqlalchemy.orm import joinedload
from typing import TYPE_CHECKING
from app.core.constantes import NOMBRE_DEL_PRODUCTO
from app.services.settings_service import outbound_http_timeout
if TYPE_CHECKING:
    from app.models.enterprise import (
        Webhook,
    )


logger = logging.getLogger("app.services.enterprise_service")

# Networks that must never be reachable from an outbound webhook delivery.
# Covers: loopback, RFC 1918, link-local (incl. AWS/GCP/Azure metadata),
# CGN (RFC 6598), documentation, IPv6 ULA, IPv6 link-local.
_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),   # link-local / AWS+GCP metadata
    ipaddress.ip_network("100.64.0.0/10"),    # CGN (RFC 6598)
    ipaddress.ip_network("192.0.2.0/24"),     # TEST-NET-1 (RFC 5737)
    ipaddress.ip_network("198.51.100.0/24"),  # TEST-NET-2
    ipaddress.ip_network("203.0.113.0/24"),   # TEST-NET-3
    ipaddress.ip_network("::1/128"),          # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),         # IPv6 ULA
    ipaddress.ip_network("fe80::/10"),        # IPv6 link-local
]
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "169.254.169.254",           # AWS/GCP/Azure IMDS
    "metadata.google.internal",
    "metadata.google",
    "metadata",
})


def _rechazar_si_es_interna(ip_str: str) -> None:
    """Levanta si esta IP es interna, reservada o está en la lista de bloqueo.

    Una cadena que no sea una IP se ignora en silencio: `getaddrinfo` puede
    devolver formas que `ip_address` no entiende, y eso no es un destino
    peligroso, es una entrada que no sabemos leer.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return

    if ip.is_loopback or ip.is_link_local or ip.is_private or ip.is_reserved or ip.is_unspecified:
        raise ValueError(f"Destino bloqueado — IP interna/reservada: {ip_str}")
    for red in _BLOCKED_NETWORKS:
        if ip in red:
            raise ValueError(f"Destino bloqueado — red interna {red}: {ip_str}")


def _validate_webhook_url(url: str) -> None:
    """Levanta `ValueError` si *url* no es un destino seguro para un webhook.

    Comprueba:
    - que el esquema sea https,
    - que el nombre no sea un punto de metadatos conocido,
    - que **ninguna** de las direcciones a las que resuelve caiga en un rango
      privado, de bucle local, link-local o reservado (prevención de SSRF).

    Se comprueban todas las direcciones y no sólo la primera: un nombre puede
    resolver a varias, y bastaría con que una fuera interna.

    Raises:
        ValueError: con un motivo legible; quien llama debe registrarlo.
    """
    try:
        parsed = _urlparse.urlparse(url)
    except Exception as exc:
        raise ValueError(f"URL malformada: {url!r}") from exc

    if parsed.scheme != "https":
        raise ValueError("Solo se permiten destinos HTTPS en webhooks")

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise ValueError("URL de webhook sin hostname")
    if hostname in _BLOCKED_HOSTNAMES:
        raise ValueError(f"Hostname de metadata bloqueado: {hostname!r}")

    try:
        direcciones = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(f"No se pudo resolver el hostname {hostname!r}: {exc}") from exc

    for *_ignorado, sockaddr in direcciones:
        _rechazar_si_es_interna(sockaddr[0])


# ── Serializers ───────────────────────────────────────────────────────────────

def serialize_webhook(h) -> dict:
    import json
    return {
        "id": h.id, "name": h.name, "url": h.url,
        "has_secret": bool(h.secret),
        "events": json.loads(h.events) if h.events else [],
        "is_active": h.is_active,
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
        with httpx.Client(timeout=outbound_http_timeout(default=10.0)) as client:
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
            "response": resp.text[:200],
            "duration_ms": int((time.time() - start) * 1000),
        }
    except httpx.TimeoutException as exc:
        logger.warning("Webhook delivery timeout: url=%r error=%s", hook.url, exc)
        return {"ok": False, "error": "Timeout al conectar con el destino del webhook"}
    except httpx.RequestError as exc:
        logger.warning("Webhook delivery network error: url=%r error=%s", hook.url, exc)
        return {"ok": False, "error": f"Error de red: {exc}"}


# ── Webhooks ──────────────────────────────────────────────────────────────────

def list_webhooks(db: Session) -> list:
    hooks = db.query(Webhook).options(joinedload(Webhook.project)).filter(
        Webhook.is_active == True
    ).order_by(Webhook.created_at.desc()).all()
    return [serialize_webhook(h) for h in hooks]


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
    hook = db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()
    if not hook:
        raise ValueError("not_found")
    data = payload.model_dump(exclude_unset=True)
    if data.get("url"):
        _validate_webhook_url(data["url"])
    if "events" in data:
        data["events"] = _json.dumps(data["events"])
    if "secret" in data and data["secret"]:
        data["secret"] = encrypt_value(data["secret"])
    for k, v in data.items():
        setattr(hook, k, v)
    db.commit()
    return serialize_webhook(hook)


def delete_webhook(hook_id: str, current_user, db: Session) -> dict:
    hook = db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()
    if not hook:
        raise ValueError("not_found")
    audit_log(db, current_user, "DELETE", "webhooks", hook.id, hook.name)
    hook.is_active = False
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


def get_webhook_for_test(hook_id: str, db: Session):
    return db.query(Webhook).filter(Webhook.id == hook_id, Webhook.is_active == True).first()
