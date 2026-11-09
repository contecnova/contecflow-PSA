"""Presupuestos: preparar a fondo (revisión 2026-11).

Lo pidió el usuario: el presupuesto es la base de áreas y proyectos y prepararlo
tiene que ser mucho más profundo. Cada prueba cubre una capacidad de P1.
"""
from __future__ import annotations

from datetime import date

import pytest

from app.models.mfa import Budget
from app.models.settings import Area, Department
from app.models.user import User
from app.models.user_cost import CountryEmployerCost, UserCostProfile
from app.services import settings_service
from tests.conftest import auth
from tests.test_presupuestos_2026_11 import URL, _crear, _linea, proyecto  # noqa: F401  (fixture)


@pytest.fixture
def area(db):
    db.add(Area(id="area-1", organization_id="1", name="Tecnología"))
    db.add(Department(organization_id="1", name="Desarrollo", area_id="area-1"))
    db.commit()
    return "area-1"


def _partida(d, desc):
    return next(l for l in d["lineas"] if l["descripcion"] == desc)


def test_conductor_unidades_por_precio_con_recurrencia(client, admin_token, proyecto):
    b = _crear(client, admin_token, periodo_hasta="2026-12-01")
    d = _linea(client, admin_token, b["id"], tipo="licencias", descripcion="Jira", unidades=10, precio_unitario=8,
               recurrencia="mensual")
    assert _partida(d, "Jira")["importe"] == 960
    d = _linea(client, admin_token, b["id"], tipo="licencias", descripcion="Soporte", unidades=1, precio_unitario=1200,
               recurrencia="trimestral", mes_desde="2026-02")
    assert sorted(_partida(d, "Soporte")["meses"]) == ["2026-02", "2026-05", "2026-08", "2026-11"]


def test_persona_por_coste_cargado_con_subida_con_fecha(client, db, admin_token, proyecto):
    dev = db.query(User).filter(User.username == "dev_test").one()
    for desde, hasta, anual in ((date(2025, 1, 1), date(2026, 1, 31), 48000), (date(2026, 2, 1), None, 60000)):
        db.add(UserCostProfile(user_id=dev.id, organization_id="1", gross_annual_salary=anual, total_annual_cost=anual,
                               cost_per_hour=anual / 1700, valid_from=desde, valid_to=hasta))
    db.commit()
    b = _crear(client, admin_token)
    d = _linea(client, admin_token, b["id"], tipo="personal", descripcion="Dev", user_id=dev.id, dedicacion_pct=50)
    assert _partida(d, "Dev")["meses"] == {"2026-01": 2000.0, "2026-02": 2500.0, "2026-03": 2500.0}


def test_vacante_con_cargas_del_pais_desde_su_alta(client, db, admin_token, proyecto):
    db.add(CountryEmployerCost(organization_id="1", country_code="ES", country_name="España", employer_cost_pct=0.30))
    db.commit()
    b = _crear(client, admin_token)
    d = _linea(client, admin_token, b["id"], tipo="personal", descripcion="Vacante QA", perfil="QA",
               salario_anual=36000, pais="ES", fecha_alta="2026-02-15")
    assert _partida(d, "Vacante QA")["meses"] == {"2026-02": 3900.0, "2026-03": 3900.0}


def test_inflacion_de_los_supuestos_sube_los_anios_siguientes(client, admin_token, proyecto):
    b = _crear(client, admin_token, periodo_desde="2026-12-01", periodo_hasta="2027-01-01", supuestos={"inflacion_pct": 10})
    d = _linea(client, admin_token, b["id"], tipo="otros", descripcion="Cuota", unidades=1, precio_unitario=100,
               recurrencia="mensual")
    assert _partida(d, "Cuota")["meses"] == {"2026-12": 100.0, "2027-01": 110.0}


def test_ingresos_dan_el_margen_y_capex_se_amortiza(client, admin_token, proyecto):
    b = _crear(client, admin_token)
    _linea(client, admin_token, b["id"], tipo="otros", descripcion="Servidor", importe=3000, meses={"2026-01": 3000},
           naturaleza="capex", vida_meses=3)
    d = _linea(client, admin_token, b["id"], sentido="ingreso", tipo="horas", descripcion="Horas facturables",
               unidades=100, precio_unitario=50, recurrencia="unica")
    inf = d["informe"]
    assert (d["total_plan"], d["total_ingreso"], inf["margen_plan"]) == (3000, 5000, 2000)
    assert inf["capex_plan"] == 3000 and [m["amortizacion"] for m in inf["meses"]] == [1000, 1000, 1000]
    r = client.post(f"{URL}/{b['id']}/lines", headers=auth(admin_token),
                    json={"tipo": "otros", "descripcion": "Sin vida", "importe": 10, "naturaleza": "capex"})
    assert r.status_code == 400


