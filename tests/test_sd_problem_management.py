import uuid

from tests.conftest import auth

from app.models.service_desk import IncidentToProblem, Problem, Ticket, TicketPriority, TicketType
from app.models.user import User
from app.services.service_desk import problem_management_service as svc


def _admin(db):
    return db.query(User).filter(User.id == "admin-test-id").first()


def _mk_problem(db, owner_user_id="admin-test-id"):
    p = Problem(
        id=str(uuid.uuid4()),
        number=f"PRB-{uuid.uuid4().hex[:8].upper()}",
        title="Problem test",
        description="Problem desc",
        priority=TicketPriority.p2_high,
        owner_user_id=owner_user_id,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


def _mk_ticket(db, *, title="Incident", requester_user_id="admin-test-id"):
    t = Ticket(
        id=str(uuid.uuid4()),
        number=f"INC-{uuid.uuid4().hex[:8].upper()}",
        ticket_type=TicketType.incident,
        title=title,
        description="Incident desc",
        priority=TicketPriority.p3_medium,
        requester_user_id=requester_user_id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def test_problem_management_service_link_incidents_idempotent(db):
    admin = _admin(db)
    problem = _mk_problem(db)
    t1 = _mk_ticket(db, title="Incident A")
    t2 = _mk_ticket(db, title="Incident B")

    out1 = svc.link_incidents_to_problem(
        db,
        problem_id=problem.id,
        ticket_ids=[t1.id, t2.id],
        current_user=admin,
        is_causal=True,
        notes="batch link",
    )
    db.commit()

    assert out1["linked_count"] == 2
    assert out1["already_linked"] == 0
    assert db.query(IncidentToProblem).filter(IncidentToProblem.problem_id == problem.id).count() == 2

    db.refresh(t1)
    assert t1.problem_id == problem.id

    out2 = svc.link_incidents_to_problem(
        db,
        problem_id=problem.id,
        ticket_ids=[t1.id],
        current_user=admin,
    )
    assert out2["linked_count"] == 0
    assert out2["already_linked"] == 1


def test_problem_management_service_create_known_error_and_list(db):
    admin = _admin(db)
    problem = _mk_problem(db)

    ke = svc.create_known_error(
        db,
        problem_id=problem.id,
        current_user=admin,
        title="Known auth issue",
        workaround="Restart auth service",
        description="Affects login",
        root_cause="Token cache invalidation",
        expires_days=30,
    )
    db.commit()

    assert ke.problem_id == problem.id
    assert ke.title == "Known auth issue"
    assert ke.is_active is True

    rows = svc.get_known_errors_for_problem(db, problem_id=problem.id)
    assert len(rows) == 1
    assert rows[0].id == ke.id


def test_sd_problems_create_list_link_and_create_change_endpoints(client, admin_token, db):
    create_res = client.post(
        "/api/v1/sd/problems",
        headers=auth(admin_token),
        json={
            "title": "API Problem",
            "description": "API problem description",
            "priority": "p2_high",
            "owner_user_id": "admin-test-id",
        },
    )
    assert create_res.status_code in (200, 201), create_res.text
    problem_id = create_res.json()["data"]["id"]

    list_res = client.get("/api/v1/sd/problems", headers=auth(admin_token))
    assert list_res.status_code == 200, list_res.text
    list_payload = list_res.json()
    items = list_payload["items"] if isinstance(list_payload, dict) else list_payload
    assert any(p["id"] == problem_id for p in items)

    t1 = _mk_ticket(db, title="API incident 1")
    t2 = _mk_ticket(db, title="API incident 2")

    link_res = client.post(
        f"/api/v1/sd/problems/{problem_id}/link-incidents",
        headers=auth(admin_token),
        json={"ticket_ids": [t1.id, t2.id]},
    )
    assert link_res.status_code == 200, link_res.text
    assert link_res.json()["data"]["ok"] is True
    assert link_res.json()["data"]["linked_count"] == 2

    linked_res = client.get(
        f"/api/v1/sd/problems/{problem_id}/linked-incidents",
        headers=auth(admin_token),
    )
    assert linked_res.status_code == 200, linked_res.text
    assert len(linked_res.json()["items"]) == 2

    rfc_res = client.post(
        f"/api/v1/sd/problems/{problem_id}/create-change",
        headers=auth(admin_token),
        json={"change_type": "normal"},
    )
    assert rfc_res.status_code == 201, rfc_res.text
    body = rfc_res.json()["data"]
    assert body["ok"] is True
    assert body["id"]

    assert body["number"].startswith("CHG")
    assert "status" in body
