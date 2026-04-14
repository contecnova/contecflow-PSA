"""Tests del flujo SOW → Milestone → Aprobación → Factura."""
from tests.conftest import auth

def make_project(client, token):
    r = client.post("/api/v1/projects", json={
        "name":"P Milestones","code":"MST","status":"active",
        "billing_type":"fixed_price","contract_amount":50000,
    }, headers=auth(token))
    return r.json()["id"]

def test_create_milestone(client, pm_token, db):
    pid = make_project(client, pm_token)
    res = client.post(f"/api/v1/milestones/project/{pid}", json={
        "name": "Entrega fase 1",
        "billing_amount": 10000,
        "due_date": "2025-12-31",
    }, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "Entrega fase 1"
    assert data["billing_status"] == "pending"
    return data["id"]

def test_complete_milestone(client, pm_token, db):
    pid = make_project(client, pm_token)
    ms = client.post(f"/api/v1/milestones/project/{pid}", json={
        "name": "M", "billing_amount": 5000,
    }, headers=auth(pm_token)).json()
    res = client.post(f"/api/v1/milestones/{ms['id']}/complete", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["billing_status"] == "completed"

def test_milestone_flow_complete(client, pm_token, db):
    """Flujo completo: create → complete → request_approval → approve → invoice."""
    pid = make_project(client, pm_token)
    ms = client.post(f"/api/v1/milestones/project/{pid}", json={
        "name": "M Full Flow", "billing_amount": 8000,
    }, headers=auth(pm_token)).json()
    mid = ms["id"]

    # complete
    r = client.post(f"/api/v1/milestones/{mid}/complete", headers=auth(pm_token))
    assert r.json()["billing_status"] == "completed"

    # request approval
    r = client.post(f"/api/v1/milestones/{mid}/request-approval", headers=auth(pm_token))
    assert r.json()["billing_status"] == "pending_approval"

    # approve
    r = client.post(f"/api/v1/milestones/{mid}/approve", json={"approved": True}, headers=auth(pm_token))
    assert r.json()["billing_status"] == "approved"

    # generate invoice
    r = client.post(f"/api/v1/milestones/{mid}/generate-invoice", headers=auth(pm_token))
    assert r.status_code == 200
    assert r.json()["billing_status"] == "invoiced"

def test_milestone_reject(client, pm_token, db):
    pid = make_project(client, pm_token)
    ms = client.post(f"/api/v1/milestones/project/{pid}", json={"name":"M","billing_amount":1000}, headers=auth(pm_token)).json()
    client.post(f"/api/v1/milestones/{ms['id']}/complete", headers=auth(pm_token))
    client.post(f"/api/v1/milestones/{ms['id']}/request-approval", headers=auth(pm_token))
    r = client.post(f"/api/v1/milestones/{ms['id']}/approve", json={"approved": False, "rejection_reason": "Falta documentación"}, headers=auth(pm_token))
    assert r.json()["billing_status"] == "rejected"

def test_pending_dashboard(client, pm_token, db):
    res = client.get("/api/v1/milestones/dashboard/pending", headers=auth(pm_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
