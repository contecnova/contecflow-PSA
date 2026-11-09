"""Presupuestos: partidas, real calculado, versiones y aprobación (revisión 2026-11).

Medido antes: un presupuesto era un total y doce meses, el «real» lo tecleaba
alguien (nadie lo hacía: la pantalla enseñaba 0 €) y aprobar era un booleano.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.expenses import Expense, ExpenseAllocation, ExpenseStatus
from app.models.imputation import Imputation
from app.models.mfa import Budget
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import User
from app.services import budgets_service
from tests.conftest import auth

URL = "/api/v1/budgets"


@pytest.fixture
def proyecto(db):
    for pid in ("p-b1", "p-b2"):
        db.add(Project(id=pid, code=pid.upper(), name=pid, status=ProjectStatus.active,
                       project_type=ProjectType.development, organization_id="1"))
    db.commit()
    return "p-b1"


def _crear(client, token, **campos):
    cuerpo = {"name": "Implantación ERP", "ambito": "proyecto", "project_id": "p-b1",
              "periodo_desde": "2026-01-01", "periodo_hasta": "2026-03-01", **campos}
    r = client.post(URL, headers=auth(token), json=cuerpo)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _linea(client, token, bid, **campos):
    r = client.post(f"{URL}/{bid}/lines", headers=auth(token), json=campos)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_el_personal_es_horas_por_coste_y_se_reparte_en_el_periodo(client, db, admin_token, proyecto):
    pm = db.query(User).filter(User.username == "pm_test").one()
    pm.hourly_rate = 50.0
    db.commit()
    b = _crear(client, admin_token)
    d = _linea(client, admin_token, b["id"], tipo="personal", descripcion="Consultor", user_id=pm.id, horas=100)
    linea = d["lineas"][0]
    assert (linea["coste_hora"], linea["importe"]) == (50.0, 5000.0)
    assert linea["meses"] == {"2026-01": 1666.67, "2026-02": 1666.67, "2026-03": 1666.66}
    d = _linea(client, admin_token, b["id"], tipo="licencias", descripcion="SaaS", importe=900,
               meses={"2026-01": 900})
    assert d["total_plan"] == 5900.0
    r = client.post(f"{URL}/{b['id']}/lines", headers=auth(admin_token),
                    json={"tipo": "licencias", "descripcion": "x", "importe": 100, "meses": {"2026-07": 100}})
    assert r.status_code == 400 and "fuera del periodo" in r.json()["detail"]
    r = client.post(f"{URL}/{b['id']}/lines", headers=auth(admin_token),
                    json={"tipo": "licencias", "descripcion": "x", "importe": 100, "meses": {"2026-01": 60}})
    assert r.status_code == 400 and "suma 60" in r.json()["detail"]
    r = client.post(f"{URL}/{b['id']}/lines", headers=auth(admin_token), json={"tipo": "inventado", "descripcion": "x", "importe": 1})
    assert r.status_code == 400 and "BUDGET_LINE_TYPES" in r.json()["detail"]


def test_EL_HALLAZGO_el_real_sale_de_imputaciones_y_gastos_con_su_reparto(client, db, admin_token, proyecto):
    pm = db.query(User).filter(User.username == "pm_test").one()
    pm.hourly_rate = 40.0
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=date(2026, 2, 3), hours=10,
                      organization_id="1", description="a"))
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=date(2026, 2, 4), hours=1,
                      cost_amount=99, organization_id="1", description="b"))
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=date(2026, 5, 4), hours=8,
                      organization_id="1", description="fuera del periodo"))
    g = Expense(id="e-b1", code="E1", user_id=pm.id, project_id="p-b1", category="software", description="x",
                amount=1000, expense_date=date(2026, 2, 10), status=ExpenseStatus.approved, organization_id="1")
    db.add(g)
    db.add(ExpenseAllocation(expense_id="e-b1", project_id="p-b1", percentage=30, organization_id="1"))
    db.add(ExpenseAllocation(expense_id="e-b1", project_id="p-b2", percentage=70, organization_id="1"))
    db.add(Expense(id="e-b2", code="E2", user_id=pm.id, project_id="p-b1", category="meals", description="y",
                   amount=50, expense_date=date(2026, 2, 11), status=ExpenseStatus.draft, organization_id="1"))
    db.commit()
    b = _crear(client, admin_token)
    _linea(client, admin_token, b["id"], tipo="personal", descripcion="Equipo", importe=900)
    inf = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]["informe"]
    feb = next(m for m in inf["meses"] if m["mes"] == "2026-02")
    assert feb["real"] == 400 + 99 + 300                       # 10 h × 40, lo guardado, 30 % de 1.000; el borrador no
    por_tipo = {t["tipo"]: t for t in inf["por_tipo"]}
    assert por_tipo["personal"]["real"] == 499 and por_tipo["licencias"]["real"] == 300   # software → licencias
    assert inf["total_real"] == 799


def test_departamento_y_area_cuentan_a_su_gente(client, db, admin_token, proyecto):
    pm = db.query(User).filter(User.username == "pm_test").one()
    dev = db.query(User).filter(User.username == "dev_test").one()
    pm.department, dev.department, pm.hourly_rate, dev.hourly_rate = "Consultoría", "Desarrollo", 10, 20
    for u in (pm, dev):
        db.add(Imputation(id=str(uuid.uuid4()), user_id=u.id, project_id="p-b2", date=date(2026, 1, 5), hours=1,
                          organization_id="1", description="x"))
    db.commit()
    dep = _crear(client, admin_token, ambito="departamento", department="Consultoría", project_id=None)
    # Revisión 2026-11: el área es una entidad que agrupa departamentos.
    from app.models.settings import Area, Department
    zona = Area(id="area-tec", organization_id="1", name="Área técnica")
    db.add(zona)
    for n in ("Consultoría", "Desarrollo"):
        db.add(Department(organization_id="1", name=n, area_id="area-tec"))
    db.commit()
    area = _crear(client, admin_token, name="Área técnica", ambito="area", area_id="area-tec", project_id=None)
    for b in (dep, area):
        _linea(client, admin_token, b["id"], tipo="personal", descripcion="x", importe=30)
    real = lambda b: client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]["informe"]["total_real"]
    assert (real(dep), real(area)) == (10, 30)


def test_un_proyecto_previsto_no_tiene_real_hasta_vincularlo(client, db, admin_token, proyecto):
    db.add(Imputation(id=str(uuid.uuid4()), user_id=db.query(User).filter(User.username == "pm_test").one().id,
                      project_id="p-b1", date=date(2026, 1, 5), hours=2, cost_amount=200, organization_id="1",
                      description="x"))
    db.commit()
    b = _crear(client, admin_token, ambito="proyecto_previsto", project_id=None, tipo_proyecto="development")
    _linea(client, admin_token, b["id"], tipo="personal", descripcion="Perfil senior", perfil="Senior", horas=10, coste_hora=60)
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    assert d["informe"]["sin_real"] is True and d["informe"]["total_real"] == 0 and d["total_plan"] == 600
    d = client.post(f"{URL}/{b['id']}/link-project", headers=auth(admin_token), json={"project_id": "p-b1"}).json()["data"]
    assert d["project_id"] == "p-b1" and d["informe"]["total_real"] == 200


def test_EL_HALLAZGO_versiones_y_aprobacion(client, db, admin_token, pm_token, proyecto):
    b = _crear(client, admin_token)
    assert client.post(f"{URL}/{b['id']}/submit", headers=auth(admin_token)).status_code == 400   # sin partidas
    _linea(client, admin_token, b["id"], tipo="otros", descripcion="x", importe=300)
    client.post(f"{URL}/{b['id']}/submit", headers=auth(admin_token))
    assert client.post(f"{URL}/{b['id']}/lines", headers=auth(admin_token),
                       json={"tipo": "otros", "descripcion": "y", "importe": 1}).status_code == 409
    assert client.post(f"{URL}/{b['id']}/decision", headers=auth(pm_token), json={"aprobado": True}).status_code == 403
    assert client.post(f"{URL}/{b['id']}/decision", headers=auth(admin_token), json={"aprobado": False}).status_code == 400
    v1 = client.post(f"{URL}/{b['id']}/decision", headers=auth(admin_token), json={"aprobado": True}).json()["data"]
    assert v1["estado"] == "aprobado"
    v2 = client.post(f"{URL}/{b['id']}/new-version", headers=auth(admin_token)).json()["data"]
    assert (v2["version"], v2["estado"], v2["total_plan"], v2["origen_id"]) == (2, "borrador", 300.0, b["id"])
    assert client.post(f"{URL}/{b['id']}/new-version", headers=auth(admin_token)).status_code == 409
    _linea(client, admin_token, v2["id"], tipo="otros", descripcion="reprevisión", importe=100)
    client.post(f"{URL}/{v2['id']}/submit", headers=auth(admin_token))
    client.post(f"{URL}/{v2['id']}/decision", headers=auth(admin_token), json={"aprobado": True})
    db.expire_all()
    assert db.get(Budget, b["id"]).estado == "sustituido"
    lista = client.get(URL, headers=auth(admin_token)).json()
    items = lista.get("items") or lista.get("data")
    assert [(i["version"], i["total_plan"]) for i in items if i["origen_id"] == b["id"]] == [(2, 400.0)]
    v3 = client.post(f"{URL}/{v2['id']}/new-version", headers=auth(admin_token)).json()["data"]
    _linea(client, admin_token, v3["id"], tipo="otros", descripcion="borrador", importe=999)
    r = client.get(f"{URL}/summary", params={"year": 2026}, headers=auth(admin_token)).json()["data"]
    assert (r["aprobados"], r["total_plan"]) == (1, 400.0)          # cuenta la aprobada, no el borrador v3


def test_la_bandeja_aplica_la_decision(client, db, admin_token, proyecto):
    from app.models.billing_reports import ApprovalRequest
    from app.services.approval_engine import fuentes
    b = _crear(client, admin_token)
    _linea(client, admin_token, b["id"], tipo="otros", descripcion="x", importe=10)
    client.post(f"{URL}/{b['id']}/submit", headers=auth(admin_token))
    admin = db.query(User).filter(User.username == "admin").one()
    req = ApprovalRequest(entity_type="budget", entity_id=b["id"], status="approved", final_note="ok", organization_id="1")
    fuentes.aplicar(req, "approved", admin, db)
    db.expire_all()
    assert db.get(Budget, b["id"]).estado == "aprobado"


def test_la_prevision_al_cierre_suma_lo_real_hasta_hoy_y_el_plan_del_resto(db, monkeypatch):
    monkeypatch.setattr(budgets_service, "_mes_actual", lambda: "2026-02")
    monkeypatch.setattr(budgets_service, "_plan_mensual", lambda b, sentido="gasto": (
        {"2026-01": {"x": 100}, "2026-02": {"x": 100}, "2026-03": {"x": 100}} if sentido == "gasto" else {}))
    monkeypatch.setattr(budgets_service, "_real_mensual", lambda db, b: {"2026-01": {"x": 150}, "2026-02": {"x": 20}})
    b = Budget(periodo_desde=date(2026, 1, 1), periodo_hasta=date(2026, 3, 1), ambito="departamento")
    inf = budgets_service.informe(db, b)
    assert inf["prevision_cierre"] == 150 + 20 + 100
    assert (inf["plan_hasta_hoy"], inf["desviacion_hasta_hoy"]) == (200, -30)
