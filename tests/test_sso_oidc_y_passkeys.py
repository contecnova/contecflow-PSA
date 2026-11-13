"""SSO OIDC de extremo a extremo y acceso con passkey sin contraseña.

Auditoria 2026-11 (comparado con contecintelligence):
- la lista de proveedores del login leia `sso_configs.name`, que no existia,
  y devolvia [] (ningun boton de SSO aparecia nunca);
- el PATCH de un proveedor exigia `provider` y no se podia activar;
- no se comprobaba el emisor (`iss`) del id_token;
- el usuario se buscaba por correo en todas las organizaciones;
- `role_mapping` se guardaba y nadie lo leia;
- el boton «Entrar con passkey» llamaba a /auth/login con contrasena vacia.
"""
from __future__ import annotations

import json
import time
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.api.v1.routers import auth_sso
from app.core.config import settings
from app.models.user import User
from tests.conftest import auth

ISS = "https://idp.example.test"
CLIENT = "contecflow-client"
ORIGEN = settings.FRONTEND_URL.rstrip("/")
REDIRECT = f"{ORIGEN}/login"
_CLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def idp(monkeypatch):
    """Proveedor simulado: discovery, token endpoint y JWKS con una clave real."""
    estado = {"claims": {}}
    monkeypatch.setattr(auth_sso, "_descubrimiento", lambda config: {
        "issuer": ISS, "authorization_endpoint": f"{ISS}/authorize",
        "token_endpoint": f"{ISS}/token", "jwks_uri": f"{ISS}/jwks"})
    monkeypatch.setattr(auth_sso, "_cliente_jwks", lambda uri: SimpleNamespace(
        get_signing_key_from_jwt=lambda t: SimpleNamespace(key=_CLAVE.public_key())))

    def _canje(config, code, redirect_uri, code_verifier):
        ahora = int(time.time())
        claims = {"iss": ISS, "aud": CLIENT, "iat": ahora, "exp": ahora + 300,
                  "sub": "idp-123", "email_verified": True, "nonce": estado["nonce"], **estado["claims"]}
        return {"id_token": jwt.encode(claims, _CLAVE, algorithm="RS256")}
    monkeypatch.setattr(auth_sso, "_intercambiar_codigo_por_tokens", _canje)
    return estado


def _proveedor(client, admin_token, **extra):
    r = client.post("/api/v1/enterprise/sso", headers=auth(admin_token), json={
        "provider": "oidc", "name": "Mi IdP", "oidc_client_id": CLIENT, "oidc_client_secret": "s",
        "oidc_discovery_url": f"{ISS}/.well-known/openid-configuration", "is_active": True, **extra})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"] if "data" in r.json() else r.json()["id"]


def _entrar(client, cid, estado, **claims):
    r = client.get(f"/api/v1/auth/sso/{cid}/authorize", params={"redirect_uri": REDIRECT})
    assert r.status_code == 200, r.text
    url = r.json()["authorization_url"]
    q = parse_qs(urlparse(url).query)
    estado["nonce"] = q["nonce"][0]
    estado["claims"] = claims
    client.cookies.clear()
    return client.post(f"/api/v1/auth/sso/{cid}/callback",
                       json={"code": "c0de", "state": q["state"][0], "redirect_uri": REDIRECT})


def test_EL_HALLAZGO_el_proveedor_activo_sale_en_el_login(client, admin_token, db):
    _proveedor(client, admin_token)
    r = client.get("/api/v1/auth/sso/providers")
    assert [p["name"] for p in r.json()] == ["Mi IdP"]


def test_SAML_no_se_ofrece_porque_no_esta_implementado(client, admin_token, db):
    r = client.post("/api/v1/enterprise/sso", headers=auth(admin_token), json={"provider": "saml"})
    assert r.status_code == 422


def test_EL_HALLAZGO_el_proveedor_se_activa_con_un_PATCH_parcial(client, admin_token, db):
    cid = _proveedor(client, admin_token, is_active=False)
    r = client.patch(f"/api/v1/enterprise/sso/{cid}", headers=auth(admin_token), json={"is_active": True})
    assert r.status_code == 200, r.text
    assert len(client.get("/api/v1/auth/sso/providers").json()) == 1


