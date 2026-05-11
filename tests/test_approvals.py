"""Tests de aprobaciones multi-nivel."""
from tests.conftest import auth


# ─── Helpers ──────────────────────────────────────────────────────────────────

def create_workflow(client, admin_token, entity_type="expense", is_default=True, name=None):
    res = client.post("/api/v1/approvals/workflows", json={
        "name": name or f"WF-{entity_type}",
        "entity_type": entity_type,
        "is_default": is_default,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201), res.text
    return res.json()


def add_step(client, admin_token, workflow_id, step_order=1, approver_type="role", approver_role="admin"):
    res = client.post(f"/api/v1/approvals/workflows/{workflow_id}/steps", json={
        "step_order": step_order,
        "name": f"Paso {step_order}",
        "approver_type": approver_type,
        "approver_role": approver_role,
        "timeout_hours": 48,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201), res.text
    return res.json()


def create_request(client, token, entity_type="expense", workflow_id=None):
    payload = {
        "entity_type": entity_type,
        "entity_id": "entity-001",
        "entity_summary": f"Solicitud de {entity_type}",
    }
    if workflow_id:
        payload["workflow_id"] = workflow_id
    res = client.post("/api/v1/approvals/requests", json=payload, headers=auth(token))
    return res


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW CRUD
# ═══════════════════════════════════════════════════════════════════════════════

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


def test_workflow_response_schema_fields(client, admin_token, db):
    """Every workflow response must have the documented contract fields."""
    wf = create_workflow(client, admin_token)
    required = {"id", "name", "entity_type", "is_active", "is_default", "step_count"}
    assert required.issubset(wf.keys()), f"Missing fields: {required - wf.keys()}"


def test_get_workflow_detail(client, admin_token, db):
    wf = create_workflow(client, admin_token)
    res = client.get(f"/api/v1/approvals/workflows/{wf['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["id"] == wf["id"]


def test_get_nonexistent_workflow(client, admin_token, db):
    res = client.get("/api/v1/approvals/workflows/nonexistent-id", headers=auth(admin_token))
    assert res.status_code == 404


def test_update_workflow(client, admin_token, db):
    wf = create_workflow(client, admin_token, name="Original")
    res = client.patch(
        f"/api/v1/approvals/workflows/{wf['id']}",
        json={"name": "Actualizado", "is_active": False},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Actualizado"
    assert res.json()["is_active"] is False


def test_delete_workflow(client, admin_token, db):
    wf = create_workflow(client, admin_token, is_default=False)
    res = client.delete(f"/api/v1/approvals/workflows/{wf['id']}", headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json().get("ok") is True
    # Verify it is gone
    res2 = client.get(f"/api/v1/approvals/workflows/{wf['id']}", headers=auth(admin_token))
    assert res2.status_code == 404


def test_filter_workflows_by_entity_type(client, admin_token, db):
    create_workflow(client, admin_token, entity_type="expense", is_default=False, name="WF-exp")
    create_workflow(client, admin_token, entity_type="timesheet", is_default=False, name="WF-ts")
    res = client.get("/api/v1/approvals/workflows?entity_type=expense", headers=auth(admin_token))
    assert res.status_code == 200
    for wf in res.json():
        assert wf["entity_type"] == "expense"


def test_workflow_requires_admin(client, dev_token, db):
    res = client.post("/api/v1/approvals/workflows", json={
        "name": "WF", "entity_type": "expense",
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# WORKFLOW STEPS CRUD
# ═══════════════════════════════════════════════════════════════════════════════

def test_add_step_to_workflow(client, admin_token, db):
    wf = create_workflow(client, admin_token, entity_type="timesheet")
    res = client.post(f"/api/v1/approvals/workflows/{wf['id']}/steps", json={
        "step_order": 1, "name": "Manager", "approver_type": "role",
        "approver_role": "pm", "timeout_hours": 48,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "Manager"
    assert data["step_order"] == 1


def test_step_response_schema_fields(client, admin_token, db):
    wf = create_workflow(client, admin_token)
    step = add_step(client, admin_token, wf["id"])
    required = {"id", "step_order", "name", "approver_type", "is_optional", "timeout_hours"}
    assert required.issubset(step.keys()), f"Missing fields: {required - step.keys()}"


def test_update_step(client, admin_token, db):
    wf = create_workflow(client, admin_token)
    step = add_step(client, admin_token, wf["id"])
    res = client.patch(
        f"/api/v1/approvals/workflows/{wf['id']}/steps/{step['id']}",
        json={"name": "Paso editado", "timeout_hours": 96},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Paso editado"
    assert res.json()["timeout_hours"] == 96


def test_delete_step(client, admin_token, db):
    wf = create_workflow(client, admin_token)
    step = add_step(client, admin_token, wf["id"])
    res = client.delete(
        f"/api/v1/approvals/workflows/{wf['id']}/steps/{step['id']}",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    assert res.json().get("ok") is True


def test_delete_group(client, admin_token, db):
    created = client.post(
        "/api/v1/approvals/groups",
        json={"name": "Grupo Delete", "description": "tmp", "member_ids": []},
        headers=auth(admin_token),
    )
    assert created.status_code in (200, 201), created.text
    gid = created.json()["id"]

    deleted = client.delete(f"/api/v1/approvals/groups/{gid}", headers=auth(admin_token))
    assert deleted.status_code == 200
    assert deleted.json().get("ok") is True

    fetched = client.get(f"/api/v1/approvals/groups/{gid}", headers=auth(admin_token))
    assert fetched.status_code == 404


def test_add_step_requires_admin(client, dev_token, db):
    res = client.post("/api/v1/approvals/workflows/any-id/steps", json={
        "step_order": 1, "name": "X", "approver_type": "role", "approver_role": "pm",
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════════════════════════
# APPROVAL REQUESTS
# ═══════════════════════════════════════════════════════════════════════════════

def test_create_approval_request_no_default(client, dev_token, db):
    """Without a default workflow, creating a request returns 404."""
    res = create_request(client, dev_token, entity_type="expense")
    assert res.status_code == 404


def test_create_approval_request_with_default_workflow(client, admin_token, dev_token, db):
    """Creating a request auto-attaches the default workflow."""
    wf = create_workflow(client, admin_token, entity_type="purchase", is_default=True)
    add_step(client, admin_token, wf["id"])
    res = create_request(client, dev_token, entity_type="purchase")
    assert res.status_code in (200, 201), res.text
    data = res.json()
    assert data["status"] == "pending"
    assert data["entity_type"] == "purchase"
    assert data["workflow_id"] == wf["id"]


def test_request_response_schema_fields(client, admin_token, dev_token, db):
    wf = create_workflow(client, admin_token, entity_type="purchase2", is_default=True)
    add_step(client, admin_token, wf["id"])
    res = create_request(client, dev_token, entity_type="purchase2")
    assert res.status_code in (200, 201)
    data = res.json()
    required = {"id", "workflow_id", "entity_type", "entity_id", "status", "current_step", "decisions"}
    assert required.issubset(data.keys()), f"Missing fields: {required - data.keys()}"


def test_list_my_requests(client, admin_token, dev_token, db):
    wf = create_workflow(client, admin_token, entity_type="myrequests", is_default=True)
    add_step(client, admin_token, wf["id"])
    create_request(client, dev_token, entity_type="myrequests")
    res = client.get("/api/v1/approvals/requests", headers=auth(dev_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1


def test_list_requests_filter_by_status(client, admin_token, dev_token, db):
    wf = create_workflow(client, admin_token, entity_type="filterstatus", is_default=True)
    add_step(client, admin_token, wf["id"])
    create_request(client, dev_token, entity_type="filterstatus")
    res = client.get("/api/v1/approvals/requests?status=pending", headers=auth(dev_token))
    assert res.status_code == 200
    for req in res.json():
        assert req["status"] == "pending"


# ═══════════════════════════════════════════════════════════════════════════════
# END-TO-END APPROVAL FLOW
# ═══════════════════════════════════════════════════════════════════════════════

def test_approve_request_single_step(client, admin_token, dev_token, db):
    """Admin creates workflow → dev requests → admin approves → status approved."""
    wf = create_workflow(client, admin_token, entity_type="e2e_approve", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")

    req = create_request(client, dev_token, entity_type="e2e_approve").json()
    assert req["status"] == "pending"

    # Admin approves
    res = client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["status"] == "approved"
    assert data["final_decision"] == "approved"


def test_reject_request(client, admin_token, dev_token, db):
    """Admin can reject a pending approval request."""
    wf = create_workflow(client, admin_token, entity_type="e2e_reject", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")

    req = create_request(client, dev_token, entity_type="e2e_reject").json()

    res = client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "rejected", "note": "No aprobado por política"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "rejected"
    assert data["final_decision"] == "rejected"


def test_cannot_decide_already_approved(client, admin_token, dev_token, db):
    """Deciding on a completed request returns 400."""
    wf = create_workflow(client, admin_token, entity_type="e2e_double", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")

    req = create_request(client, dev_token, entity_type="e2e_double").json()
    client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    )
    # Second attempt should fail
    res = client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    )
    assert res.status_code == 400


def test_multistep_workflow_progresses(client, admin_token, pm_token, dev_token, db):
    """2-step workflow: after step-1 approval request should move to step 2, not complete."""
    wf = create_workflow(client, admin_token, entity_type="multistep", is_default=True)
    add_step(client, admin_token, wf["id"], step_order=1, approver_type="role", approver_role="admin")
    add_step(client, admin_token, wf["id"], step_order=2, approver_type="role", approver_role="pm")

    req = create_request(client, dev_token, entity_type="multistep").json()
    assert req["current_step"] == 1

    # Admin approves step 1
    after_step1 = client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    ).json()
    # Should advance to step 2, not yet approved
    assert after_step1["current_step"] == 2
    assert after_step1["status"] == "pending"

    # PM approves step 2 → fully approved
    after_step2 = client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(pm_token),
    ).json()
    assert after_step2["status"] == "approved"


def test_sod_self_approval_blocked(client, admin_token, db):
    """The requester cannot approve their own request (Segregation of Duties)."""
    wf = create_workflow(client, admin_token, entity_type="sod_test", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")

    # Admin requests (and is also the approver type)
    req = create_request(client, admin_token, entity_type="sod_test").json()
    assert req["status"] == "pending"

    # Admin tries to approve their own request → SoD violation → 403
    res = client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    )
    assert res.status_code == 403
    assert "SoD" in res.json().get("detail", "") or "segreg" in res.json().get("detail", "").lower()


def test_cancel_request(client, admin_token, dev_token, db):
    """The requester can cancel their own pending request."""
    wf = create_workflow(client, admin_token, entity_type="cancel_test", is_default=True)
    add_step(client, admin_token, wf["id"])
    req = create_request(client, dev_token, entity_type="cancel_test").json()

    res = client.post(
        f"/api/v1/approvals/requests/{req['id']}/cancel",
        headers=auth(dev_token),
    )
    assert res.status_code == 200
    assert res.json().get("ok") is True


def test_decide_nonexistent_request(client, admin_token, db):
    res = client.post(
        "/api/v1/approvals/requests/nonexistent-id/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    )
    assert res.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# PENDING MY ACTION
# ═══════════════════════════════════════════════════════════════════════════════

def test_pending_my_action_empty(client, admin_token, db):
    res = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_pending_my_action_after_request(client, admin_token, dev_token, db):
    """After a request is submitted, the approver sees it in their pending queue."""
    wf = create_workflow(client, admin_token, entity_type="pending_action", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")
    create_request(client, dev_token, entity_type="pending_action")

    res = client.get("/api/v1/approvals/requests/pending-my-action", headers=auth(admin_token))
    assert res.status_code == 200
    # Admin is the approver → should see the request
    assert len(res.json()) >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# STATS
# ═══════════════════════════════════════════════════════════════════════════════

def test_approval_stats(client, admin_token, db):
    res = client.get("/api/v1/approvals/stats", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "pending" in data
    assert "approved" in data
    assert "rejected" in data
    assert "by_entity_type" in data


def test_stats_counts_update_after_approvals(client, admin_token, dev_token, db):
    wf = create_workflow(client, admin_token, entity_type="stats_count", is_default=True)
    add_step(client, admin_token, wf["id"], approver_type="role", approver_role="admin")

    req = create_request(client, dev_token, entity_type="stats_count").json()
    before = client.get("/api/v1/approvals/stats", headers=auth(admin_token)).json()

    client.post(
        f"/api/v1/approvals/requests/{req['id']}/decide",
        json={"decision": "approved"},
        headers=auth(admin_token),
    )
    after = client.get("/api/v1/approvals/stats", headers=auth(admin_token)).json()
    assert after["approved"] >= before["approved"]


def test_stats_requires_manager(client, dev_token, db):
    res = client.get("/api/v1/approvals/stats", headers=auth(dev_token))
    assert res.status_code in (401, 403)

