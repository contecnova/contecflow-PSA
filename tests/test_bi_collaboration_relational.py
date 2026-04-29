from tests.conftest import auth

from app.models.bi_collaboration import DashboardComment, DashboardShare, DashboardVersion


def test_bi_comments_persist_in_relational_table(client, admin_token, db):
    create_res = client.post(
        "/api/v1/bi/collaboration/comments",
        headers=auth(admin_token),
        json={
            "dashboard_key": "executive",
            "widget_id": "kpi_margin",
            "message": "Need annotate margin variance",
        },
    )
    assert create_res.status_code == 200, create_res.text
    comment = create_res.json()["comment"]

    rows = db.query(DashboardComment).filter(DashboardComment.id == comment["id"]).all()
    assert len(rows) == 1

    resolve_res = client.patch(
        f"/api/v1/bi/collaboration/comments/{comment['id']}/resolve",
        headers=auth(admin_token),
    )
    assert resolve_res.status_code == 200, resolve_res.text

    db.refresh(rows[0])
    assert rows[0].resolved is True


def test_bi_dashboard_versions_persist_in_relational_table(client, admin_token, db):
    create_res = client.post(
        "/api/v1/bi/collaboration/dashboards/executive/versions",
        headers=auth(admin_token),
        json={"config": {"layout": "grid", "period_days": 30}, "change_log": "Initial snapshot"},
    )
    assert create_res.status_code == 200, create_res.text
    version = create_res.json()["version"]

    rows = db.query(DashboardVersion).filter(DashboardVersion.id == version["id"]).all()
    assert len(rows) == 1
    assert rows[0].version == 1

    list_res = client.get(
        "/api/v1/bi/collaboration/dashboards/executive/versions",
        headers=auth(admin_token),
    )
    assert list_res.status_code == 200, list_res.text
    assert list_res.json()["count"] >= 1


def test_bi_dashboard_shares_persist_in_relational_table(client, admin_token, db):
    share_res = client.post(
        "/api/v1/bi/collaboration/dashboards/executive/shares",
        headers=auth(admin_token),
        json={"target_user_id": "pm-test-id", "target_user_name": "PM Test", "permission": "edit"},
    )
    assert share_res.status_code == 200, share_res.text
    share = share_res.json()["share"]

    rows = db.query(DashboardShare).filter(DashboardShare.id == share["id"]).all()
    assert len(rows) == 1
    assert rows[0].permission == "edit"

    revoke_res = client.delete(
        f"/api/v1/bi/collaboration/dashboards/executive/shares/{share['id']}",
        headers=auth(admin_token),
    )
    assert revoke_res.status_code == 200, revoke_res.text

    assert db.query(DashboardShare).filter(DashboardShare.id == share["id"]).count() == 0
