from tests.conftest import auth


def _create_active_workflow(client, admin_token, step_type: str, config: dict) -> str:
    create_res = client.post(
        "/api/v1/billing-reports/automation-workflows",
        headers=auth(admin_token),
        json={
            "name": f"WF {step_type}",
            "trigger_type": "manual.provisioning",
            "is_global": True,
            "steps": [
                {
                    "step_type": "action",
                    "name": f"{step_type} step",
                    "config": config,
                }
            ],
        },
    )
    assert create_res.status_code == 201, create_res.text
    wf_id = create_res.json()["data"]["id"]

    activate_res = client.patch(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}",
        headers=auth(admin_token),
        json={"status": "active"},
    )
    assert activate_res.status_code == 200, activate_res.text
    return wf_id


def test_run_workflow_now_executes_provision_identity_step(client, admin_token, monkeypatch):
    from app.services import bookings_service as svc

    def fake_execute_provision_action(config, context):
        assert config.get("operation") == "create_ad_user"
        return {"ok": True, "action_type": "create_ad_user", "status_code": 201}

    monkeypatch.setattr(svc, "_execute_provision_action", fake_execute_provision_action)

    wf_id = _create_active_workflow(
        client,
        admin_token,
        "provision_identity",
        {
            "type": "provision_identity",
            "operation": "create_ad_user",
            "url": "https://idm.example.local/ad/users",
            "payload": {"username": "{employee_username}", "email": "{employee_email}"},
        },
    )

    run_res = client.post(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/run",
        headers=auth(admin_token),
        json={"context": {"employee_username": "jdoe", "employee_email": "jdoe@example.com"}},
    )
    assert run_res.status_code == 200, run_res.text
    out = run_res.json()["data"]
    assert out["ok"] is True
    assert out["processed"] >= 1
    assert out["errors"] == 0

    hist_res = client.get(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/executions",
        headers=auth(admin_token),
    )
    assert hist_res.status_code == 200, hist_res.text
    _hist_body = hist_res.json()
    history = _hist_body.get("items") if isinstance(_hist_body, dict) else _hist_body
    assert history
    step_log = history[0]["steps_log"][0]
    assert step_log["ok"] is True


def test_run_workflow_now_executes_terraform_step(client, admin_token, monkeypatch):
    from app.services import bookings_service as svc

    def fake_execute_terraform_action(config, context):
        assert config.get("command") == "apply"
        return {"ok": True, "action_type": "terraform", "exit_code": 0, "stdout": "apply complete"}

    monkeypatch.setattr(svc, "_execute_terraform_action", fake_execute_terraform_action)

    wf_id = _create_active_workflow(
        client,
        admin_token,
        "terraform",
        {
            "type": "terraform_apply",
            "workdir": "/iac/provisioning",
            "vars": {"username": "{employee_username}"},
        },
    )

    run_res = client.post(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/run",
        headers=auth(admin_token),
        json={"context": {"employee_username": "jdoe"}},
    )
    assert run_res.status_code == 200, run_res.text
    out = run_res.json()["data"]
    assert out["ok"] is True
    assert out["errors"] == 0


def test_run_workflow_now_executes_ansible_step(client, admin_token, monkeypatch):
    from app.services import bookings_service as svc

    def fake_execute_ansible_action(config, context):
        assert config.get("playbook") == "onboarding.yml"
        return {"ok": True, "action_type": "ansible", "exit_code": 0, "stdout": "changed=3 failed=0"}

    monkeypatch.setattr(svc, "_execute_ansible_action", fake_execute_ansible_action)

    wf_id = _create_active_workflow(
        client,
        admin_token,
        "ansible",
        {
            "type": "ansible_playbook",
            "playbook": "onboarding.yml",
            "inventory": "inventory.ini",
            "extra_vars": {"employee": "{employee_username}"},
        },
    )

    run_res = client.post(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/run",
        headers=auth(admin_token),
        json={"context": {"employee_username": "jdoe"}},
    )
    assert run_res.status_code == 200, run_res.text
    out = run_res.json()["data"]
    assert out["ok"] is True
    assert out["errors"] == 0


def test_update_workflow_step_retries_endpoint(client, admin_token):
    wf_id = _create_active_workflow(
        client,
        admin_token,
        "provision_identity",
        {
            "type": "provision_identity",
            "operation": "create_ad_user",
            "url": "https://idm.example.local/ad/users",
        },
    )

    wf_list_res = client.get("/api/v1/billing-reports/automation-workflows", headers=auth(admin_token))
    assert wf_list_res.status_code == 200, wf_list_res.text
    _wf_body = wf_list_res.json()
    _wf_items = _wf_body.get("items") if isinstance(_wf_body, dict) else _wf_body
    workflow = next(w for w in _wf_items if w["id"] == wf_id)
    step_id = workflow["steps"][0]["id"]

    patch_res = client.patch(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/steps/{step_id}/retries",
        headers=auth(admin_token),
        json={"max_retries": 2, "delay_seconds": 1, "backoff": "linear"},
    )
    assert patch_res.status_code == 200, patch_res.text
    data = patch_res.json()["data"]
    assert data["ok"] is True
    assert data["retry"]["max_retries"] == 2
    assert data["retry"]["delay_seconds"] == 1
    assert data["retry"]["backoff"] == "linear"


def test_run_workflow_now_retries_failed_action_and_records_metrics(client, admin_token, monkeypatch):
    from app.services import bookings_service as svc

    calls = {"n": 0}

    def flaky_provision(config, context):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient_idm_error")
        return {"ok": True, "action_type": "create_ad_user", "status_code": 201}

    monkeypatch.setattr(svc, "_execute_provision_action", flaky_provision)

    wf_id = _create_active_workflow(
        client,
        admin_token,
        "provision_identity",
        {
            "type": "provision_identity",
            "operation": "create_ad_user",
            "url": "https://idm.example.local/ad/users",
            "retry": {"max_retries": 1, "delay_seconds": 0, "backoff": "none"},
        },
    )

    run_res = client.post(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/run",
        headers=auth(admin_token),
        json={"context": {"employee_username": "jdoe"}},
    )
    assert run_res.status_code == 200, run_res.text
    out = run_res.json()["data"]
    assert out["ok"] is True
    assert out["errors"] == 0
    assert calls["n"] == 2

    hist_res = client.get(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/executions",
        headers=auth(admin_token),
    )
    assert hist_res.status_code == 200, hist_res.text
    _hist2_body = hist_res.json()
    _hist2_items = _hist2_body.get("items") if isinstance(_hist2_body, dict) else _hist2_body
    step_log = _hist2_items[0]["steps_log"][0]
    assert step_log["retry_attempts"] == 1
    assert step_log["execution_attempts"] == 2
    assert step_log["duration_ms"] >= 0
    assert step_log["workflow_metrics"]["total_retry_attempts"] == 1


def test_run_workflow_now_rejects_non_allowlisted_terraform_command(client, admin_token):
    wf_id = _create_active_workflow(
        client,
        admin_token,
        "terraform",
        {
            "type": "terraform",
            "command": "state",
            "allowed_commands": ["plan", "apply", "destroy"],
            "workdir": "/iac/provisioning",
        },
    )

    run_res = client.post(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/run",
        headers=auth(admin_token),
        json={"context": {}},
    )
    assert run_res.status_code == 200, run_res.text
    out = run_res.json()["data"]
    assert out["errors"] >= 1
