"""Las 7 métricas de facturación, con valores calculados a mano.

Auditoría 2026-08 (P3-18). `_serie_invoice` era complejidad **24**: siete ramas
sobre `metric_key`, y seis de ellas el mismo bucle copiado cambiando sólo tres
cosas — el estado que cuenta, de qué campo sale la fecha, y si suma el importe o
cuenta facturas.

Además del refactor, este fichero fija un defecto que se encontró al escribirlo
y que está en `test_una_factura_sin_vencimiento_no_desaparece`: la consulta
compartida filtraba `due_date >= start_date`, y `due_date` es **nullable** —
tanto el esquema (`app/models/billing_reports.py`) como la API
(`InvoiceCreate.due_date: Optional[date] = None`) aceptan una factura sin fecha
de vencimiento. Esa factura quedaba fuera de las **siete** métricas, incluidas
las cuatro que ni usan el vencimiento porque van por emisión o por pago.

Es el patrón central de la auditoría otra vez: no fallaba, devolvía cero.

Los datos (todas con `total` distinto para que un cruce de métricas se note):

    factura   estado    emisión      vencim.      pago         total
    F1        overdue   2026-01-10   2026-02-10   —              1.000
    F2        overdue   2026-01-15   2026-02-20   —              2.000
    F3        overdue   2026-03-01   2026-04-01   —              4.000
    F4        draft     2026-02-05   2026-03-05   —              8.000
    F5        sent      2026-02-07   2026-03-07   —             16.000
    F6        paid      2026-01-05   2026-02-05   2026-01-25    32.000
    F7        paid      2026-01-08   2026-02-08   2026-02-18    64.000

La rejilla de meses es la del año en curso cuando no hay imputaciones, así que
2026 entero. Cada aserción mira el mes concreto que le toca, no la serie plana.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.billing_reports import Invoice, InvoiceStatus
from app.services.bi_smart_alerts.metrics import _fetch_metric_series

ANIO = 2026


def _factura(db, num, estado, emision, vencimiento, pago, total):
    db.add(Invoice(
        id=str(uuid.uuid4()),
        organization_id="1",
        number=f"INV-TEST-{num}-{uuid.uuid4().hex[:6]}",
        client_name="Cliente de prueba",
        subtotal=total,
        tax_rate=0.0,
        tax_amount=0.0,
        total=total,
        currency="EUR",
        issue_date=emision,
        due_date=vencimiento,
        paid_date=pago,
        status=estado,
    ))


@pytest.fixture
def facturas(db):
    _factura(db, 1, InvoiceStatus.overdue, date(ANIO, 1, 10), date(ANIO, 2, 10), None, 1_000)
    _factura(db, 2, InvoiceStatus.overdue, date(ANIO, 1, 15), date(ANIO, 2, 20), None, 2_000)
    _factura(db, 3, InvoiceStatus.overdue, date(ANIO, 3, 1), date(ANIO, 4, 1), None, 4_000)
    _factura(db, 4, InvoiceStatus.draft, date(ANIO, 2, 5), date(ANIO, 3, 5), None, 8_000)
    _factura(db, 5, InvoiceStatus.sent, date(ANIO, 2, 7), date(ANIO, 3, 7), None, 16_000)
    _factura(db, 6, InvoiceStatus.paid, date(ANIO, 1, 5), date(ANIO, 2, 5),
             date(ANIO, 1, 25), 32_000)
    _factura(db, 7, InvoiceStatus.paid, date(ANIO, 1, 8), date(ANIO, 2, 8),
             date(ANIO, 2, 18), 64_000)
    db.commit()


def _por_mes(db, clave: str) -> dict[str, float]:
    """La serie indexada por mes, para poder afirmar mes a mes."""
    from app.services.bi_smart_alerts.metrics import _construir_contexto
    ctx = _construir_contexto(db, clave, "1")
    serie = _fetch_metric_series(db, clave, "1")
    assert serie is not None and len(serie) == len(ctx.series), clave
    return {m["month"]: v for m, v in zip(ctx.series, serie, strict=True)}


# ── Vencidas: van por fecha de VENCIMIENTO ────────────────────────────────────

def test_vencidas_se_cuentan_en_el_mes_de_vencimiento(db, facturas):
    """F1 y F2 vencen en febrero, F3 en abril. Ninguna cae en enero, que es
    cuando se emitieron: es la distinción que separa esta métrica de las de
    borradores y enviadas."""
    v = _por_mes(db, "invoice_overdue_count")
    assert v[f"{ANIO}-02"] == 2.0
    assert v[f"{ANIO}-04"] == 1.0
    assert v[f"{ANIO}-01"] == 0.0


def test_el_importe_vencido_suma_los_totales(db, facturas):
    v = _por_mes(db, "invoice_overdue_amount")
    assert v[f"{ANIO}-02"] == 3_000.0     # 1.000 + 2.000
    assert v[f"{ANIO}-04"] == 4_000.0


# ── Borradores y enviadas: van por fecha de EMISIÓN ───────────────────────────

def test_los_borradores_van_por_mes_de_emision(db, facturas):
    v = _por_mes(db, "invoices_draft_count")
    assert v[f"{ANIO}-02"] == 1.0          # F4, emitida el 5 de febrero
    assert v[f"{ANIO}-03"] == 0.0          # su vencimiento, que no cuenta aquí


def test_las_enviadas_van_por_mes_de_emision(db, facturas):
    v = _por_mes(db, "invoices_sent_count")
    assert v[f"{ANIO}-02"] == 1.0          # F5
    assert v[f"{ANIO}-03"] == 0.0


def test_borradores_y_enviadas_no_se_confunden(db, facturas):
    """Las dos van por emisión y las dos caen en febrero; lo único que las
    separa es el estado. Si el estado se cruzara, ambas darían 2."""
    assert _por_mes(db, "invoices_draft_count")[f"{ANIO}-02"] == 1.0
    assert _por_mes(db, "invoices_sent_count")[f"{ANIO}-02"] == 1.0


# ── Cobradas: van por fecha de PAGO, con la de emisión como respaldo ──────────

def test_las_cobradas_van_por_mes_de_pago(db, facturas):
    """F6 se emitió en enero y se cobró en enero; F7 se emitió en enero y se
    cobró en febrero. Van a meses distintos, y eso demuestra que manda la fecha
    de pago y no la de emisión."""
    v = _por_mes(db, "invoices_paid_count")
    assert v[f"{ANIO}-01"] == 1.0     # F6
    assert v[f"{ANIO}-02"] == 1.0     # F7


def test_el_importe_cobrado_va_al_mes_de_pago(db, facturas):
    v = _por_mes(db, "invoices_paid_total")
    assert v[f"{ANIO}-01"] == 32_000.0
    assert v[f"{ANIO}-02"] == 64_000.0


def test_una_cobrada_sin_fecha_de_pago_cae_en_su_mes_de_emision(db):
    """El respaldo `paid or iss`. Una factura marcada como cobrada sin fecha de
    pago sigue siendo dinero que entró: se imputa al mes de emisión antes que
    perderla de la serie."""
    _factura(db, 90, InvoiceStatus.paid, date(ANIO, 5, 3), date(ANIO, 6, 3), None, 7_000)
    db.commit()
    assert _por_mes(db, "invoices_paid_total")[f"{ANIO}-05"] == 7_000.0


# ── Días hasta el cobro: media, no acumulación ────────────────────────────────

def test_los_dias_hasta_el_cobro_se_promedian_en_el_mes_de_emision(db, facturas):
    """F6: 5 → 25 de enero = 20 días. F7: 8 de enero → 18 de febrero = 41 días.
    Las dos se emitieron en enero, así que la media de enero es (20 + 41) / 2 =
    30,5. Se imputa al mes de EMISIÓN a propósito: la pregunta que responde es
    «lo que facturé en enero, cuánto tardó en cobrarse»."""
    v = _por_mes(db, "invoice_days_to_pay_avg")
    assert v[f"{ANIO}-01"] == pytest.approx(30.5)


def test_un_mes_sin_cobros_da_cero_y_no_divide_por_cero(db, facturas):
    v = _por_mes(db, "invoice_days_to_pay_avg")
    assert v[f"{ANIO}-07"] == 0.0


# ── El defecto del vencimiento nulo ───────────────────────────────────────────

def test_una_factura_sin_vencimiento_no_desaparece(db):
    """El defecto que se encontró escribiendo estos tests.

    La consulta compartida filtraba `due_date >= start_date`. Con `due_date`
    nulo la comparación es NULL en SQL —ni verdadera ni falsa— así que la fila
    se descartaba. Y `due_date` es nullable en el modelo y opcional en la API:
    una factura recién creada sin vencimiento es un caso normal, no un dato
    corrupto.

    El resultado era que esa factura no aparecía en NINGUNA de las siete
    métricas, ni en las que van por emisión o por pago y no necesitan el
    vencimiento para nada. Sin fallar: devolvía cero.

    Este test falla contra el código anterior al arreglo. Es su razón de ser.
    """
    _factura(db, 91, InvoiceStatus.draft, date(ANIO, 6, 10), None, None, 5_000)
    _factura(db, 92, InvoiceStatus.paid, date(ANIO, 6, 12), None,
             date(ANIO, 6, 20), 9_000)
    db.commit()

    assert _por_mes(db, "invoices_draft_count")[f"{ANIO}-06"] == 1.0, (
        "un borrador sin vencimiento no aparece en el recuento de borradores"
    )
    assert _por_mes(db, "invoices_paid_total")[f"{ANIO}-06"] == 9_000.0, (
        "una factura cobrada sin vencimiento no aparece en el importe cobrado"
    )


def test_el_vencimiento_nulo_no_cuela_en_las_metricas_de_vencidas(db):
    """La otra mitad del arreglo: incluir las filas de vencimiento nulo no puede
    meterlas en las métricas que agrupan POR vencimiento, porque no tienen mes
    al que ir. El filtro de fecha de cada métrica sigue descartándolas."""
    _factura(db, 93, InvoiceStatus.overdue, date(ANIO, 6, 10), None, None, 5_000)
    db.commit()
    serie = _fetch_metric_series(db, "invoice_overdue_count", "1")
    assert sum(serie) == 0.0, "una vencida sin fecha de vencimiento se ha colado"


# ── Que el fichero no se quede atrás ──────────────────────────────────────────

def test_las_7_claves_de_facturacion_estan_cubiertas():
    from app.services.bi_smart_alerts.metrics import CLAVES_DE_FACTURA

    probadas = {
        "invoice_overdue_count", "invoice_overdue_amount",
        "invoices_draft_count", "invoices_sent_count",
        "invoices_paid_count", "invoices_paid_total",
        "invoice_days_to_pay_avg",
    }
    assert probadas == set(CLAVES_DE_FACTURA), (
        f"sin probar: {set(CLAVES_DE_FACTURA) - probadas}; "
        f"sobran: {probadas - set(CLAVES_DE_FACTURA)}"
    )


def test_las_claves_cableadas_y_las_atendidas_coinciden():
    """La propiedad que evita que el conjunto y la tabla se separen.

    `_serie_invoice` devuelve `None` si la clave no está en `CLAVES_DE_FACTURA`,
    y el despachador interpreta `None` como «esta métrica no me toca». Así que
    una clave cableada a `_serie_invoice` pero ausente del conjunto no fallaría:
    se quedaría sin serie en silencio. Igual que el caso del vencimiento nulo, e
    igual que el endpoint `/analytics/adhoc` que la auditoría encontró muerto.
    """
    from app.services.bi_smart_alerts.metrics import (
        CLAVES_DE_FACTURA, _RESOLUTORES, _serie_invoice,
    )

    cableadas = {k for k, v in _RESOLUTORES.items() if v is _serie_invoice}
    assert cableadas == set(CLAVES_DE_FACTURA), (
        f"cableadas sin atender: {cableadas - set(CLAVES_DE_FACTURA)}; "
        f"atendidas sin cablear: {set(CLAVES_DE_FACTURA) - cableadas}"
    )
