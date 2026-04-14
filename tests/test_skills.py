"""Tests de Skills y Catálogo de Habilidades — CRUD, asignación a usuarios, matriz."""
from tests.conftest import auth


def test_list_skill_catalog(client, admin_token, db):
    res = client.get("/api/v1/skills/catalog", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_create_skill(client, admin_token, db):
    res = client.post("/api/v1/skills/catalog", json={
        "name": "Python Avanzado",
        "category": "technical",
        "description": "Python con frameworks como FastAPI y Django",
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)
    data = res.json()
    assert "id" in data
    assert data["name"] == "Python Avanzado"


def test_update_skill(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Skill a Editar", "category": "tool",
    }, headers=auth(admin_token)).json()
    res = client.patch(f"/api/v1/skills/catalog/{skill['id']}",
        json={"name": "Skill a Editar", "category": "tool", "description": "Descripción actualizada"},
        headers=auth(admin_token))
    assert res.status_code == 200


def test_delete_skill(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Skill a Borrar", "category": "soft",
    }, headers=auth(admin_token)).json()
    res = client.delete(f"/api/v1/skills/catalog/{skill['id']}",
        headers=auth(admin_token))
    assert res.status_code in (200, 204)


def test_assign_skill_to_user(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "React", "category": "language",
    }, headers=auth(admin_token)).json()
    res = client.post("/api/v1/skills/users/dev-test-id", json={
        "skill_id": skill["id"],
        "level": "intermediate",
        "years_experience": 2.5,
    }, headers=auth(admin_token))
    assert res.status_code in (200, 201)


def test_list_user_skills(client, admin_token, db):
    res = client.get("/api/v1/skills/users/dev-test-id", headers=auth(admin_token))
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_skills_matrix(client, admin_token, db):
    res = client.get("/api/v1/skills/matrix", headers=auth(admin_token))
    assert res.status_code == 200


def test_skill_search(client, admin_token, db):
    skill = client.post("/api/v1/skills/catalog", json={
        "name": "Docker Expert", "category": "methodology",
    }, headers=auth(admin_token)).json()
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
    }, headers=auth(admin_token)).json()
    assign = client.post("/api/v1/skills/users/dev-test-id", json={
        "skill_id": skill["id"], "level": "basic",
    }, headers=auth(admin_token)).json()
    us_id = assign["id"]
    res = client.delete(f"/api/v1/skills/users/dev-test-id/{us_id}",
        headers=auth(admin_token))
    assert res.status_code in (200, 204)
