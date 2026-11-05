"""La carga del almacén analítico (PostgreSQL → DuckDB) (revisión 2026-11).

Medido el 05-11-2026: la carga reventaba (`Project.end_date` no existe) y la
DuckDB viva tenía sus 9 tablas vacías; muchos campos se leían con `getattr` de
nombres que no existen y se habrían cargado vacíos. Con una DuckDB real en un
fichero temporal.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import duckdb
import pytest

from app.models.imputation import Imputation
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.service_desk.tickets import Ticket
from app.models.user import User
from app.services.olap import etl
from tests.conftest import auth


@pytest.fixture
def almacen(tmp_path, monkeypatch):
    ruta = str(tmp_path / "olap.duckdb")
    monkeypatch.setattr(etl, "DUCKDB_PATH", ruta)
    return ruta


@pytest.fixture
def datos(db):
    u = db.query(User).filter(User.username == "pm_test").one()
    u.hourly_rate = 40.0
    p = Project(id="p-olap", code="OLAP1", name="Almacén", status=ProjectStatus.active,
                project_type=ProjectType.development, organization_id="1", budget_amount=10000,
                contract_amount=15000, end_date_planned=date(2026, 12, 31), risk_level="high")
    db.add(p)
    # Una imputación guarda su coste; la otra sólo la tarifa de entonces; la tercera, nada (tarifa del usuario).
    db.add(Imputation(id=str(uuid.uuid4()), user_id=u.id, project_id=p.id, date=date(2026, 10, 1), hours=2,
                      cost_amount=100, organization_id="1", description="a"))
    db.add(Imputation(id=str(uuid.uuid4()), user_id=u.id, project_id=p.id, date=date(2026, 10, 2), hours=3,
                      hourly_rate_snapshot=30, organization_id="1", description="b"))
    db.add(Imputation(id=str(uuid.uuid4()), user_id=u.id, project_id=p.id, date=date(2026, 10, 3), hours=1,
                      organization_id="1", description="c", is_billable=True))
    abierto = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc)
    db.add(Ticket(id="t-olap", number="INC-OLAP", ticket_type="incident", title="x", description="x",
                  organization_id="1", created_at=abierto, closed_at=abierto + timedelta(hours=5, minutes=30),
                  assigned_to_user_id=u.id, csat_score=4, sla_resolution_breached=True))
    db.commit()
    return u


def _uno(ruta, sql, *params):
    c = duckdb.connect(ruta, read_only=True)
    try:
        return c.execute(sql, list(params)).fetchone()
    finally:
        c.close()


def test_EL_HALLAZGO_la_carga_termina_y_cuadra_con_la_base(db, almacen, datos):
    r = etl.run_full_etl(db)
    assert r["status"] == "ok" and r["since"] == "full"
    assert r["imputations"] == db.query(Imputation).count() and r["tickets"] == db.query(Ticket).count()
    assert r["dim_projects"] == db.query(Project).count()


def test_cada_campo_sale_de_su_columna_real(db, almacen, datos):
    etl.run_full_etl(db)
    assert _uno(almacen, "SELECT budget, end_date FROM dim_project WHERE project_id='p-olap'") == \
        (10000.0, date(2026, 12, 31))
    # 100 (guardado) + 3h×30 (tarifa de entonces) + 1h×40 (tarifa del usuario) = 230
    assert _uno(almacen, "SELECT budget, total_hours, total_cost, revenue, margin, risk_level FROM fact_projects "
                         "WHERE project_id='p-olap'") == (10000.0, 6.0, 230.0, 15000.0, 14770.0, "high")
    assert _uno(almacen, "SELECT sum(billable_hours) FROM fact_imputations WHERE project_id='p-olap'") == (1.0,)
    assert _uno(almacen, "SELECT cost_per_hour FROM dim_user WHERE user_id=?", datos.id) == (40.0,)
    assert _uno(almacen, "SELECT resolution_hours, sla_breached, satisfaction, agent_id FROM fact_tickets "
                         "WHERE ticket_id='t-olap'") == (5.5, True, 4, datos.id)


def test_lo_borrado_en_la_base_desaparece_en_la_siguiente_carga(db, almacen, datos):
    etl.run_full_etl(db)
    db.delete(db.get(Ticket, "t-olap"))
    db.commit()
    etl.run_full_etl(db)
    assert _uno(almacen, "SELECT count(*) FROM fact_tickets WHERE ticket_id='t-olap'") == (0,)


def test_un_fallo_deja_lo_que_habia_y_queda_apuntado(db, almacen, datos, monkeypatch):
    etl.run_full_etl(db)
    antes = _uno(almacen, "SELECT count(*) FROM fact_imputations")
    monkeypatch.setattr(etl, "_load_fact_tickets", lambda db, conn: 1 / 0)
    with pytest.raises(ZeroDivisionError):
        etl.run_full_etl(db)
    assert _uno(almacen, "SELECT count(*) FROM fact_imputations") == antes
    e = etl.estado("1")
    assert e["last_run"]["status"] == "error" and "ZeroDivisionError" in e["last_run"]["detail"]["error"]
    assert e["last_ok"]["status"] == "ok" and e["company_rows"]["fact_imputations"] == antes[0]


def test_estado_y_recarga_por_la_api(client, db, almacen, datos, admin_token, pm_token):
    assert client.get("/api/v1/analytics/olap/status", headers=auth(pm_token)).json()["data"]["last_run"] is None
    assert client.post("/api/v1/analytics/olap/refresh", headers=auth(pm_token)).status_code == 403
    r = client.post("/api/v1/analytics/olap/refresh", headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["data"]["status"] == "ok"
    e = client.get("/api/v1/analytics/olap/status", headers=auth(pm_token)).json()["data"]
    assert e["last_ok"]["status"] == "ok" and e["company_rows"]["fact_tickets"] >= 1


def test_la_hora_de_la_carga_se_guarda_en_utc(db, almacen, datos):
    etl.run_full_etl(db)
    hora = datetime.fromisoformat(etl.estado("1")["last_run"]["run_at"]).replace(tzinfo=timezone.utc)
    assert abs((datetime.now(timezone.utc) - hora).total_seconds()) < 120
