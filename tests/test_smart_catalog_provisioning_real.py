import uuid

from app.models.service_desk import (
    ServiceCategory,
    ServiceItem,
    Ticket,
    TicketHistory,
    TicketPriority,
    TicketStatus,
    TicketType,
)
from tests.conftest import auth


def _seed_service_and_ticket(db):
    cat = ServiceCategory(name="Provisioning", description="Cat", icon="⚙️")
    db.add(cat)
    db.flush()

    service = ServiceItem(
        category_id=cat.id,
        name="Alta empleado",
        description="Provisioning onboarding",
        ticket_type=TicketType.service_request,
        default_priority=TicketPriority.p3_medium,
    )
    db.add(service)
    db.flush()

    ticket = Ticket(
        number=f"TKT-{uuid.uuid4().hex[:8].upper()}",
        ticket_type=TicketType.service_request,
        title="Onboarding user",
        description="Crear usuario y accesos",
        status=TicketStatus.new,
        priority=TicketPriority.p3_medium,
        requester_name="Jane Doe",
        requester_email="jane@example.com",
        requester_user_id="admin-test-id",
        created_by_user_id="admin-test-id",
        service_item_id=service.id,
    )
    db.add(ticket)
    db.commit()
    return service.id, ticket.id


def test_smart_catalog_provisioning_executes_ad_terraform_ansible(client, admin_token, db, monkeypatch):
    service_id, ticket_id = _seed_service_and_ticket(db)

    called = {"ad": 0, "tf": 0, "ans": 0}

    def fake_ad(config, context):
        called["ad"] += 1
        assert context["ticket_id"] == ticket_id
        return {"ok": True, "status_code": 201, "operation": config.get("operation", "create_ad_user")}

    def fake_tf(config, context):
        called["tf"] += 1
        assert context["service_item_id"] == service_id
        return {"ok": True, "exit_code": 0, "stdout": "apply complete"}

    def fake_ans(config, context):
        called["ans"] += 1
        assert context["requester_email"] == "jane@example.com"
        return {"ok": True, "exit_code": 0, "stdout": "changed=2 failed=0"}

    import app.services.bookings_service as booking_exec

    monkeypatch.setattr(booking_exec, "_execute_provision_action", fake_ad)
    monkeypatch.setattr(booking_exec, "_execute_terraform_action", fake_tf)
    monkeypatch.setattr(booking_exec, "_execute_ansible_action", fake_ans)

    config_payload = {
        "enabled": True,
        "steps": [
            {"type": "provision_identity", "operation": "create_ad_user", "url": "https://idm.local/users"},
            {"type": "terraform_apply", "workdir": "/iac/onboarding"},
            {"type": "ansible_playbook", "playbook": "onboarding.yml", "inventory": "inventory.ini"},
        ],
        "notify_on_provision": True,
    }

    put_res = client.put(
        f"/api/v1/sd/catalog/smart/services/{service_id}/provisioning",
        headers=auth(admin_token),
        json=config_payload,
    )
    assert put_res.status_code == 200, put_res.text

    run_res = client.post(
        f"/api/v1/sd/catalog/smart/services/{service_id}/provision",
        headers=auth(admin_token),
        json={"ticket_id": ticket_id, "service_item_id": service_id},
    )
    assert run_res.status_code == 200, run_res.text

    out = run_res.json()["data"]
    assert out["status"] == "completed"
    assert len(out["steps_executed"]) == 3
    assert all(step["status"] == "ok" for step in out["steps_executed"])
    assert called == {"ad": 1, "tf": 1, "ans": 1}

    hist_count = db.query(TicketHistory).filter(TicketHistory.ticket_id == ticket_id).count()
    assert hist_count >= 2


def test_smart_catalog_provisioning_skips_when_disabled(client, admin_token, db):
    service_id, ticket_id = _seed_service_and_ticket(db)

    put_res = client.put(
        f"/api/v1/sd/catalog/smart/services/{service_id}/provisioning",
        headers=auth(admin_token),
        json={"enabled": False, "steps": []},
    )
    assert put_res.status_code == 200, put_res.text

    run_res = client.post(
        f"/api/v1/sd/catalog/smart/services/{service_id}/provision",
        headers=auth(admin_token),
        json={"ticket_id": ticket_id, "service_item_id": service_id},
    )
    assert run_res.status_code == 200, run_res.text
    out = run_res.json()["data"]
    assert out["status"] == "skipped"
