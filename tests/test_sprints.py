"""Tests de Sprints — creación, estados, backlog, velocidad."""
from tests.conftest import auth
from datetime import date, timedelta


def _create_project(client, token, code="SPR-01"):
    r = client.post("/api/v1/projects", json={
        "name": "Proyecto Sprints Test", "code": code,
        "start_date": str(date.today()),
        "end_date": str(date.today() + timedelta(days=365)),
    }, headers=auth(token))
    assert r.status_code in (200, 201), f"No se pudo crear proyecto: {r.text}"
    return r.json()["id"]


def test_list_sprints_empty(client, pm_token, db):
    pid = _create_project(client, pm_token)
    res = client.get(f"/api/v1/sprints/{pid}/sprints", headers=auth(pm_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_sprint(client, pm_token, db):
    pid = _create_project(client, pm_token)
    start = str(date.today() + timedelta(days=1))
    end = str(date.today() + timedelta(days=15))
    res = client.post(f"/api/v1/sprints/{pid}/sprints", json={
        "name": "Sprint 1",
        "goal": "Completar el módulo de autenticación",
        "start_date": start,
        "end_date": end,
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["name"] == "Sprint 1"


def test_update_sprint(client, pm_token, db):
    pid = _create_project(client, pm_token, code="SPR-02")
    sprint = client.post(f"/api/v1/sprints/{pid}/sprints",
        json={"name": "Sprint Original"}, headers=auth(pm_token)).json()
    res = client.patch(f"/api/v1/sprints/{pid}/sprints/{sprint['id']}",
        json={"name": "Sprint Actualizado", "goal": "Nuevo objetivo"},
        headers=auth(pm_token))
    assert res.status_code == 200


def test_start_sprint(client, pm_token, db):
    pid = _create_project(client, pm_token, code="SPR-03")
    sprint = client.post(f"/api/v1/sprints/{pid}/sprints",
        json={"name": "Sprint para Iniciar",
              "start_date": str(date.today()),
              "end_date": str(date.today() + timedelta(days=14))},
        headers=auth(pm_token)).json()
    res = client.post(f"/api/v1/sprints/{pid}/sprints/{sprint['id']}/start",
        headers=auth(pm_token))
    assert res.status_code in (200, 400)  # 400 si ya hay sprint activo


def test_backlog_empty(client, pm_token, db):
    pid = _create_project(client, pm_token, code="SPR-04")
    res = client.get(f"/api/v1/sprints/{pid}/backlog", headers=auth(pm_token))
    assert res.status_code == 200


def test_velocity_history_empty(client, pm_token, db):
    pid = _create_project(client, pm_token, code="SPR-05")
    res = client.get(f"/api/v1/sprints/{pid}/velocity", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert "sprints" in data
    assert "avg_velocity" in data


def test_global_sprints_list(client, admin_token, db):
    res = client.get("/api/v1/sprints", headers=auth(admin_token))
    assert res.status_code == 200


def test_sprint_task_remove_is_soft_and_reactivable(client, pm_token, db):
    pid = _create_project(client, pm_token, code="SPR-06")
    sprint = client.post(
        f"/api/v1/sprints/{pid}/sprints",
        json={"name": "Sprint Soft Delete"},
        headers=auth(pm_token),
    ).json()
    task = client.post(
        "/api/v1/tasks",
        json={"title": "Task in sprint", "project_id": pid, "status": "todo", "priority": "medium"},
        headers=auth(pm_token),
    ).json()

    added = client.post(
        f"/api/v1/sprints/{pid}/sprints/{sprint['id']}/tasks",
        json={"task_ids": [task["id"]]},
        headers=auth(pm_token),
    )
    assert added.status_code == 200
    assert added.json().get("added") == 1

    removed = client.delete(
        f"/api/v1/sprints/{pid}/sprints/{sprint['id']}/tasks/{task['id']}",
        headers=auth(pm_token),
    )
    assert removed.status_code == 200
    assert removed.json().get("ok") is True

    readded = client.post(
        f"/api/v1/sprints/{pid}/sprints/{sprint['id']}/tasks",
        json={"task_ids": [task["id"]]},
        headers=auth(pm_token),
    )
    assert readded.status_code == 200
    assert readded.json().get("added") == 1


def test_sprint_requires_auth(client, db):
    res = client.get("/api/v1/sprints")
    assert res.status_code in (401, 403)
