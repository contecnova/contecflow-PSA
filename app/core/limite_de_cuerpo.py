"""Límite global del tamaño del cuerpo de las peticiones (auditoría 22-11-2026, 01 M4).

En la aplicación no había ningún tope: solo nginx en Docker
(`client_max_body_size`). En local, uvicorn escucha sin límite y un cliente
podía mandar gigas que Starlette volcaba a disco/memoria al parsear el
formulario, antes de que ningún endpoint validara nada (también en los portales
de usuarios externos: demanda y proveedores).

Middleware ASGI puro (no `BaseHTTPMiddleware`, que leería el cuerpo):

- si `Content-Length` declara más que el tope → 413 sin leer nada;
- si no lo declara (chunked) o miente → cuenta los bytes según llegan y corta
  con 413 en cuanto se pasa (el endpoint recibe `http.disconnect`).

El tope es `settings.MAX_REQUEST_BODY_MB` (0 = sin comprobar). Los perfiles de
`app/core/uploads.py` acotan además por tipo de subida.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


def _tope_en_bytes() -> int:
    from app.core.config import settings

    mb = int(getattr(settings, "MAX_REQUEST_BODY_MB", 0) or 0)
    return mb * 1024 * 1024 if mb > 0 else 0


def _respuesta_413(tope: int) -> tuple[dict, dict]:
    from app.core.codigos_de_error import texto

    mb = tope // (1024 * 1024)
    cuerpo = json.dumps({
        "detail": texto("cuerpo_demasiado_grande", {"max": mb}),
        "code": "cuerpo_demasiado_grande",
        "params": {"max": mb},
    }).encode()
    inicio = {"type": "http.response.start", "status": 413,
              "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(cuerpo)).encode()),
                          (b"connection", b"close")]}
    return inicio, {"type": "http.response.body", "body": cuerpo}


class LimiteDeCuerpoMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        tope = _tope_en_bytes()
        if not tope:
            return await self.app(scope, receive, send)

        for nombre, valor in scope.get("headers") or []:
            if nombre == b"content-length":
                try:
                    declarado = int(valor)
                except ValueError:
                    declarado = 0
                if declarado > tope:
                    logger.warning("Cuerpo rechazado por tamaño declarado (%s bytes > %s) en %s",
                                   declarado, tope, scope.get("path"))
                    inicio, cuerpo = _respuesta_413(tope)
                    await send(inicio)
                    await send(cuerpo)
                    return
                break

        recibido = 0
        excedido = False
        respondido = False

        async def receive_contado():
            # Al pasarse se le dice a la app que el cliente se ha ido: Starlette
            # aborta el parseo (ClientDisconnect) sin bufferizar más.
            nonlocal recibido, excedido
            if excedido:
                return {"type": "http.disconnect"}
            mensaje = await receive()
            if mensaje.get("type") == "http.request":
                recibido += len(mensaje.get("body") or b"")
                if recibido > tope:
                    excedido = True
                    return {"type": "http.disconnect"}
            return mensaje

        async def send_vigilado(mensaje):
            nonlocal respondido
            if excedido:
                return  # lo que la app conteste ya no vale: va el 413
            if mensaje.get("type") == "http.response.start":
                respondido = True
            await send(mensaje)

        try:
            await self.app(scope, receive_contado, send_vigilado)
        except Exception:
            if not excedido:
                raise
        if excedido and not respondido:
            logger.warning("Cuerpo rechazado al superar %s bytes en %s", tope, scope.get("path"))
            inicio, cuerpo = _respuesta_413(tope)
            await send(inicio)
            await send(cuerpo)
