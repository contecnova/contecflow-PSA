"""Enlaces de pago y webhook de Stripe.

Auditoria 2026-08 (hallazgo 22). Este codigo vivia en `v238_service.py`, un
fichero de 784 lineas nombrado por NUMERO DE VERSION y con SEIS dominios sin
relacion dentro: etapas del embudo, planificacion de capacidad, analitica
ad-hoc, pagos, instantaneas de colaboracion y SCIM.

Agrupar por version en lugar de por dominio tiene un coste concreto: nadie sabe
donde buscar, y un fichero con seis dominios no tiene revisor natural — quien
entra a tocar los pagos no revisa la analitica que hay 300 lineas mas abajo. Fue
esa misma mala ubicacion la que oculto el P0 numero 1 de la auditoria, escondido
en un fichero llamado `mfa_service`.

El reparto se pudo hacer mecanicamente porque los seis dominios nunca estuvieron
acoplados, solo apilados: se comprobo por AST que no habia ni una llamada entre
grupos ni un solo ciclo. Los cuerpos se movieron verbatim.
"""

from datetime import datetime, timezone
from typing import Optional
import json
import logging
import hmac
import hashlib
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.config import settings
from app.models.billing_reports import Invoice
from app.core import timeutil

logger = logging.getLogger(__name__)


def create_payment_link_record(invoice_id: str, db: Session) -> dict:
    from app.services.integration_credentials_service import get_credential
    org_id = None  # Stripe creds resolved at org-NULL scope unless caller threads through
    stripe_secret = get_credential(db, "stripe", "secret_key", org_id=org_id)
    if not stripe_secret:
        raise HTTPException(
            status_code=503,
            detail="Stripe no configurado. Edita en Settings → Sistema → Credenciales → Stripe, o define STRIPE_SECRET_KEY en .env."
        )
    inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if inv.status not in ("sent", "overdue"):
        raise HTTPException(status_code=400, detail=f"Invoice status must be 'sent' or 'overdue', got '{inv.status}'")
    if not inv.total or inv.total <= 0:
        raise HTTPException(status_code=400, detail="Invoice total must be greater than 0")

    if inv.stripe_payment_link_url:
        return {
            "invoice_id": invoice_id,
            "payment_link_url": inv.stripe_payment_link_url,
            "stripe_payment_link_id": inv.stripe_payment_link_id,
            "already_existed": True,
        }

    import httpx
    amount_cents = int(inv.total * 100)
    currency = (inv.currency or settings.DEFAULT_CURRENCY).lower()

    try:
        from app.services.settings_service import outbound_http_timeout
        with httpx.Client(timeout=outbound_http_timeout(db, default=10.0)) as client:
            price_resp = client.post(
                "https://api.stripe.com/v1/prices",
                auth=(stripe_secret, ""),
                data={
                    "unit_amount": str(amount_cents),
                    "currency": currency,
                    "product_data[name]": f"Factura {inv.number}",
                },
            )
            if price_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Stripe price creation failed: {price_resp.text}")
            price_id = price_resp.json()["id"]

            link_resp = client.post(
                "https://api.stripe.com/v1/payment_links",
                auth=(stripe_secret, ""),
                data={
                    "line_items[0][price]": price_id,
                    "line_items[0][quantity]": "1",
                    "metadata[invoice_id]": invoice_id,
                    "metadata[invoice_number]": inv.number,
                    "after_completion[type]": "redirect",
                    "after_completion[redirect][url]": f"{settings.FRONTEND_URL}/invoices?paid={invoice_id}",
                },
            )
            if link_resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Stripe payment link creation failed: {link_resp.text}")
            link_data = link_resp.json()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Stripe API error: {str(e)}")

    inv.stripe_payment_link_id = link_data["id"]
    inv.stripe_payment_link_url = link_data["url"]
    db.commit()

    return {
        "invoice_id": invoice_id,
        "invoice_number": inv.number,
        "payment_link_url": link_data["url"],
        "stripe_payment_link_id": link_data["id"],
        "amount": inv.total,
        "currency": currency,
    }


def handle_stripe_webhook(raw_body: bytes, stripe_signature: Optional[str], db: Session) -> dict:
    from app.services.integration_credentials_service import get_credential
    webhook_secret = get_credential(db, "stripe", "webhook_secret")

    if webhook_secret and stripe_signature:
        try:
            parts = {p.split("=")[0]: p.split("=")[1] for p in stripe_signature.split(",")}
            timestamp = parts.get("t", "")
            sig = parts.get("v1", "")
            signed_payload = f"{timestamp}.{raw_body.decode('utf-8')}"
            expected = hmac.new(
                webhook_secret.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(expected, sig):
                raise HTTPException(status_code=400, detail="Invalid Stripe signature")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=400, detail="Signature verification failed")

    try:
        event = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})

    if event_type in ("checkout.session.completed", "payment_intent.succeeded"):
        invoice_id = (data.get("metadata") or {}).get("invoice_id")
        if invoice_id:
            inv = db.query(Invoice).filter(Invoice.id == invoice_id).first()
            if inv and inv.status != "paid":
                inv.status = "paid"
                inv.paid_date = timeutil.today()
                inv.stripe_paid_at = datetime.now(timezone.utc)
                if data.get("payment_intent"):
                    inv.stripe_payment_intent_id = data["payment_intent"]
                db.commit()
                logger.info(f"Invoice {invoice_id} marked as paid via Stripe webhook")

    return {"received": True, "event_type": event_type}
