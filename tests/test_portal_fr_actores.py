"""Cada decisión con su actor en las peticiones de funcionalidad del portal (22-11-2026).

Antes el operador podía poner `approved` (el estado «lo aprobó el cliente») y la
aprobación del cliente creaba la petición de cambio ya aprobada. Ver
docs/FLUJO_DE_DEMANDA.md §1.2.
"""
from tests.conftest import auth


def _proyecto(client, token):
    r = client.post("/api/v1/projects", headers=auth(token), json={
        "name": "Portal actores", "code": "PACT1", "description": "x", "status": "active",
        "billing_type": "time_material", "is_billable": True})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _cliente(client, token, pid):
    r = client.post("/api/v1/portal/clients", headers=auth(token), json={
        "project_ids": [pid], "full_name": "Cliente Actores", "email": "actores@test.com",
        "password": "ClientPass123!", "can_request_changes": True, "language": "es"})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/portal/auth/login", json={"email": "actores@test.com", "password": "ClientPass123!"})
    assert r.status_code == 200, r.text


def test_el_operador_no_aprueba_en_nombre_del_cliente(client, pm_token, db):
    pid = _proyecto(client, pm_token)
    _cliente(client, pm_token, pid)
    fr = client.post("/api/v1/portal/feature-requests", json={
        "title": "Exportar a Excel", "description": "Exportar el informe", "project_id": pid}).json()["data"]
    r = client.post(f"/api/v1/portal/feature-requests/{fr['id']}/respond", headers=auth(pm_token),
                    json={"status": "approved", "pm_response": "Hecho por el equipo"})
    assert r.status_code == 422


def test_la_aprobacion_del_cliente_deja_la_cr_enviada(client, pm_token, db):
    from sqlalchemy import text
    pid = _proyecto(client, pm_token)
    _cliente(client, pm_token, pid)
    fr = client.post("/api/v1/portal/feature-requests", json={
        "title": "Exportar a PDF", "description": "Exportar el informe", "project_id": pid}).json()["data"]
    r = client.post(f"/api/v1/portal/feature-requests/{fr['id']}/respond", headers=auth(pm_token),
                    json={"status": "estimated", "pm_response": "Dos días", "estimated_cost": 800})
    assert r.status_code == 200, r.text
    r = client.post(f"/api/v1/portal/feature-requests/{fr['id']}/decide", json={"approved": True})
    assert r.status_code == 200, r.text
    estados = db.execute(text("SELECT status FROM change_requests WHERE project_id = :p"), {"p": pid}).fetchall()
    assert [e[0] for e in estados] == ["submitted"]
    acciones = db.execute(text("SELECT action FROM audit_logs WHERE resource_id = :i"), {"i": fr["id"]}).fetchall()
    assert {"FEATURE_REQUEST_RESPOND", "FEATURE_REQUEST_CLIENT_DECISION"} <= {a[0] for a in acciones}
