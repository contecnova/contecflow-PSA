from app.core.config import settings
from app.core.deps import require_admin
from app.main import app
from app.models.mfa import Organization
from app.models.user import User, UserRole
from tests.conftest import auth


def _seed_org_for_admin(db):
    org = Organization(name="Acme", slug="acme")
    db.add(org)
    db.commit()
    db.refresh(org)
    admin = db.query(User).filter(User.username == "admin").first()
    admin.organization_id = org.id
    db.commit()
    return org.id


def test_policy_pack_and_evidence_flow(client, admin_token, db):
    _seed_org_for_admin(db)

    packs = client.get("/api/v1/governance/policy-packs", headers=auth(admin_token))
    assert packs.status_code == 200
    assert isinstance(packs.json()["items"], list)

    upsert = client.put(
        "/api/v1/governance/policy-packs/access_baseline",
        headers=auth(admin_token),
        json={"is_enabled": True, "pack_version": "1.1", "config": {"review_days": 30}},
    )
    assert upsert.status_code == 200

    evidence = client.post(
        "/api/v1/governance/compliance/evidence",
        headers=auth(admin_token),
        json={
            "framework": "SOC2",
            "control_id": "SOC2-CC6.1",
            "evidence_type": "policy",
            "title": "Access review policy",
            "artifact_uri": "s3://evidence/policies/access-review-v1.pdf",
        },
    )
    assert evidence.status_code == 200
    eid = evidence.json()["data"]["id"]
    assert eid

    status = client.get(
        "/api/v1/governance/compliance/controls/status",
        headers=auth(admin_token),
        params={"framework": "SOC2"},
    )
    assert status.status_code == 200
    controls = status.json()["data"]["controls"]
    assert any(c["control_id"] == "SOC2-CC6.1" and c["evidence_count"] >= 1 for c in controls)


def test_scim_user_provisioning(client, db):
    org_id = _seed_org_for_admin(db)
    token = settings.SCIM_BEARER_TOKEN
    assert token
    headers = {"Authorization": f"Bearer {token}"}

    create = client.post(
        f"/api/v1/scim/v2/{org_id}/Users",
        headers=headers,
        json={
            "userName": "scim.user",
            "externalId": "ext-123",
            "name": {"givenName": "Scim", "familyName": "User", "formatted": "Scim User"},
            "emails": [{"value": "scim.user@acme.com", "primary": True}],
            "active": True,
            "roles": [{"value": "employee"}],
        },
    )
    assert create.status_code == 201
    user_id = create.json()["id"]

    list_res = client.get(f"/api/v1/scim/v2/{org_id}/Users", headers=headers)
    assert list_res.status_code == 200
    assert list_res.json()["totalResults"] >= 1

    patch = client.patch(
        f"/api/v1/scim/v2/{org_id}/Users/{user_id}",
        headers=headers,
        json={
            "Operations": [
                {"op": "Replace", "path": "active", "value": False},
            ]
        },
    )
    assert patch.status_code == 200
    assert patch.json()["active"] is False


def test_governance_ai_read_endpoints_allow_admin_without_org(client, admin_token, db):
    # users.organization_id is NOT NULL at the DB layer (audit #37), so we cannot
    # persist an org-less admin. Override require_admin with a transient admin whose
    # organization_id is None to exercise the production strict=False read path.
    orgless_admin = User(
        id="orgless-admin",
        username="orgless_admin",
        email="orgless@contecflow.com",
        full_name="Orgless Admin",
        role=UserRole.admin,
        is_active=True,
        hashed_password="x",
    )
    orgless_admin.organization_id = None
    app.dependency_overrides[require_admin] = lambda: orgless_admin
    try:
        config_res = client.get("/api/v1/governance/config", headers=auth(admin_token))
        assert config_res.status_code == 200
        config_payload = config_res.json()["items"]
        assert isinstance(config_payload, list)
        assert len(config_payload) > 0
        assert all("module" in item for item in config_payload)
        assert all("is_enabled" in item for item in config_payload)

        stats_res = client.get("/api/v1/governance/stats", headers=auth(admin_token))
        assert stats_res.status_code == 200
        stats_payload = stats_res.json()["data"]
        assert "total_calls" in stats_payload
        assert "by_module" in stats_payload

        logs_res = client.get("/api/v1/governance/logs", headers=auth(admin_token))
        assert logs_res.status_code == 200
        assert isinstance(logs_res.json()["items"], list)
    finally:
        app.dependency_overrides.pop(require_admin, None)
