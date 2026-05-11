"""Regression tests for Service Desk templates delete hardening."""

from app.models.service_desk import CannedResponse
from app.models.service_desk import TicketTemplate
from tests.conftest import auth


def test_delete_ticket_template_is_soft_and_hidden(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/ticket-templates",
        headers=auth(admin_token),
        json={"name": "Template Delete", "ticket_type": "incident", "custom_fields": []},
    )
    assert created.status_code in (200, 201)
    template_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/sd/ticket-templates/{template_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed = client.get("/api/v1/sd/ticket-templates", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(t["id"] != template_id for t in listed.json())

    row = db.query(TicketTemplate).filter(TicketTemplate.id == template_id).first()
    assert row is not None
    assert row.is_active is False


def test_delete_canned_response_is_soft_and_hidden(client, admin_token, db):
    created = client.post(
        "/api/v1/sd/canned-responses",
        headers=auth(admin_token),
        json={"title": "Resp Delete", "body": "Texto base", "category": "general"},
    )
    assert created.status_code == 201
    canned_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/sd/canned-responses/{canned_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed = client.get("/api/v1/sd/canned-responses", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(c["id"] != canned_id for c in listed.json())

    row = db.query(CannedResponse).filter(CannedResponse.id == canned_id).first()
    assert row is not None
    assert row.is_active is False
