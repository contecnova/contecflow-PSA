"""Pasarela de pago Stripe — creación de Checkout Sessions para facturas.

Implementación real contra la API REST de Stripe usando httpx (sin añadir el SDK
de stripe como dependencia). Se configura mediante ``STRIPE_SECRET_KEY``. Si la
clave no está presente, la funcionalidad no está disponible y el llamante debe
devolver un error claro (501), en lugar de fingir que "no está configurado".

Se usa Checkout Session (mode=payment) en vez de Payment Links porque permite
importes ad-hoc por factura (``price_data`` en línea) sin crear un Price previo.
La confirmación del pago se realiza vía webhook (``STRIPE_WEBHOOK_SECRET``), que
es una pieza separada del ciclo de cobro.
"""
from __future__ import annotations
import logging

import httpx

from app.core.config import settings
from app.services.settings_service import outbound_http_timeout

_STRIPE_CHECKOUT_URL = "https://api.stripe.com/v1/checkout/sessions"

# Monedas "zero-decimal" de Stripe: el importe NO se multiplica por 100.
# https://docs.stripe.com/currencies#zero-decimal
_ZERO_DECIMAL = frozenset(
    {
        "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga",
        "pyg", "rwf", "ugx", "vnd", "vuv", "xaf", "xof", "xpf",
    }
)


class StripeError(RuntimeError):
    """Error al interactuar con Stripe (no configurado, importe inválido o fallo de API)."""


def clave_secreta(db=None, org_id=None) -> str | None:
    """La clave secreta de Stripe de ESA empresa.

    Auditoria 2026-11-22 (A-RZ6): solo existia `settings.STRIPE_SECRET_KEY`,
    una cuenta para todo el despliegue: los cobros de las facturas de todas
    las empresas entraban en la misma cuenta de Stripe. Ahora, con empresa, la
    credencial `stripe.secret_key` de esa empresa (o su ajuste
    `STRIPE_SECRET_KEY`), sin caer a la global; sin empresa (plataforma), la
    global del entorno.
    """
    if org_id and db is not None:
        from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
        return secreto_propio_de_la_organizacion(db, "stripe", "secret_key", "STRIPE_SECRET_KEY", org_id)
    return settings.STRIPE_SECRET_KEY or None


def secreto_del_webhook(db=None, org_id=None) -> str | None:
    """El secreto de firma del webhook de Stripe de ESA empresa (como `clave_secreta`)."""
    if org_id and db is not None:
        from app.services.integration_credentials_service import secreto_propio_de_la_organizacion
        return secreto_propio_de_la_organizacion(db, "stripe", "webhook_secret", "STRIPE_WEBHOOK_SECRET", org_id)
    return getattr(settings, "STRIPE_WEBHOOK_SECRET", None) or None


def is_configured(db=None, org_id=None) -> bool:
    """True si hay una clave secreta de Stripe configurada (la de la empresa, si se indica)."""
    return bool(clave_secreta(db, org_id))


def to_minor_units(amount: float, currency: str) -> int:
    """Convierte un importe en unidades menores (céntimos) respetando zero-decimal."""
    if currency.lower() in _ZERO_DECIMAL:
        return int(round(float(amount)))
    return int(round(float(amount) * 100))


def create_checkout_session(
    *,
    invoice_id: str,
    invoice_number: str,
    amount: float,
    currency: str,
    success_url: str,
    cancel_url: str,
    customer_email: str | None = None,
    db=None,
    org_id=None,
) -> dict:
    """Crea una Checkout Session de Stripe para cobrar una factura.

    Devuelve ``{"id", "url", "payment_intent"}``. Lanza ``StripeError`` si Stripe
    no está configurado, el importe no es positivo o la API responde con error.
    Es idempotente por (factura, importe) mediante Idempotency-Key.
    """
    clave = clave_secreta(db, org_id)
    if not clave:
        raise StripeError("Stripe no está configurado (define STRIPE_SECRET_KEY).")

    unit_amount = to_minor_units(amount, currency)
    if unit_amount <= 0:
        raise StripeError("El importe de la factura debe ser mayor que cero para poder cobrarla.")

    form = {
        "mode": "payment",
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": str(invoice_id),
        "metadata[invoice_id]": str(invoice_id),
        "metadata[invoice_number]": str(invoice_number),
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency.lower(),
        "line_items[0][price_data][unit_amount]": str(unit_amount),
        "line_items[0][price_data][product_data][name]": f"Factura {invoice_number}",
    }
    if customer_email:
        form["customer_email"] = customer_email

    try:
        resp = httpx.post(
            _STRIPE_CHECKOUT_URL,
            data=form,
            auth=(clave, ""),
            headers={"Idempotency-Key": f"invoice-checkout-{invoice_id}-{unit_amount}"},
            timeout=outbound_http_timeout(default=20.0),
        )
    except httpx.HTTPError as e:
        raise StripeError(f"No se pudo contactar con Stripe: {e}") from e

    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            logging.getLogger(__name__).warning("create_checkout_session: excepcion ignorada", exc_info=True)
            msg = resp.text
        raise StripeError(f"Stripe rechazó la petición ({resp.status_code}): {msg}")

    body = resp.json()
    return {
        "id": body.get("id"),
        "url": body.get("url"),
        "payment_intent": body.get("payment_intent"),
    }


def sesion_reutilizable(session_id: str | None, *, amount: float, currency: str,
                        db=None, org_id=None) -> bool:
    """¿Sigue abierta la Checkout Session y cobra este mismo importe?

    Auditoria 2026-11-22 (A-RZ6): el enlace guardado en la factura se
    reutilizaba siempre, aunque la sesion de Stripe caduca a las 24 h y aunque
    el total de la factura hubiera cambiado: el cliente pagaba otro importe o
    no podia pagar. Ante cualquier duda (sin id, error de red, otro importe o
    moneda), no se reutiliza y se crea una sesion nueva.
    """
    clave = clave_secreta(db, org_id)
    if not session_id or not clave:
        return False
    try:
        resp = httpx.get(f"{_STRIPE_CHECKOUT_URL}/{session_id}", auth=(clave, ""),
                         timeout=outbound_http_timeout(default=20.0))
    except httpx.HTTPError:
        logging.getLogger(__name__).warning("Stripe: no se pudo consultar la sesion %s", session_id, exc_info=True)
        return False
    if resp.status_code >= 400:
        return False
    s = resp.json()
    return (s.get("status") == "open"
            and s.get("amount_total") == to_minor_units(amount, currency)
            and (s.get("currency") or "").lower() == (currency or "").lower())
