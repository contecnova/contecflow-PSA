from tests.conftest import auth



## Todos los tests usan el fixture seed_multitenant de conftest.py


def test_users_endpoint_is_scoped_to_current_tenant(client, admin_token, db, seed_multitenant):
    res = client.get("/api/v1/users", headers=auth(admin_token))
    assert res.status_code == 200
    usernames = {user["username"] for user in res.json()}
    assert usernames == {"admin", "pm_test", "dev_test", "hr_test"}
    assert "outsider" not in usernames


def test_users_with_rates_is_scoped_to_current_tenant(client, admin_token, db, seed_multitenant):
    res = client.get("/api/v1/users/with-rates", headers=auth(admin_token))
    assert res.status_code == 200
    usernames = {user["username"] for user in res.json()}
    assert "outsider" not in usernames
    assert all(user["username"] != "outsider" for user in res.json())


def test_user_load_map_is_scoped_to_current_tenant(client, admin_token, db, seed_multitenant):
    res = client.get("/api/v1/users/load", headers=auth(admin_token))
    assert res.status_code == 200
    usernames = {row["user"]["username"] for row in res.json()}
    assert usernames == {"admin", "pm_test", "dev_test", "hr_test"}
    assert "outsider" not in usernames


def test_tasks_endpoint_is_scoped_to_current_tenant(client, pm_token, db, seed_multitenant):
    res = client.get("/api/v1/tasks", headers=auth(pm_token))
    assert res.status_code == 200
    body = res.json()
    items = body if isinstance(body, list) else body.get("items", [])
    task_ids = {task["id"] for task in items}
    assert "task-a-test" in task_ids
    assert "task-b-test" not in task_ids


def test_foreign_tenant_task_detail_is_not_exposed(client, pm_token, db, seed_multitenant):
    res = client.get("/api/v1/tasks/task-b-test", headers=auth(pm_token))
    assert res.status_code == 404


def test_deliverables_for_foreign_tenant_project_are_not_exposed(client, pm_token, db, seed_multitenant):
    res = client.get("/api/v1/deliverables/project-b-test", headers=auth(pm_token))
    assert res.status_code == 200
    payload = res.json()
    assert payload["deliverables"] == []
    assert payload["summary"]["total"] == 0


def test_analytics_query_forbidden_foreign_project_returns_403(client, admin_token, db, seed_multitenant):
    res = client.get(
        "/api/v1/analytics/query/hours_by_project",
        params={"project_id": "project-b-test"},
        headers=auth(admin_token),
    )
    assert res.status_code == 403


def test_analytics_query_empty_scope_returns_empty_rows(client, admin_token, db, seed_multitenant):
    res = client.get(
        "/api/v1/analytics/query/hours_by_project",
        params={"project_type": "development"},
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    payload = res.json()
    assert payload["rows"] == []
    assert payload["total"] == 0


def test_advanced_utilization_forbidden_foreign_project_returns_403(client, admin_token, db, seed_multitenant):
    res = client.get(
        "/api/v1/analytics/utilization/advanced",
        params={"project_id": "project-b-test"},
        headers=auth(admin_token),
    )
    assert res.status_code == 403
