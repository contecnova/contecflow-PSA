"""Las 133 métricas, comparadas contra la versión anterior al refactor.

Auditoría 2026-08 (P3-18). Cuatro resolutores de `bi_smart_alerts/metrics.py`
se reescribieron como tablas de despacho: perfil de coste (27), facturación (24),
tickets (18) y hojas de horas (13). Los tests por métrica
(`test_bi_cost_profile_metrics`, `test_bi_invoice_metrics`,
`test_bi_ticket_metrics`) fijan los valores calculados a mano, que es la
verificación que importa.

Esto es la otra mitad: una comparación de las **133** claves del catálogo contra
el fichero tal como estaba antes de tocarlo, sobre los mismos datos. Cubre las
claves que ningún test por métrica mira, y sirve de red para los refactores que
queden en este fichero.

La copia anterior vive en `tests/_fixtures/metrics_pre_refactor.py` y se carga
como módulo aparte. No es código de producción y no se mantiene: es una foto.

**Se esperan exactamente dos diferencias**, las dos deliberadas y documentadas:

  · `invoices_draft_count` y las otras seis de facturación cuando hay una
    factura con `due_date` nulo — antes desaparecía de las siete métricas
    (ver `test_bi_invoice_metrics.test_una_factura_sin_vencimiento_no_desaparece`);
  · `cost_profile_total_annual` sobre base sin perfiles devolvía `int 0` en vez
    de `0.0`, la única métrica del catálogo con tipo mixto en la serie.

Cualquier otra diferencia es una regresión y este test la nombra.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services.bi_smart_alerts.constants import SUPPORTED_METRICS
from app.services.bi_smart_alerts.metrics import _fetch_metric_series

FOTO = pathlib.Path(__file__).parent / "_fixtures" / "metrics_pre_refactor.py"

# Las dos diferencias esperadas, con su razón.
DIFERENCIAS_ESPERADAS = {
    "cost_profile_total_annual":
        "antes devolvía int 0 sobre base vacía; ahora 0.0 como el resto",
    "invoice_overdue_count":  "facturas sin due_date antes se descartaban",
    "invoice_overdue_amount": "facturas sin due_date antes se descartaban",
    "invoices_draft_count":   "facturas sin due_date antes se descartaban",
    "invoices_sent_count":    "facturas sin due_date antes se descartaban",
    "invoices_paid_count":    "facturas sin due_date antes se descartaban",
    "invoices_paid_total":    "facturas sin due_date antes se descartaban",
    "invoice_days_to_pay_avg": "facturas sin due_date antes se descartaban",
}


@pytest.fixture(scope="module")
def anterior():
    """El módulo tal como estaba antes del refactor, cargado aparte."""
    if not FOTO.exists():
        pytest.skip(f"falta la foto previa en {FOTO}")
    nombre = "_metrics_pre_refactor"
    spec = importlib.util.spec_from_file_location(nombre, FOTO)
    modulo = importlib.util.module_from_spec(spec)
    # Registrarlo en `sys.modules` ANTES de ejecutarlo no es opcional: el módulo
    # define `@dataclass`, y `dataclasses` resuelve las anotaciones mirando
    # `sys.modules[cls.__module__]`. Sin registrar, eso es None y el decorador
    # revienta con un AttributeError que no dice nada del problema real.
    sys.modules[nombre] = modulo
    try:
        spec.loader.exec_module(modulo)
    except Exception:
        sys.modules.pop(nombre, None)
        raise
    return modulo


@pytest.fixture
def datos(db):
    """Datos en los cuatro dominios tocados, para que las series no salgan a cero.

    Una comparación sobre base vacía sería vacua: todas las métricas darían 0.0
    en las dos versiones y el test pasaría sin medir nada.
    """
    from app.models.billing_reports import Invoice, InvoiceStatus
    from app.models.financial import Timesheet
    from app.models.service_desk import Ticket
    from app.models.user import User, UserRole, UserStatus
    from app.models.user_cost import CountryEmployerCost, UserCostProfile

    anio = date.today().year

    # Perfiles de coste
    for n, (por_hora, anual, pais, depto) in enumerate([
        (50.0, 85_000.0, "ES", "Ingeniería"),
        (70.0, 119_000.0, "ES", "Ingeniería"),
        (30.0, 51_000.0, "PT", "Ventas"),
    ]):
        uid = f"eq-u{n}-{uuid.uuid4().hex[:8]}"
        db.add(User(
            id=uid, username=f"eq_{uid}", email=f"{uid}@x.com",
            full_name=f"Eq {n}", role=UserRole.employee, status=UserStatus.active,
            is_active=True, hashed_password="x", department=depto,
            hourly_rate=0.0, weekly_capacity_hours=40.0, currency="EUR",
            organization_id="1",
        ))
        db.flush()
        db.add(UserCostProfile(
            id=str(uuid.uuid4()), user_id=uid, organization_id="1",
            country_code=pais, currency="EUR",
            gross_annual_salary=anual / 1.32, employer_cost_pct=0.32,
            extra_annual_costs=0.0, productive_hours_year=anual / por_hora,
            total_annual_cost=anual, cost_per_hour=por_hora,
            valid_from=date(2000, 1, 1), valid_to=None,
        ))
    for codigo, nombre, pct in (("ES", "España", 0.32), ("PT", "Portugal", 0.24)):
        db.add(CountryEmployerCost(
            id=str(uuid.uuid4()), organization_id="1", country_code=codigo,
            country_name=nombre, currency="EUR", employer_cost_pct=pct,
            productive_hours_year=1700,
        ))

    # Facturas, incluida UNA SIN VENCIMIENTO — es la que provoca la diferencia
    # esperada y la razón de que este fixture no sea neutro.
    for n, (estado, emision, vence, pago, total) in enumerate([
        (InvoiceStatus.overdue, date(anio, 1, 10), date(anio, 2, 10), None, 1_000),
        (InvoiceStatus.draft, date(anio, 2, 5), date(anio, 3, 5), None, 8_000),
        (InvoiceStatus.paid, date(anio, 1, 5), date(anio, 2, 5), date(anio, 1, 25), 32_000),
        (InvoiceStatus.draft, date(anio, 6, 10), None, None, 5_000),
    ]):
        db.add(Invoice(
            id=str(uuid.uuid4()), organization_id="1",
            number=f"EQ-{n}-{uuid.uuid4().hex[:6]}", client_name="Cliente",
            subtotal=total, tax_rate=0.0, tax_amount=0.0, total=total,
            currency="EUR", issue_date=emision, due_date=vence,
            paid_date=pago, status=estado,
        ))

    # Tickets
    for estado, pri, resp, resol, csat in [
        ("new", "p1_critical", 10, None, None),
        ("in_progress", "p2_high", 30, None, None),
        ("resolved", "p3_medium", 15, 120, 5),
        ("closed", "p3_medium", 20, 300, 4),
        ("cancelled", "p4_low", None, None, None),
    ]:
        db.add(Ticket(
            id=str(uuid.uuid4()), organization_id="1",
            number=f"EQ-{uuid.uuid4().hex[:8]}", title="Eq", description="—",
            ticket_type="incident", status=estado, priority=pri,
            created_at=datetime(anio, 4, 10, 12, 0, tzinfo=timezone.utc),
            first_response_minutes=resp, resolution_minutes=resol,
            csat_score=csat, sla_response_breached=(resp or 0) > 25,
            sla_resolution_breached=(resol or 0) > 200, auto_resolved=csat == 5,
            time_spent_minutes=(resol or 0) // 2 or None,
        ))

    # Hojas de horas
    for n, (estado, horas, coste) in enumerate([
        ("draft", 38.0, 1_900.0),
        ("submitted", 40.0, 2_000.0),
        ("rejected", 12.0, 600.0),
        ("approved", 40.0, 2_000.0),
    ]):
        inicio = date(anio, 4, 6) + timedelta(days=7 * n)
        db.add(Timesheet(
            id=str(uuid.uuid4()), organization_id="1", user_id="admin-test-id",
            week_start=inicio, week_end=inicio + timedelta(days=6),
            status=estado, total_hours=horas, total_cost=coste,
        ))

    db.commit()


def test_las_133_claves_dan_lo_mismo_que_antes(db, datos, anterior):
    """La comparación completa. Nombra cada diferencia con sus dos series."""
    diferencias = {}
    for clave in sorted(SUPPORTED_METRICS):
        antes = anterior._fetch_metric_series(db, clave, "1")
        ahora = _fetch_metric_series(db, clave, "1")
        if antes != ahora:
            diferencias[clave] = (antes, ahora)

    inesperadas = {
        k: v for k, v in diferencias.items() if k not in DIFERENCIAS_ESPERADAS
    }
    assert not inesperadas, "\n".join(
        f"{k}:\n  antes: {a}\n  ahora: {b}" for k, (a, b) in inesperadas.items()
    )


def test_la_correccion_de_facturacion_se_produce_de_verdad(db, datos, anterior):
    """Que la lista de excepciones no sea una coartada.

    Si la corrección del vencimiento nulo se deshiciera, su clave dejaría de
    diferir y `DIFERENCIAS_ESPERADAS` la seguiría excusando en silencio. Aquí se
    exige que la diferencia **ocurra**.

    Sólo se comprueba la de facturación: la del `int 0` de
    `cost_profile_total_annual` no se ve con estos datos porque el fixture SÍ
    tiene perfiles de coste, y con perfiles la suma ya es float en las dos
    versiones. Esa se comprueba donde se puede ver, sobre base sin perfiles, en
    `test_bi_cost_profile_metrics.test_sin_ningun_perfil_todo_vale_cero_y_no_lanza`.
    """
    antes = anterior._fetch_metric_series(db, "invoices_draft_count", "1")
    ahora = _fetch_metric_series(db, "invoices_draft_count", "1")
    assert antes != ahora, (
        "invoices_draft_count ya no difiere de la versión anterior: la "
        f"corrección del vencimiento nulo puede haberse deshecho ({ahora})"
    )
    assert sum(ahora) > sum(antes), (
        "la corrección sólo puede AÑADIR facturas que antes se descartaban"
    )


def test_la_diferencia_de_tipo_solo_aparece_sin_perfiles(db, anterior):
    """La otra corrección, comprobada donde se ve: sin perfiles de coste.

    `round(sum([]), 2)` es `int 0`, no `0.0`. Era la única métrica del catálogo
    con tipo mixto en la serie.
    """
    antes = anterior._fetch_metric_series(db, "cost_profile_total_annual", "1")
    ahora = _fetch_metric_series(db, "cost_profile_total_annual", "1")
    assert all(isinstance(v, int) and not isinstance(v, bool) for v in antes), (
        f"la foto previa ya no devuelve enteros: {antes[:3]}"
    )
    assert all(isinstance(v, float) for v in ahora), f"{ahora[:3]}"


def test_la_foto_previa_es_la_de_verdad(anterior):
    """Guarda contra el fallo que haría inútil todo lo de arriba: que la foto se
    actualizara con el código nuevo y se comparara consigo misma."""
    fuente = FOTO.read_text(encoding="utf-8")
    assert "_CALCULOS_DE_COSTE" not in fuente, "la foto tiene ya el refactor"
    assert "_METRICAS_DE_FACTURA" not in fuente, "la foto tiene ya el refactor"
    assert fuente.count('if metric_key == "invoice') == 7, (
        "la foto no tiene las 7 ramas de facturación originales"
    )
