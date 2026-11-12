"""Tests de autenticación — login, tokens, 2FA."""
import uuid
from datetime import timedelta
from types import SimpleNamespace

import pyotp
import pytest
from sqlalchemy import text as _sa_text
from fastapi import HTTPException
from pydantic import ValidationError

from tests.conftest import TEST_PASSWORD, auth
from app.services.auth_service import (
    resolve_sso_organization_id as _resolve_sso_organization_id,
    validate_https_discovery_url as _validate_https_discovery_url,
)
from app.core.config import Settings
from app.core.network import extract_client_ip
from app.models.enterprise import SSOConfig, SSOProvider
from app.models.mfa import Organization, WebAuthnCredential
from app.models.sessions import UserSession
from app.core.errores import ErrorDeDominio


def test_login_admin(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert res.status_code == 200
    data = res.json()
    assert data.get("access_token") in (None, "")
    assert data.get("refresh_token") in (None, "")
    assert data["user"]["role"] == "admin"
    assert res.cookies.get("access_token")
    assert res.cookies.get("refresh_token")


def test_login_wrong_password(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    assert res.status_code == 401


def test_login_unknown_user(client, db):
    res = client.post("/api/v1/auth/login", json={"username": "ghost", "password": "pass"})
    assert res.status_code == 401


def test_password_forgot_always_returns_generic_ok(client, db):
    res_unknown = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "unknown@example.com"})
    assert res_unknown.status_code == 200
    assert res_unknown.json().get("ok") is True

    res_known = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "admin"})
    assert res_known.status_code == 200
    assert res_known.json().get("ok") is True


def test_password_reset_flow_with_token(client, db):
    # Request reset for existing user (response is always generic).
    res = client.post("/api/v1/auth/password/forgot", json={"email_or_username": "admin"})
    assert res.status_code == 200

    # Build a valid token directly using endpoint helper for deterministic test.
    from app.services.auth_service import issue_password_reset_token as _issue_password_reset_token
    from app.models.user import User

    admin = db.query(User).filter(User.username == "admin").first()
    token = _issue_password_reset_token(admin)

    new_password = "ResetPass2026!"
    reset = client.post(
        "/api/v1/auth/password/reset",
        json={"token": token, "new_password": new_password},
    )
    assert reset.status_code == 200
    assert reset.json().get("ok") is True

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": new_password})
    assert login.status_code == 200


def test_get_me(client, admin_token, db):
    res = client.get("/api/v1/auth/me", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "admin"
    assert data["role"] == "admin"


def test_get_me_no_token(client, db):
    res = client.get("/api/v1/auth/me")
    assert res.status_code in (401, 403)


def test_get_me_invalid_token(client, db):
    res = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer token_invalido"})
    assert res.status_code in (401, 403)


def test_refresh_token(client, db):
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    refresh = login.cookies.get("refresh_token")
    assert refresh
    res = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert res.status_code == 200
    assert res.json().get("access_token") in (None, "")


def test_refresh_token_works_with_cookie_only(client, db):
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert login.status_code == 200
    assert client.cookies.get("refresh_token")

    res = client.post("/api/v1/auth/refresh")
    assert res.status_code == 200
    assert res.json().get("access_token") in (None, "")
    assert res.cookies.get("refresh_token")


def test_sso_providers_empty(client, db):
    """Sin SSO configurado devuelve lista vacía."""
    res = client.get("/api/v1/auth/sso/providers")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_validate_https_discovery_url_accepts_https():
    url = "https://accounts.example.com/.well-known/openid-configuration"
    assert _validate_https_discovery_url(url) == url


@pytest.mark.parametrize("url", [
    "http://accounts.example.com/.well-known/openid-configuration",
    "file:///etc/passwd",
    "",
])
def test_validate_https_discovery_url_rejects_non_https(url):
    with pytest.raises((HTTPException, ErrorDeDominio)):
        _validate_https_discovery_url(url)


def test_mfa_setup_requires_auth(client, db):
    res = client.post("/api/v1/auth/mfa/setup")
    assert res.status_code in (401, 403)


def test_mfa_setup_flow(client, admin_token, db):
    """Setup MFA genera un secreto y URI."""
    res = client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token))
    assert res.status_code == 200
    data = res.json()
    # Robustez: aceptar variantes válidas
    assert "secret" in data and data["secret"]
    assert "provisioning_uri" in data and "otpauth://" in data["provisioning_uri"]


