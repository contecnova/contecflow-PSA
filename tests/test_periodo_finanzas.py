"""Periodo libre en los informes de finanzas, BI y cuadros de mando (16-11-2026).

Cada informe migrado acepta `desde`/`hasta`/`granularidad`/`tz` (ver
`app/core/periodo.py`) y sigue aceptando su parámetro histórico (`days`,
`days_back`, `period_days`, `date_from`/`date_to`, `period=daily|weekly|monthly`).
Los que se alimentan de datos por día de calendario rechazan `granularidad=hour`
con un código traducible.
"""
from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone

from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.service_desk import Ticket, TicketPriority, TicketStatus, TicketType
from tests.conftest import auth

UTC = timezone.utc


def _codigo(r) -> str:
    assert r.status_code == 422, r.text
    return r.json()["detail"]["code"]


def _datos(db):
    """Proyecto facturable con imputaciones hace 5 días (2 h) y hace 200 días (10 h)."""
    p = Project(code="PLFIN", name="Periodo fin", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id="1", is_billable=True, billing_rate=100.0, currency="EUR")
    db.add(p)
    db.commit()
    hoy = date.today()
    for dias, horas in ((5, 2.0), (200, 10.0)):
        db.add(Imputation(user_id="dev-test-id", project_id=p.id, organization_id="1",
                          date=hoy - timedelta(days=dias), hours=horas, is_billable=True, cost_amount=horas * 40))
    db.commit()
    return p


def _rango_30_dias() -> dict:
    hoy = date.today()
    return {"desde": str(hoy - timedelta(days=30)), "hasta": str(hoy + timedelta(days=1)), "tz": "UTC"}


# ── /profitability ────────────────────────────────────────────────────────────
def test_rentabilidad_sin_periodo_es_el_historico_y_con_desde_hasta_filtra(client, pm_token, db):
    _datos(db)
    todo = client.get("/api/v1/profitability/summary", headers=auth(pm_token)).json()["data"]
    assert todo["portfolio"]["total_revenue"] == 1200 and todo["periodo"] is None
    mes = client.get("/api/v1/profitability/summary", headers=auth(pm_token), params=_rango_30_dias()).json()["data"]
    assert mes["portfolio"]["total_revenue"] == 200 and mes["portfolio"]["total_cost"] == 80
    assert mes["periodo"]["origen"] == "rango"


def test_rentabilidad_acepta_days_y_el_alias_date_from_date_to(client, pm_token, db):
    p = _datos(db)
    hoy = date.today()
    for params in ({"days": 30}, {"date_from": str(hoy - timedelta(days=30)), "date_to": str(hoy)}):
        filas = client.get("/api/v1/profitability/projects", headers=auth(pm_token), params=params).json()
        filas = filas.get("data", filas) if isinstance(filas, dict) else filas
        filas = filas.get("items", filas) if isinstance(filas, dict) else filas
        fila = next(f for f in filas if f.get("project_id", f.get("id")) == p.id)
        assert fila["internal_cost"] == 80, params


