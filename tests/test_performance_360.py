"""Tests para evaluaciones 360° con preguntas configurables, elegibilidad smart,
campañas multi-evaluador, anonimización y self-service de managers."""
from tests.conftest import auth


# ── Helpers ─────────────────────────────────────────────────────────────────

def _setup_team(db, *, team="Frontend", department="Engineering"):
    """Asigna team/department a los users del fixture para que las reglas
    de elegibilidad funcionen. Devuelve (admin, pm, dev, hr)."""
    from app.models.user import User
    admin = db.query(User).filter(User.username == "admin").first()
    pm    = db.query(User).filter(User.username == "pm_test").first()
    dev   = db.query(User).filter(User.username == "dev_test").first()
    hr    = db.query(User).filter(User.username == "hr_test").first()
    for u in (admin, pm, dev, hr):
        u.department = department
        u.team = team
    db.commit()
    return admin, pm, dev, hr


def _make_active_cycle(client, admin_token, *, name="Cycle 360"):
    cid = client.post(
        "/api/v1/performance/cycles", headers=auth(admin_token),
        json={"name": name},
    ).json()["id"]
    client.post(f"/api/v1/performance/cycles/{cid}/activate",
                headers=auth(admin_token))
    return cid


# ── Phase 1: configurable questions ─────────────────────────────────────────

def test_cycle_seeds_default_questions(client, admin_token, db):
    cid = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "C1"}).json()["id"]
    res = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                     headers=auth(admin_token))
    assert res.status_code == 200
    qs = res.json()
    # 5 ratings + 3 textos por defecto
    assert len(qs) == 8
    keys = {q["key"] for q in qs}
    assert "score_quality" in keys
    assert "strengths" in keys


def test_create_cycle_without_default_questions(client, admin_token, db):
    cid = client.post(
        "/api/v1/performance/cycles", headers=auth(admin_token),
        json={"name": "Empty", "seed_default_questions": False},
    ).json()["id"]
    qs = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                    headers=auth(admin_token)).json()
    assert qs == []


def test_clone_questions_from_previous_cycle(client, admin_token, db):
    src = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "Src"}).json()["id"]
    dst = client.post(
        "/api/v1/performance/cycles", headers=auth(admin_token),
        json={"name": "Dst", "seed_default_questions": False,
              "clone_questions_from_cycle_id": src},
    ).json()["id"]
    src_keys = {q["key"] for q in
                client.get(f"/api/v1/performance/cycles/{src}/questions",
                           headers=auth(admin_token)).json()}
    dst_keys = {q["key"] for q in
                client.get(f"/api/v1/performance/cycles/{dst}/questions",
                           headers=auth(admin_token)).json()}
    assert src_keys == dst_keys and len(dst_keys) == 8


def test_questions_immutable_after_activate(client, admin_token, db):
    cid = _make_active_cycle(client, admin_token, name="Immut")
    r = client.post(
        f"/api/v1/performance/cycles/{cid}/questions",
        headers=auth(admin_token),
        json={"key": "x", "label": "X?", "kind": "rating_5"},
    )
    assert r.status_code == 400
    assert "borrador" in r.json()["detail"].lower()


