"""Tests de Automatizaciones — reglas, ejecución, plantillas."""
from app.models.automations import AutomationRule
from tests.conftest import auth


def test_list_automations_empty(client, admin_token, db):
    res = client.get("/api/v1/automations", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    items = payload.get("items") if isinstance(payload, dict) else payload
    assert isinstance(items, list)


def test_create_automation(client, admin_token, db):
    res = client.post("/api/v1/automations", json={
        "name": "Notificación tarea vencida",
        "trigger_type": "task_overdue",
        "trigger_conditions": {"field": "days_overdue", "operator": "greater_than", "value": "3"},
        "actions": [
            {"type": "notify_user", "params": {"message": "Tu tarea lleva días vencida"}}
        ],
        "is_active": True,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert "id" in data
    assert data["name"] == "Notificación tarea vencida"


def test_update_automation(client, admin_token, db):
    rule = client.post("/api/v1/automations", json={
        "name": "Regla a Editar",
        "trigger_type": "task_overdue",
        "actions": [{"type": "notify_user", "params": {"message": "Vencida"}}],
    }, headers=auth(admin_token)).json()["data"]
    res = client.patch(f"/api/v1/automations/{rule['id']}",
        json={"is_active": False, "name": "Regla Desactivada"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_automation(client, admin_token, db):
    rule = client.post("/api/v1/automations", json={
        "name": "Regla a Borrar",
        "trigger_type": "task_overdue",
        "actions": [{"type": "notify_user", "params": {"message": "Vencida"}}],
    }, headers=auth(admin_token)).json()["data"]
    res = client.delete(f"/api/v1/automations/{rule['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["ok"] is True

    listed = client.get("/api/v1/automations", headers=auth(admin_token))
    assert listed.status_code == 200
    listed_payload = listed.json()
    listed_items = listed_payload.get("items") if isinstance(listed_payload, dict) else listed_payload
    assert all(r["id"] != rule["id"] for r in listed_items)

    # Auditoria 2026-11: borrar borra; pausar (is_active=False) es otra cosa.
    assert db.query(AutomationRule).filter(AutomationRule.id == rule["id"]).first() is None


def test_automation_templates(client, admin_token, db):
    res = client.get("/api/v1/automations/templates/list", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json()["items"], list)


def test_automation_executions(client, admin_token, db):
    rule = client.post("/api/v1/automations", json={
        "name": "Regla con historial",
        "trigger_type": "task_overdue",
        "actions": [{"type": "notify_user", "params": {"message": "Vencida"}}],
    }, headers=auth(admin_token)).json()["data"]
    res = client.get(f"/api/v1/automations/{rule['id']}/executions",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json()["items"], list)


def test_automation_requires_admin(client, dev_token, db):
    res = client.post("/api/v1/automations", json={
        "name": "No autorizado",
        "trigger_type": "task_overdue",
        "actions": [],
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)
