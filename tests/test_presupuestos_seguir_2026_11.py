"""Presupuestos: seguir a fondo (revisión 2026-11, P2).

Lo pidió el usuario: el presupuesto es la base de áreas y proyectos y seguirlo
tiene que ser mucho más profundo. Cada prueba cubre una capacidad de P2: el
comprometido (ALM y pedidos), el control al aprobar un gasto, el cierre mensual
con explicación de desviaciones, la reprevisión por tipo, los traspasos con
aprobación, el proyecto, las alertas, el detalle hasta la imputación y el cuadro.
"""
from __future__ import annotations

import uuid
from datetime import date

import pytest

from app.models.expenses import Expense, ExpenseStatus
from app.models.imputation import Imputation
from app.models.mfa import Budget
from app.models.project import Project
from app.models.user import User
from app.services import budgets_service, settings_service
from tests.conftest import auth
from tests.test_presupuestos_2026_11 import URL, _crear, _linea, proyecto  # noqa: F401  (fixture)


@pytest.fixture
def abril(monkeypatch):
    monkeypatch.setattr(budgets_service, "_mes_actual", lambda: "2026-04")


def _aprobado(client, token):
    """Proyecto p-b1, enero a junio: licencias 100/mes y viajes 100/mes."""
    b = _crear(client, token, periodo_hasta="2026-06-01")
    _linea(client, token, b["id"], tipo="licencias", descripcion="Licencias", importe=600)
    _linea(client, token, b["id"], tipo="viajes", descripcion="Viajes", importe=600)
    client.post(f"{URL}/{b['id']}/submit", headers=auth(token))
    r = client.post(f"{URL}/{b['id']}/decision", headers=auth(token), json={"aprobado": True})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _fila(d, tipo):
    return next(x for x in d["seguir"]["por_tipo"] if x["tipo"] == tipo)


def _gasto(db, importe, dia, estado=ExpenseStatus.approved, categoria="travel"):
    pm = db.query(User).filter(User.username == "pm_test").one()
    g = Expense(id=str(uuid.uuid4()), code=f"E{uuid.uuid4().hex[:6]}", user_id=pm.id, project_id="p-b1",
                category=categoria, description="viaje", amount=importe, expense_date=dia, status=estado,
                organization_id="1")
    db.add(g)
    db.commit()
    return g


def test_comprometido_de_alm_y_pedidos_y_el_disponible(client, db, admin_token, proyecto, abril):
    from app.models.alm import ALMContract, ALMContractStatus, ALMContractType, ALMLicense, LicenseType
    db.add(ALMContract(id="c-1", title="Soporte ERP", type=ALMContractType.support, annual_value=1200,
                       start_date=date(2026, 1, 1), project_id="p-b1", organization_id="1"))
    db.add(ALMContract(title="Cancelado", type=ALMContractType.support, annual_value=9999, project_id="p-b1",
                       status=ALMContractStatus.cancelled, organization_id="1"))
    db.add(ALMLicense(name="Va en el contrato", type=LicenseType.named, annual_cost=5000, contract_id="c-1",
                      project_id="p-b1", organization_id="1"))
    db.add(ALMLicense(name="Suelta", type=LicenseType.named, annual_cost=240, expiry_date=date(2026, 5, 31),
                      project_id="p-b1", organization_id="1"))
    db.commit()
    b = _aprobado(client, admin_token)
    r = client.post(f"{URL}/{b['id']}/commitments", headers=auth(admin_token),
                    json={"tipo": "viajes", "descripcion": "Billetes", "proveedor": "Agencia", "importe": 150, "mes": "2026-05"})
    assert r.status_code == 200, r.text
    pedido = r.json()["data"]["id"]
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    # contrato: 100/mes de abril a junio; licencia suelta: 20/mes abril y mayo; la del contrato y el cancelado no.
    assert _fila(d, "licencias")["comprometido"] == 340
    assert (_fila(d, "viajes")["comprometido"], _fila(d, "viajes")["disponible"]) == (150, 450)
    r = client.patch(f"/api/v1/budget-commitments/{pedido}", headers=auth(admin_token),
                     json={"estado": "facturado", "fecha_factura": "2026-03-10", "importe_facturado": 120})
    assert r.status_code == 200
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    assert (_fila(d, "viajes")["real"], _fila(d, "viajes")["comprometido"]) == (120, 0)
    assert next(m for m in d["informe"]["meses"] if m["mes"] == "2026-03")["real"] == 120


