"""Extended tests for Automations — run-scheduled, test-rule, fire-trigger actions."""
from tests.conftest import auth


def make_rule(client, token, name="Test Rule", trigger="task_overdue", actions=None):
    if actions is None:
        actions = [{"type": "create_alert", "params": {"title": "Triggered", "severity": "warning"}}]
    res = client.post("/api/v1/automations", json={
        "name": name,
        "trigger_type": trigger,
        "actions": actions,
    }, headers=auth(token))
    assert res.status_code in (200, 201)
    return res.json()


# ── List with filters ──────────────────────────────────────────────────────

def test_list_automations_active_filter(client, pm_token, db):
    make_rule(client, pm_token, name="Active Rule")
    res = client.get("/api/v1/automations?is_active=true", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert all(r["is_active"] for r in data)


def test_list_automations_inactive_filter(client, pm_token, db):
    rule = make_rule(client, pm_token, name="To Disable")
    client.patch(f"/api/v1/automations/{rule['id']}",
        json={"is_active": False}, headers=auth(pm_token))
    res = client.get("/api/v1/automations?is_active=false", headers=auth(pm_token))
    res.json()
    assert res.status_code == 200


# ── Run Scheduled ──────────────────────────────────────────────────────────

def test_run_scheduled_admin(client, admin_token, db):
    res = client.post("/api/v1/automations/run-scheduled", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "executed" in data
    assert "errors" in data


def test_run_scheduled_requires_admin(client, pm_token, db):
    res = client.post("/api/v1/automations/run-scheduled", headers=auth(pm_token))
    assert res.status_code in (401, 403)


# ── Test Rule Manually ─────────────────────────────────────────────────────

def test_test_rule(client, pm_token, db):
    rule = make_rule(client, pm_token, name="Testable Rule")
    res = client.post(f"/api/v1/automations/{rule['id']}/test", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "results" in data


def test_test_rule_not_found(client, pm_token, db):
    res = client.post("/api/v1/automations/nonexistent-id/test", headers=auth(pm_token))
    assert res.status_code == 404


def test_test_rule_with_notify_role_action(client, pm_token, db):
    rule = make_rule(client, pm_token, name="Notify PM Rule", actions=[
        {"type": "notify_role", "params": {"role": "pm", "message": "Test notification"}}
    ])
    res = client.post(f"/api/v1/automations/{rule['id']}/test", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["ok"] is True


def test_test_rule_with_notify_user_action(client, pm_token, db):
    rule = make_rule(client, pm_token, name="Notify User Rule", actions=[
        {"type": "notify_user", "params": {"user_id": "pm-test-id", "message": "Hello!"}}
    ])
    res = client.post(f"/api/v1/automations/{rule['id']}/test", headers=auth(pm_token))
    assert res.status_code == 200


# ── Templates ──────────────────────────────────────────────────────────────

def test_automation_templates_structure(client, pm_token, db):
    res = client.get("/api/v1/automations/templates/list", headers=auth(pm_token))
    assert res.status_code == 200
    templates = res.json()
    assert len(templates) >= 5
    for t in templates:
        assert "id" in t
        assert "name" in t
        assert "trigger_type" in t
        assert "actions" in t


# ── Executions ─────────────────────────────────────────────────────────────

def test_executions_after_test(client, pm_token, db):
    rule = make_rule(client, pm_token, name="Rule With Exec")
    client.post(f"/api/v1/automations/{rule['id']}/test", headers=auth(pm_token))
    res = client.get(f"/api/v1/automations/{rule['id']}/executions", headers=auth(pm_token))
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 1
    assert "executed_at" in data[0]
    assert "success" in data[0]


def test_executions_limit(client, pm_token, db):
    rule = make_rule(client, pm_token, name="Rule Limit Test")
    # Fire 3 times
    for _ in range(3):
        client.post(f"/api/v1/automations/{rule['id']}/test", headers=auth(pm_token))
    res = client.get(f"/api/v1/automations/{rule['id']}/executions?limit=2", headers=auth(pm_token))
    assert res.status_code == 200
    assert len(res.json()) <= 2


# ── Rule with project scope ────────────────────────────────────────────────

def test_create_automation_with_project(client, pm_token, db):
    project = client.post("/api/v1/projects", json={
        "name": "Auto Project", "code": "AUTO1",
        "status": "active", "billing_type": "time_material",
    }, headers=auth(pm_token)).json()

    res = client.post("/api/v1/automations", json={
        "name": "Project-scoped rule",
        "trigger_type": "task_overdue",
        "project_id": project["id"],
        "actions": [{"type": "create_alert", "params": {"title": "Overdue"}}],
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    assert res.json()["project_id"] == project["id"]


def test_list_automations_by_project(client, pm_token, db):
    project = client.post("/api/v1/projects", json={
        "name": "Filter Project", "code": "FP01",
        "status": "active", "billing_type": "time_material",
    }, headers=auth(pm_token)).json()

    client.post("/api/v1/automations", json={
        "name": "Scoped",
        "trigger_type": "task_overdue",
        "project_id": project["id"],
        "actions": [{"type": "create_alert"}],
    }, headers=auth(pm_token))

    res = client.get(f"/api/v1/automations?project_id={project['id']}", headers=auth(pm_token))
    assert res.status_code == 200