def test_delete_question_response_and_concealment(client, admin_token, db):
    """Regresión reforzada del DELETE /questions/{id}:
    valida la respuesta y verifica que la pregunta deja de aparecer en el GET
    listado del ciclo (ABAC + concealment pattern)."""
    # Ciclo en draft (las preguntas solo se pueden borrar en draft)
    cid = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "Del-Q", "seed_default_questions": False}).json()["id"]
    # Creamos una pregunta y memorizamos su id + key
    q = client.post(
        f"/api/v1/performance/cycles/{cid}/questions", headers=auth(admin_token),
        json={"key": "tobedeleted", "label": "Borrar esta",
              "kind": "rating_5", "required": False},
    ).json()
    assert q["id"] and q["key"] == "tobedeleted"

    # Antes de borrar: aparece en el listado
    listing_before = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                                headers=auth(admin_token)).json()
    assert any(x["id"] == q["id"] for x in listing_before)

    # 1) Respuesta del DELETE: 204 sin body
    res = client.delete(f"/api/v1/performance/questions/{q['id']}",
                        headers=auth(admin_token))
    assert res.status_code == 204
    # Body vacío en 204
    assert res.content == b""

    # 2) Concealment: ya no aparece en el listado del ciclo
    listing_after = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                               headers=auth(admin_token)).json()
    assert all(x["id"] != q["id"] for x in listing_after)
    assert all(x["key"] != "tobedeleted" for x in listing_after)
    # Y un PATCH posterior contra el id eliminado responde 404
    res2 = client.patch(f"/api/v1/performance/questions/{q['id']}",
                        headers=auth(admin_token), json={"label": "x"})
    assert res2.status_code == 404


def test_delete_question_blocked_after_activate(client, admin_token, db):
    """Una vez el ciclo está activo, el DELETE de preguntas debe rechazarse."""
    cid = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "Del-Q-active"}).json()["id"]
    qs = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                    headers=auth(admin_token)).json()
    qid = qs[0]["id"]
    client.post(f"/api/v1/performance/cycles/{cid}/activate",
                headers=auth(admin_token))
    res = client.delete(f"/api/v1/performance/questions/{qid}",
                        headers=auth(admin_token))
    assert res.status_code == 400
    # Y la pregunta sigue ahí (concealment NO debe ocurrir cuando el delete falla)
    qs_after = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                          headers=auth(admin_token)).json()
    assert any(q["id"] == qid for q in qs_after)


def test_delete_question_employee_forbidden(client, admin_token, dev_token, db):
    """RBAC: solo admin/HR puede borrar preguntas."""
    cid = client.post("/api/v1/performance/cycles", headers=auth(admin_token),
                      json={"name": "Del-Q-rbac"}).json()["id"]
    qid = client.get(f"/api/v1/performance/cycles/{cid}/questions",
                     headers=auth(admin_token)).json()[0]["id"]
    res = client.delete(f"/api/v1/performance/questions/{qid}",
                        headers=auth(dev_token))
    assert res.status_code == 403


# ── Phase 1: smart eligibility ──────────────────────────────────────────────

def test_eligible_reviewers_no_manager_returns_empty(client, admin_token, db):
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="Elig-mgr")
    from app.models.user import User
    pm = db.query(User).filter(User.username == "pm_test").first()
    # pm no tiene manager_id configurado
    r = client.get(
        f"/api/v1/performance/cycles/{cid}/eligible-reviewers/{pm.id}/manager",
        headers=auth(admin_token),
    )
    assert r.status_code == 200
    body = r.json()
    assert body["users"] == []
    assert "manager" in body["reason_blocked"].lower()


def test_eligible_peers_filter_by_team(client, admin_token, db):
    _setup_team(db, team="Frontend")
    cid = _make_active_cycle(client, admin_token, name="Elig-peer")
    from app.models.user import User
    pm = db.query(User).filter(User.username == "pm_test").first()
    r = client.get(
        f"/api/v1/performance/cycles/{cid}/eligible-reviewers/{pm.id}/peer",
        headers=auth(admin_token),
    )
    body = r.json()
    # 3 pares (admin, dev, hr) — todos en team=Frontend
    assert len(body["users"]) == 3
    assert body["reason_blocked"] is None


def test_eligible_upward_uses_reverse_org_chart(client, admin_token, db):
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="Elig-up")
    from app.models.user import User
    pm  = db.query(User).filter(User.username == "pm_test").first()
    dev = db.query(User).filter(User.username == "dev_test").first()
    dev.manager_id = pm.id
    db.commit()
    r = client.get(
        f"/api/v1/performance/cycles/{cid}/eligible-reviewers/{pm.id}/upward",
        headers=auth(admin_token),
    )
    body = r.json()
    assert len(body["users"]) == 1
    assert body["users"][0]["id"] == dev.id