def test_control_al_aprobar_un_gasto_avisa_o_bloquea(client, db, admin_token, proyecto, abril):
    from app.services.approval_engine import fuentes
    _aprobado(client, admin_token)
    g = _gasto(db, 700, date(2026, 4, 2), estado=ExpenseStatus.submitted)
    settings_service.set_runtime_value(db, "presupuestos", "BUDGET_CONTROL_POLICY", "bloquear", "1")
    r = client.post(f"/api/v1/expenses/{g.id}/review", headers=auth(admin_token), json={"approved": True})
    assert r.status_code == 409 and "quedan 600" in r.json()["detail"], r.text

    class Req:      # la bandeja lo comprueba antes de anotar la aprobación
        entity_type, entity_id = "expense", g.id
    with pytest.raises(Exception) as exc:
        fuentes.comprobar_antes(Req, "approved", db)
    assert getattr(exc.value, "status_code", None) == 409
    settings_service.set_runtime_value(db, "presupuestos", "BUDGET_CONTROL_POLICY", "avisar", "1")
    r = client.post(f"/api/v1/expenses/{g.id}/review", headers=auth(admin_token), json={"approved": True})
    assert r.status_code == 200 and r.json()["data"]["avisos_de_presupuesto"], r.text


def test_cierre_mensual_exige_explicar_y_congela_el_real(client, db, admin_token, pm_token, proyecto, abril):
    b = _aprobado(client, admin_token)
    settings_service.set_runtime_value(db, "presupuestos", "BUDGET_VARIANCE_EXPLAIN_MIN_AMOUNT", 250, "1")   # sólo el +300 de febrero
    _gasto(db, 400, date(2026, 2, 10))
    r = client.post(f"{URL}/{b['id']}/close", headers=auth(admin_token), json={"mes": "2026-02"})
    assert r.status_code == 409 and "viajes (+300)" in r.json()["detail"], r.text
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    assert [(x["mes"], x["tipo"]) for x in d["seguir"]["desviaciones_sin_explicar"]] == [("2026-02", "viajes")]
    client.post(f"{URL}/{b['id']}/variance-notes", headers=auth(admin_token),
                json={"mes": "2026-02", "tipo": "viajes", "explicacion": "Viaje al cliente no previsto"})
    d = client.post(f"{URL}/{b['id']}/close", headers=auth(admin_token), json={"mes": "2026-02"}).json()["data"]
    assert "2026-02" in d["seguir"]["meses_cerrados"]
    _gasto(db, 50, date(2026, 2, 20))          # llega tarde: el mes cerrado no cambia
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    assert next(m for m in d["informe"]["meses"] if m["mes"] == "2026-02")["real"] == 400
    assert client.post(f"{URL}/{b['id']}/close", headers=auth(admin_token), json={"mes": "2026-04"}).status_code == 400
    assert client.delete(f"{URL}/{b['id']}/close/2026-02", headers=auth(pm_token)).status_code == 403
    d = client.delete(f"{URL}/{b['id']}/close/2026-02", headers=auth(admin_token)).json()["data"]
    assert next(m for m in d["informe"]["meses"] if m["mes"] == "2026-02")["real"] == 450


def test_reprevision_por_tipo_plan_ritmo_y_a_mano(client, db, admin_token, proyecto, abril):
    b = _aprobado(client, admin_token)
    _gasto(db, 400, date(2026, 2, 10))
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    assert _fila(d, "viajes")["prevision"] == 700          # 400 real hasta marzo + plan de abril a junio
    d = client.put(f"{URL}/{b['id']}/forecast", headers=auth(admin_token),
                   json={"tipo": "viajes", "metodo": "ritmo"}).json()["data"]
    assert _fila(d, "viajes")["prevision"] == pytest.approx(800, abs=0.05)   # 133,33 al mes desde abril
    d = client.put(f"{URL}/{b['id']}/forecast", headers=auth(admin_token),
                   json={"tipo": "viajes", "metodo": "manual", "meses": {"2026-04": 0, "2026-05": 50, "2026-06": 0}}).json()["data"]
    assert (_fila(d, "viajes")["prevision"], _fila(d, "viajes")["metodo"]) == (450, "manual")
    assert client.put(f"{URL}/{b['id']}/forecast", headers=auth(admin_token),
                      json={"tipo": "viajes", "metodo": "magia"}).status_code == 400


