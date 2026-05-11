"""Tests de Automatizaciones — reglas, ejecución, plantillas."""
from app.models.automations import AutomationRule
from tests.conftest import auth


def test_list_automations_empty(client, admin_token, db):
    res = client.get("/api/v1/automations", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_automation(client, admin_token, db):
    res = client.post("/api/v1/automations", json={
        "name": "Notificación tarea vencida",
        "trigger_type": "task_overdue",
        "trigger_conditions": {"days_overdue": 3},
        "actions": [
            {"type": "notify_assignee", "message": "Tu tarea lleva {days} días vencida"}
        ],
        "is_active": True,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["name"] == "Notificación tarea vencida"


def test_update_automation(client, admin_token, db):
    rule = client.post("/api/v1/automations", json={
        "name": "Regla a Editar",
        "trigger_type": "task_overdue",
        "actions": [{"type": "notify_assignee"}],
    }, headers=auth(admin_token)).json()
    res = client.patch(f"/api/v1/automations/{rule['id']}",
        json={"is_active": False, "name": "Regla Desactivada"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_automation(client, admin_token, db):
    rule = client.post("/api/v1/automations", json={
        "name": "Regla a Borrar",
        "trigger_type": "task_overdue",
        "actions": [{"type": "notify_assignee"}],
    }, headers=auth(admin_token)).json()
    res = client.delete(f"/api/v1/automations/{rule['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert payload["ok"] is True

    listed = client.get("/api/v1/automations", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(r["id"] != rule["id"] for r in listed.json())

    row = db.query(AutomationRule).filter(AutomationRule.id == rule["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_automation_templates(client, admin_token, db):
    res = client.get("/api/v1/automations/templates/list", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_automation_executions(client, admin_token, db):
    rule = client.post("/api/v1/automations", json={
        "name": "Regla con historial",
        "trigger_type": "task_overdue",
        "actions": [{"type": "notify_assignee"}],
    }, headers=auth(admin_token)).json()
    res = client.get(f"/api/v1/automations/{rule['id']}/executions",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_automation_requires_admin(client, dev_token, db):
    res = client.post("/api/v1/automations", json={
        "name": "No autorizado",
        "trigger_type": "task_overdue",
        "actions": [],
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)
