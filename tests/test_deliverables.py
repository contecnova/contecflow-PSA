"""Tests de Entregables — ciclo de vida completo: crear, entregar, aceptar, rechazar."""
from tests.conftest import auth
from datetime import date, timedelta


def _create_project(client, token, code="DEL-01"):
    r = client.post("/api/v1/projects", json={
        "name": "Proyecto Entregables Test", "code": code,
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=180)),
    }, headers=auth(token))
    assert r.status_code in (200, 201)
    return r.json()["id"]


def test_list_deliverables_empty(client, pm_token, db):
    pid = _create_project(client, pm_token)
    res = client.get(f"/api/v1/deliverables/{pid}", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert "deliverables" in data
    assert isinstance(data["deliverables"], list)


def test_create_deliverable(client, pm_token, db):
    pid = _create_project(client, pm_token)
    res = client.post(f"/api/v1/deliverables/{pid}", json={
        "name": "Informe Técnico v1.0",
        "description": "Documento de especificaciones técnicas",
        "format": "PDF",
        "planned_date": str(date.today() + timedelta(days=30)),
        "acceptance_criteria": "Aprobado por director técnico",
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["name"] == "Informe Técnico v1.0"


def test_update_deliverable(client, pm_token, db):
    pid = _create_project(client, pm_token, code="DEL-02")
    deliv = client.post(f"/api/v1/deliverables/{pid}",
        json={"name": "Entregable Original"},
        headers=auth(pm_token)).json()
    res = client.patch(f"/api/v1/deliverables/{pid}/{deliv['id']}",
        json={"name": "Entregable Actualizado", "format": "Excel"},
        headers=auth(pm_token))
    assert res.status_code == 200


def test_deliverable_lifecycle(client, pm_token, admin_token, db):
    """Ciclo completo: crear → entregar → aceptar."""
    pid = _create_project(client, pm_token, code="DEL-03")
    deliv = client.post(f"/api/v1/deliverables/{pid}",
        json={"name": "Entregable Ciclo"},
        headers=auth(pm_token)).json()
    did = deliv["id"]

    # Marcar como entregado
    res = client.post(f"/api/v1/deliverables/{pid}/{did}/deliver",
        headers=auth(pm_token))
    assert res.status_code == 200

    # Aceptar el entregable
    res = client.post(f"/api/v1/deliverables/{pid}/{did}/accept",
        json={"notes": "Cumple criterios de aceptación"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_deliverable_lifecycle_reject(client, pm_token, admin_token, db):
    """Ciclo de rechazo: crear → entregar → rechazar."""
    pid = _create_project(client, pm_token, code="DEL-04")
    deliv = client.post(f"/api/v1/deliverables/{pid}",
        json={"name": "Entregable Rechazado"},
        headers=auth(pm_token)).json()
    did = deliv["id"]

    client.post(f"/api/v1/deliverables/{pid}/{did}/deliver", headers=auth(pm_token))
    res = client.post(f"/api/v1/deliverables/{pid}/{did}/reject",
        params={"reason": "No cumple los requisitos de formato"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_deliverable(client, pm_token, db):
    pid = _create_project(client, pm_token, code="DEL-05")
    deliv = client.post(f"/api/v1/deliverables/{pid}",
        json={"name": "Entregable a Borrar"},
        headers=auth(pm_token)).json()
    res = client.delete(f"/api/v1/deliverables/{pid}/{deliv['id']}",
        headers=auth(pm_token))
    assert res.status_code in (200, 204)


def test_deliverables_overview(client, admin_token, db):
    """Vista global de todos los entregables."""
    res = client.get("/api/v1/deliverables/all/overview", headers=auth(admin_token))
    assert res.status_code == 200
