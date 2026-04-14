from tests.conftest import auth, TEST_PASSWORD

from app.models.mfa import Organization
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User, UserRole, UserStatus
from app.core.security import get_password_hash


ORG_A_ID = "org-a-test"
ORG_B_ID = "org-b-test"
PROJECT_A_ID = "project-a-test"
PROJECT_B_ID = "project-b-test"
TASK_A_ID = "task-a-test"
TASK_B_ID = "task-b-test"
OUTSIDER_ID = "outsider-test-id"


def _seed_multitenant_data(db):
    org_a = Organization(id=ORG_A_ID, name="Org A", slug="org-a")
    org_b = Organization(id=ORG_B_ID, name="Org B", slug="org-b")
    db.add_all([org_a, org_b])
    db.flush()

    admin = db.query(User).filter(User.id == "admin-test-id").first()
    pm = db.query(User).filter(User.id == "pm-test-id").first()
    dev = db.query(User).filter(User.id == "dev-test-id").first()
    hr = db.query(User).filter(User.id == "hr-test-id").first()

    for user in (admin, pm, dev, hr):
        user.organization_id = ORG_A_ID

    outsider = User(
        id=OUTSIDER_ID,
        username="outsider",
        email="outsider@example.com",
        full_name="Outsider User",
        role=UserRole.employee,
        status=UserStatus.active,
        is_active=True,
        organization_id=ORG_B_ID,
        hourly_rate=999.0,
        hashed_password=get_password_hash(TEST_PASSWORD),
    )
    db.add(outsider)
    db.flush()

    project_a = Project(
        id=PROJECT_A_ID,
        organization_id=ORG_A_ID,
        code="PRJ-TA",
        name="Tenant Project A",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        pm_id=pm.id,
        created_by=admin.id,
    )
    project_b = Project(
        id=PROJECT_B_ID,
        organization_id=ORG_B_ID,
        code="PRJ-TB",
        name="Tenant Project B",
        project_type=ProjectType.consulting,
        status=ProjectStatus.active,
        created_by=OUTSIDER_ID,
    )
    db.add_all([project_a, project_b])
    db.flush()

    task_a = Task(
        id=TASK_A_ID,
        code="TSK-TA001",
        project_id=PROJECT_A_ID,
        title="Task tenant A",
        assignee_id=dev.id,
        reporter_id=admin.id,
        created_by=admin.id,
        status=TaskStatus.todo,
        priority=TaskPriority.medium,
    )
    task_b = Task(
        id=TASK_B_ID,
        code="TSK-TB001",
        project_id=PROJECT_B_ID,
        title="Task tenant B",
        assignee_id=OUTSIDER_ID,
        reporter_id=OUTSIDER_ID,
        created_by=OUTSIDER_ID,
        status=TaskStatus.todo,
        priority=TaskPriority.high,
    )
    db.add_all([task_a, task_b])
    db.commit()


def test_users_endpoint_is_scoped_to_current_tenant(client, admin_token, db):
    _seed_multitenant_data(db)

    res = client.get("/api/v1/users", headers=auth(admin_token))
    assert res.status_code == 200
    usernames = {user["username"] for user in res.json()}
    assert usernames == {"admin", "pm_test", "dev_test", "hr_test"}
    assert "outsider" not in usernames


def test_users_with_rates_is_scoped_to_current_tenant(client, admin_token, db):
    _seed_multitenant_data(db)

    res = client.get("/api/v1/users/with-rates", headers=auth(admin_token))
    assert res.status_code == 200
    usernames = {user["username"] for user in res.json()}
    assert "outsider" not in usernames
    assert all(user["username"] != "outsider" for user in res.json())


def test_user_load_map_is_scoped_to_current_tenant(client, admin_token, db):
    _seed_multitenant_data(db)

    res = client.get("/api/v1/users/load", headers=auth(admin_token))
    assert res.status_code == 200
    usernames = {row["user"]["username"] for row in res.json()}
    assert usernames == {"admin", "pm_test", "dev_test", "hr_test"}
    assert "outsider" not in usernames


def test_tasks_endpoint_is_scoped_to_current_tenant(client, pm_token, db):
    _seed_multitenant_data(db)

    res = client.get("/api/v1/tasks", headers=auth(pm_token))
    assert res.status_code == 200
    task_ids = {task["id"] for task in res.json()}
    assert TASK_A_ID in task_ids
    assert TASK_B_ID not in task_ids


def test_foreign_tenant_task_detail_is_not_exposed(client, pm_token, db):
    _seed_multitenant_data(db)

    res = client.get(f"/api/v1/tasks/{TASK_B_ID}", headers=auth(pm_token))
    assert res.status_code == 404


def test_analytics_query_forbidden_foreign_project_returns_403(client, admin_token, db):
    _seed_multitenant_data(db)

    res = client.get(
        "/api/v1/analytics/query/hours_by_project",
        params={"project_id": PROJECT_B_ID},
        headers=auth(admin_token),
    )
    assert res.status_code == 403


def test_analytics_query_empty_scope_returns_empty_rows(client, admin_token, db):
    _seed_multitenant_data(db)

    # Org A only has consulting projects in this seed, so this scope should be empty.
    res = client.get(
        "/api/v1/analytics/query/hours_by_project",
        params={"project_type": "development"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["rows"] == []
    assert payload["total"] == 0


def test_advanced_utilization_forbidden_foreign_project_returns_403(client, admin_token, db):
    _seed_multitenant_data(db)

    res = client.get(
        "/api/v1/analytics/utilization/advanced",
        params={"project_id": PROJECT_B_ID},
        headers=auth(admin_token),
    )
    assert res.status_code == 403