def test_rentabilidad_rechaza_la_hora(client, pm_token):
    r = client.get("/api/v1/profitability/summary", headers=auth(pm_token), params={"days": 7, "granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"


# ── /dashboard ────────────────────────────────────────────────────────────────
def test_cuadro_de_mando_rentabilidad_filtra_por_periodo(client, admin_token, db):
    p = _datos(db)

    def _coste(params=None):
        filas = client.get("/api/v1/dashboard/profitability", headers=auth(admin_token), params=params or {}).json()["data"]
        return next(f for f in filas if f["project_id"] == p.id)["total_cost"]

    assert _coste() == 480
    assert _coste(_rango_30_dias()) == 80
    assert _coste({"date_from": str(date.today() - timedelta(days=30)), "date_to": str(date.today())}) == 80
    r = client.get("/api/v1/dashboard/profitability", headers=auth(admin_token), params={"granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"


def test_productividad_del_equipo_sin_periodo_es_el_mes_en_curso(client, pm_token):
    d = client.get("/api/v1/dashboard/productivity/team", headers=auth(pm_token)).json()["data"]
    assert str(d["period_start"]).startswith(date.today().replace(day=1).isoformat())
    assert d["periodo"] is None
    d = client.get("/api/v1/dashboard/productivity/team", headers=auth(pm_token),
                   params={"desde": "2026-01-01", "hasta": "2026-02-01", "tz": "UTC"}).json()["data"]
    assert str(d["period_start"]).startswith("2026-01-01") and str(d["period_end"]).startswith("2026-01-31")
    assert d["periodo"]["origen"] == "rango"


# ── /analytics ────────────────────────────────────────────────────────────────
def test_consulta_analitica_acepta_desde_hasta_y_el_alias_viejo(client, admin_token):
    nuevo = client.get("/api/v1/analytics/query/projects_by_type", headers=auth(admin_token),
                       params={"desde": "2026-03-01", "hasta": "2026-04-01", "tz": "UTC", "no_cache": True})
    assert nuevo.status_code == 200, nuevo.text
    d = nuevo.json()["data"]
    assert d["filters"]["date_from"] == "2026-03-01" and d["filters"]["date_to"] == "2026-03-31"
    assert d["periodo"]["granularidad"] in ("day", "week", "month")
    viejo = client.get("/api/v1/analytics/query/projects_by_type", headers=auth(admin_token),
                       params={"date_from": "2026-03-01", "date_to": "2026-03-31", "tz": "UTC", "no_cache": True})
    assert viejo.json()["data"]["filters"] == d["filters"]


def test_consulta_analitica_rechaza_la_hora(client, admin_token):
    r = client.get("/api/v1/analytics/query/projects_by_type", headers=auth(admin_token),
                   params={"days": 7, "granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"


def test_estadisticas_de_imputaciones_serie_con_la_granularidad_y_alias(client, dev_token, db):
    _datos(db)
    r = client.get("/api/v1/analytics/imputations", headers=auth(dev_token),
                   params={"days_back": 28, "period": "weekly", "tz": "UTC"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["period"] == "weekly" and d["periodo"]["granularidad"] == "week" and d["periodo"]["origen"] == "days"
    assert sum(p["total_hours"] for p in d["serie"]) == 2  # la de hace 200 días queda fuera
    assert sum(x["total_hours"] for x in d["daily"]) == 2
    r = client.get("/api/v1/analytics/imputations", headers=auth(dev_token), params={"days_back": 7, "granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"


def test_estadisticas_de_documentos_alias_days_back(client, admin_token):
    r = client.get("/api/v1/analytics/documents", headers=auth(admin_token), params={"days_back": 7})
    assert r.status_code == 200, r.text
    per = r.json()["data"]["periodo"]
    assert datetime.fromisoformat(per["hasta"]) - datetime.fromisoformat(per["desde"]) == timedelta(days=7)


def test_exportar_imputaciones_con_desde_hasta_y_sin_periodo_todo(client, hr_token, db):
    _datos(db)

    def _n(params):
        r = client.get("/api/v1/analytics/exports/imputations-csv", headers=auth(hr_token), params=params)
        assert r.status_code == 200, r.text
        return len(list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))) - 1  # sin cabecera

    assert _n({}) == 2
    assert _n(_rango_30_dias()) == 1
    r = client.get("/api/v1/analytics/exports/imputations-csv", headers=auth(hr_token), params={"granularidad": "hour"})
    assert _codigo(r) == "periodo.hora_no_admitida"


# ── /bi/export ────────────────────────────────────────────────────────────────
def test_exportar_bi_acepta_period_days_y_solo_admite_meses(client, admin_token):
    r = client.get("/api/v1/bi/export/excel", headers=auth(admin_token), params={"period_days": 90})
    assert r.status_code == 200, r.text
    r = client.get("/api/v1/bi/export/excel", headers=auth(admin_token),
                   params={"desde": "2026-01-01", "hasta": "2026-07-01", "tz": "UTC"})
    assert r.status_code == 200, r.text
    import openpyxl
    libro = openpyxl.load_workbook(io.BytesIO(r.content))
    assert "01/01/2026 – 30/06/2026" in libro["Resumen"]["A2"].value
    r = client.get("/api/v1/bi/export/excel", headers=auth(admin_token), params={"granularidad": "week"})
    assert _codigo(r) == "periodo.granularidad_no_admitida"


# ── /billing-reports/itsm-metrics/agent-performance ──────────────────────────
def test_rendimiento_por_agente_filtra_por_instante(client, pm_token, db):
    base = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
    for i, horas in enumerate((0, 5, 30)):  # 09:00, 14:00 y el día siguiente a las 15:00
        db.add(Ticket(number=f"PLF-{i}", ticket_type=TicketType.incident, title=f"T{i}", description="x",
                      status=TicketStatus.new, priority=TicketPriority.p3_medium, organization_id="1",
                      assigned_to_user_id="dev-test-id", created_at=base + timedelta(hours=horas)))
    db.commit()

    def _total(params):
        r = client.get("/api/v1/billing-reports/itsm-metrics/agent-performance", headers=auth(pm_token), params=params)
        assert r.status_code == 200, r.text
        filas = r.json()
        filas = filas.get("data", filas) if isinstance(filas, dict) else filas
        filas = filas.get("items", filas) if isinstance(filas, dict) else filas
        return sum(f["total"] for f in filas if f["user_id"] == "dev-test-id")

    # Con hora: solo la mañana del día 1.
    assert _total({"desde": "2026-10-01T08:00:00Z", "hasta": "2026-10-01T12:00:00Z", "granularidad": "hour"}) == 1
    assert _total({"desde": "2026-10-01T00:00:00Z", "hasta": "2026-10-02T00:00:00Z"}) == 2
    # `days` sigue valiendo (últimos N días hasta ahora); los tickets son del 1-10-2026.
    assert _total({"days": 1}) == 0
    assert _total({"days": 365}) == 3  # 3650 ya no vale: el periodo libre limita el rango a 1830 dias (LimitesDePeriodo.max_dias) -> 422 periodo.rango_excedido
