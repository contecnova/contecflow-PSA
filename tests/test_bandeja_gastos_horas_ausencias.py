"""Gastos y ausencias llegan a la bandeja de aprobaciones cuando hay flujo.

Auditoria 2026-11: el disenador ofrecia estos tipos y nada abria solicitudes;
la bandeja solo veia documentos y peticiones del portal.
"""
from app.models.expenses import Expense
from app.models.resources import Absence
from tests.conftest import auth
from tests.test_approvals import add_step, create_workflow


def _bandeja(client, token):
    r = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _gasto_enviado(client, token):
    gid = client.post("/api/v1/expenses", headers=auth(token), json={
        "description": "Taxi aeropuerto", "amount": 42.0, "category": "travel",
        "expense_date": "2026-10-01", "currency": "EUR"}).json()["data"]["id"]
    r = client.post(f"/api/v1/expenses/my/{gid}/submit", headers=auth(token))
    assert r.status_code == 200, r.text
    return gid


def _flujo(client, admin_token, tipo):
    wf = create_workflow(client, admin_token, entity_type=tipo, is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")


def test_sin_flujo_no_se_abre_nada(client, admin_token, dev_token, db):
    _gasto_enviado(client, dev_token)
    assert _bandeja(client, admin_token) == []


def test_el_gasto_se_aprueba_desde_la_bandeja(client, admin_token, dev_token, db):
    _flujo(client, admin_token, "expense")
    gid = _gasto_enviado(client, dev_token)
    pendientes = [p for p in _bandeja(client, admin_token) if p["entity_id"] == gid]
    assert len(pendientes) == 1 and pendientes[0]["entity_type"] == "expense"

    r = client.post(f"/api/v1/approvals/requests/{pendientes[0]['id']}/decide",
                    json={"decision": "approved"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert str(db.query(Expense).filter(Expense.id == gid).one().status.value) == "approved"


def test_revisar_en_gastos_cierra_la_solicitud(client, admin_token, dev_token, db):
    _flujo(client, admin_token, "expense")
    gid = _gasto_enviado(client, dev_token)
    r = client.post(f"/api/v1/expenses/{gid}/review", headers=auth(admin_token),
                    json={"approved": False, "rejection_reason": "Sin ticket"})
    assert r.status_code == 200, r.text
    assert [p for p in _bandeja(client, admin_token) if p["entity_id"] == gid] == []


def test_la_ausencia_se_rechaza_desde_la_bandeja(client, admin_token, dev_token, db):
    _flujo(client, admin_token, "leave")
    r = client.post("/api/v1/absences/my", headers=auth(dev_token), json={
        "type": "vacation", "start_date": "2026-12-01", "end_date": "2026-12-05", "reason": "Viaje"})
    assert r.status_code in (200, 201), r.text
    aid = r.json()["data"]["id"]
    pendiente = next(p for p in _bandeja(client, admin_token) if p["entity_id"] == aid)
    r = client.post(f"/api/v1/approvals/requests/{pendiente['id']}/decide",
                    json={"decision": "rejected", "note": "Cierre de año"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    ausencia = db.query(Absence).filter(Absence.id == aid).one()
    assert str(ausencia.status.value) == "rejected" and ausencia.rejection_reason == "Cierre de año"


def test_el_parte_de_horas_se_aprueba_desde_la_bandeja(client, admin_token, dev_token, pm_token, db):
    from app.models.financial import Timesheet
    from tests.test_timesheets_extended import add_imputation, make_project, next_monday
    _flujo(client, admin_token, "timesheet")
    add_imputation(client, dev_token, make_project(client, pm_token), hours=8)
    r = client.post(f"/api/v1/timesheets/my/{next_monday()}/submit", headers=auth(dev_token))
    assert r.status_code == 200, r.text
    pendiente = next(p for p in _bandeja(client, admin_token) if p["entity_type"] == "timesheet")
    r = client.post(f"/api/v1/approvals/requests/{pendiente['id']}/decide",
                    json={"decision": "approved"}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    assert str(db.query(Timesheet).filter(Timesheet.id == pendiente["entity_id"]).one().status.value) == "approved"
