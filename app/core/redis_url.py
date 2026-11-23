"""Contraseña de Redis en su URL (auditoría 22-11-2026, 01 M5).

Redis no tenía contraseña: cualquier proceso del host (puerto 127.0.0.1:6381) o
de la red de compose podía leer los tickets de WebSocket, tocar los contadores
de rate limit o encolar tareas de Celery. Ahora `REDIS_PASSWORD` se pasa a
`redis-server --requirepass` (docker-compose) y se inyecta aquí en las URLs que
no traen credenciales, para no tener que repetirla en `REDIS_URL`.
"""
from __future__ import annotations

from urllib.parse import quote, urlsplit, urlunsplit


def con_contrasena(url: str, contrasena: str) -> str:
    """La URL con `:<contrasena>@` si no lleva ya usuario o contraseña."""
    if not url or not contrasena:
        return url
    partes = urlsplit(url)
    if not partes.scheme.startswith("redis") or partes.password or partes.username:
        return url
    host = partes.netloc
    return urlunsplit((partes.scheme, f":{quote(contrasena, safe='')}@{host}", partes.path, partes.query,
                       partes.fragment))
