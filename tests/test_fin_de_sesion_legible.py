"""Cookie legible con el fin de la sesión de acceso (19-11-2026).

La pantalla renueva la sesión un minuto antes de que caduque en vez de esperar a
un 401. La cookie solo lleva un instante (sin nada secreto) y se borra al salir.
"""
import time

from app.core.config import settings


def _cookie(resp, nombre):
    for c in resp.headers.get_list("set-cookie"):
        if c.startswith(nombre + "="):
            return c
    return None


def test_login_pone_el_fin_de_sesion_legible(client):
    from tests.conftest import _TEST_PASSWORD
    r = client.post("/api/v1/auth/login", json={"username": "admin", "password": _TEST_PASSWORD})
    assert r.status_code == 200, r.text
    c = _cookie(r, "session_expires_at")
    assert c is not None and "httponly" not in c.lower()
    fin = int(c.split("=", 1)[1].split(";", 1)[0])
    assert time.time() < fin <= time.time() + settings.ACCESS_TOKEN_MAX_MINUTES * 60 + 5


def test_poner_y_quitar_fin_de_sesion():
    from fastapi import Response

    from app.api.cookies_de_sesion import COOKIE_FIN_DE_SESION, poner_fin_de_sesion, quitar_fin_de_sesion
    r = Response()
    poner_fin_de_sesion(r, 600)
    puesta = r.headers.get("set-cookie")
    assert puesta.startswith(COOKIE_FIN_DE_SESION + "=") and "Max-Age=600" in puesta
    r2 = Response()
    quitar_fin_de_sesion(r2)
    assert 'Max-Age=0' in r2.headers.get("set-cookie") or "expires=" in r2.headers.get("set-cookie").lower()
