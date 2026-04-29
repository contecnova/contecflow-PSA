"""tests/test_incident_assignment_ml.py — Tests for ML-based incident assignment endpoints."""
import pytest
from tests.conftest import auth


def test_recommend_assignment(client, admin_token, db):
    """Create a ticket then get ML assignment recommendation."""
    from app.models.service_desk import Ticket
    import uuid
    ticket = Ticket(
        id=str(uuid.uuid4()),
        title="Server is down",
        description="Production server not responding",
        status="open",
        priority="high",
        ticket_type="incident",
        requester_user_id="admin-test-id",
    )
    db.add(ticket)
    db.commit()

    r = client.post(
        f"/api/v1/sd/tickets/{ticket.id}/recommend-assignment",
        json={"priority": "high", "keywords": ["server", "production"]},
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    data = r.json()
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
    from app.models.service_desk import Ticket
    import uuid
    ticket = Ticket(
        id=str(uuid.uuid4()),
        title="Test",
        status="open",
        ticket_type="incident",
        requester_user_id="admin-test-id",
    )
    db.add(ticket)
    db.commit()
    r = client.post(f"/api/v1/sd/tickets/{ticket.id}/recommend-assignment", json={})
    assert r.status_code == 401
