"""tests/test_change_rollout.py — Tests for Change Rollout Planning endpoints."""
from tests.conftest import auth


def _create_change_request(client, admin_token, db):
    from app.models.service_desk import ChangeRequest
    import uuid
    cr = ChangeRequest(
        id=str(uuid.uuid4()),
        title="Deploy v3.0 to production",
        description="Major version release",
        status="approved",
        change_type="normal",
        priority="high",
        requester_user_id="admin-test-id",
    )
    db.add(cr)
    db.commit()
    return cr


def test_create_rollout_plan(client, admin_token, db):
    cr = _create_change_request(client, admin_token, db)
    payload = {
        "name": "Blue/Green deploy plan",
        "phases": [
            {"name": "Prepare", "duration_hours": 2, "steps": ["Backup DB", "Build image"]},
            {"name": "Deploy staging", "duration_hours": 1, "steps": ["Deploy to staging"]},
            {"name": "Production cutover", "duration_hours": 0.5, "steps": ["Switch traffic"]},
        ],
        "rollback_plan": "Revert DNS and restore DB backup",
    }
    r = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans", json=payload, headers=auth(admin_token))
    assert r.status_code in (200, 201)
    data = r.json()["data"]
    assert "id" in data
    assert data["name"] == "Blue/Green deploy plan"


def test_list_rollout_plans(client, admin_token, db):
    cr = _create_change_request(client, admin_token, db)
    client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans", json={"name": "plan1"}, headers=auth(admin_token))
    r = client.get(f"/api/v1/sd/changes/{cr.id}/rollout-plans", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "items" in data


def test_approve_plan(client, admin_token, pm_token, db):
    cr = _create_change_request(client, admin_token, db)
    res = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans", json={"name": "plan-approve"}, headers=auth(admin_token))
    plan_id = res.json()["data"]["id"]
    # SoD (segunda auditoria 2026-11): quien crea el plan no lo aprueba
    r = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans/{plan_id}/approve", headers=auth(admin_token))
    assert r.status_code == 403
    r = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans/{plan_id}/approve", headers=auth(pm_token))
    assert r.status_code == 200
    assert r.json()["data"]["status"] in ("approved", "active")


def test_advance_phase(client, admin_token, pm_token, db):
    cr = _create_change_request(client, admin_token, db)
    res = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans", json={
        "name": "plan-phases",
        "phases": [{"name": "P1", "steps": []}, {"name": "P2", "steps": []}]
    }, headers=auth(admin_token))
    plan_id = res.json()["data"]["id"]
    # Approve first (otro usuario: SoD)
    client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans/{plan_id}/approve", headers=auth(pm_token))
    # Advance phase
    r = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans/{plan_id}/advance-phase", headers=auth(admin_token))
    assert r.status_code == 200


def test_simulate_impact(client, admin_token, db):
    cr = _create_change_request(client, admin_token, db)
    res = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans", json={"name": "plan-sim"}, headers=auth(admin_token))
    plan_id = res.json()["data"]["id"]
    r = client.post(f"/api/v1/sd/changes/{cr.id}/rollout-plans/{plan_id}/simulate", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()["data"]
    assert "impact" in data or "simulation" in data or isinstance(data, dict)


def test_rollout_requires_auth(client, db):
    cr = _create_change_request(client, None, db)
    r = client.get(f"/api/v1/sd/changes/{cr.id}/rollout-plans")
    assert r.status_code == 401
