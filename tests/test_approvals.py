"""Tests de aprobaciones multi-nivel."""
from tests.conftest import auth

def test_list_workflows_empty(client, admin_token, db):
    res = client.get("/api/v1/approvals/workflows", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_create_workflow(client, admin_token, db):
    res = client.post("/api/v1/approvals/workflows", json={
        "name": "Aprobación gastos",
        "entity_type": "expense",
        "is_default": True,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "Aprobación gastos"
    assert data["entity_type"] == "expense"
    return data["id"]

def test_add_step_to_workflow(client, admin_token, db):
    wf = client.post("/api/v1/approvals/workflows", json={
        "name": "WF Test", "entity_type": "timesheet", "is_default": False,
    }, headers=auth(admin_token)).json()
    res = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", json={
        "step_order": 1, "name": "Manager", "approver_type": "role",
        "approver_role": "pm", "timeout_hours": 48,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "Manager"
    assert data["step_order"] == 1

def test_create_approval_request_no_default(client, dev_token, db):
    """Sin workflow default configurado, devuelve 404."""
    res = client.post("/api/v1/approvals/requests", json={
        "entity_type": "expense",
        "entity_id": "some-expense-id",
        "entity_summary": "Gasto de viaje",
    }, headers=auth(dev_token))
    assert res.status_code == 404

def test_pending_my_action_empty(client, admin_token, db):
    res = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)

def test_approval_stats(client, admin_token, db):
    res = client.get("/api/v1/approvals/stats", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "pending" in data

def test_workflow_requires_admin(client, dev_token, db):
    res = client.post("/api/v1/approvals/workflows", json={
        "name": "WF", "entity_type": "expense",
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)
