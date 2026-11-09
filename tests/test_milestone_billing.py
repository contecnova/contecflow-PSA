"""Tests del flujo SOW → Milestone → Aprobación → Factura."""
from tests.conftest import auth

def make_project(client, token):
    r = client.post("/api/v1/projects", json={
        "name":"P Milestones","code":"MST","status":"active",
        "billing_type":"fixed_price","contract_amount":50000,
    }, headers=auth(token))
    return r.json()["data"]["id"]

def test_create_milestone(client, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.post(f"/api/v1/milestones/project/{pid}", json={
        "name": "Entrega fase 1",
        "billing_amount": 10000,
        "due_date": "2025-12-31",
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert data["name"] == "Entrega fase 1"
    assert data["billing_status"] == "pending"
    return data["id"]

def test_complete_milestone(client, pm_token, db):
    pid = make_project(client, pm_token)
    ms = client.post(f"/api/v1/milestones/project/{pid}", json={
        "name": "M", "billing_amount": 5000,
    }, headers=auth(pm_token)).json()["data"]
    res = client.post(f"/api/v1/milestones/{ms['id']}/complete", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["data"]["billing_status"] == "completed"

def test_milestone_flow_complete(client, pm_token, admin_token, db):
    """Flujo completo: create → complete → request_approval → approve → invoice."""
    pid = make_project(client, pm_token)
    ms = client.post(f"/api/v1/milestones/project/{pid}", json={
        "name": "M Full Flow", "billing_amount": 8000,
    }, headers=auth(pm_token)).json()["data"]
    mid = ms["id"]

    # complete
    r = client.post(f"/api/v1/milestones/{mid}/complete", headers=auth(pm_token))
    assert r.json()["data"]["billing_status"] == "completed"

    # request approval
    r = client.post(f"/api/v1/milestones/{mid}/request-approval", headers=auth(pm_token))
    assert r.json()["data"]["billing_status"] == "pending_approval"

    # approve
    # Aprueba otro: quien pide no decide (segregación de funciones).
    r = client.post(f"/api/v1/milestones/{mid}/approve", json={"approved": True}, headers=auth(admin_token))
    assert r.json()["data"]["billing_status"] == "approved"

    # generate invoice
    r = client.post(f"/api/v1/milestones/{mid}/generate-invoice", headers=auth(pm_token))
    assert r.status_code == 200
    assert r.json()["data"]["billing_status"] == "invoiced"

def test_milestone_reject(client, pm_token, admin_token, db):
    pid = make_project(client, pm_token)
    ms = client.post(f"/api/v1/milestones/project/{pid}", json={"name":"M","billing_amount":1000}, headers=auth(pm_token)).json()["data"]
    client.post(f"/api/v1/milestones/{ms['id']}/complete", headers=auth(pm_token))
    client.post(f"/api/v1/milestones/{ms['id']}/request-approval", headers=auth(pm_token))
    r = client.post(f"/api/v1/milestones/{ms['id']}/approve", json={"approved": False, "rejection_reason": "Falta documentación"}, headers=auth(admin_token))
    assert r.json()["data"]["billing_status"] == "rejected"

def test_pending_dashboard(client, pm_token, db):
    res = client.get("/api/v1/milestones/dashboard/pending", headers=auth(pm_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload
