"""Webhook de Stripe: marca como pagada la factura cuando Stripe confirma el cobro.

Auditoria 2026-11. Este modulo no lo importaba nadie: tenia un segundo creador
de enlaces de pago (duplicado del de `stripe_service`, que es el que usa
`POST /invoices/{id}/payment-link`) y el unico manejador del webhook, que no
estaba montado en ninguna ruta. Resultado: se generaban enlaces de cobro y la
factura nunca pasaba a pagada. El duplicado se ha borrado y el webhook se monta
en `POST /invoices/stripe/webhook`.

Ademas el manejador antiguo aceptaba el evento SIN firma si faltaba el secreto o
la cabecera: cualquiera podia marcar facturas como pagadas. Ahora la firma es
obligatoria, con tolerancia de tiempo contra reenvios, como pide Stripe.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import timeutil
from app.models.billing_reports import Invoice
from app.core.codigos_de_error import error

logger = logging.getLogger(__name__)

# https://docs.stripe.com/webhooks#verify-manually: 5 minutos por defecto.
_TOLERANCIA_S = 300


def _secreto(db: Session, org_id: Optional[str] = None) -> Optional[str]:
    """El secreto del webhook de la empresa de la factura (A-RZ6: Stripe por empresa)."""
    from app.services.stripe_service import secreto_del_webhook
    return secreto_del_webhook(db, org_id)


def _factura_del_evento(db: Session, raw_body: bytes) -> Optional[Invoice]:
    """La factura que dice el evento, SOLO para elegir con que secreto verificar.

    El cuerpo aun no esta autenticado: de el solo se toma el id para saber de
    que empresa es la cuenta de Stripe; nada se aplica hasta verificar la firma
    con el secreto de esa empresa.
    """
    from app.db.session import sin_filtro_de_tenant
    try:
        evento = json.loads(raw_body)
    except (ValueError, TypeError):
        return None
    objeto = ((evento or {}).get("data") or {}).get("object") or {}
    invoice_id = (objeto.get("metadata") or {}).get("invoice_id")
    if not invoice_id:
        return None
    with sin_filtro_de_tenant(db):
        return db.query(Invoice).filter(Invoice.id == str(invoice_id)).first()


def verificar_firma(raw_body: bytes, cabecera: Optional[str], secreto: str, ahora: Optional[float] = None) -> bool:
    """`Stripe-Signature: t=...,v1=...[,v1=...]` con HMAC-SHA256 de `t.body`."""
    if not cabecera:
        return False
    marca, firmas = None, []
    for parte in cabecera.split(","):
        clave, _, valor = parte.strip().partition("=")
        if clave == "t":
            marca = valor
        elif clave == "v1":
            firmas.append(valor)
    if not marca or not firmas or not marca.isdigit():
        return False
    if abs((ahora if ahora is not None else time.time()) - int(marca)) > _TOLERANCIA_S:
        return False
    esperada = hmac.new(secreto.encode(), marca.encode() + b"." + raw_body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(esperada, f) for f in firmas)


def handle_stripe_webhook(raw_body: bytes, stripe_signature: Optional[str], db: Session) -> dict:
    factura = _factura_del_evento(db, raw_body)
    secreto = _secreto(db, getattr(factura, "organization_id", None))
    if not secreto:
        # Sin secreto no se puede autenticar: no se procesa nada.
        raise error(503, "webhook_secreto_no_configurado", detail="Webhook de Stripe no configurado (STRIPE_WEBHOOK_SECRET).", servicio="Stripe")
    if not verificar_firma(raw_body, stripe_signature, secreto):
        raise error(400, "firma_no_valida", detail="Firma de Stripe invalida")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise error(400, "json_no_valido", detail="JSON invalido")

    event_type = event.get("type", "")
    data = (event.get("data") or {}).get("object") or {}

    # El enlace se crea como Checkout Session (stripe_service); solo cuenta
    # como cobrada si Stripe dice `paid` (los pagos diferidos llegan despues
    # como `checkout.session.async_payment_succeeded`).
    pagada = (
        event_type == "checkout.session.completed" and data.get("payment_status") == "paid"
    ) or event_type == "checkout.session.async_payment_succeeded"
    if not pagada:
        return {"received": True, "event_type": event_type, "applied": False}

    invoice_id = (data.get("metadata") or {}).get("invoice_id")
    if not invoice_id:
        return {"received": True, "event_type": event_type, "applied": False}
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    # La sesion tiene que ser la que se genero para esa factura: el metadata
    # solo no basta para atar el evento a la factura.
    if not inv or (inv.stripe_payment_link_id and inv.stripe_payment_link_id != data.get("id")):
        logger.warning("Stripe webhook: sesion %s no corresponde a la factura %s", data.get("id"), invoice_id)
        return {"received": True, "event_type": event_type, "applied": False}
    # Auditoria 2026-11-22: lo cobrado tiene que ser el total de la factura en
    # su moneda; antes se marcaba pagada con cualquier importe.
    from app.services.stripe_service import to_minor_units
    moneda = (inv.currency or "").lower()
    if (data.get("amount_total") != to_minor_units(inv.total or 0, moneda)
            or (data.get("currency") or "").lower() != moneda):
        logger.warning("Stripe webhook: importe o moneda de la sesion %s no cuadran con la factura %s",
                       data.get("id"), invoice_id)
        return {"received": True, "event_type": event_type, "applied": False}
    # 24-11-2026 (migración 208): ruta anónima (firma de Stripe); lo que creen
    # los escuchadores al marcarla pagada (eventos, ingresos) va a su empresa.
    # `fijar_contexto` y no `publicar_empresa`: un cobro de una empresa ya
    # desactivada se sigue anotando (un 403 haría reintentar a Stripe).
    from app.db.contexto_de_tenant import fijar_contexto
    fijar_contexto(db, inv.organization_id, "stripe: factura sin empresa")
    if inv.status != "paid":
        inv.status = "paid"
        inv.paid_date = timeutil.today()
        inv.stripe_paid_at = datetime.now(timezone.utc)
        if data.get("payment_intent"):
            inv.stripe_payment_intent_id = data["payment_intent"]
        db.commit()
        logger.info("Factura %s pagada via webhook de Stripe", invoice_id)
    return {"received": True, "event_type": event_type, "applied": True}
