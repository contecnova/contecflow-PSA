"""Tests para Organization.require_mfa enforcement en el login flow."""
import os
import json
from tests.conftest import auth, _TEST_PASSWORD


def test_login_succeeds_when_org_does_not_require_mfa(client, db):
    """Caso normal: la org no exige MFA, login devuelve tokens."""
    res = client.post("/api/v1/auth/login",
                      json={"username": "dev_test", "password": _TEST_PASSWORD})
    assert res.status_code == 200
    assert "access_token" in res.json() or "user" in res.json()


def test_login_blocked_when_org_requires_mfa_and_user_lacks_factor(client, db):
    """Org con require_mfa=True y usuario sin TOTP/passkey → 403."""
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.id == 1).first()
    org.require_mfa = True
    db.commit()

    # dev_test no tiene mfa_enabled ni passkeys
    res = client.post("/api/v1/auth/login",
                      json={"username": "dev_test", "password": _TEST_PASSWORD})
    assert res.status_code == 403
    assert "mfa" in res.json()["detail"].lower()


def test_login_passes_to_mfa_challenge_when_user_has_factor(client, db):
    """Org con require_mfa=True y usuario CON MFA habilitada → flujo MFA normal."""
    from app.models.user import User
    from app.models.mfa import Organization
    org = db.query(Organization).filter(Organization.id == 1).first()
    org.require_mfa = True
    user = db.query(User).filter(User.username == "dev_test").first()
    user.mfa_enabled = True
    user.mfa_secret = "encrypted-placeholder"  # solo para el check inicial
    db.commit()

    res = client.post("/api/v1/auth/login",
                      json={"username": "dev_test", "password": _TEST_PASSWORD})
    # No bloquea con 403 — entra al flujo MFA challenge
    assert res.status_code == 200
    body = res.json()
    assert body.get("mfa_required") is True


# ── Flujo end-to-end PATCH → require_mfa → enforcement ─────────────────────

def test_patch_organization_persists_require_mfa(client, admin_token, db):
    """PATCH /organizations/{id} con {require_mfa: true} debe actualizar la
    columna (antes el servicio whitelisteaba sin incluirla → silently dropped)."""
    res = client.patch("/api/v1/organizations/1",
                       headers=auth(admin_token), json={"require_mfa": True})
    assert res.status_code == 200, res.text

    from app.models.mfa import Organization
    db.expire_all()  # forzar recarga desde DB
    org = db.query(Organization).filter(Organization.id == 1).first()
    assert org.require_mfa is True


def test_patch_organization_require_mfa_writes_audit(client, admin_token, db):
    """Cambiar require_mfa deja una entrada en audit_logs."""
    from app.models.enterprise import AuditLog

    before_count = db.query(AuditLog).filter(
        AuditLog.resource == "organizations",
        AuditLog.resource_id == "1",
        AuditLog.action == "UPDATE",
    ).count()

    client.patch("/api/v1/organizations/1",
                 headers=auth(admin_token), json={"require_mfa": True})

    after = (
        db.query(AuditLog)
        .filter(AuditLog.resource == "organizations",
                AuditLog.resource_id == "1",
                AuditLog.action == "UPDATE")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert db.query(AuditLog).filter(
        AuditLog.resource == "organizations",
        AuditLog.resource_id == "1",
        AuditLog.action == "UPDATE",
    ).count() == before_count + 1
    meta = json.loads(after.metadata_ or "{}")
    assert meta.get("field") == "require_mfa"
    assert meta.get("after") is True


def test_patch_organization_require_mfa_no_audit_when_unchanged(client, admin_token, db):
    """Si require_mfa no cambia, no se escribe audit log para ese campo."""
    from app.models.enterprise import AuditLog
    # require_mfa por defecto es False; PATCH con False no debe disparar audit
    before_count = db.query(AuditLog).filter(
        AuditLog.resource == "organizations",
        AuditLog.resource_id == "1",
    ).count()
    res = client.patch("/api/v1/organizations/1",
                       headers=auth(admin_token), json={"require_mfa": False})
    assert res.status_code == 200
    after_count = db.query(AuditLog).filter(
        AuditLog.resource == "organizations",
        AuditLog.resource_id == "1",
    ).count()
    assert after_count == before_count  # no entries añadidas


def test_full_flow_patch_then_login_blocked(client, admin_token, db):
    """End-to-end: admin activa require_mfa vía PATCH, usuario sin factor
    intenta login y recibe 403."""
    res = client.patch("/api/v1/organizations/1",
                       headers=auth(admin_token), json={"require_mfa": True})
    assert res.status_code == 200

    # dev_test no tiene MFA configurado
    res = client.post("/api/v1/auth/login",
                      json={"username": "dev_test", "password": _TEST_PASSWORD})
    assert res.status_code == 403
    assert "mfa" in res.json()["detail"].lower()
