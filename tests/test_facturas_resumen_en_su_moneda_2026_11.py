"""El resumen de facturas suma en la moneda de la empresa (revisión 2026-11).

Medido antes: sumaba los importes tal cual, en la moneda de cada factura, y la
pantalla les ponía un € fijo.
"""
from __future__ import annotations

from datetime import date

from app.models.billing_reports import Invoice
from app.models.bookings import ExchangeRate
from tests.conftest import auth


def test_EL_HALLAZGO_convierte_y_dice_lo_que_no_puede(client, db, admin_token):
    db.add(ExchangeRate(from_currency="USD", to_currency="EUR", rate=0.9, effective_date=date(2026, 1, 1)))
    for n, (moneda, total, estado) in enumerate((("EUR", 1000, "paid"), ("USD", 1100, "sent"), ("GBP", 500, "sent"))):
        db.add(Invoice(number=f"INV-T-{n}", currency=moneda, total=total, subtotal=total, status=estado,
                       issue_date=date(2026, 3, 1), organization_id="1"))
    db.commit()
    d = client.get("/api/v1/invoices/summary", headers=auth(admin_token)).json()["data"]
    assert d["currency"] == "EUR"
    assert (d["total_invoiced"], d["total_paid"], d["total_pending"]) == (1990.0, 1000.0, 990.0)
    assert d["sin_tipo_de_cambio"] == {"GBP": 500.0}


def test_EL_HALLAZGO_un_empleado_no_ve_la_facturacion(client, dev_token):
    assert client.get("/api/v1/invoices/summary", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/invoices", headers=auth(dev_token)).status_code == 403
