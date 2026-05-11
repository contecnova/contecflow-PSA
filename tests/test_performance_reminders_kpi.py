"""Tests para Phase A: recordatorios automáticos y KPIs operativos."""
from datetime import date, datetime, timedelta, timezone
from tests.conftest import auth


def _setup(db):
    """Asigna team a los users del fixture para que la elegibilidad pase."""
    from app.models.user import User
    for u in db.query(User).all():
        u.team = "Frontend"
        u.department = "Engineering"
    db.commit()


_CYCLE_COUNTER = {"n": 0}


def _make_active_cycle_with_reviews(client, admin_token, db, *, end_in_days=3, n_reviews=4):
    from app.models.user import User
    from app.models.performance import PerformanceReview, ReviewStatus
    from app.core.security import get_password_hash
    _CYCLE_COUNTER["n"] += 1
    suffix = _CYCLE_COUNTER["n"]
    end_date = (date.today() + timedelta(days=end_in_days)).isoformat()
    cid = client.post("/api/v1/performance/cycles",
                      headers=auth(admin_token),
                      json={"name": f"C-end{end_in_days}-{suffix}",
                            "end_date": end_date}).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cid}/activate",
                headers=auth(admin_token))
    # Creamos N pares (ids únicos por ciclo) y los enlazamos a un subject
    pm = db.query(User).filter(User.username == "pm_test").first()
    for i in range(n_reviews):
        peer = User(
            id=f"rk-{suffix}-{i}", username=f"rk_{suffix}_{i}",
            email=f"rk{suffix}_{i}@x.com",
            full_name=f"RK {suffix}-{i}", role="employee",
            team="Frontend", department="Engineering",
            is_active=True, hashed_password=get_password_hash("x"),
            organization_id=1,
        )
        db.add(peer)
    db.commit()
    for i in range(n_reviews):
        rev = PerformanceReview(
            id=f"rev-rk-{suffix}-{i}", cycle_id=cid,
            reviewee_id=pm.id, reviewer_id=f"rk-{suffix}-{i}",
            review_type="peer",
            status=ReviewStatus.pending,
            answers_json={},
        )
        db.add(rev)
    db.commit()
    return cid


# ── Recordatorios ──────────────────────────────────────────────────────────

def test_reminders_created_for_cycles_closing_soon(client, admin_token, db):
    _setup(db)
    cid = _make_active_cycle_with_reviews(client, admin_token, db, end_in_days=3, n_reviews=3)

    res = client.post("/api/v1/performance/admin/run-reminders",
                      headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert body["cycles_processed"] >= 1
    assert body["reminders_sent"] == 3  # uno por reviewer pendiente

    # Verificar notificaciones creadas
    from app.models.enterprise import Notification
    notes = db.query(Notification).filter(
        Notification.resource == "performance_reminder",
        Notification.resource_id == cid,
    ).all()
    assert len(notes) == 3
    assert all("pendiente" in n.title.lower() for n in notes)


def test_reminders_dedup_within_window(client, admin_token, db):
    _setup(db)
    _make_active_cycle_with_reviews(client, admin_token, db, end_in_days=2, n_reviews=2)

    first = client.post("/api/v1/performance/admin/run-reminders",
                        headers=auth(admin_token)).json()
    assert first["reminders_sent"] == 2
    # Segunda corrida inmediata: todos deduplicados
    second = client.post("/api/v1/performance/admin/run-reminders",
                         headers=auth(admin_token)).json()
    assert second["reminders_sent"] == 0
    assert second["reminders_skipped_dedup"] == 2


def test_reminders_skip_far_future_cycles(client, admin_token, db):
    _setup(db)
    # Ciclo que cierra en 30 días — fuera de la ventana de 7 días
    _make_active_cycle_with_reviews(client, admin_token, db, end_in_days=30, n_reviews=2)

    body = client.post("/api/v1/performance/admin/run-reminders",
                       headers=auth(admin_token)).json()
    assert body["reminders_sent"] == 0


# ── KPIs ───────────────────────────────────────────────────────────────────

def test_cycle_kpis_basic(client, admin_token, db):
    _setup(db)
    cid = _make_active_cycle_with_reviews(client, admin_token, db, end_in_days=5, n_reviews=4)

    # Marcamos 1 review como submitted con tiempo medible
    from app.models.performance import PerformanceReview, ReviewStatus
    rev = db.query(PerformanceReview).filter(PerformanceReview.cycle_id == cid).first()
    rev.status = ReviewStatus.submitted
    rev.submitted_at = datetime.now(timezone.utc)
    db.commit()

    res = client.get(f"/api/v1/performance/cycles/{cid}/kpis",
                     headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert body["total_reviews"] == 4
    assert body["submitted"] == 1
    assert body["pending"] == 3
    assert body["completion_rate"] == 25.0
    assert body["days_to_close"] == 5
    assert "peer" in body["by_type"]
    assert body["by_type"]["peer"]["submitted"] == 1
    # 3 reviewers con review pendiente
    assert len(body["top_stalled_reviewers"]) == 3


def test_org_kpis_aggregate_active_cycles(client, admin_token, db):
    _setup(db)
    _make_active_cycle_with_reviews(client, admin_token, db, end_in_days=5, n_reviews=2)
    _make_active_cycle_with_reviews(client, admin_token, db, end_in_days=14, n_reviews=2)

    res = client.get("/api/v1/performance/kpis", headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert body["active_cycles"] >= 2
    assert body["total_reviews_active"] == 4
    assert body["pending_reviews_active"] == 4
    assert body["global_completion_rate"] == 0.0


def test_kpis_require_management_role(client, dev_token, db):
    res = client.get("/api/v1/performance/kpis", headers=auth(dev_token))
    assert res.status_code == 403
