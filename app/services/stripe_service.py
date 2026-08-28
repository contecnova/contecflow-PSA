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

import httpx

from app.core.config import settings

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


def is_configured() -> bool:
    """True si hay una clave secreta de Stripe configurada."""
    return bool(settings.STRIPE_SECRET_KEY)


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
) -> dict:
    """Crea una Checkout Session de Stripe para cobrar una factura.

    Devuelve ``{"id", "url", "payment_intent"}``. Lanza ``StripeError`` si Stripe
    no está configurado, el importe no es positivo o la API responde con error.
    Es idempotente por (factura, importe) mediante Idempotency-Key.
    """
    if not is_configured():
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
            auth=(settings.STRIPE_SECRET_KEY or "", ""),
            headers={"Idempotency-Key": f"invoice-checkout-{invoice_id}-{unit_amount}"},
            timeout=20.0,
        )
    except httpx.HTTPError as e:
        raise StripeError(f"No se pudo contactar con Stripe: {e}") from e

    if resp.status_code >= 400:
        try:
            msg = resp.json().get("error", {}).get("message", resp.text)
        except Exception:
            msg = resp.text
        raise StripeError(f"Stripe rechazó la petición ({resp.status_code}): {msg}")

    body = resp.json()
    return {
        "id": body.get("id"),
        "url": body.get("url"),
        "payment_intent": body.get("payment_intent"),
    }
