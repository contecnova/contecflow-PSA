from datetime import date

from tests.conftest import auth

from app.models.project import ProjectMember, ProjectMemberRole
from app.models.task import Task, TaskPriority, TaskStatus


def _create_project(client, token, code):
    res = client.post(
        "/api/v1/projects",
        json={
            "name": f"Proyecto {code}",
            "code": code,
            "status": "active",
            "billing_type": "time_material",
        },
        headers=auth(token),
    )
    assert res.status_code in (200, 201), res.text
    return res.json()["data"]["id"]


def test_imputation_rejects_user_not_assigned_when_project_has_members(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPG-01")

    # Add a different member to enforce membership checks.
    db.add(
        ProjectMember(
            project_id=project_id,
            user_id="pm-test-id",
            role=ProjectMemberRole.lead,
        )
    )
    db.commit()

    res = client.post(
        "/api/v1/imputations",
        headers=auth(dev_token),
        json={
            "project_id": project_id,
            "date": str(date.today()),
            "hours": 2.0,
        },
    )

    assert res.status_code == 403
    assert "no estás asignado" in res.json()["detail"].lower()


def test_imputation_rejects_closed_task_status(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPG-02")

    task = Task(
        code="TASK-IMPG-02",
        project_id=project_id,
        title="Task cerrada",
        assignee_id="dev-test-id",
        status=TaskStatus.done,
        priority=TaskPriority.medium,
    )
    db.add(task)
    db.commit()

    res = client.post(
        "/api/v1/imputations",
        headers=auth(dev_token),
        json={
            "project_id": project_id,
            "task_id": task.id,
            "date": str(date.today()),
            "hours": 1.0,
        },
    )

    assert res.status_code == 400
    assert "tarea" in res.json()["detail"].lower()


def test_imputation_rejects_duplicate_same_user_task_date(client, admin_token, dev_token, db):
    project_id = _create_project(client, admin_token, "IMPG-03")

    task = Task(
        code="TASK-IMPG-03",
        project_id=project_id,
        title="Task duplicados",
        assignee_id="dev-test-id",
        status=TaskStatus.in_progress,
        priority=TaskPriority.medium,
    )
    db.add(task)
    db.commit()

    payload = {
        "project_id": project_id,
        "task_id": task.id,
        "date": str(date.today()),
        "hours": 1.5,
    }

    first = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert first.status_code in (200, 201), first.text

    second = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert second.status_code == 409
    assert "ya existe" in second.json()["detail"].lower()


def test_imputation_rejects_duplicate_no_task_same_project_date(client, admin_token, dev_token, db):
    """When task_id is None the unique index doesn't protect (NULL != NULL); app must block."""
    project_id = _create_project(client, admin_token, "IMPG-04")

    # Add dev user as a member so the membership check passes (no task assignee to rely on).
    db.add(
        ProjectMember(
            project_id=project_id,
            user_id="dev-test-id",
            role=ProjectMemberRole.developer,
        )
    )
    db.commit()

    payload = {
        "project_id": project_id,
        "date": str(date.today()),
        "hours": 2.0,
    }

    first = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert first.status_code in (200, 201), first.text

    second = client.post("/api/v1/imputations", headers=auth(dev_token), json=payload)
    assert second.status_code == 409
    assert "ya existe" in second.json()["detail"].lower()
