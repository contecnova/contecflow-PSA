import uuid

import pytest

from tests.conftest import auth

from app.models.service_desk import ChangeStatus, ChangeType, ITSMChangeRequest, TicketPriority
from app.models.user import User
from app.services.service_desk import cab_workflow_service as svc


def _user(db, user_id):
    return db.query(User).filter(User.id == user_id).first()


def _mk_change(db):
    chg = ITSMChangeRequest(
        id=str(uuid.uuid4()),
        number=f"CHG{uuid.uuid4().hex[:6].upper()}",
        title="CAB test change",
        description="Change for CAB workflow tests",
        change_type=ChangeType.normal,
        priority=TicketPriority.p3_medium,
        requester_id="admin-test-id",
    )
    db.add(chg)
    db.commit()
    db.refresh(chg)
    return chg


def test_cab_workflow_service_happy_path(db):
    admin = _user(db, "admin-test-id")
    pm = _user(db, "pm-test-id")
    dev = _user(db, "dev-test-id")
    change = _mk_change(db)

    state = svc.start_cab_workflow(
        db,
        change_id=change.id,
        requester=admin,
        manager_user_id=pm.id,
        cab_members=[pm.id, dev.id],
        quorum=2,
    )
    assert state["status"] == "requester"

    state = svc.schedule_cab_meeting(
        db,
        change_id=change.id,
        manager=pm,
        when_iso="2026-04-30T10:00:00+00:00",
        agenda="Review risk and rollback",
    )
    assert state["status"] == "cab"

    state = svc.cast_cab_vote(db, change_id=change.id, voter=pm, approve=True, note="ok")
    assert state["status"] == "cab"

    state = svc.cast_cab_vote(db, change_id=change.id, voter=dev, approve=True, note="ok")
    assert state["status"] == "executor"

    change_db = db.query(ITSMChangeRequest).filter(ITSMChangeRequest.id == change.id).first()
    assert change_db.status == ChangeStatus.approved

    state = svc.assign_executor(db, change_id=change.id, executor_user_id=dev.id, manager=pm)
    assert state["executor_user_id"] == dev.id


def test_cab_workflow_service_rejects_non_member_vote(db):
    admin = _user(db, "admin-test-id")
    pm = _user(db, "pm-test-id")
    hr = _user(db, "hr-test-id")
    change = _mk_change(db)

    svc.start_cab_workflow(
        db,
        change_id=change.id,
        requester=admin,
        manager_user_id=pm.id,
        cab_members=[pm.id],
        quorum=1,
    )

    with pytest.raises(ValueError, match="user_not_in_cab"):
        svc.cast_cab_vote(db, change_id=change.id, voter=hr, approve=True)


def test_sd_cab_workflow_endpoints_full_flow(client, admin_token, pm_token, dev_token):
    create_res = client.post(
        "/api/v1/sd/changes",
        headers=auth(admin_token),
        json={
            "title": "Endpoint CAB Change",
            "description": "Endpoint CAB test",
            "change_type": "normal",
        },
    )
    assert create_res.status_code == 200, create_res.text
    change_id = create_res.json()["data"]["id"]

    start_res = client.post(
        f"/api/v1/sd/changes/{change_id}/cab/workflow",
        headers=auth(admin_token),
        json={"manager_user_id": "pm-test-id", "cab_members": ["pm-test-id", "dev-test-id"], "quorum": 2},
    )
    assert start_res.status_code == 201, start_res.text
    assert start_res.json()["ok"] is True

    meeting_res = client.post(
        f"/api/v1/sd/changes/{change_id}/cab/meeting",
        headers=auth(pm_token),
        json={"scheduled_at": "2026-04-30T12:00:00+00:00", "agenda": "CAB formal review"},
    )
    assert meeting_res.status_code == 200, meeting_res.text

    vote_1 = client.post(
        f"/api/v1/sd/changes/{change_id}/cab/vote",
        headers=auth(pm_token),
        json={"approve": True, "note": "approved"},
    )
    assert vote_1.status_code == 200, vote_1.text

    vote_2 = client.post(
        f"/api/v1/sd/changes/{change_id}/cab/vote",
        headers=auth(dev_token),
        json={"approve": True, "note": "approved"},
    )
    assert vote_2.status_code == 200, vote_2.text

    status_res = client.get(f"/api/v1/sd/changes/{change_id}/cab/workflow", headers=auth(admin_token))
    assert status_res.status_code == 200, status_res.text
    assert status_res.json()["status"] == "executor"

    exec_res = client.post(
        f"/api/v1/sd/changes/{change_id}/cab/executor",
        headers=auth(admin_token),
        json={"executor_user_id": "dev-test-id"},
    )
    assert exec_res.status_code == 200, exec_res.text
    assert exec_res.json()["workflow"]["executor_user_id"] == "dev-test-id"


def test_sd_cab_templates_endpoint(client, admin_token):
    res = client.get("/api/v1/sd/changes/cab/templates", headers=auth(admin_token))
    assert res.status_code == 200, res.text
    payload = res.json()
    assert "testing_plan" in payload
    assert "comms_plan" in payload
