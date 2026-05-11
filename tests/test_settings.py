"""Tests de Configuración Global — tipos de proyecto, departamentos, festivos, ajustes."""
from app.models.settings import CustomProjectType
from app.models.settings import Department
from app.models.settings import Holiday
from tests.conftest import auth


def test_get_general_settings(client, admin_token, db):
    res = client.get("/api/v1/settings/general", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), (list, dict))


def test_list_project_types(client, admin_token, db):
    res = client.get("/api/v1/settings/project-types", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_project_type(client, admin_token, db):
    res = client.post("/api/v1/settings/project-types",
        json={"label": "Consultoría", "value": "consulting", "color": "#0070F3"},
        headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data


def test_update_project_type(client, admin_token, db):
    created = client.post("/api/v1/settings/project-types",
        json={"label": "Tipo a Editar", "value": "edit_type"},
        headers=auth(admin_token)).json()
    res = client.patch(f"/api/v1/settings/project-types/{created['id']}",
        json={"label": "Tipo Editado", "value": "edit_type", "color": "#FF0000"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_project_type(client, admin_token, db):
    created = client.post("/api/v1/settings/project-types",
        json={"label": "Tipo a Borrar", "value": "delete_type"},
        headers=auth(admin_token)).json()
    res = client.delete(f"/api/v1/settings/project-types/{created['id']}",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    listed = client.get("/api/v1/settings/project-types", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(pt["id"] != created["id"] for pt in listed.json())

    row = db.query(CustomProjectType).filter(CustomProjectType.id == created["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_list_departments(client, admin_token, db):
    res = client.get("/api/v1/settings/departments", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_department(client, admin_token, db):
    res = client.post("/api/v1/settings/departments",
        json={"name": "Ingeniería de Software"},
        headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data


def test_delete_department(client, admin_token, db):
    dept = client.post("/api/v1/settings/departments",
        json={"name": "Dpto a Borrar"},
        headers=auth(admin_token)).json()
    res = client.delete(f"/api/v1/settings/departments/{dept['id']}",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    listed = client.get("/api/v1/settings/departments", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(d["id"] != dept["id"] for d in listed.json())

    row = db.query(Department).filter(Department.id == dept["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_list_holidays(client, admin_token, db):
    res = client.get("/api/v1/settings/holidays", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_holiday(client, admin_token, db):
    res = client.post("/api/v1/settings/holidays",
        json={"name": "Día de la Hispanidad", "date": "2025-10-12"},
        headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data


def test_delete_holiday_hard_and_hidden(client, admin_token, db):
    created = client.post(
        "/api/v1/settings/holidays",
        json={"name": "Fiesta Borrable", "date": "2026-12-08"},
        headers=auth(admin_token),
    ).json()
    res = client.delete(f"/api/v1/settings/holidays/{created['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True

    listed = client.get("/api/v1/settings/holidays", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(h["id"] != created["id"] for h in listed.json())

    row = db.query(Holiday).filter(Holiday.id == created["id"]).first()
    assert row is None


def test_settings_require_admin(client, dev_token, db):
    res = client.post("/api/v1/settings/departments",
        json={"name": "No autorizado"},
        headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_task_statuses_list(client, admin_token, db):
    res = client.get("/api/v1/settings/task-statuses", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
