from tests.conftest import auth


def test_delete_report_catalog_item(client, admin_token, db):
    created = client.post(
        "/api/v1/billing-reports/report-catalog/save",
        headers=auth(admin_token),
        json={
            "name": "Delete Custom Report",
            "data_source": "projects",
            "icon": "chart",
            "is_public": False,
            "category": "custom",
        },
    )
    assert created.status_code in (200, 201)
    report_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/billing-reports/report-catalog/{report_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    deleted_again = client.delete(
        f"/api/v1/billing-reports/report-catalog/{report_id}",
        headers=auth(admin_token),
    )
    assert deleted_again.status_code == 404


def test_delete_automation_workflow(client, admin_token, db):
    created = client.post(
        "/api/v1/billing-reports/automation-workflows",
        headers=auth(admin_token),
        json={
            "name": "Delete Workflow",
            "trigger_type": "manual",
            "steps": [],
        },
    )
    assert created.status_code in (200, 201)
    wf_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/billing-reports/automation-workflows/{wf_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed = client.get("/api/v1/billing-reports/automation-workflows", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(w["id"] != wf_id for w in listed.json())


def test_delete_scheduled_report(client, admin_token, db):
    created = client.post(
        "/api/v1/billing-reports/scheduled-reports",
        headers=auth(admin_token),
        json={
            "name": "Delete Scheduled",
            "metric": "hours_by_month",
            "frequency": "weekly",
            "recipients": ["ops@example.com"],
            "include_pdf": True,
            "filters_json": "{}",
        },
    )
    assert created.status_code in (200, 201)
    report_id = created.json()["id"]

    deleted = client.delete(
        f"/api/v1/billing-reports/scheduled-reports/{report_id}",
        headers=auth(admin_token),
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    listed = client.get("/api/v1/billing-reports/scheduled-reports", headers=auth(admin_token))
    assert listed.status_code == 200
    assert all(r["id"] != report_id for r in listed.json())
