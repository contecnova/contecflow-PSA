"""RATE_LIMIT_DEFAULT se aplica, y la cuota es de cada usuario (revisión 2026-11).

Medido antes: sin `SlowAPIMiddleware` el límite por defecto no se aplicaba a
nada, y la clave era la IP de la conexión (tras nginx, la del proxy: una cuota
para toda la empresa). Medido después en la copia: la petición 201 de un mismo
usuario a una ruta da 429, y otro cliente sigue con su cuota; una navegación
real de 40 s hizo 285 peticiones repartidas y ninguna tocó el límite, que es
por ruta y usuario.
"""
from __future__ import annotations

from slowapi.middleware import SlowAPIMiddleware
from starlette.requests import Request

from app.core.ratelimit import _rate_limit_key
from app.core.security import create_access_token
from app.main import app


def _peticion(cabeceras=(), ip="203.0.113.7"):
    return Request({"type": "http", "headers": [(k.encode(), v.encode()) for k, v in cabeceras], "client": (ip, 1234)})


def test_el_middleware_esta_puesto():
    assert any(m.cls is SlowAPIMiddleware for m in app.user_middleware)


def test_con_sesion_cuenta_el_usuario_y_sin_ella_la_ip(monkeypatch):
    monkeypatch.setenv("TESTING", "0")
    token = create_access_token(subject="usuario-42")
    assert _rate_limit_key(_peticion([("cookie", f"access_token={token}")])) == "u:usuario-42"
    assert _rate_limit_key(_peticion([("authorization", f"Bearer {token}")])) == "u:usuario-42"
    assert _rate_limit_key(_peticion()) == "ip:203.0.113.7"
    assert _rate_limit_key(_peticion([("authorization", "Bearer basura")])) == "ip:203.0.113.7"
