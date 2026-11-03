"""El segundo factor activado en la pantalla /mfa protege la entrada.

Auditoria 2026-11: la pantalla escribia `mfa_configs` y el login miraba
`users.mfa_secret`; activarlo ahi no pedia codigo al entrar. Ademas el QR se
pedia a un servicio externo con el secreto en la URL.
"""
import pyotp

from tests.conftest import _TEST_PASSWORD, auth


def _entrar(client):
    return client.post("/api/v1/auth/login", json={"username": "admin", "password": _TEST_PASSWORD})


def _activar(client, token):
    alta = client.post("/api/v1/mfa/setup", headers=auth(token))
    assert alta.status_code == 200, alta.text
    datos = alta.json()["data"]
    assert datos["qr_url"].startswith("data:image/png;base64,")
    ok = client.post("/api/v1/mfa/verify", headers=auth(token),
                     json={"code": pyotp.TOTP(datos["secret"]).now()})
    assert ok.status_code == 200, ok.text
    return datos["secret"], ok.json()["data"]["backup_codes"]


def test_activar_en_la_pantalla_exige_codigo_al_entrar(client, admin_token):
    secreto, respaldo = _activar(client, admin_token)

    reto = _entrar(client).json()
    assert reto.get("mfa_required") is True, reto
    malo = client.post("/api/v1/auth/mfa/validate",
                       json={"mfa_challenge_token": reto["mfa_challenge_token"], "code": "000000"})
    assert malo.status_code == 401

    reto = _entrar(client).json()
    bueno = client.post("/api/v1/auth/mfa/validate",
                        json={"mfa_challenge_token": reto["mfa_challenge_token"],
                              "code": pyotp.TOTP(secreto).now()})
    assert bueno.status_code == 200, bueno.text

    # Un codigo de respaldo de la pantalla vale una vez.
    reto = _entrar(client).json()
    r = client.post("/api/v1/auth/mfa/validate",
                    json={"mfa_challenge_token": reto["mfa_challenge_token"], "code": respaldo[0]})
    assert r.status_code == 200, r.text
    reto = _entrar(client).json()
    r = client.post("/api/v1/auth/mfa/validate",
                    json={"mfa_challenge_token": reto["mfa_challenge_token"], "code": respaldo[0]})
    assert r.status_code == 401


def test_desactivar_en_la_pantalla_deja_entrar_sin_codigo(client, admin_token):
    secreto, _ = _activar(client, admin_token)
    r = client.request("DELETE", "/api/v1/mfa/disable", headers=auth(admin_token),
                       json={"code": pyotp.TOTP(secreto).now()})
    assert r.status_code == 200, r.text
    assert not _entrar(client).json().get("mfa_required")
