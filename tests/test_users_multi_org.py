from tests.conftest import auth

from app.models.mfa import Organization
from app.models.user import User, UserOrganizationMembership


def _ensure_org(db, org_id: str, slug: str, name: str):
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if org:
        return org
    org = Organization(id=org_id, slug=slug, name=name, is_active=True)
    db.add(org)
    db.commit()
    return org


def test_update_user_allows_multiple_organizations_from_profile(client, admin_token, db):
    _ensure_org(db, "org-extra-1", "org-extra-1", "Org Extra 1")

    user = db.query(User).filter(User.username == "dev_test").first()
    assert user is not None

    res = client.patch(
        f"/api/v1/users/{user.id}",
        json={
            "organization_id": "org-extra-1",
            "organization_ids": [str(user.organization_id), "org-extra-1"],
        },
        headers=auth(admin_token),
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["organization_id"] == "org-extra-1"
    assert set(data["organization_ids"]) == {"1", "org-extra-1"}

    memberships = db.query(UserOrganizationMembership).filter(UserOrganizationMembership.user_id == user.id).all()
    assert {str(m.organization_id) for m in memberships} == {"1", "org-extra-1"}


def test_create_user_with_multiple_organizations_from_profile(client, admin_token, db):
    _ensure_org(db, "org-extra-2", "org-extra-2", "Org Extra 2")
    _ensure_org(db, "org-extra-3", "org-extra-3", "Org Extra 3")

    payload = {
        "username": "multi_org_user",
        "email": "multi_org_user@example.com",
        "full_name": "Multi Org User",
        "password": "StrongPass123!",
        "organization_id": "org-extra-2",
        "organization_ids": ["org-extra-2", "org-extra-3"],
    }

    res = client.post("/api/v1/users", json=payload, headers=auth(admin_token))
    assert res.status_code == 200, res.text
    data = res.json()

    assert data["organization_id"] == "org-extra-2"
    assert set(data["organization_ids"]) == {"org-extra-2", "org-extra-3"}

    created = db.query(User).filter(User.username == "multi_org_user").first()
    assert created is not None

    memberships = db.query(UserOrganizationMembership).filter(UserOrganizationMembership.user_id == created.id).all()
    assert {str(m.organization_id) for m in memberships} == {"org-extra-2", "org-extra-3"}


def test_remove_user_from_last_organization_is_blocked(client, admin_token, db):
    users = db.query(User).filter(User.username.in_(["admin", "pm_test", "dev_test"])).all()
    by_username = {u.username: u for u in users}
    admin = by_username["admin"]
    pm = by_username["pm_test"]
    dev = by_username["dev_test"]

    # Ensure base memberships exist in org 1 for this test scenario.
    for u in (admin, pm, dev):
        exists = db.query(UserOrganizationMembership).filter(
            UserOrganizationMembership.user_id == u.id,
            UserOrganizationMembership.organization_id == "1",
        ).first()
        if not exists:
            db.add(UserOrganizationMembership(user_id=u.id, organization_id="1"))
    db.commit()

    res = client.delete(
        f"/api/v1/organizations/1/remove-user/{dev.id}",
        headers=auth(admin_token),
    )

    assert res.status_code == 400, res.text
    assert "última organización" in res.json()["detail"]

    still_exists = db.query(User).filter(User.id == dev.id).first()
    assert still_exists is not None

    memberships = db.query(UserOrganizationMembership).filter(
        UserOrganizationMembership.user_id == dev.id
    ).all()
    assert {str(m.organization_id) for m in memberships} == {"1"}
