"""Credenciales Bearer opcionales que valen para HTTP y para WebSocket.

Auditoria 2026-11. Las tres guardas globales de la API (zona horaria, ABAC y
matriz GRC) se registran sobre el router entero y pedian `Request` y
`HTTPBearer(auto_error=False)`. En un WebSocket no hay `Request` y `HTTPBearer`
revienta (`__call__() missing 'request'`), asi que el saludo de **todos** los
WebSocket respondia 500 desde agosto: avisos en tiempo real, avisos del portal,
chat de colaboracion y edicion conjunta de documentos. Medido contra la pila
local: los cuatro, 500.

`HTTPConnection` es la base comun de `Request` y `WebSocket`: con ella la
dependencia se resuelve en los dos. Los WebSocket se autentican con su propio
ticket de un solo uso; las guardas no los evaluan (`es_websocket`).
"""
from __future__ import annotations

from typing import Optional

from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import HTTPConnection


def credenciales_opcionales(conn: HTTPConnection) -> Optional[HTTPAuthorizationCredentials]:
    """Lo mismo que `HTTPBearer(auto_error=False)`: el token Bearer o `None`."""
    cabecera = conn.headers.get("Authorization") or ""
    esquema, _, token = cabecera.partition(" ")
    if esquema.lower() != "bearer" or not token.strip():
        return None
    return HTTPAuthorizationCredentials(scheme=esquema, credentials=token.strip())


def es_websocket(conn: HTTPConnection) -> bool:
    return conn.scope.get("type") == "websocket"
