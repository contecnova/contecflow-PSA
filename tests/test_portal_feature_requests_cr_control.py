"""
Test: Iniciar desarrollo de FR NO crea ChangeRequest si no está aprobada por el cliente.
"""
from tests.conftest import auth

def _create_project(client, token, code: str, name: str):
    payload = {
        "name": name,
        "code": code,
        "description": "Proyecto de prueba",
        "status": "active",
        "billing_type": "time_material",
        "is_billable": True,
    }
    res = client.post("/api/v1/projects", json=payload, headers=auth(token))
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


def test_no_cr_on_start_dev_without_approval(client, pm_token, db):
    # 1) Proyecto y usuario portal
    pid = _create_project(client, pm_token, code="PORTCR", name="Portal CR")
    client_email = "portal.cr@test.com"
    client_password = "ClientPass123!"
    create_res = client.post(
        "/api/v1/portal/clients",
        json={
            "project_ids": [pid],
            "full_name": "Portal CR",
            "email": client_email,
            "password": client_password,
            "can_request_changes": True,
            "language": "es",
        },
        headers=auth(pm_token),
    )
    assert create_res.status_code == 200, create_res.text

    # 2) Login portal
    login_res = client.post(
        "/api/v1/portal/auth/login",
        json={"email": client_email, "password": client_password},
    )
    assert login_res.status_code == 200, login_res.text

    # 3) Crear FR
    fr_create = client.post(
        "/api/v1/portal/feature-requests",
        json={
            "title": "CR no debe crearse",
            "description": "Test de control de cambios.",
            "priority": "medium",
            "project_id": pid,
        },
    )
    assert fr_create.status_code == 200, fr_create.text
    fr_id = fr_create.json()["data"]["id"]

    # 4) Estimar
    est = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={
            "pm_response": "Estimación para test CR.",
            "estimated_hours": 5,
            "estimated_cost": 500,
            "estimated_delivery_weeks": 1,
            "status": "estimated",
        },
        headers=auth(pm_token),
    )
    assert est.status_code == 200, est.text

    # 5) Iniciar desarrollo SIN aprobación cliente
    start_dev = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={"status": "in_development"},
        headers=auth(pm_token),
    )
    assert start_dev.status_code == 200, start_dev.text
    assert start_dev.json()["data"]["status"] == "in_development"

    # 6) Verificar que NO existe ChangeRequest para ese proyecto
    from sqlalchemy import text
    crs = db.execute(
        text("SELECT * FROM change_requests WHERE project_id = :pid"),
        {"pid": pid}
    ).fetchall()
    assert len(crs) == 0, f"Se creó un ChangeRequest sin aprobación del cliente: {crs}"