def test_login_lockout_after_failed_attempts(client, db):
    from app.core.config import settings

    prev_max = settings.LOGIN_MAX_ATTEMPTS
    prev_window = settings.LOGIN_ATTEMPT_WINDOW_SECONDS
    prev_lockout = settings.LOGIN_LOCKOUT_SECONDS
    try:
        settings.LOGIN_MAX_ATTEMPTS = 2
        settings.LOGIN_ATTEMPT_WINDOW_SECONDS = 60
        settings.LOGIN_LOCKOUT_SECONDS = 30

        unknown = f"ghost-{uuid.uuid4().hex[:8]}"
        res1 = client.post("/api/v1/auth/login", json={"username": unknown, "password": "wrong"})
        assert res1.status_code == 401
        res2 = client.post("/api/v1/auth/login", json={"username": unknown, "password": "wrong"})
        assert res2.status_code == 429
    finally:
        settings.LOGIN_MAX_ATTEMPTS = prev_max
        settings.LOGIN_ATTEMPT_WINDOW_SECONDS = prev_window
        settings.LOGIN_LOCKOUT_SECONDS = prev_lockout


def test_mfa_enforced_on_login(client, admin_token, db):
    # 1) Setup MFA and activate it
    setup = client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token))
    assert setup.status_code == 200
    secret = setup.json().get("secret")
    assert secret, "MFA secret missing in setup response"
    verify_code = pyotp.TOTP(secret).now()
    verify = client.post(
        "/api/v1/auth/mfa/verify-setup",
        headers=auth(admin_token),
        json={"code": verify_code},
    )
    assert verify.status_code == 200

    # 2) Login should require MFA challenge and must not issue auth tokens yet
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert login.status_code == 200
    payload = login.json()
    assert payload.get("mfa_required") is True
    assert payload.get("mfa_challenge_token")
    assert payload.get("access_token") in (None, "", False)

    # 3) Complete MFA with challenge token and receive final auth tokens
    mfa_code = pyotp.TOTP(secret).now()
    validate = client.post(
        "/api/v1/auth/mfa/validate",
        json={"mfa_challenge_token": payload["mfa_challenge_token"], "code": mfa_code},
    )
    assert validate.status_code == 200
    assert "access_token" in validate.json()


def test_mfa_challenge_token_is_one_time_use(client, admin_token, db):
    setup = client.post("/api/v1/auth/mfa/setup", headers=auth(admin_token))
    secret = setup.json()["secret"]
    verify = client.post(
        "/api/v1/auth/mfa/verify-setup",
        headers=auth(admin_token),
        json={"code": pyotp.TOTP(secret).now()},
    )
    assert verify.status_code == 200

    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert login.status_code == 200
    challenge = login.json()["mfa_challenge_token"]

    first = client.post(
        "/api/v1/auth/mfa/validate",
        json={"mfa_challenge_token": challenge, "code": pyotp.TOTP(secret).now()},
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/mfa/validate",
        json={"mfa_challenge_token": challenge, "code": pyotp.TOTP(secret).now()},
    )
    assert second.status_code == 401
    assert "ya utilizado" in second.json()["detail"]


def test_login_requires_mfa_when_passkey_exists(client, db):
    db.add(WebAuthnCredential(
        user_id="admin-test-id",
        credential_id=f"cred-{uuid.uuid4().hex}",
        public_key="cHVibGljLWtleQ",
        sign_count=0,
        is_active=True,
        name="MacBook",
    ))
    db.commit()

    res = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert res.status_code == 200
    data = res.json()
    assert data.get("mfa_required") is True
    assert data.get("mfa_challenge_token")
    assert "webauthn" in (data.get("mfa_methods") or [])
    assert data.get("access_token") in (None, "")


