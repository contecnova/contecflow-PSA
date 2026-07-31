"""Tests de proyectos — CRUD, estados, permisos, aislamiento multi-tenant."""
import uuid
from tests.conftest import auth

PROJECT_PAYLOAD = {
    "name": "Proyecto Test Alpha",
    "code": "ALPHA",
    "description": "Proyecto de prueba",
    "status": "planning",
    "billing_type": "time_material",
    "is_billable": True,
}


def test_create_project_as_pm(client, pm_token, db):
    res = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(pm_token))
    assert res.status_code in (200, 201)
    data = res.json()["data"]
    assert data["name"] == "Proyecto Test Alpha"
    assert data["code"] == "ALPHA"
    return data["id"]


def test_create_project_as_dev_forbidden(client, dev_token, db):
    """Un developer no puede crear proyectos."""
    res = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(dev_token))
    assert res.status_code in (403, 422)


def test_list_projects(client, admin_token, db):
    # Crear primero
    client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(admin_token))
    res = client.get("/api/v1/projects", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    projects = data if isinstance(data, list) else data.get("items", data.get("projects", []))
    assert len(projects) >= 1


def test_get_project_by_id(client, pm_token, db):
    create = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(pm_token))
    pid = create.json()["data"]["id"]
    res = client.get(f"/api/v1/projects/{pid}", headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["id"] == pid


def test_update_project_status(client, pm_token, db):
    create = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(pm_token))
    pid = create.json()["data"]["id"]
    res = client.patch(f"/api/v1/projects/{pid}", json={"status": "active"}, headers=auth(pm_token))
    assert res.status_code == 200
    assert res.json()["status"] == "active"


def test_project_not_found(client, admin_token, db):
    res = client.get("/api/v1/projects/nonexistent-id-xyz", headers=auth(admin_token))
    assert res.status_code == 404


def test_project_requires_auth(client, db):
    res = client.get("/api/v1/projects")
    assert res.status_code in (401, 403)


def test_create_project_duplicate_code(client, pm_token, db):
    client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(pm_token))
    res = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(pm_token))
    # Debe fallar o crear (depende de la implementación)
    # Lo importante es que no crashea
    assert res.status_code in (200, 201, 400, 409, 422)


def test_delete_project(client, admin_token, db):
    create = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth(admin_token))
    pid = create.json()["data"]["id"]
    res = client.delete(f"/api/v1/projects/{pid}", headers=auth(admin_token))
    assert res.status_code in (200, 204)


def test_project_member_remove_is_soft_and_reactivable(client, admin_token, db):
    create = client.post("/api/v1/projects", json={**PROJECT_PAYLOAD, "code": "ALPHA-MEM"}, headers=auth(admin_token))
    pid = create.json()["data"]["id"]

    me = client.get("/api/v1/auth/me", headers=auth(admin_token))
    uid = me.json()["id"]

    add = client.post(
        f"/api/v1/projects/{pid}/members",
        json={"user_id": uid},
        headers=auth(admin_token),
    )
    assert add.status_code in (200, 201), add.text
    member_id = add.json()["id"]

    remove = client.delete(f"/api/v1/projects/{pid}/members/{member_id}", headers=auth(admin_token))
    assert remove.status_code == 200

    listed = client.get(f"/api/v1/projects/{pid}/members", headers=auth(admin_token))
    assert listed.status_code == 200
    ids = [m["id"] for m in listed.json()]
    assert member_id not in ids

    # Re-adding same user should reactivate previous row (no duplicate conflict)
    add_again = client.post(
        f"/api/v1/projects/{pid}/members",
        json={"user_id": uid},
        headers=auth(admin_token),
    )
    assert add_again.status_code in (200, 201), add_again.text


# ── Multi-tenancy org isolation tests ─────────────────────────────────────────

