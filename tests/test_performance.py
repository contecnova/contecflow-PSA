"""Tests de Performance Reviews — ciclos, evaluaciones, submit."""
from tests.conftest import auth


def test_list_cycles_empty(client, admin_token, db):
    res = client.get("/api/v1/performance/cycles", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)
    # Paginación expuesta vía header X-Total-Count
    assert "x-total-count" in {k.lower() for k in res.headers.keys()}
    assert res.headers["x-total-count"] == "0"


def test_list_cycles_pagination(client, admin_token, db):
    """Total real expuesto en el header aunque la página recortada sea menor."""
    for i in range(3):
        client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                    json={"name": f"P{i}"})
    res = client.get("/api/v1/performance/cycles?limit=2&offset=0",
                     headers=auth(admin_token))
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 2
    assert res.headers["x-total-count"] == "3"


def test_create_cycle(client, admin_token, db):
    res = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"name": "Evaluación Q2 2025", "start_date": "2025-04-01", "end_date": "2025-06-30"})
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert data["name"] == "Evaluación Q2 2025"


def test_create_cycle_requires_name(client, admin_token, db):
    res = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"start_date": "2025-01-01"})
    assert res.status_code == 422


def test_employee_cannot_create_cycle(client, dev_token, db):
    res = client.post("/api/v1/performance/cycles",
        headers=auth(dev_token),
        json={"name": "Ciclo no autorizado"})
    assert res.status_code in (403, 401)


def test_activate_cycle(client, admin_token, db):
    cycle_id = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"name": "Ciclo activar"}
    ).json()["id"]
    res = client.post(f"/api/v1/performance/cycles/{cycle_id}/activate",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["status"] == "active"


def test_close_cycle(client, admin_token, db):
    cycle_id = client.post("/api/v1/performance/cycles",
        headers=auth(admin_token),
        json={"name": "Ciclo cerrar"}
    ).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cycle_id}/activate", headers=auth(admin_token))
    res = client.post(f"/api/v1/performance/cycles/{cycle_id}/close",
        headers=auth(admin_token))
    assert res.status_code == 200
    assert res.json()["status"] == "closed"


def test_my_reviews_empty(client, dev_token, db):
    res = client.get("/api/v1/performance/my-reviews", headers=auth(dev_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_full_evaluation_flow(client, admin_token, dev_token, db):
    """Flujo end-to-end: ciclo → asignar evaluación → puntuar → enviar."""
    from app.models.user import User

    # 1) Admin crea y activa un ciclo
    cycle_id = client.post(
        "/api/v1/performance/cycles", headers=auth(admin_token),
        json={"name": "E2E flow", "start_date": "2025-01-01", "end_date": "2025-03-31"},
    ).json()["id"]
    r = client.post(f"/api/v1/performance/cycles/{cycle_id}/activate", headers=auth(admin_token))
    assert r.status_code == 200

    # 2) Asignamos una evaluación: dev evalúa al pm (peer review)
    # Saltamos la validación de elegibilidad (los usuarios del fixture no
    # comparten equipo/departamento). Esa validación se cubre en
    # tests/test_performance_360.py.
    pm = db.query(User).filter(User.username == "pm_test").first()
    dev = db.query(User).filter(User.username == "dev_test").first()
    r = client.post(
        f"/api/v1/performance/cycles/{cycle_id}/reviews", headers=auth(admin_token),
        json={"reviewer_id": dev.id, "reviewee_id": pm.id, "review_type": "peer",
              "validate_eligibility": False},
    )
    assert r.status_code == 201, r.text
    review_id = r.json()["id"]

    # 3) Dev (el evaluador) ve la evaluación pendiente en su lista
    pending = client.get("/api/v1/performance/my-reviews", headers=auth(dev_token)).json()
    assert any(rev["id"] == review_id for rev in pending), "La review asignada no aparece en my-reviews"
    me_review = next(rev for rev in pending if rev["id"] == review_id)
    assert me_review["status"] == "pending"
    assert me_review["reviewee_name"]  # nombre del evaluado serializado

    # 4) Dev guarda puntuaciones (PATCH)
    r = client.patch(
        f"/api/v1/performance/reviews/{review_id}", headers=auth(dev_token),
        json={
            "score_quality": 4, "score_delivery": 5,
            "score_teamwork": 4, "score_leadership": 3, "score_innovation": 4,
            "strengths": "Comunicación clara con el equipo.",
            "improvements": "Documentar más decisiones técnicas.",
            "goals_next": "Asumir lead técnico en el próximo proyecto.",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["score_quality"] == 4
    assert body["score_overall"] == 4.0  # media de las 5 puntuaciones
    assert body["status"] == "pending"   # aún no enviada

    # 5) Solo el evaluador puede modificarla (no admin, no otro)
    r = client.patch(
        f"/api/v1/performance/reviews/{review_id}", headers=auth(admin_token),
        json={"score_quality": 1},
    )
    assert r.status_code == 403

    # 6) Dev envía la evaluación
    r = client.post(f"/api/v1/performance/reviews/{review_id}/submit", headers=auth(dev_token))
    assert r.status_code == 200
    assert r.json()["status"] == "submitted"

    # 7) Ya no aparece en pending para el evaluador
    pending_after = client.get("/api/v1/performance/my-reviews", headers=auth(dev_token)).json()
    assert not any(rev["id"] == review_id for rev in pending_after)

    # 8) Aparece en histórico del evaluado
    history = client.get(f"/api/v1/performance/users/{pm.id}/history", headers=auth(admin_token)).json()
    assert any(rev["id"] == review_id for rev in history)

    # 9) Tras cerrar el ciclo, no se pueden modificar las evaluaciones
    client.post(f"/api/v1/performance/cycles/{cycle_id}/close", headers=auth(admin_token))
    r = client.patch(
        f"/api/v1/performance/reviews/{review_id}", headers=auth(dev_token),
        json={"strengths": "intento modificar"},
    )
    assert r.status_code == 400
    assert "cerrado" in r.json()["detail"].lower()


def test_create_review_requires_both_ids(client, admin_token, db):
    """Validación: faltan reviewer_id o reviewee_id → 422."""
    cycle_id = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                           json={"name": "Validación"}).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cycle_id}/activate", headers=auth(admin_token))
    r = client.post(f"/api/v1/performance/cycles/{cycle_id}/reviews",
                    headers=auth(admin_token), json={"reviewer_id": "x"})
    assert r.status_code == 422
