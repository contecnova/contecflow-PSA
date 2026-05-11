"""Tests para Phase C: export PDF y email-on-campaign-creation (best-effort)."""
from tests.conftest import auth


def _setup_team(db):
    from app.models.user import User
    for u in db.query(User).all():
        u.team = "Frontend"
        u.department = "Engineering"
    db.commit()


def test_campaign_dashboard_pdf_export(client, admin_token, db):
    _setup_team(db)
    from app.models.user import User
    from app.core.security import get_password_hash
    pm = db.query(User).filter(User.username == "pm_test").first()

    cid = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "PDF cycle"}).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cid}/activate",
                headers=auth(admin_token))

    # Crear pares y campaña
    for i in range(3):
        u = User(id=f"pdf-{i}", username=f"pdf_{i}", email=f"pdf{i}@x.com",
                 full_name=f"PDF {i}", role="employee",
                 team="Frontend", department="Engineering",
                 is_active=True, hashed_password=get_password_hash("x"),
                 organization_id=1)
        db.add(u)
    db.commit()
    camp_id = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(admin_token),
        json={"subject_id": pm.id, "self_review": True,
              "peer_reviewer_ids": [f"pdf-{i}" for i in range(3)],
              "anonymity_threshold": 3},
    ).json()["id"]

    # Marcar algunas reviews como submitted para tener contenido
    from app.models.performance import PerformanceReview, ReviewStatus
    for r in db.query(PerformanceReview).filter(
        PerformanceReview.campaign_id == camp_id,
    ).all():
        r.status = ReviewStatus.submitted
        r.answers_json = {"score_quality": 4, "strengths": "comentario"}
    db.commit()

    res = client.get(
        f"/api/v1/performance/campaigns/{camp_id}/dashboard.pdf",
        headers=auth(admin_token),
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    body = res.content
    assert body[:4] == b"%PDF"
    assert len(body) > 1000


def test_pdf_export_requires_admin_or_hr(client, dev_token, db):
    res = client.get("/api/v1/performance/campaigns/nonexistent/dashboard.pdf",
                     headers=auth(dev_token))
    assert res.status_code == 403


def test_campaign_creation_does_not_fail_when_smtp_missing(client, admin_token, db):
    """Verifica que la creación de campañas no se cae si el SMTP no está
    configurado (la integración email es best-effort)."""
    _setup_team(db)
    from app.models.user import User
    pm = db.query(User).filter(User.username == "pm_test").first()
    cid = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "SMTP-less"}).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cid}/activate",
                headers=auth(admin_token))
    res = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(admin_token),
        json={"subject_id": pm.id, "self_review": True},
    )
    assert res.status_code == 201
