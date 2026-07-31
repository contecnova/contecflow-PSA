"""Tests de imputaciones (registro de horas)."""
from datetime import date
from tests.conftest import auth
from app.models.project import Project
from app.models.imputation import Imputation


def _create_project(client, token):
    res = client.post("/api/v1/projects", json={
        "name": "Proyecto Imputaciones Test",
        "code": "IMP-01",
        "start_date": str(date.today()),
        "end_date": "2025-12-31",
    }, headers=auth(token))
    assert res.status_code in (200, 201), f"No se pudo crear proyecto: {res.text}"
    project_id = res.json()["data"]["id"]
    # Strict assignment: explicit member required to impute.
    client.post(
        f"/api/v1/projects/{project_id}/members",
        json={"user_id": "dev-test-id", "role": "developer"},
        headers=auth(token),
    )
    return project_id


def test_log_hours(client, admin_token, dev_token, db):
    pid = _create_project(client, admin_token)
    res = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": pid,
        "date": str(date.today()),
        "hours": 4.0,
        "description": "Trabajo realizado hoy",
    })
    assert res.status_code in (200, 201)
    assert res.json()["data"]["hours"] == 4.0


def test_log_hours_exceeds_24(client, admin_token, dev_token, db):
    pid = _create_project(client, admin_token)
    client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": pid, "date": str(date.today()), "hours": 20.0,
    })
    res = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": pid, "date": str(date.today()), "hours": 8.0,
    })
    assert res.status_code == 400


def test_list_my_imputations(client, dev_token, db):
    res = client.get("/api/v1/imputations/my/week", headers=auth(dev_token))
    assert res.status_code == 200


def test_imputation_requires_auth(client, db):
    res = client.get("/api/v1/imputations/my/week")
    assert res.status_code in (401, 403)


def test_delete_imputation(client, admin_token, dev_token, db):
    pid = _create_project(client, admin_token)
    create = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": pid, "date": str(date.today()), "hours": 2.0,
    })
    assert create.status_code in (200, 201)
    iid = create.json()["data"]["id"]
    res = client.delete(f"/api/v1/imputations/{iid}", headers=auth(dev_token))
    assert res.status_code in (200, 204)


def test_manager_can_reject_imputation(client, admin_token, dev_token, pm_token, db):
    pid = _create_project(client, admin_token)
    project = db.query(Project).filter(Project.id == pid).first()
    project.pm_id = "pm-test-id"
    db.commit()

    create = client.post("/api/v1/imputations", headers=auth(dev_token), json={
        "project_id": pid,
        "date": str(date.today()),
        "hours": 2.0,
        "description": "Imputación para rechazo",
    })
    assert create.status_code in (200, 201)
    iid = create.json()["data"]["id"]

    res = client.post(f"/api/v1/imputations/{iid}/reject", headers=auth(pm_token))
    assert res.status_code == 200

    imp = db.query(Imputation).filter(Imputation.id == iid).first()
    assert imp is not None
    assert imp.is_approved is False
    assert imp.approved_by is None
    assert imp.approved_at is None
