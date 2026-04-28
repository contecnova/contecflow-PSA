from tests.conftest import auth


def _create_sd_change(client, token):
    res = client.post(
        "/api/v1/sd/changes",
        headers=auth(token),
        json={
            "title": "Cambio de configuracion API Gateway",
            "description": "Ajustar timeout y retries para reducir errores 504",
            "change_type": "normal",
            "risk": "medium",
            "rollback_plan": "Revertir configuracion previa del gateway",
            "impact_description": "Afecta API publica y servicios internos",
            "affected_cis": "[\"ci-gateway-1\", \"ci-service-2\"]",
        },
    )
    assert res.status_code in (200, 201), res.text
    return res.json()


def test_change_assess_risk_endpoint(client, admin_token, db):
    change = _create_sd_change(client, admin_token)

    assessed = client.post(
        f"/api/v1/sd/changes/{change['id']}/assess-risk",
        headers=auth(admin_token),
    )
    assert assessed.status_code == 200, assessed.text
    data = assessed.json()
    assert data["change_id"] == change["id"]
    assert "assessment" in data
    assert "risk_level" in data["assessment"]


def test_change_plan_rollout_endpoint(client, admin_token, db):
    change = _create_sd_change(client, admin_token)

    planned = client.post(
        f"/api/v1/sd/changes/{change['id']}/plan-rollout",
        headers=auth(admin_token),
        json={"estimated_duration_minutes": 90},
    )
    assert planned.status_code == 200, planned.text
    data = planned.json()
    assert data["change_id"] == change["id"]
    assert "rollout_plan" in data
    assert "phases" in data["rollout_plan"]
    assert len(data["rollout_plan"]["phases"]) >= 1


def test_change_automation_check_and_rollback_script(client, admin_token, db):
    change = _create_sd_change(client, admin_token)

    automation = client.get(
        f"/api/v1/sd/changes/{change['id']}/automation-check",
        headers=auth(admin_token),
    )
    assert automation.status_code == 200, automation.text
    auto_data = automation.json()
    assert auto_data["change_id"] == change["id"]
    assert "automation_level" in auto_data

    rollback = client.post(
        f"/api/v1/sd/changes/{change['id']}/rollback-script",
        headers=auth(admin_token),
    )
    assert rollback.status_code == 200, rollback.text
    rb_data = rollback.json()
    assert rb_data["change_id"] == change["id"]
    assert "script" in rb_data
    assert "ROLLBACK" in rb_data["script"]
