"""Evolución del margen con ingreso, coste y desglose (17-11-2026).

``/analytics/olap/margin-evolution`` y ``/analytics/olap/margin-evolution/breakdown``
(``app/services/evolucion_del_margen.py``): ingreso por tarifa del proyecto y
por hitos facturados, margen, filtros por proyecto y cliente, desglose por
proyecto y por cliente, aislamiento entre empresas y solo admin/PM.
"""
from __future__ import annotations

import uuid
from datetime import date

from app.models.clients import Client
from app.models.financial import ProjectMilestone
from app.models.imputation import Imputation
from app.models.mfa import Organization
from app.models.project import Project, ProjectStatus, ProjectType
from tests.conftest import auth

URL = "/api/v1/analytics/olap/margin-evolution"
MES = {"desde": "2026-09-01", "hasta": "2026-11-01", "granularidad": "month", "tz": "UTC"}


def _cliente(db, nombre, org="1"):
    c = Client(id=str(uuid.uuid4()), name=nombre, organization_id=org)
    db.add(c)
    db.commit()
    return c


def _proyecto(db, code, *, cliente=None, tarifa=None, contrato=None, org="1"):
    p = Project(code=code, name=f"Proyecto {code}", status=ProjectStatus.active, project_type=ProjectType.development,
                organization_id=org, is_billable=True, billing_rate=tarifa, contract_amount=contrato, currency="EUR",
                client_id=cliente.id if cliente else None)
    db.add(p)
    db.commit()
    return p


def _imputar(db, p, dia, horas, coste, org="1", facturable=True):
    db.add(Imputation(id=str(uuid.uuid4()), user_id="dev-test-id", project_id=p.id, organization_id=org,
                      date=dia, hours=horas, is_billable=facturable, cost_amount=coste))
    db.commit()


def _hito(db, p, importe, dia, org="1"):
    db.add(ProjectMilestone(project_id=p.id, organization_id=org, name="Hito", billing_amount=importe,
                            is_billed=True, billed_at=dia))
    db.commit()


def _datos(db):
    acme = _cliente(db, "Acme")
    beta = _cliente(db, "Beta")
    hora = _proyecto(db, "HORA", cliente=acme, tarifa=100.0)        # ingreso = 100 €/h facturable
    cerrado = _proyecto(db, "CERR", cliente=beta, contrato=10000.0)  # ingreso = hitos facturados
    _imputar(db, hora, date(2026, 9, 10), 10, 400)     # sep: ingreso 1000, coste 400
    _imputar(db, hora, date(2026, 10, 5), 5, 200)      # oct: ingreso 500, coste 200
    _imputar(db, hora, date(2026, 10, 6), 2, 80, facturable=False)  # oct: no factura, sí cuesta
    _imputar(db, cerrado, date(2026, 10, 20), 8, 600)  # oct: coste 600
    _hito(db, cerrado, 3000.0, date(2026, 10, 25))     # oct: ingreso 3000
    _hito(db, cerrado, 9999.0, date(2026, 12, 1))      # fuera del periodo
    return acme, beta, hora, cerrado


def test_serie_con_ingreso_por_tarifa_y_por_hitos(client, admin_token, db):
    _datos(db)
    r = client.get(URL, headers=auth(admin_token), params=MES)
    assert r.status_code == 200, r.text
    sep, oct_ = r.json()["items"]
    assert (sep["clave"], oct_["clave"]) == ("2026-09-01T00:00", "2026-10-01T00:00")
    assert (sep["revenue"], sep["total_cost"], sep["margin"], sep["margin_pct"]) == (1000.0, 400.0, 600.0, 60.0)
    assert (oct_["revenue"], oct_["total_cost"], oct_["margin"]) == (3500.0, 880.0, 2620.0)
    assert sep["active_projects"] == 1 and oct_["active_projects"] == 2
    assert oct_["hours"] == 15.0 and oct_["month"] == "2026-10"


def test_tramo_sin_ingreso_tiene_margen_pct_nulo(client, admin_token, db):
    p = _proyecto(db, "SIN")
    _imputar(db, p, date(2026, 9, 3), 1, 50)
    r = client.get(URL, headers=auth(admin_token), params=MES)
    sep, oct_ = r.json()["items"]
    assert sep["margin"] == -50.0 and sep["margin_pct"] is None
    assert oct_["total_cost"] == 0.0 and oct_["margin_pct"] is None


def test_filtros_por_proyecto_y_por_cliente(client, admin_token, db):
    _acme, beta, hora, _cerrado = _datos(db)
    r = client.get(URL, headers=auth(admin_token), params={**MES, "proyecto_id": hora.id})
    assert [x["revenue"] for x in r.json()["items"]] == [1000.0, 500.0]
    r = client.get(URL, headers=auth(admin_token), params={**MES, "cliente_id": beta.id})
    assert [x["revenue"] for x in r.json()["items"]] == [0.0, 3000.0]
    assert [x["total_cost"] for x in r.json()["items"]] == [0.0, 600.0]


def test_desglose_por_proyecto_y_por_cliente(client, pm_token, db):
    acme, beta, hora, cerrado = _datos(db)
    r = client.get(f"{URL}/breakdown", headers=auth(pm_token), params={**MES, "por": "proyecto"})
    assert r.status_code == 200, r.text
    filas = r.json()["items"]
    assert [f["id"] for f in filas] == [cerrado.id, hora.id]   # de más a menos margen
    assert filas[0]["codigo"] == "CERR" and filas[0]["margin"] == 2400.0
    assert filas[1]["revenue"] == 1500.0 and filas[1]["total_cost"] == 680.0
    r = client.get(f"{URL}/breakdown", headers=auth(pm_token), params={**MES, "por": "cliente"})
    filas = {f["id"]: f for f in r.json()["items"]}
    assert filas[acme.id]["nombre"] == "Acme" and filas[acme.id]["margin"] == 820.0
    assert filas[beta.id]["proyectos"] == 1 and filas[beta.id]["margin_pct"] == 80.0
    assert client.get(f"{URL}/breakdown", headers=auth(pm_token), params={"por": "otro"}).status_code == 422


def test_otra_empresa_ni_se_ve_ni_se_puede_filtrar(client, admin_token, db):
    _datos(db)
    db.add(Organization(id="org-otra-margen", name="Otra", slug="otra-margen"))
    db.commit()
    ajeno = _proyecto(db, "AJENO", tarifa=500.0, org="org-otra-margen")
    _imputar(db, ajeno, date(2026, 9, 10), 100, 1, org="org-otra-margen")
    otro_cliente = _cliente(db, "Ajeno", org="org-otra-margen")
    r = client.get(URL, headers=auth(admin_token), params=MES)
    assert r.json()["items"][0]["revenue"] == 1000.0
    r = client.get(URL, headers=auth(admin_token), params={**MES, "proyecto_id": ajeno.id})
    assert r.status_code == 404 and r.json()["code"] == "proyecto_no_encontrado"
    r = client.get(f"{URL}/breakdown", headers=auth(admin_token), params={**MES, "cliente_id": otro_cliente.id})
    assert r.status_code == 404 and r.json()["code"] == "cliente_no_encontrado"
    ids = {f["id"] for f in client.get(f"{URL}/breakdown", headers=auth(admin_token), params=MES).json()["items"]}
    assert ajeno.id not in ids


def test_solo_admin_y_pm(client, dev_token, hr_token):
    for token in (dev_token, hr_token):
        assert client.get(URL, headers=auth(token)).status_code == 403
        assert client.get(f"{URL}/breakdown", headers=auth(token)).status_code == 403
