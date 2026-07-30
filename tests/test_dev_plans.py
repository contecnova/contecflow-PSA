"""Tests para Phase B: Development Plans (plan de acción tras 360°)."""
from tests.conftest import auth


def test_user_can_create_own_plan(client, dev_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    res = client.post(
        "/api/v1/performance/dev-plans", headers=auth(dev_token),
        json={
            "subject_id": dev.id,
            "title": "Mejora comunicación 2026",
            "summary": "Tras 360° del Q1 — focalizar en presentaciones cliente.",
            "goals": [
                {"title": "Asistir a curso de oratoria", "due_date": "2026-06-30"},
                {"title": "Liderar 3 reuniones de cliente"},
            ],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()["data"]
    assert body["subject_id"] == dev.id
    assert body["status"] == "draft"
    assert len(body["goals"]) == 2
    assert body["progress_pct"] == 0.0


def test_user_cannot_create_plan_for_other(client, dev_token, db):
    from app.models.user import User
    pm = db.query(User).filter(User.username == "pm_test").first()
    res = client.post(
        "/api/v1/performance/dev-plans", headers=auth(dev_token),
        json={"subject_id": pm.id, "title": "Plan ajeno"},
    )
    assert res.status_code == 403


def test_manager_can_create_plan_for_direct_report(client, pm_token, db):
    from app.models.user import User
    pm  = db.query(User).filter(User.username == "pm_test").first()
    dev = db.query(User).filter(User.username == "dev_test").first()
    dev.manager_id = pm.id
    db.commit()
    res = client.post(
        "/api/v1/performance/dev-plans", headers=auth(pm_token),
        json={"subject_id": dev.id, "title": "Plan del manager"},
    )
    assert res.status_code == 201


def test_completing_all_goals_marks_plan_completed(client, dev_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    plan_id = client.post(
        "/api/v1/performance/dev-plans", headers=auth(dev_token),
        json={
            "subject_id": dev.id, "title": "P",
            "goals": [{"title": "G1"}, {"title": "G2"}],
        },
    ).json()["data"]["id"]
    plan = client.get(f"/api/v1/performance/dev-plans/{plan_id}",
                      headers=auth(dev_token)).json()["data"]
    g1, g2 = plan["goals"]
    # Marcamos ambos como done
    client.patch(f"/api/v1/performance/dev-goals/{g1['id']}",
                 headers=auth(dev_token), json={"status": "done"})
    res = client.patch(f"/api/v1/performance/dev-goals/{g2['id']}",
                       headers=auth(dev_token), json={"status": "done"})
    assert res.status_code == 200
    # El plan ahora está completed
    plan2 = client.get(f"/api/v1/performance/dev-plans/{plan_id}",
                       headers=auth(dev_token)).json()["data"]
    assert plan2["status"] == "completed"
    assert plan2["progress_pct"] == 100.0
    # Cada goal completed_at != null y progress=100
    for g in plan2["goals"]:
        assert g["status"] == "done"
        assert g["progress"] == 100
        assert g["completed_at"] is not None


def test_other_user_cannot_view_plan(client, dev_token, pm_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    plan_id = client.post(
        "/api/v1/performance/dev-plans", headers=auth(dev_token),
        json={"subject_id": dev.id, "title": "Privado"},
    ).json()["data"]["id"]
    res = client.get(f"/api/v1/performance/dev-plans/{plan_id}",
                     headers=auth(pm_token))
    assert res.status_code == 403


def test_admin_can_view_any_plan(client, admin_token, dev_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    plan_id = client.post(
        "/api/v1/performance/dev-plans", headers=auth(dev_token),
        json={"subject_id": dev.id, "title": "Visible"},
    ).json()["data"]["id"]
    res = client.get(f"/api/v1/performance/dev-plans/{plan_id}",
                     headers=auth(admin_token))
    assert res.status_code == 200


def test_add_and_delete_goal(client, dev_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    plan_id = client.post(
        "/api/v1/performance/dev-plans", headers=auth(dev_token),
        json={"subject_id": dev.id, "title": "P"},
    ).json()["data"]["id"]
    g = client.post(f"/api/v1/performance/dev-plans/{plan_id}/goals",
                    headers=auth(dev_token),
                    json={"title": "Nuevo objetivo"}).json()["data"]
    plan = client.get(f"/api/v1/performance/dev-plans/{plan_id}",
                      headers=auth(dev_token)).json()["data"]
    assert len(plan["goals"]) == 1
    res = client.delete(f"/api/v1/performance/dev-goals/{g['id']}",
                        headers=auth(dev_token))
    assert res.status_code == 204
    plan2 = client.get(f"/api/v1/performance/dev-plans/{plan_id}",
                       headers=auth(dev_token)).json()["data"]
    assert plan2["goals"] == []
