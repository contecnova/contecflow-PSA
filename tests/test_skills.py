"""Tests de Skills y Catálogo de Habilidades — CRUD, asignación a usuarios, matriz."""
from app.models.resources import Skill
from app.models.resources import UserSkill
from tests.conftest import auth


def test_list_skill_catalog(client, admin_token, db):
    res = client.get("/api/v1/skills/catalog", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload


def test_create_skill(client, admin_token, db):
    res = client.post("/api/v1/skills/catalog", json={
        "name": "Python Avanzado",
        "category": "technical",
        "description": "Python con frameworks como FastAPI y Django",
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert "id" in data
    assert data["name"] == "Python Avanzado"


def test_update_skill(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Skill a Editar", "category": "tool",
    }, headers=auth(admin_token)).json()["data"]
    res = client.patch(f"/api/v1/skills/catalog/{skill['id']}",
        json={"name": "Skill a Editar", "category": "tool", "description": "Descripción actualizada"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_skill(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Skill a Borrar", "category": "soft",
    }, headers=auth(admin_token)).json()["data"]
    res = client.delete(f"/api/v1/skills/catalog/{skill['id']}",
        headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["ok"] is True

    listed = client.get("/api/v1/skills/catalog", headers=auth(admin_token))
    assert listed.status_code == 200
    listed_payload = listed.json()
    listed_items = listed_payload.get("items", listed_payload) if isinstance(listed_payload, dict) else listed_payload
    assert all(s["id"] != skill["id"] for s in listed_items)

    row = db.query(Skill).filter(Skill.id == skill["id"]).first()
    assert row is not None
    assert row.is_active is False


def test_assign_skill_to_user(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "React", "category": "language",
    }, headers=auth(admin_token)).json()["data"]
    res = client.post("/api/v1/skills/users/dev-test-id", json={
        "skill_id": skill["id"],
        "level": "intermediate",
        "years_experience": 2.5,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)


def test_list_user_skills(client, admin_token, db):
    res = client.get("/api/v1/skills/users/dev-test-id", headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()
    assert isinstance(payload, dict)
    assert isinstance(payload["items"], list)
    assert "meta" in payload


def test_skills_matrix(client, admin_token, db):
    res = client.get("/api/v1/skills/matrix", headers=auth(admin_token))
    assert res.status_code == 200


def test_skill_search(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Docker Expert", "category": "methodology",
    }, headers=auth(admin_token)).json()["data"]
    res = client.get(f"/api/v1/skills/search?skill_ids={skill['id']}", headers=auth(admin_token))
    assert res.status_code == 200


def test_skill_requires_admin(client, dev_token, db):
    res = client.post("/api/v1/skills/catalog", json={
        "name": "No autorizado", "category": "soft",
    }, headers=auth(dev_token))
    assert res.status_code in (401, 403)


def test_remove_user_skill(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Git Flow", "category": "certification",
    }, headers=auth(admin_token)).json()["data"]
    assign = client.post("/api/v1/skills/users/dev-test-id", json={
        "skill_id": skill["id"], "level": "basic",
    }, headers=auth(admin_token)).json()["data"]
    us_id = assign["id"]
    res = client.delete(f"/api/v1/skills/users/dev-test-id/{us_id}",
        headers=auth(admin_token))
    assert res.status_code == 200
    payload = res.json()["data"]
    assert payload["ok"] is True

    listed = client.get("/api/v1/skills/users/dev-test-id", headers=auth(admin_token))
    assert listed.status_code == 200
    # #67: APIListResponse wrapper — items en payload["items"]
    listed_items = listed.json().get("items") if isinstance(listed.json(), dict) else listed.json()
    assert all(us["id"] != us_id for us in listed_items)

    row = db.query(UserSkill).filter(UserSkill.id == us_id).first()
    assert row is None
