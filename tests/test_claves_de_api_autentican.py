"""Claves de API y tokens del portal autentican en la API, recortados por alcance.

Auditoria 2026-11. Antes ninguna de las dos servia para llamar a la API: las
claves solo las miraba un `/verify` sin autenticar, y los tokens del portal se
guardaban con sal aleatoria y se buscaban por ese hash, que no coincide nunca
(ni `/developer/userinfo` funcionaba).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.models.bookings import ApiKey
from tests.conftest import auth


def _clave(client, token, scopes=("read",), **extra):
    r = client.post("/api/v1/bookings/api-keys", headers=auth(token),
                    json={"name": "integracion", "scopes": list(scopes), **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]["key"]


def _proyecto(client, token, code="KEY1"):
    r = client.post("/api/v1/projects", headers=auth(token),
                    json={"name": "Por clave", "code": code, "status": "active", "billing_type": "time_material"})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _sin_sesion(client):
    client.cookies.clear()
    return client


# ── Claves de API ───────────────────────────────────────────────────────────

def test_EL_HALLAZGO_una_clave_de_API_autentica(client, pm_token, db):
    _proyecto(client, pm_token)
    clave = _clave(client, pm_token)
    c = _sin_sesion(client)
    r = c.get("/api/v1/projects", headers={"X-API-Key": clave})
    assert r.status_code == 200, r.text
    assert any(p["code"] == "KEY1" for p in r.json()["items"])
    # Tambien como Bearer.
    assert c.get("/api/v1/projects", headers={"Authorization": f"Bearer {clave}"}).status_code == 200


def test_una_clave_de_lectura_no_escribe(client, pm_token, db):
    clave = _clave(client, pm_token, scopes=["read"])
    r = _sin_sesion(client).post("/api/v1/projects", headers={"X-API-Key": clave},
                                 json={"name": "x", "code": "NOPE", "status": "active"})
    assert r.status_code == 403
    assert "lectura" in r.text


def test_una_clave_de_escritura_escribe(client, pm_token, db):
    clave = _clave(client, pm_token, scopes=["read", "write"])
    r = _sin_sesion(client).post("/api/v1/projects", headers={"X-API-Key": clave},
                                 json={"name": "Por API", "code": "BYKEY", "status": "active",
                                       "billing_type": "time_material"})
    assert r.status_code in (200, 201), r.text


@pytest.mark.parametrize("metodo,ruta", [
    ("post", "/api/v1/bookings/api-keys"),
    ("post", "/api/v1/auth/change-password"),
    ("post", "/api/v1/auth/mfa/setup"),
    ("post", "/api/v1/developer/apps"),
])
def test_EL_HALLAZGO_una_clave_no_gestiona_credenciales(client, pm_token, db, metodo, ruta):
    clave = _clave(client, pm_token, scopes=["read", "write", "admin"])
    r = getattr(_sin_sesion(client), metodo)(ruta, headers={"X-API-Key": clave}, json={"name": "x", "scopes": ["admin"]})
    assert r.status_code == 403, r.text


def test_la_clave_actua_con_el_rol_de_su_dueno(client, pm_token, db):
    clave = _clave(client, pm_token, scopes=["write"])
    r = _sin_sesion(client).post("/api/v1/automations/run-scheduled", headers={"X-API-Key": clave})
    assert r.status_code == 403, "una clave de un PM no puede hacer lo que solo hace un admin"


def test_revocada_o_caducada_no_entra(client, pm_token, db):
    clave = _clave(client, pm_token)
    fila = db.query(ApiKey).filter(ApiKey.key_prefix == clave[:12]).one()
    fila.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    db.commit()
    c = _sin_sesion(client)
    assert c.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 401
    fila.expires_at = None
    fila.is_active = False
    db.commit()
    assert c.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 401


def test_el_limite_por_hora_corta_y_se_reinicia_en_la_hora_siguiente(client, pm_token, db):
    clave = _clave(client, pm_token, rate_limit_per_hour=2)
    c = _sin_sesion(client)
    assert c.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 200
    assert c.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 200
    assert c.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 429
    fila = db.query(ApiKey).filter(ApiKey.key_prefix == clave[:12]).one()
    db.refresh(fila)
    fila.last_reset_at = datetime.now(timezone.utc) - timedelta(hours=1, minutes=1)
    db.commit()
    assert c.get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 200


def test_una_clave_antigua_sin_huella_entra_y_la_recibe(client, pm_token, db):
    clave = _clave(client, pm_token)
    fila = db.query(ApiKey).filter(ApiKey.key_prefix == clave[:12]).one()
    fila.key_digest = None
    db.commit()
    assert _sin_sesion(client).get("/api/v1/projects", headers={"X-API-Key": clave}).status_code == 200
    db.refresh(fila)
    assert fila.key_digest is not None


def test_alcances_inventados_no_se_guardan(client, pm_token, db):
    r = client.post("/api/v1/bookings/api-keys", headers=auth(pm_token), json={"name": "x", "scopes": ["root"]})
    assert r.status_code == 422


def test_un_bearer_cualquiera_no_entra(client, db):
    r = _sin_sesion(client).get("/api/v1/projects", headers={"Authorization": "Bearer no-es-nada"})
    assert r.status_code == 401


# ── Tokens del portal de desarrolladores ────────────────────────────────────

def _token_de_app(client, pm_token, scopes, pedir):
    app = client.post("/api/v1/developer/apps", headers=auth(pm_token),
                      json={"name": "Integra", "scopes": scopes}).json()["data"]
    r = _sin_sesion(client).post("/api/v1/developer/token", json={
        "grant_type": "client_credentials", "client_id": app["client_id"],
        "client_secret": app["client_secret"], "scope": pedir})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_EL_HALLAZGO_el_token_del_portal_vale_en_userinfo_y_en_la_API(client, pm_token, db):
    _proyecto(client, pm_token, code="OAU1")
    token = _token_de_app(client, pm_token, ["read"], "read")
    h = {"Authorization": f"Bearer {token}"}
    r = client.get("/api/v1/developer/userinfo", headers=h)
    assert r.status_code == 200, "userinfo no encontraba nunca el token (hash con sal aleatoria)"
    assert r.json()["sub"] == "pm-test-id"
    assert client.get("/api/v1/projects", headers=h).status_code == 200


def test_un_token_de_area_solo_abre_su_area(client, pm_token, db):
    token = _token_de_app(client, pm_token, ["tasks"], "tasks")
    h = {"Authorization": f"Bearer {token}"}
    c = _sin_sesion(client)
    assert c.get("/api/v1/tasks", headers=h).status_code == 200
    assert c.get("/api/v1/projects", headers=h).status_code == 403


def test_el_token_revocado_deja_de_valer(client, pm_token, db):
    token = _token_de_app(client, pm_token, ["read"], "read")
    h = {"Authorization": f"Bearer {token}"}
    c = _sin_sesion(client)
    assert c.post("/api/v1/developer/token/revoke", headers=h).status_code == 200
    assert c.get("/api/v1/projects", headers=h).status_code == 401
