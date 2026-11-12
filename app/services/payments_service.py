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
from app.core.errores import ErrorDeDominio
from app.models.billing_reports import Invoice

logger = logging.getLogger(__name__)

# https://docs.stripe.com/webhooks#verify-manually: 5 minutos por defecto.
_TOLERANCIA_S = 300


def _secreto(db: Session) -> Optional[str]:
    from app.services.integration_credentials_service import get_credential
    return get_credential(db, "stripe", "webhook_secret")


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
    secreto = _secreto(db)
    if not secreto:
        # Sin secreto no se puede autenticar: no se procesa nada.
        raise ErrorDeDominio(status_code=503, detail="Webhook de Stripe no configurado (STRIPE_WEBHOOK_SECRET).")
    if not verificar_firma(raw_body, stripe_signature, secreto):
        raise ErrorDeDominio(status_code=400, detail="Firma de Stripe invalida")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise ErrorDeDominio(status_code=400, detail="JSON invalido")

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
    if inv.status != "paid":
        inv.status = "paid"
        inv.paid_date = timeutil.today()
        inv.stripe_paid_at = datetime.now(timezone.utc)
        if data.get("payment_intent"):
            inv.stripe_payment_intent_id = data["payment_intent"]
        db.commit()
        logger.info("Factura %s pagada via webhook de Stripe", invoice_id)
    return {"received": True, "event_type": event_type, "applied": True}
