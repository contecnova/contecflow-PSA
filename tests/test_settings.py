"""Tests de Configuración Global — tipos de proyecto, departamentos, festivos, ajustes."""
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
    assert res.status_code in (200, 204)


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
    assert res.status_code in (200, 204)


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


def test_settings_require_admin(client, dev_token, db):
    res = client.post("/api/v1/settings/departments",
        json={"name": "No autorizado"},
        headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_task_statuses_list(client, admin_token, db):
    res = client.get("/api/v1/settings/task-statuses", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