def test_EL_HALLAZGO_entrar_por_SSO_crea_al_usuario_con_el_rol_de_su_grupo(client, admin_token, idp, db):
    cid = _proveedor(client, admin_token, role_mapping={"CF-PMs": "pm"}, organization_id="1")
    r = _entrar(client, cid, idp, email="nueva@empresa.com", name="Nueva", groups=["CF-PMs", "Otros"])
    assert r.status_code == 200, r.text
    assert client.cookies.get("access_token")
    u = db.query(User).filter(User.email == "nueva@empresa.com").one()
    assert getattr(u.role, "value", u.role) == "pm" and u.organization_id == "1" and u.sso_provider == "oidc"
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["sso_provider"] == "oidc"
    # El rol se resincroniza en cada acceso.
    r = _entrar(client, cid, idp, email="nueva@empresa.com", groups=[])
    assert r.status_code == 200
    db.expire_all()
    r2 = db.query(User).filter(User.email == "nueva@empresa.com").one().role
    assert getattr(r2, "value", r2) == "pm"
    admin = auth(admin_token)
    client.patch(f"/api/v1/enterprise/sso/{cid}", headers=admin, json={"role_mapping": {"CF-Admins": "admin"}})
    _entrar(client, cid, idp, email="nueva@empresa.com", groups=["CF-Admins"])
    db.expire_all()
    r3 = db.query(User).filter(User.email == "nueva@empresa.com").one().role
    assert getattr(r3, "value", r3) == "admin"


def test_EL_HALLAZGO_un_id_token_de_otro_emisor_no_entra(client, admin_token, idp, db):
    cid = _proveedor(client, admin_token, organization_id="1")
    r = _entrar(client, cid, idp, email="x@empresa.com", iss="https://evil.example.test")
    assert r.status_code == 502 and "id_token" in r.text


def test_EL_HALLAZGO_un_correo_de_otra_organizacion_no_entra(client, admin_token, idp, db):
    db.add(User(id="ajeno", username="ajeno", email="ajeno@empresa.com", full_name="A", role="employee",
                status="active", is_active=True, organization_id="org-otra", hashed_password="x"))
    db.commit()
    cid = _proveedor(client, admin_token, organization_id="1")
    r = _entrar(client, cid, idp, email="ajeno@empresa.com")
    assert r.status_code == 409


def test_los_dominios_permitidos_se_aplican(client, admin_token, idp, db):
    cid = _proveedor(client, admin_token, organization_id="1", allowed_domains="empresa.com")
    assert _entrar(client, cid, idp, email="fuera@gmail.com").status_code == 403
    assert _entrar(client, cid, idp, email="dentro@empresa.com").status_code == 200


# ── Passkeys ────────────────────────────────────────────────────────────────

def test_EL_HALLAZGO_el_acceso_con_passkey_no_pide_usuario_ni_contrasena(client, db):
    r = client.post("/api/v1/auth/passkey/login/start")
    assert r.status_code == 200, r.text
    opciones = r.json()["options"]
    assert opciones.get("allowCredentials", []) == [] and opciones["userVerification"] == "required"
    r = client.post("/api/v1/auth/passkey/login/finish", json={
        "webauthn_challenge_token": r.json()["webauthn_challenge_token"],
        "credential": {"id": "desconocida", "rawId": "x", "type": "public-key", "response": {}}})
    assert r.status_code == 401


def test_el_acceso_sin_contrasena_se_puede_apagar(client, admin_token, db):
    from app.services import settings_service
    settings_service.set_runtime_value(db, "tokens", "PASSKEY_PASSWORDLESS_ENABLED", False, None)
    db.commit()
    assert client.post("/api/v1/auth/passkey/login/start").status_code == 403


def test_registrar_pide_credencial_descubrible_y_se_renombra(client, pm_token, db):
    from app.models.mfa import WebAuthnCredential
    from tests.conftest import TEST_PASSWORD
    # Auditoria 2026-11 (#21): registrar una passkey pide la contrasena actual.
    assert client.post("/api/v1/auth/mfa/webauthn/register/start",
                       headers=auth(pm_token)).status_code == 401
    r = client.post("/api/v1/auth/mfa/webauthn/register/start", headers=auth(pm_token),
                    json={"password": TEST_PASSWORD})
    assert r.status_code == 200, r.text
    sel = r.json()["options"]["authenticatorSelection"]
    assert sel["residentKey"] == "preferred" and sel["userVerification"] == "required"
    cred = WebAuthnCredential(user_id="pm-test-id", credential_id="cred-1", public_key="pk", organization_id="1")
    db.add(cred)
    db.commit()
    r = client.patch(f"/api/v1/auth/mfa/webauthn/credentials/{cred.id}", json={"name": "MacBook"}, headers=auth(pm_token))
    assert r.status_code == 200, r.text
    lista = client.get("/api/v1/auth/mfa/webauthn/credentials", headers=auth(pm_token)).json()
    assert [c["name"] for c in lista] == ["MacBook"]
