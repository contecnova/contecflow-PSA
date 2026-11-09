"""Monedas sin listas fijas (revisión 2026-11).

Medido el 09-11-2026: tres pantallas (Gastos, Ingresos, Subcontratas) tenían su
propia lista de monedas escrita en el código, distinta en cada una, el servidor
otra (`bookings_service.SUPPORTED_CURRENCIES`) y el PDF de factura sus símbolos.
Ahora salen de `SUPPORTED_CURRENCIES` y `CURRENCY_SYMBOLS` (Admin → Locale).
"""
from app.services import invoice_pdf, settings_service
from tests.conftest import auth


def _ajuste(db, clave, valor):
    settings_service.set_runtime_value(db, "locale", clave, valor, "1")
    db.commit()
    settings_service.invalidate_cache()


def test_las_monedas_de_las_pantallas_son_las_del_ajuste_y_la_de_por_defecto_va_siempre(client, db, pm_token):
    _ajuste(db, "SUPPORTED_CURRENCIES", "usd, mxn")
    d = client.get("/api/v1/settings/org-defaults", headers=auth(pm_token)).json()["data"]
    assert d["currencies"] == [d["currency"], "USD", "MXN"]


def test_el_simbolo_del_pdf_sale_del_ajuste_de_la_empresa(db, monkeypatch):
    _ajuste(db, "CURRENCY_SYMBOLS", "EUR:€,CHF:Fr.")
    assert settings_service.simbolos_de_moneda(db, "1") == {"EUR": "€", "CHF": "Fr."}
    vistos = []
    monkeypatch.setattr(invoice_pdf, "_importe", lambda v, etiqueta: vistos.append(etiqueta) or f"{v} {etiqueta}")
    invoice_pdf.generate_invoice_pdf("F-1", None, None, "Cliente", None, None, None,
                                     [{"description": "x", "unit": "h", "quantity": 1, "unit_price": 10, "amount": 10}],
                                     10, 21, 2.1, 12.1, currency="CHF",
                                     simbolo=settings_service.simbolos_de_moneda(db, "1").get("CHF"))
    assert vistos and set(vistos) == {"Fr."}
