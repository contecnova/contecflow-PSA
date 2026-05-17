"""Tests de tareas — CRUD, estados, asignación."""
from tests.conftest import auth

from app.models.advanced_config import NumberingSequence


def _unwrap_items(payload):
    return payload if isinstance(payload, list) else payload.get("items", [])

def make_project(client, token):
    r = client.post("/api/v1/projects", json={"name":"P","code":"TSK","status":"active","billing_type":"time_material"}, headers=auth(token))
    return r.json()["id"]

def test_create_task(client, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.post("/api/v1/tasks", json={
        "title": "Tarea de prueba", "project_id": pid,
        "status": "todo", "priority": "medium",
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    assert res.json()["title"] == "Tarea de prueba"
    assert res.json()["code"] == "TSK-00001"


def test_task_codes_use_transactional_sequence(client, pm_token, db):
    pid = make_project(client, pm_token)
    first = client.post("/api/v1/tasks", json={
        "title": "T1", "project_id": pid, "status": "todo", "priority": "medium",
    }, headers=auth(pm_token))
    second = client.post("/api/v1/tasks", json={
        "title": "T2", "project_id": pid, "status": "todo", "priority": "medium",
    }, headers=auth(pm_token))

    assert first.status_code in (200, 201)
    assert second.status_code in (200, 201)
    assert first.json()["code"] == "TSK-00001"
    assert second.json()["code"] == "TSK-00002"

    seq = db.query(NumberingSequence).filter(NumberingSequence.entity == "task").first()
    assert seq is not None
    assert seq.current_value == 2

def test_list_tasks_by_project(client, pm_token, db):
    pid = make_project(client, pm_token)
    client.post("/api/v1/tasks", json={"title":"T1","project_id":pid,"status":"todo","priority":"low"}, headers=auth(pm_token))
    client.post("/api/v1/tasks", json={"title":"T2","project_id":pid,"status":"in_progress","priority":"high"}, headers=auth(pm_token))
    res = client.get(f"/api/v1/tasks?project_id={pid}", headers=auth(pm_token))
    assert res.status_code == 200
    tasks = res.json() if isinstance(res.json(), list) else res.json().get("items", [])
    assert len(tasks) >= 2

def test_update_task_status(client, pm_token, db):
    pid = make_project(client, pm_token)
    task = client.post("/api/v1/tasks", json={"title":"T","project_id":pid,"status":"todo","priority":"medium"}, headers=auth(pm_token)).json()
    res = client.patch(f"/api/v1/tasks/{task['id']}", json={"status":"done"}, headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["status"] == "done"

def test_task_requires_auth(client, db):
    res = client.get("/api/v1/tasks")
    assert res.status_code in (401, 403)

def test_bulk_dates_update(client, pm_token, db):
    pid = make_project(client, pm_token)
    task = client.post("/api/v1/tasks", json={"title":"T","project_id":pid,"status":"todo","priority":"medium"}, headers=auth(pm_token)).json()
    res = client.post("/api/v1/tasks/bulk-dates", json={
        "updates": [{"id": task["id"], "start_date": "2025-01-01", "due_date": "2025-01-31"}]
    }, headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["updated"] >= 1

def test_delete_task(client, pm_token, db):
    pid = make_project(client, pm_token)
    task = client.post("/api/v1/tasks", json={"title":"T","project_id":pid,"status":"todo","priority":"medium"}, headers=auth(pm_token)).json()
    res = client.delete(f"/api/v1/tasks/{task['id']}", headers=auth(pm_token))
    assert res.status_code in (200, 204)


def test_task_dependency_remove_is_soft_and_reactivable(client, pm_token, db):
    pid = make_project(client, pm_token)
    t1 = client.post(
        "/api/v1/tasks",
        json={"title": "T1", "project_id": pid, "status": "todo", "priority": "medium"},
        headers=auth(pm_token),
    ).json()
    t2 = client.post(
        "/api/v1/tasks",
        json={"title": "T2", "project_id": pid, "status": "todo", "priority": "medium"},
        headers=auth(pm_token),
    ).json()

    created = client.post(
        "/api/v1/tasks/dependencies",
        json={"predecessor_id": t1["id"], "successor_id": t2["id"], "dependency_type": "FS", "lag_days": 0},
        headers=auth(pm_token),
    )
    assert created.status_code == 201
    dep_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/tasks/dependencies/{dep_id}", headers=auth(pm_token))
    assert deleted.status_code == 200
    assert deleted.json().get("ok") is True

    listed_after_delete = client.get(f"/api/v1/tasks/dependencies/{pid}", headers=auth(pm_token))
    assert listed_after_delete.status_code == 200
    items = _unwrap_items(listed_after_delete.json())
    assert all(dep["id"] != dep_id for dep in items)

    recreated = client.post(
        "/api/v1/tasks/dependencies",
        json={"predecessor_id": t1["id"], "successor_id": t2["id"], "dependency_type": "FS", "lag_days": 1},
        headers=auth(pm_token),
    )
    assert recreated.status_code == 201
    assert recreated.json()["id"] == dep_id
    assert recreated.json()["lag_days"] == 1