def test_EL_HALLAZGO_el_area_es_una_entidad_y_el_techo_lo_consumen_los_hijos(client, db, admin_token, proyecto, area):
    a = _crear(client, admin_token, name="Tecnología 2026", ambito="area", area_id=area, project_id=None, techo=1000)
    dep = _crear(client, admin_token, name="Desarrollo 2026", ambito="departamento", department="Desarrollo",
                 project_id=None)
    assert dep["padre_id"] == a["id"]      # el padre por defecto: el presupuesto de su área
    d = _linea(client, admin_token, dep["id"], tipo="otros", descripcion="Grande", importe=1500)
    assert "techo" in (d["aviso_techo_del_padre"] or "")
    settings_service.set_runtime_value(db, "presupuestos", "BUDGET_CEILING_POLICY", "bloquear", "1")
    r = client.post(f"{URL}/{dep['id']}/submit", headers=auth(admin_token))
    assert r.status_code == 409, r.text
    ficha = client.get(f"{URL}/{a['id']}", headers=auth(admin_token)).json()["data"]
    assert ficha["techo_estado"]["excedido"] and ficha["consolidado_plan"] == 1500


def test_justificacion_obligatoria_por_encima_del_umbral(client, db, admin_token, proyecto):
    settings_service.set_runtime_value(db, "presupuestos", "BUDGET_JUSTIFICATION_MIN_AMOUNT", 1000, "1")
    b = _crear(client, admin_token)
    d = _linea(client, admin_token, b["id"], tipo="otros", descripcion="Caro", importe=2000)
    r = client.post(f"{URL}/{b['id']}/submit", headers=auth(admin_token))
    assert r.status_code == 400 and "justificación" in r.json()["detail"]
    lid = _partida(d, "Caro")["id"]
    client.patch(f"{URL}/{b['id']}/lines/{lid}", headers=auth(admin_token), json={"justificacion": "Migración"})
    assert client.post(f"{URL}/{b['id']}/submit", headers=auth(admin_token)).status_code == 200


def test_plantilla_y_copia_del_anio_anterior_con_ajuste(client, admin_token, proyecto):
    viejo = _crear(client, admin_token, periodo_desde="2025-01-01", periodo_hasta="2025-03-01")
    _linea(client, admin_token, viejo["id"], tipo="licencias", descripcion="SaaS", importe=300)
    r = client.post("/api/v1/budget-templates", headers=auth(admin_token),
                    json={"nombre": "Proyecto estándar", "desde_presupuesto": viejo["id"]})
    assert r.status_code == 200, r.text
    con_plantilla = _crear(client, admin_token, plantilla_id=r.json()["data"]["id"])
    assert con_plantilla["total_plan"] == 300
    copia = _crear(client, admin_token, copiar_de=viejo["id"], base="plan", ajuste_pct=10)
    assert copia["total_plan"] == 330 and sorted(copia["lineas"][0]["meses"]) == ["2026-01", "2026-02", "2026-03"]


def test_escenarios_con_supuestos_distintos_y_comparacion(client, admin_token, proyecto):
    b = _crear(client, admin_token, periodo_desde="2026-12-01", periodo_hasta="2027-01-01")
    _linea(client, admin_token, b["id"], tipo="otros", descripcion="Cuota", unidades=1, precio_unitario=100,
           recurrencia="mensual")
    r = client.post(f"{URL}/{b['id']}/scenario", headers=auth(admin_token),
                    json={"nombre": "pesimista", "supuestos": {"inflacion_pct": 20}})
    assert r.status_code == 200, r.text
    e = r.json()["data"]
    assert e["escenario"] == "pesimista" and e["origen_id"] == e["id"] and e["total_plan"] == 220
    cmp = client.post(f"{URL}/compare", headers=auth(admin_token), json={"ids": [b["id"], e["id"]]}).json()["data"]
    assert [p["gasto"] for p in cmp["presupuestos"]] == [200, 220]


def test_campana_con_fecha_limite_avisa_a_los_responsables(client, db, admin_token, proyecto):
    from app.models.enterprise import Notification
    from app.services.presupuestos_preparar import recordar_campana
    hoy = date.today()
    r = client.post("/api/v1/budget-campaigns", headers=auth(admin_token),
                    json={"nombre": "Ejercicio", "year": hoy.year, "fecha_limite": hoy.isoformat()})
    assert r.status_code == 200, r.text
    b = _crear(client, admin_token, campana_id=r.json()["data"]["id"])
    assert b["responsable_id"]
    assert recordar_campana(db) == 1
    assert db.query(Notification).filter(Notification.resource_id == b["id"]).count() == 1
    campanas = client.get("/api/v1/budget-campaigns", headers=auth(admin_token)).json()["items"]
    assert campanas[0]["presupuestos"] == 1 and campanas[0]["por_estado"] == {"borrador": 1}


def test_areas_en_ajustes(client, admin_token):
    r = client.post("/api/v1/settings/areas", headers=auth(admin_token), json={"name": "Operaciones"})
    assert r.status_code == 200, r.text
    aid = r.json()["data"]["id"]
    r = client.post("/api/v1/settings/departments", headers=auth(admin_token), json={"name": "Soporte", "area_id": aid})
    assert r.status_code == 200, r.text
    areas = client.get("/api/v1/settings/areas", headers=auth(admin_token)).json()["items"]
    assert next(a for a in areas if a["id"] == aid)["departamentos"] == ["Soporte"]