def test_active_sessions_panel_and_revoke_device(client, admin_token, db):
    list_res = client.get("/api/v1/auth/sessions/active", headers=auth(admin_token))
    assert list_res.status_code == 200
    body = list_res.json()
    sessions = body.get("items") if isinstance(body, dict) else body
    assert len(sessions) >= 1
    first = sessions[0]
    assert "risk_score" in first
    assert "risk_level" in first
    assert "device_name" in first

    revoke_res = client.delete(f"/api/v1/auth/sessions/{first['id']}", headers=auth(admin_token))
    assert revoke_res.status_code == 200
    assert revoke_res.json().get("ok") is True


def test_refresh_rotates_same_session_row(client, db):
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": TEST_PASSWORD})
    assert login.status_code == 200
    old_refresh = login.cookies.get("refresh_token")
    assert old_refresh

    before = db.query(UserSession).count()
    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert refresh.status_code == 200
    after = db.query(UserSession).count()

    assert before == 1
    assert after == 1


def test_resolve_sso_org_requires_explicit_tenant(db):
    org = Organization(id="org-sso-test", name="Org SSO", slug="org-sso")
    db.add(org)
    db.commit()

    config = SSOConfig(
        id="sso-config-test",
        provider=SSOProvider.google,
        is_active=True,
        organization_id=org.id,
    )
    db.add(config)
    db.commit()

    assert _resolve_sso_organization_id(db, config, "user@example.com") == org.id


def test_resolve_sso_org_rejects_orphan_autoprovisioning(db):
    config = SSOConfig(
        id="sso-config-no-org",
        provider=SSOProvider.google,
        is_active=True,
        organization_id=None,
    )
    db.add(config)
    db.commit()

    # Auditoria 2026-08. El `organization_id` se vuelve a poner a NULL con SQL
    # directo **a proposito**: desde que la suite corre con la semantica de
    # produccion, `_sellar_organizacion` rellena en el `flush` la organizacion
    # de la sesion, asi que la fila ya no nace huerfana por mucho que se pida.
    # Y la fila huerfana es justo el caso que este test defiende: una
    # configuracion de SSO anterior al sellado, que no puede servir para
    # autoaprovisionar usuarios porque no se sabe en que organizacion meterlos.
    db.execute(_sa_text(
        "UPDATE sso_configs SET organization_id = NULL WHERE id = :i"),
        {"i": config.id})
    db.commit()
    db.refresh(config)
    assert config.organization_id is None

    with pytest.raises(Exception) as exc:
        _resolve_sso_organization_id(db, config, "user@example.com")

    assert "organization_id" in str(exc.value)


def test_client_ip_ignores_spoofed_forwarded_headers_without_trusted_proxy(monkeypatch):
    monkeypatch.setattr("app.core.network.settings.TRUST_PROXY_HEADERS", False)
    import app.core.network as _net
    _net._PROXY_CACHE.update({"expires_at": 0.0, "trust": None, "cidrs_raw": None})
    request = SimpleNamespace(
        headers={"x-forwarded-for": "127.0.0.1", "x-real-ip": "127.0.0.1"},
        client=SimpleNamespace(host="198.51.100.10"),
    )
    assert extract_client_ip(request) == "198.51.100.10"