def test_create_review_rejects_ineligible_reviewer(client, admin_token, db):
    _setup_team(db, team="Frontend")
    cid = _make_active_cycle(client, admin_token, name="Reject")
    from app.models.user import User
    # Creamos un user en otro equipo y lo intentamos asignar como par
    outsider = User(
        id="outsider-id", username="outsider", email="out@x.com",
        full_name="Outsider", role="employee",
        team="Backend", department="Engineering",
        is_active=True, hashed_password="x",
    )
    db.add(outsider)
    db.commit()
    pm = db.query(User).filter(User.username == "pm_test").first()
    r = client.post(
        f"/api/v1/performance/cycles/{cid}/reviews", headers=auth(admin_token),
        json={"reviewer_id": outsider.id, "reviewee_id": pm.id, "review_type": "peer"},
    )
    assert r.status_code == 400


# ── Phase 2: campañas 360° + anonimización ──────────────────────────────────

def _seed_users(db, *, team="Frontend", n_extra_peers=2):
    """Crea N usuarios extra como pares para tests de anonimización."""
    from app.models.user import User
    from app.core.security import get_password_hash
    extra = []
    for i in range(n_extra_peers):
        u = User(
            id=f"peer-{i}", username=f"peer_{i}", email=f"p{i}@x.com",
            full_name=f"Peer {i}", role="employee",
            team=team, department="Engineering",
            is_active=True, hashed_password=get_password_hash("x"),
            organization_id=1,
        )
        db.add(u)
        extra.append(u)
    db.commit()
    return extra


def test_campaign_creates_all_reviews_and_notifies(client, admin_token, db):
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="Camp1")
    from app.models.user import User
    from app.models.enterprise import Notification
    pm  = db.query(User).filter(User.username == "pm_test").first()
    dev = db.query(User).filter(User.username == "dev_test").first()
    pm.manager_id = None  # explícito
    dev.manager_id = pm.id
    db.commit()

    extras = _seed_users(db, n_extra_peers=2)
    peer_ids = [u.id for u in extras]

    r = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(admin_token),
        json={
            "subject_id": pm.id,
            "self_review": True,
            "manager_reviewer_id": None,
            "peer_reviewer_ids": peer_ids,
            "upward_reviewer_ids": [dev.id],
            "anonymity_threshold": 3,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total_reviewers"] == 1 + 2 + 1  # self + 2 peers + 1 upward
    assert body["by_type"] == {"self": 1, "manager": 0, "peer": 2, "upward": 1}

    # Notificaciones encoladas para cada reviewer
    notes = db.query(Notification).filter(
        Notification.resource == "performance_review"
    ).all()
    assert len(notes) == 4
    assert {n.user_id for n in notes} == {pm.id, *peer_ids, dev.id}


def _submit_rating(client, dev_token_or_admin, review_id, score):
    return client.patch(
        f"/api/v1/performance/reviews/{review_id}",
        headers=auth(dev_token_or_admin),
        json={"answers": {"score_quality": score}},
    )


def test_dashboard_anonymizes_below_threshold(client, admin_token, db):
    """Con 1 par bajo el umbral=3 → comentarios de pares anonimizados;
    con 3 pares → expuestos."""
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="Anon")
    from app.models.user import User
    pm = db.query(User).filter(User.username == "pm_test").first()

    # 1 par solo
    one_peer = _seed_users(db, n_extra_peers=1)[0]
    r = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(admin_token),
        json={"subject_id": pm.id, "self_review": False,
              "peer_reviewer_ids": [one_peer.id], "anonymity_threshold": 3},
    )
    camp_id = r.json()["id"]
    # El par envía con texto
    review_id = client.get(
        f"/api/v1/performance/campaigns/{camp_id}/reviews",
        headers=auth(admin_token),
    ).json()[0]["id"]
    # Como reviewer es peer-0, hacemos login para PATCH? No, ese reviewer es
    # otro user. Pero solo el reviewer puede modificar. Lo modificamos
    # directamente a través de la sesión DB para simplificar el test.
    from app.models.performance import PerformanceReview, ReviewStatus
    rev = db.query(PerformanceReview).filter(PerformanceReview.id == review_id).first()
    rev.answers_json = {"score_quality": 4, "strengths": "Comentario de un par único"}
    rev.status = ReviewStatus.submitted
    db.commit()

    dash = client.get(f"/api/v1/performance/campaigns/{camp_id}/dashboard",
                      headers=auth(admin_token)).json()
    peer_group = dash["groups"]["peer"]
    assert peer_group["count"] == 1
    assert peer_group["anonymized"] is True
    # texto NO expuesto
    assert peer_group["text_by_question"].get("strengths", []) == []
    # rating SÍ expuesto (anonimización solo aplica a textos)
    assert peer_group["ratings_by_question"]["score_quality"]["avg"] == 4