def test_traspaso_con_aprobacion_y_sin_aprobarse_el_suyo(client, db, admin_token, pm_token, proyecto, abril):
    b = _aprobado(client, admin_token)
    lic, via = (next(l["id"] for l in b["lineas"] if l["tipo"] == t) for t in ("licencias", "viajes"))
    r = client.post(f"{URL}/{b['id']}/transfers", headers=auth(pm_token),
                    json={"desde_linea_id": lic, "hacia_linea_id": via, "importe": 400, "motivo": "más viajes"})
    assert r.status_code == 400 and "quedan 300" in r.json()["detail"]
    t = client.post(f"{URL}/{b['id']}/transfers", headers=auth(pm_token),
                    json={"desde_linea_id": lic, "hacia_linea_id": via, "importe": 150, "motivo": "más viajes"}).json()["data"]
    assert client.post(f"/api/v1/budget-transfers/{t['id']}/decision", headers=auth(pm_token),
                       json={"aprobado": True}).status_code == 403
    r = client.post(f"/api/v1/budget-transfers/{t['id']}/decision", headers=auth(admin_token), json={"aprobado": True})
    assert r.status_code == 200, r.text
    d = client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]
    meses = {l["tipo"]: l["meses"] for l in d["lineas"]}
    assert meses["licencias"]["2026-01"] == 100 and meses["licencias"]["2026-04"] == 50   # los pasados no se tocan
    assert meses["viajes"]["2026-06"] == 150 and d["total_plan"] == 1200
    # Ampliación (sin origen) que pide el admin: él no la decide.
    t = client.post(f"{URL}/{b['id']}/transfers", headers=auth(admin_token),
                    json={"hacia_tipo": "material", "importe": 90, "motivo": "portátil"}).json()["data"]
    assert client.post(f"/api/v1/budget-transfers/{t['id']}/decision", headers=auth(admin_token),
                       json={"aprobado": True}).status_code == 403
    assert client.get(f"{URL}/{b['id']}", headers=auth(admin_token)).json()["data"]["seguir"]["traspasos_pendientes"] == 1


def test_el_presupuesto_aprobado_es_la_base_del_proyecto(client, db, admin_token, proyecto, abril):
    _aprobado(client, admin_token)
    db.expire_all()
    assert db.get(Project, "p-b1").budget_amount == 1200


def test_alertas_de_consumo_y_prevision(client, db, admin_token, proyecto, abril):
    from app.models.alert import Alert, AlertType
    from app.services.alert_service import AlertEngine
    _aprobado(client, admin_token)
    pm = db.query(User).filter(User.username == "pm_test").one()
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=date(2026, 2, 3), hours=20,
                      cost_amount=1100, organization_id="1", description="x"))    # 92 % (aviso al 90 %, crítica al 100 %)
    db.commit()
    AlertEngine(db).run_all()      # la del proyecto (sólo imputaciones) no se suma: lo vigila su presupuesto
    tipos = {a.alert_type for a in db.query(Alert).filter(Alert.project_id == "p-b1").all()}
    assert tipos == {AlertType.budget_exceeded, AlertType.budget_forecast_overrun}
    AlertEngine(db).run_all()
    assert db.query(Alert).filter(Alert.project_id == "p-b1").count() == 2


def test_detalle_hasta_la_imputacion_y_csv(client, db, admin_token, proyecto, abril):
    b = _aprobado(client, admin_token)
    pm = db.query(User).filter(User.username == "pm_test").one()
    db.add(Imputation(id=str(uuid.uuid4()), user_id=pm.id, project_id="p-b1", date=date(2026, 3, 3), hours=2,
                      cost_amount=80, organization_id="1", description="reunión"))
    db.commit()
    _gasto(db, 30, date(2026, 3, 5))
    _gasto(db, 20, date(2026, 3, 6), categoria="software")
    r = client.get(f"{URL}/{b['id']}/drilldown", params={"mes": "2026-03"}, headers=auth(admin_token)).json()
    assert sorted((x["origen"], x["tipo"], x["importe"]) for x in r["items"]) == [
        ("gasto", "licencias", 20), ("gasto", "viajes", 30), ("imputacion", "personal", 80)]
    r = client.get(f"{URL}/{b['id']}/drilldown", params={"mes": "2026-03", "tipo": "viajes"}, headers=auth(admin_token)).json()
    assert [x["origen"] for x in r["items"]] == ["gasto"]
    csv = client.get(f"{URL}/{b['id']}/export.csv", headers=auth(admin_token)).text
    assert csv.splitlines()[0] == '"mes","tipo","plan","real","comprometido","prevision","cerrado"'
    assert '"2026-03","viajes","100.00","30.00","0.00","30.00","no"' in csv     # mes pasado: la previsión es el real


def test_cuadro_de_control_con_semaforo(client, db, admin_token, proyecto, abril):
    b = _aprobado(client, admin_token)
    r = client.get(f"{URL}/control-board", params={"year": 2026}, headers=auth(admin_token)).json()["items"]
    assert [(x["id"], x["semaforo"]) for x in r] == [(b["id"], "ambar")]    # quedan meses por cerrar
    _gasto(db, 1300, date(2026, 2, 10))
    r = client.get(f"{URL}/control-board", params={"year": 2026}, headers=auth(admin_token)).json()["items"]
    assert (r[0]["semaforo"], r[0]["consumo_pct"]) == ("rojo", pytest.approx(108.3, abs=0.1))
    assert db.get(Budget, b["id"]).estado == "aprobado"
