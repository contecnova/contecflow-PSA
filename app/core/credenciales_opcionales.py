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


# ── Auditoría 22-11-2026 (A2, M1): un solo principal para GRC y ABAC ─────────
#
# Las guardas globales de GRC y ABAC decodificaban el JWT por su cuenta: con una
# clave de API (`X-API-Key`/`Bearer nxpm_…`) o un token OAuth no veían usuario y
# no decidían, y con JWT evaluaban la empresa de la FICHA y no la activa.
# Ahora se aplican dentro de `get_current_user`, con el principal ya resuelto
# (sesión, clave o token) y la empresa activa publicada. La guarda global solo
# actúa en las rutas que NO resuelven al usuario con `get_current_user`.

_RESUELVE_USUARIO: dict[int, bool] = {}


def _llamadas(dependant, acumuladas: set) -> set:
    for dep in getattr(dependant, "dependencies", ()) or ():
        acumuladas.add(dep.call)
        _llamadas(dep, acumuladas)
    return acumuladas


def ruta_resuelve_usuario(conn: HTTPConnection) -> bool:
    """¿La ruta de esta petición depende de `get_current_user`? (cacheado por ruta)."""
    ruta = conn.scope.get("route")
    dependant = getattr(ruta, "dependant", None)
    if dependant is None:
        return False
    clave = id(ruta)
    if clave not in _RESUELVE_USUARIO:
        from app.core.deps import get_current_user
        _RESUELVE_USUARIO[clave] = get_current_user in _llamadas(dependant, set())
    return _RESUELVE_USUARIO[clave]