def test_dashboard_exposes_text_above_threshold(client, admin_token, db):
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="Anon-ok")
    from app.models.user import User
    from app.models.performance import PerformanceReview, ReviewStatus
    pm = db.query(User).filter(User.username == "pm_test").first()

    three_peers = _seed_users(db, n_extra_peers=3)
    r = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(admin_token),
        json={"subject_id": pm.id, "self_review": False,
              "peer_reviewer_ids": [u.id for u in three_peers],
              "anonymity_threshold": 3},
    )
    camp_id = r.json()["id"]
    revs = db.query(PerformanceReview).filter(
        PerformanceReview.campaign_id == camp_id
    ).all()
    for i, rv in enumerate(revs):
        rv.answers_json = {"score_quality": 4 + (i % 2),
                           "strengths": f"texto del par {i}"}
        rv.status = ReviewStatus.submitted
    db.commit()

    dash = client.get(f"/api/v1/performance/campaigns/{camp_id}/dashboard",
                      headers=auth(admin_token)).json()
    peer_group = dash["groups"]["peer"]
    assert peer_group["count"] == 3
    assert peer_group["anonymized"] is False
    texts = peer_group["text_by_question"]["strengths"]
    assert len(texts) == 3


# ── Phase 3: self-service y histórico ───────────────────────────────────────

def test_pm_cannot_launch_campaign_for_non_direct_report(client, admin_token, pm_token, db):
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="SS-no")
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    # dev NO tiene manager_id apuntando a pm
    r = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(pm_token),
        json={"subject_id": dev.id, "self_review": True},
    )
    assert r.status_code == 403


def test_pm_can_launch_campaign_for_direct_report(client, admin_token, pm_token, db):
    _setup_team(db)
    cid = _make_active_cycle(client, admin_token, name="SS-yes")
    from app.models.user import User
    pm  = db.query(User).filter(User.username == "pm_test").first()
    dev = db.query(User).filter(User.username == "dev_test").first()
    dev.manager_id = pm.id
    db.commit()
    r = client.post(
        f"/api/v1/performance/cycles/{cid}/campaigns", headers=auth(pm_token),
        json={"subject_id": dev.id, "self_review": True},
    )
    assert r.status_code == 201


def test_user_can_view_own_360_history(client, dev_token, db):
    from app.models.user import User
    dev = db.query(User).filter(User.username == "dev_test").first()
    r = client.get(f"/api/v1/performance/users/{dev.id}/360-history",
                   headers=auth(dev_token))
    assert r.status_code == 200
    body = r.json()
    assert body["subject_id"] == dev.id
    assert body["series"] == []  # sin campañas aún


def test_user_cannot_view_other_users_360_history(client, dev_token, db):
    from app.models.user import User
    pm = db.query(User).filter(User.username == "pm_test").first()
    r = client.get(f"/api/v1/performance/users/{pm.id}/360-history",
                   headers=auth(dev_token))
    assert r.status_code == 403
