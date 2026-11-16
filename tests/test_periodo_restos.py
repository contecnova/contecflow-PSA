"""Periodo libre: los restos (16-11-2026).

1. ``/analytics/olap/margin-evolution`` con ``periodo()`` y la agrupación
   común (día/semana/mes; hora no), en DuckDB y en el respaldo.
2. Horizontes de previsión de recursos (``sentido="futuro"``) con
   ``weeks``/``horizon_months`` como alias.
3. ``/bi/data/timesheets``: periodo con la zona de la empresa del token BI (y
   la empresa del token aplicada a los datos).
4. Exportación BI (Excel/PowerPoint): las cifras son las del periodo.
5. ABAC y gobierno de IA: 403 antes que el 422 de un periodo mal formado.
"""
from __future__ import annotations

import io
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.periodo import SIN_HORA, resolver_periodo
from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from tests.conftest import auth

UTC = timezone.utc


def _codigo(r) -> str:
    assert r.status_code == 422, r.text
    return r.json()["detail"]["code"]


def _proyecto(db, code="PLR"):
    p = Project(code=code, name="Periodo restos", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1", is_billable=True, billing_rate=100.0, currency="EUR")
    db.add(p)
    db.commit()
    return p


def _imputar(db, p, dia: date, horas: float, coste: float, org="1", billable=True):
    db.add(Imputation(id=str(uuid.uuid4()), user_id="dev-test-id", project_id=p.id, organization_id=org,
                      date=dia, hours=horas, is_billable=billable, cost_amount=coste))
    db.commit()


# ── 1. margin-evolution ───────────────────────────────────────────────────────
@pytest.fixture
def sin_duckdb(monkeypatch):
    monkeypatch.setattr("app.services.olap.query_engine._try_olap", lambda: None)


def test_margen_por_semana_con_desde_hasta_y_tramos_vacios(client, admin_token, db, sin_duckdb):
    p = _proyecto(db)
    _imputar(db, p, date(2026, 10, 5), 2, 100)    # domingo → semana del lunes 29-09
    _imputar(db, p, date(2026, 10, 6), 3, 150)    # lunes 06-10
    _imputar(db, p, date(2026, 10, 8), 1, 50)     # miércoles 06-10
    _imputar(db, p, date(2026, 11, 20), 9, 999)   # fuera del periodo
    r = client.get("/api/v1/analytics/olap/margin-evolution", headers=auth(admin_token),
                   params={"desde": "2026-09-29", "hasta": "2026-10-20", "granularidad": "week", "tz": "UTC"})
    assert r.status_code == 200, r.text
    puntos = r.json()["items"]
    assert [x["clave"] for x in puntos] == ["2026-09-29T00:00", "2026-10-06T00:00", "2026-10-13T00:00"]
    assert [x["total_cost"] for x in puntos] == [100.0, 200.0, 0.0]
    assert [x["active_projects"] for x in puntos] == [1, 1, 0]
    assert {x["granularidad"] for x in puntos} == {"week"}
    assert [x["month"] for x in puntos] == ["2026-09", "2026-10", "2026-10"]


def test_margen_sin_periodo_son_12_meses_por_mes_y_months_sigue_valiendo(client, admin_token, db, sin_duckdb):
    r = client.get("/api/v1/analytics/olap/margin-evolution", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    puntos = r.json()["items"]
    assert len(puntos) == 12
    assert all(x["granularidad"] == "month" for x in puntos)
    r = client.get("/api/v1/analytics/olap/margin-evolution", headers=auth(admin_token), params={"months": 3})
    assert len(r.json()["items"]) == 3


def test_margen_no_admite_hora(client, admin_token, sin_duckdb):
    r = client.get("/api/v1/analytics/olap/margin-evolution", headers=auth(admin_token),
                   params={"desde": "2026-10-01", "hasta": "2026-10-02", "granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"


def test_margen_duckdb_misma_clave_que_python(monkeypatch):
    """La consulta OLAP agrupa con ``date_trunc`` y da la misma clave que ``Periodo.clave``."""
    duckdb = pytest.importorskip("duckdb")
    from app.services.olap import query_engine as qe

    conn = duckdb.connect(":memory:")
    conn.execute("CREATE TABLE dim_date (date_key INTEGER, date DATE)")
    conn.execute("CREATE TABLE fact_imputations (date_key INTEGER, project_id VARCHAR, cost DOUBLE, organization_id VARCHAR)")
    filas = [(date(2026, 10, 5), "a", 100.0, "1"), (date(2026, 10, 6), "a", 150.0, "1"),
             (date(2026, 10, 8), "b", 50.0, "1"), (date(2026, 10, 7), "a", 777.0, "otra")]
    for d, proj, coste, org in filas:
        k = int(d.strftime("%Y%m%d"))
        conn.execute("INSERT INTO dim_date VALUES (?, ?)", [k, d])
        conn.execute("INSERT INTO fact_imputations VALUES (?, ?, ?, ?)", [k, proj, coste, org])
    monkeypatch.setattr(qe, "_try_olap", lambda: conn)
    p = resolver_periodo(desde="2026-09-29", hasta="2026-10-13", granularidad="week", tz="UTC", admitidas=SIN_HORA)
    puntos = qe.get_margin_evolution("1", p=p)
    assert [x["clave"] for x in puntos] == [p.clave(date(2026, 10, 5)), p.clave(date(2026, 10, 6))]
    assert [x["total_cost"] for x in puntos] == [100.0, 200.0]
    assert [x["active_projects"] for x in puntos] == [1, 2]


# ── 2. Horizontes de previsión ────────────────────────────────────────────────
def test_heatmap_de_prevision_con_desde_hasta_y_weeks_como_alias(client, admin_token):
    r = client.get("/api/v1/resource-forecast/weeks", headers=auth(admin_token),
                   params={"desde": "2027-01-04", "hasta": "2027-02-01", "tz": "UTC"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["from_date"] == "2027-01-04"
    assert d["weeks"] == 4
    assert d["periodo"]["origen"] == "rango"
    r = client.get("/api/v1/resource-forecast/weeks", headers=auth(admin_token), params={"weeks": 6})
    d = r.json()["data"]
    assert d["weeks"] == 6 and d["periodo"]["origen"] == "weeks"


def test_horizonte_de_prevision_days_hacia_delante_y_tope_de_52_semanas(client, admin_token):
    r = client.get("/api/v1/resource-forecast/summary", headers=auth(admin_token), params={"days": 28})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["weeks"] in (4, 5)  # según el día de la semana de hoy
    r = client.get("/api/v1/resource-forecast/summary", headers=auth(admin_token),
                   params={"desde": "2027-01-04", "hasta": "2028-06-01"})
    assert _codigo(r) == "periodo.demasiados_puntos"


def test_detalle_de_persona_y_mapa_de_reservas_con_periodo(client, admin_token):
    r = client.get("/api/v1/resource-forecast/users/dev-test-id", headers=auth(admin_token),
                   params={"desde": "2027-03-01", "hasta": "2027-03-15", "tz": "UTC"})
    assert r.status_code == 200, r.text
    assert [w["week_start"] for w in r.json()["data"]["weeks"]] == ["2027-03-01", "2027-03-08"]
    r = client.get("/api/v1/bookings/heatmap", headers=auth(admin_token),
                   params={"desde": "2027-03-01", "hasta": "2027-03-22", "tz": "UTC"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["start_date"] == "2027-03-01" and d["weeks"] == 3
    r = client.get("/api/v1/bookings/heatmap", headers=auth(admin_token), params={"weeks": 4})
    assert r.json()["data"]["weeks"] == 4


def test_demanda_del_pipeline_respeta_el_horizonte(client, admin_token, db):
    from app.models.activity import ResourceDemandForecast
    from app.models.pipeline import Opportunity, OpportunityStage

    hoy = date.today()
    for code, inicio in (("OPP-CERCA", hoy + timedelta(days=20)), ("OPP-LEJOS", hoy + timedelta(days=400)),
                         ("OPP-SINFECHA", None)):
        o = Opportunity(code=code, name=code, client_name="C", stage=OpportunityStage.proposal, probability=50,
                        expected_start_date=inicio, organization_id="1")
        db.add(o)
        db.flush()
        db.add(ResourceDemandForecast(opportunity_id=o.id, role_or_skill="Dev", hours_required=10, organization_id="1"))
    db.commit()
    nombres = lambda r: sorted(x["name"] for x in r.json()["data"]["opportunity_breakdown"])  # noqa: E731
    r = client.get("/api/v1/activity/pipeline/resource-demand", headers=auth(admin_token), params={"days": 90})
    assert r.status_code == 200, r.text
    assert nombres(r) == ["OPP-CERCA", "OPP-SINFECHA"]
    r = client.get("/api/v1/activity/pipeline/resource-demand", headers=auth(admin_token), params={"horizon_months": 24})
    assert nombres(r) == ["OPP-CERCA", "OPP-LEJOS", "OPP-SINFECHA"]


# ── 3. /bi/data/timesheets ────────────────────────────────────────────────────
def _token_bi(db) -> str:
    from app.services.bi_tokens_service import create_bi_token
    return create_bi_token({"name": "pbi"}, "admin-test-id", db)["token"]


def test_bi_timesheets_periodo_con_zona_de_la_empresa_del_token(client, db):
    from app.models.mfa import Organization

    org = db.get(Organization, "1")
    if org is not None:
        org.timezone = "Pacific/Kiritimati"  # UTC+14: «hoy» y «ayer» difieren de UTC
        db.commit()
    p = _proyecto(db)
    _imputar(db, p, date(2026, 10, 1), 2, 0)
    _imputar(db, p, date(2026, 10, 2), 3, 0, billable=False)
    _imputar(db, p, date(2026, 10, 9), 4, 0)
    _imputar(db, p, date(2026, 10, 2), 50, 0, org="otra-empresa")  # otra empresa: nunca sale
    cab = {"Authorization": f"Bearer {_token_bi(db)}"}

    r = client.get("/api/v1/bi/data/timesheets", headers=cab, params={"desde": "2026-10-01", "hasta": "2026-10-03"})
    assert r.status_code == 200, r.text
    assert sorted(x["hours"] for x in r.json()) == [2, 3]

    r = client.get("/api/v1/bi/data/timesheets", headers=cab,
                   params={"desde": "2026-10-01", "hasta": "2026-10-15", "granularidad": "week"})
    assert r.status_code == 200, r.text
    serie = r.json()
    assert [x["clave"] for x in serie] == ["2026-09-28T00:00", "2026-10-05T00:00", "2026-10-12T00:00"]
    assert [x["hours"] for x in serie] == [5.0, 4.0, 0.0]
    assert [x["billable_hours"] for x in serie] == [2.0, 4.0, 0.0]
    if org is not None:
        assert serie[0]["t"].endswith("+14:00")

    # date_from/date_to (date_to incluido) siguen valiendo
    r = client.get("/api/v1/bi/data/timesheets", headers=cab, params={"date_from": "2026-10-02", "date_to": "2026-10-09"})
    assert sorted(x["hours"] for x in r.json()) == [3, 4]


def test_bi_timesheets_401_antes_que_422_y_sin_hora(client, db):
    r = client.get("/api/v1/bi/data/timesheets", params={"granularidad": "hour"})
    assert r.status_code == 401
    cab = {"Authorization": f"Bearer {_token_bi(db)}"}
    r = client.get("/api/v1/bi/data/timesheets", headers=cab, params={"desde": "2026-10-01", "granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"
    r = client.get("/api/v1/bi/data/timesheets", headers=cab, params={"date_to": "31/10/2026"})
    assert _codigo(r) == "periodo.fecha_invalida"


# ── 4. Exportación BI: las cifras del periodo ─────────────────────────────────
def _facturas_y_tickets(db):
    from app.models.billing_reports import Invoice, InvoiceStatus
    from app.models.service_desk import Ticket, TicketPriority, TicketStatus, TicketType

    for numero, dia, total, estado in (("F-1", date(2026, 1, 10), 1000, InvoiceStatus.sent),
                                       ("F-2", date(2026, 2, 3), 500, InvoiceStatus.paid),
                                       ("F-3", date(2026, 2, 4), 9999, InvoiceStatus.draft),     # borrador: no cuenta
                                       ("F-4", date(2026, 5, 1), 7777, InvoiceStatus.paid)):     # fuera del periodo
        db.add(Invoice(id=str(uuid.uuid4()), number=numero, organization_id="1", client_name="C",
                       issue_date=dia, status=estado, total=total))
    base = datetime(2026, 2, 10, 9, 0, tzinfo=UTC)
    for i, sla in enumerate(("ok", "breached")):
        db.add(Ticket(number=f"BIX-{i}", ticket_type=TicketType.incident, title=f"T{i}", description="x",
                      status=TicketStatus.resolved, priority=TicketPriority.p3_medium, organization_id="1",
                      created_at=base, resolved_at=base + timedelta(hours=4), sla_resolution_status=sla))
    db.commit()


def test_kpis_de_la_exportacion_son_los_del_periodo(db):
    from app.services.bi_export_service import _get_kpi_data

    _facturas_y_tickets(db)
    p = resolver_periodo(desde="2026-01-01", hasta="2026-03-01", tz="UTC", admitidas=("month",), serie=False)
    datos = _get_kpi_data(db, "1", periodo=p)
    assert datos["labels"] == ["01/2026", "02/2026"]
    assert datos["revenue"] == [1000.0, 500.0]
    assert datos["total_revenue_period"] == 1500.0
    assert datos["tickets"] == [0, 2]
    assert datos["sla_compliance"] == [None, 0.5]  # enero sin tickets: sin dato, no 0 %
    assert datos["avg_resolution_hours"] == 4.0


def test_excel_exportado_lleva_las_cifras_del_periodo(client, admin_token, db):
    import openpyxl

    _facturas_y_tickets(db)
    r = client.get("/api/v1/bi/export/excel", headers=auth(admin_token),
                   params={"desde": "2026-01-01", "hasta": "2026-03-01", "tz": "UTC"})
    assert r.status_code == 200, r.text
    libro = openpyxl.load_workbook(io.BytesIO(r.content))
    resumen = {fila[0].value: fila[1].value for fila in libro["Resumen"].iter_rows(min_row=5) if fila[0].value}
    assert resumen[next(k for k in resumen if k.startswith("Ingresos totales"))] == 1500.0
    assert resumen["Tickets gestionados"] == 2
    assert resumen["Cumplimiento SLA promedio"] == "50.0%"
    meses = [fila[0].value for fila in libro["Datos Mensuales"].iter_rows(min_row=2) if fila[0].value not in (None, "TOTAL")]
    assert meses == ["01/2026", "02/2026"]


def test_pptx_exportado_con_periodo(client, admin_token, db):
    pytest.importorskip("pptx")
    _facturas_y_tickets(db)
    r = client.get("/api/v1/bi/export/pptx", headers=auth(admin_token),
                   params={"desde": "2026-01-01", "hasta": "2026-03-01", "tz": "UTC"})
    assert r.status_code == 200, r.text
    from pptx import Presentation
    prs = Presentation(io.BytesIO(r.content))
    textos = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
    assert "50.0%" in textos


# ── 5. 403 antes que 422 ─────────────────────────────────────────────────────
@pytest.mark.parametrize("ruta", [
    "/api/v1/abac/admin/overview",
    "/api/v1/abac/admin/policies/effectiveness",
    "/api/v1/abac/admin/access-patterns",
    "/api/v1/abac/admin/audit-log",
    "/api/v1/abac/admin/audit-log/stats",
    "/api/v1/ai-governance/audit-log",
    "/api/v1/ai-governance/audit-log/stats",
])
@pytest.mark.parametrize("params", [
    {"desde": "no-es-fecha"},
    {"desde": "2026-10-10", "hasta": "2026-10-01"},
    {"granularidad": "lustro"},
    {"days": 99999},
])
def test_sin_permiso_es_403_aunque_el_periodo_este_mal(client, pm_token, admin_token, ruta, params):
    r = client.get(ruta, headers=auth(pm_token), params=params)
    assert r.status_code == 403, (ruta, params, r.status_code, r.text)
    # Con permiso, el mismo periodo sí es un 422.
    r = client.get(ruta, headers=auth(admin_token), params=params)
    assert r.status_code == 422, (ruta, params, r.status_code, r.text)
