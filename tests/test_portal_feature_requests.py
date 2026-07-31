"""Tests del flujo portal/backoffice de Feature Requests.

Cubre:
- Cliente portal con multi-proyecto puede crear FR para un proyecto concreto.
- Equipo interno puede estimar (requiere pm_response) y el cliente aprobar.
- El backoffice puede iniciar desarrollo/marcar done sin pm_response.

Estos tests evitan regresiones del botón "🚀 Iniciar desarrollo" en backoffice.
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


def test_portal_fr_multi_project_estimate_approve_start_dev(client, pm_token, db):
    # 1) Dos proyectos
    p1 = _create_project(client, pm_token, code="PORT1", name="Portal Project 1")
    p2 = _create_project(client, pm_token, code="PORT2", name="Portal Project 2")

    # 2) Usuario portal con acceso a ambos proyectos
    client_email = "portal.user@test.com"
    client_password = "ClientPass123!"
    create_res = client.post(
        "/api/v1/portal/clients",
        json={
            "project_ids": [p1, p2],
            "full_name": "Portal User",
            "email": client_email,
            "password": client_password,
            "can_request_changes": True,
            "language": "es",
        },
        headers=auth(pm_token),
    )
    assert create_res.status_code == 200, create_res.text

    # 3) Login portal (cookie)
    login_res = client.post(
        "/api/v1/portal/auth/login",
        json={"email": client_email, "password": client_password},
    )
    assert login_res.status_code == 200, login_res.text

    # Confirmar que el portal ve ambos proyectos
    me_res = client.get("/api/v1/portal/auth/me")
    assert me_res.status_code == 200, me_res.text
    me = me_res.json()["data"]
    assert set(me.get("project_ids") or []) == {p1, p2}

    # 4) Crear FR para el segundo proyecto
    fr_create = client.post(
        "/api/v1/portal/feature-requests",
        json={
            "title": "Nueva mejora portal",
            "description": "Descripción suficientemente larga para pasar validación.",
            "priority": "medium",
            "project_id": p2,
        },
    )
    assert fr_create.status_code == 200, fr_create.text
    fr = fr_create.json()["data"]
    fr_id = fr["id"]
    assert fr["project_id"] == p2
    assert fr["status"] in ("new", "reviewing")

    # 5) El equipo NO puede presupuestar sin pm_response
    bad_est = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={"status": "estimated"},
        headers=auth(pm_token),
    )
    assert bad_est.status_code == 422

    # 6) Presupuestar correctamente
    est = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={
            "pm_response": "Podemos hacerlo; estimación preliminar.",
            "estimated_hours": 12,
            "estimated_cost": 1200,
            "estimated_delivery_weeks": 2,
            "status": "estimated",
        },
        headers=auth(pm_token),
    )
    assert est.status_code == 200, est.text
    assert est.json()["data"]["status"] == "estimated"

    # 7) Cliente aprueba
    approve = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/decide",
        json={"approved": True},
    )
    assert approve.status_code == 200, approve.text
    assert approve.json()["data"]["status"] == "approved"

    # 8) Backoffice inicia desarrollo SIN pm_response (regresión del 422)
    start_dev = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={"status": "in_development"},
        headers=auth(pm_token),
    )
    assert start_dev.status_code == 200, start_dev.text
    assert start_dev.json()["data"]["status"] == "in_development"

    # 9) Backoffice marca done SIN pm_response
    done = client.post(
        f"/api/v1/portal/feature-requests/{fr_id}/respond",
        json={"status": "done"},
        headers=auth(pm_token),
    )
    assert done.status_code == 200, done.text
    assert done.json()["data"]["status"] == "done"
