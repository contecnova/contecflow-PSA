"""Tests for unified ticket assignment behavior.

Covers:
- Auto-assignment at creation (all creation paths)
- Routing-rule assigned user sets status to assigned
- Productive ML endpoints: auto-assign, smart-assign, routing-candidates
"""

from tests.conftest import auth


def _create_group_with_members(db, user_ids):
    import uuid
    from app.models.service_desk import AgentGroup, AgentGroupMember, SupportLevel

    group = AgentGroup(
        id=str(uuid.uuid4()),
        name=f"SD Group {uuid.uuid4().hex[:6]}",
        support_level=SupportLevel.l1,
        is_active=True,
    )
    db.add(group)
    db.flush()

    for uid in user_ids:
        db.add(
            AgentGroupMember(
                id=str(uuid.uuid4()),
                group_id=group.id,
                user_id=uid,
            )
        )
    db.commit()
    return group


def test_ticket_is_auto_assigned_on_create(client, admin_token, db):
    group = _create_group_with_members(db, ["admin-test-id", "dev-test-id"])

    create = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "Auto-assignment create path",
            "description": "Ticket should be auto-assigned",
            "ticket_type": "incident",
            "priority": "p3_medium",
            "assigned_group_id": group.id,
        },
    )
    assert create.status_code in (200, 201), create.text
    data = create.json()["data"]

    assert data.get("assigned_group_id") == group.id
    assert data.get("assigned_to_id") in {"admin-test-id", "dev-test-id"}
    assert data.get("status") == "assigned"


def test_routing_rule_assign_user_sets_assigned_status(client, admin_token, db):
    import json
    import uuid
    from app.models.service_desk import RoutingRule, Ticket

    # Rule: all incidents -> assign to dev-test-id
    rule = RoutingRule(
        id=str(uuid.uuid4()),
        name="Assign all incidents to dev",
        is_active=True,
        priority=1,
        conditions=json.dumps({"ticket_type": "incident"}),
        actions=json.dumps({"assign_user": "dev-test-id"}),
    )
    db.add(rule)
    db.commit()

    create = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "Routing rule assignment",
            "description": "Rule should set assignee and status",
            "ticket_type": "incident",
            "priority": "p3_medium",
        },
    )
    assert create.status_code in (200, 201), create.text
    ticket_id = create.json()["data"]["id"]

    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    assert ticket is not None
    assert str(ticket.assigned_to_user_id) == "dev-test-id"
    status_value = ticket.status.value if hasattr(ticket.status, "value") else str(ticket.status)
    assert status_value == "assigned"


def test_productive_ml_assignment_endpoints(client, admin_token, db):
    group = _create_group_with_members(db, ["admin-test-id", "dev-test-id"])

    create = client.post(
        "/api/v1/sd/tickets",
        headers=auth(admin_token),
        json={
            "title": "ML endpoints coverage",
            "description": "cover auto-assign/smart-assign/routing-candidates",
            "ticket_type": "incident",
            "priority": "p2_high",
            "assigned_group_id": group.id,
        },
    )
    assert create.status_code in (200, 201), create.text
    ticket_id = create.json()["data"]["id"]

    candidates = client.get(
        f"/api/v1/sd/tickets/{ticket_id}/routing-candidates",
        headers=auth(admin_token),
    )
    assert candidates.status_code == 200, candidates.text
    cand_data = candidates.json()["data"]
    assert isinstance(cand_data.get("candidates"), list)
    assert len(cand_data["candidates"]) >= 1

    auto_assign = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/auto-assign",
        headers=auth(admin_token),
    )
    assert auto_assign.status_code == 200, auto_assign.text
    auto_data = auto_assign.json()["data"]
    assert auto_data.get("ok") is True
    assert auto_data.get("method") == "ml_score_v2"
    assert auto_data.get("assigned_to") in {"admin-test-id", "dev-test-id"}

    smart_assign = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/smart-assign",
        headers=auth(admin_token),
    )
    assert smart_assign.status_code == 200, smart_assign.text
    smart_data = smart_assign.json()["data"]
    assert smart_data.get("ok") is True
    assert smart_data.get("method") == "ml_score_v2"


def test_task_assignee_suggestion_requires_manual_confirmation(client, admin_token):
    r = client.post(
        "/api/v1/tasks/suggest-assignee",
        headers=auth(admin_token),
        json={
            "title": "Preparar informe semanal",
            "description": "Consolidar métricas y riesgos",
            "candidate_user_ids": ["admin-test-id", "dev-test-id"],
            "priority": "medium",
        },
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data.get("requires_confirmation") is True
    assert isinstance(data.get("suggestion"), dict)
    assert "suggested_user_id" in data["suggestion"]
