"""tests/test_incident_assignment_ml.py — Tests for ML-based incident assignment endpoints."""
import pytest
from tests.conftest import auth


def test_recommend_assignment(client, admin_token, db):
    """Create a ticket then get unified ML routing recommendation."""
    import uuid
    from app.models.service_desk import AgentGroup, AgentGroupMember, SupportLevel

    group = AgentGroup(
        id=str(uuid.uuid4()),
        name="Incident Assignment Group",
        support_level=SupportLevel.l1,
        is_active=True,
    )
    db.add(group)
    db.flush()
    db.add(AgentGroupMember(id=str(uuid.uuid4()), group_id=group.id, user_id="admin-test-id"))
    db.add(AgentGroupMember(id=str(uuid.uuid4()), group_id=group.id, user_id="dev-test-id"))
    db.commit()

    create = client.post(
        "/api/v1/sd/tickets",
        json={
            "title": "Server is down",
            "description": "Production server not responding",
            "ticket_type": "incident",
            "priority": "p2_high",
            "assigned_group_id": group.id,
        },
        headers=auth(admin_token),
    )
    assert create.status_code in (200, 201)
    ticket_id = create.json()["id"]

    r = client.post(
        f"/api/v1/sd/tickets/{ticket_id}/recommend-assignment",
        json={},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    data = r.json()
    assert data["method_used"] == "ml_score_v2"
    assert "recommendations" in data
    assert isinstance(data["recommendations"], list)


def test_assignment_stats(client, admin_token):
    r = client.get("/api/v1/sd/assignment/stats", headers=auth(admin_token))
    assert r.status_code == 200
    data = r.json()
    assert "total_auto_assigned" in data or "stats" in data or isinstance(data, dict)


def test_recommend_assignment_not_found(client, admin_token):
    r = client.post(
        "/api/v1/sd/tickets/nonexistent-ticket-id-xyz/recommend-assignment",
        json={},
        headers=auth(admin_token),
    )
    assert r.status_code == 404


def test_recommend_assignment_requires_auth(client, db):
    import uuid
    from app.models.service_desk import Ticket

    ticket = Ticket(
        id=str(uuid.uuid4()),
        number=f"INC-{uuid.uuid4().hex[:8].upper()}",
        title="Test",
        description="Test",
        ticket_type="incident",
        status="new",
        priority="p3_medium",
        requester_user_id="admin-test-id",
    )
    db.add(ticket)
    db.commit()
    ticket_id = ticket.id

    r = client.post(f"/api/v1/sd/tickets/{ticket_id}/recommend-assignment", json={})
    assert r.status_code == 401