def _create_org_and_user(db, role="admin"):
    """Helper: create an organisation and a user belonging to it, return (org_id, user)."""
    from app.models.mfa import Organization
    from app.models.user import User, UserRole, UserStatus
    from app.core.security import get_password_hash

    org_id = str(uuid.uuid4())
    org = Organization(id=org_id, name=f"Org-{org_id[:8]}", slug=f"org-{org_id[:8]}")
    db.add(org)
    db.flush()

    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        username=f"user-{user_id[:8]}",
        email=f"user-{user_id[:8]}@test.com",
        full_name="Test User",
        role=UserRole.admin,
        status=UserStatus.active,
        is_active=True,
        organization_id=org_id,
        hashed_password=get_password_hash("TestPass123!"),
        weekly_capacity_hours=40.0,
        currency="EUR"
    )
    db.add(user)
    db.commit()
    return org_id, user


def test_project_auto_assigns_org_on_create(client, db):
    """A project created by a user with org_id should inherit that org_id."""
    org_id, user = _create_org_and_user(db)
    # Login as the new org user
    res = client.post("/api/v1/auth/login", json={"username": user.username, "password": "TestPass123!"})
    assert res.status_code == 200
    token = res.cookies.get("access_token")
    assert token

    create = client.post("/api/v1/projects", json={
        **PROJECT_PAYLOAD, "code": f"ORG-{org_id[:4]}",
    }, headers=auth(token))
    assert create.status_code in (200, 201)
    pid = create.json()["data"]["id"]

    # Check the stored project has organization_id set
    from app.models.project import Project
    proj = db.query(Project).filter(Project.id == pid).first()
    assert proj is not None
    assert proj.organization_id == org_id


def test_project_list_scoped_to_org(client, db):
    """Users from different orgs should not see each other's projects."""
    org_a_id, user_a = _create_org_and_user(db)
    org_b_id, user_b = _create_org_and_user(db)

    # Login as user_a and create a project
    login_a = client.post("/api/v1/auth/login", json={"username": user_a.username, "password": "TestPass123!"})
    token_a = login_a.cookies.get("access_token")
    assert token_a
    create_a = client.post("/api/v1/projects", json={
        **PROJECT_PAYLOAD, "code": f"A-{org_a_id[:4]}",
    }, headers=auth(token_a))
    proj_a_id = create_a.json()["data"]["id"]

    # Login as user_b — should NOT see project from org_a
    login_b = client.post("/api/v1/auth/login", json={"username": user_b.username, "password": "TestPass123!"})
    token_b = login_b.cookies.get("access_token")
    assert token_b

    list_b = client.get("/api/v1/projects", headers=auth(token_b))
    assert list_b.status_code == 200
    body_b = list_b.json()
    items_b = body_b if isinstance(body_b, list) else body_b.get("items", [])
    ids_seen_by_b = [p["id"] for p in items_b]
    assert proj_a_id not in ids_seen_by_b, "Org B user must not see Org A's project"


def test_project_get_cross_org_returns_404(client, db):
    """Accessing another org's project by ID must return 404 (not 403 to avoid enumeration)."""
    org_a_id, user_a = _create_org_and_user(db)
    org_b_id, user_b = _create_org_and_user(db)

    login_a = client.post("/api/v1/auth/login", json={"username": user_a.username, "password": "TestPass123!"})
    token_a = login_a.cookies.get("access_token")
    assert token_a
    create_a = client.post("/api/v1/projects", json={
        **PROJECT_PAYLOAD, "code": f"XA-{org_a_id[:4]}",
    }, headers=auth(token_a))
    proj_a_id = create_a.json()["data"]["id"]

    login_b = client.post("/api/v1/auth/login", json={"username": user_b.username, "password": "TestPass123!"})
    token_b = login_b.cookies.get("access_token")
    assert token_b

    res = client.get(f"/api/v1/projects/{proj_a_id}", headers=auth(token_b))
    assert res.status_code == 404, "Cross-org project GET must return 404"