def test_client_ip_accepts_proxy_headers_from_trusted_proxy(monkeypatch):
    monkeypatch.setattr("app.core.network.settings.TRUST_PROXY_HEADERS", True)
    monkeypatch.setattr("app.core.network.settings.TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    # _effective_proxy_config() caches for 5 min on the hot path; reset it so the
    # monkeypatched settings above are actually read instead of a warm cache value.
    import app.core.network as _net
    _net._PROXY_CACHE.update({"expires_at": 0.0, "trust": None, "cidrs_raw": None})
    request = SimpleNamespace(
        headers={"x-forwarded-for": "203.0.113.5, 10.1.1.1"},
        client=SimpleNamespace(host="10.1.1.1"),
    )
    assert extract_client_ip(request) == "203.0.113.5"


def test_expired_access_token_is_rejected(client, db):
    """Un token de acceso expirado debe ser rechazado con 401/403, no reutilizable."""
    from app.core.security import create_access_token

    expired_token = create_access_token("admin", expires_delta=timedelta(seconds=-1))

    # Reuse of an expired token must be denied on any protected endpoint.
    res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res.status_code in (401, 403), f"Expected 401/403 for expired token, got {res.status_code}"

    # Replaying the same expired token a second time must still fail.
    res2 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res2.status_code in (401, 403), "Expired token replay must remain rejected"


def test_production_requires_operational_secrets():
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            PROJECT_NAME="Contecflow",
            VERSION="test",
            API_V1_STR="/api/v1",
            ENVIRONMENT="production",
            SECRET_KEY="a" * 32,
            DATABASE_URL="sqlite://",
            SUPERADMIN_EMAIL="admin@example.com",
            SUPERADMIN_PASSWORD="secret-password",
            CLIENT_PORTAL_SECRET="b" * 32,
            WEBHOOK_SECRET="",
            INBOUND_EMAIL_SECRET="",
        )


# ── Propiedades que el refactor de `login` preserva (auditoría 2026-08, P3-18) ─
#
# `login` era complejidad 18 y se partió en fases. Estas propiedades no tenían
# test propio y son exactamente las que un refactor podría romper sin que nada
# más fallara.

def test_login_no_revela_si_el_usuario_existe(client, db):
    """El 401 debe ser IDÉNTICO para usuario inexistente y contraseña incorrecta.

    Si los dos caminos respondieran distinto —otro mensaje, otro código, otro
    tiempo apreciable— el login sería un oráculo de usuarios existentes y valdría
    para enumerar la plantilla antes de atacar contraseñas.

    Los dos caminos están ahora en la misma función (`_rechazar_credenciales`)
    justamente para que no puedan divergir por descuido.
    """
    inexistente = client.post("/api/v1/auth/login",
                              json={"username": "fantasma_que_no_existe", "password": "x"})
    mala = client.post("/api/v1/auth/login",
                       json={"username": "admin", "password": "contrasena-incorrecta"})

    assert inexistente.status_code == mala.status_code == 401
    assert inexistente.json()["detail"] == mala.json()["detail"]
    assert inexistente.json()["detail"] == "Credenciales incorrectas"


def test_login_fallido_no_deja_cookies(client, db):
    """Ni sesión a medias ni cookie huérfana: un login fallido no emite nada."""
    res = client.post("/api/v1/auth/login",
                      json={"username": "admin", "password": "mal"})
    assert res.status_code == 401
    assert not res.cookies.get("access_token")
    assert not res.cookies.get("refresh_token")


def test_el_bypass_de_superadmin_no_se_aplica_en_la_suite(db):
    """Ocho condiciones, y `TESTING=1` es una de ellas.

    El camino de recuperación local existe para desbloquear un entorno de
    desarrollo. Que la suite no pueda activarlo es deliberado: si pudiera, todos
    los tests de autenticación se ejecutarían por un camino que en producción no
    existe, y dejarían de verificar el de verdad.
    """
    from app.api.v1.routers.auth_core import _bypass_de_superadmin_aplicable
    from app.schemas.auth import LoginRequest
    from app.models.user import User

    falso_superadmin = User(id="x", username="x", email="x@x.com",
                            is_superadmin=True, hashed_password="x")
    payload = LoginRequest(username="x", password="cualquiera")
    assert _bypass_de_superadmin_aplicable(falso_superadmin, payload) is False
