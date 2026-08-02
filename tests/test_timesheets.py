"""Tests de timesheets — registro de horas, aprobación."""
from tests.conftest import auth
from datetime import date

def make_project(client, token):
    r = client.post("/api/v1/projects", json={"name":"P","code":"IMP","status":"active","billing_type":"time_material"}, headers=auth(token))
    pid = r.json()["data"]["id"]
    client.post(
        f"/api/v1/projects/{pid}/members",
        json={"user_id": "dev-test-id", "role": "developer"},
        headers=auth(token),
    )
    return pid

def test_create_imputation(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.post("/api/v1/imputations", json={
        "project_id": pid,
        "date": str(date.today()),
        "hours": 4.5,
        "description": "Desarrollo feature X",
        "is_billable": True,
    }, headers=auth(dev_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert data["hours"] == 4.5
    assert data["is_billable"] is True

def test_list_imputations(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token)
    client.post("/api/v1/imputations", json={"project_id":pid,"date":str(date.today()),"hours":2,"description":"a","is_billable":True}, headers=auth(dev_token))
    res = client.get("/api/v1/imputations", headers=auth(dev_token))
    assert res.status_code == 200

def test_imputation_negative_hours_rejected(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.post("/api/v1/imputations", json={
        "project_id": pid, "date": str(date.today()),
        "hours": -1, "description": "Negativo", "is_billable": True,
    }, headers=auth(dev_token))
    assert res.status_code in (400, 422)

def test_imputation_too_many_hours(client, dev_token, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.post("/api/v1/imputations", json={
        "project_id": pid, "date": str(date.today()),
        "hours": 25, "description": "Muchas horas", "is_billable": True,
    }, headers=auth(dev_token))
    assert res.status_code in (400, 422)

def test_imputation_requires_auth(client, db):
    res = client.post("/api/v1/imputations", json={})
    assert res.status_code in (401, 403)
