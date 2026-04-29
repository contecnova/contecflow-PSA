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
    wf_id = create_res.json()["id"]

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
    out = run_res.json()
    assert out["ok"] is True
    assert out["processed"] >= 1
    assert out["errors"] == 0

    hist_res = client.get(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}/executions",
        headers=auth(admin_token),
    )
    assert hist_res.status_code == 200, hist_res.text
    history = hist_res.json()
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
    out = run_res.json()
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
    out = run_res.json()
    assert out["ok"] is True
    assert out["errors"] == 0
