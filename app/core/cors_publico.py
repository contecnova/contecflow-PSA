"""CORS abierto sólo para las rutas públicas que usan los widgets (revisión 2026-11).

`CORSMiddleware` admite sólo `ALLOWED_ORIGINS` y contesta él mismo la petición
previa (preflight): el envío del widget de solicitudes desde la web de un
cliente —un POST con `Content-Type: application/json`— se cortaba ahí y nunca
llegaba a la ruta (medido en el navegador). Este middleware va por fuera y
contesta la petición previa sólo para estas rutas, que no usan credenciales;
el resto de la API sigue igual.
"""
from __future__ import annotations

RUTAS_PUBLICAS = ("/api/v1/forms/public/",)


class CorsPublico:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if (scope["type"] == "http" and scope["method"] == "OPTIONS"
                and scope["path"].startswith(RUTAS_PUBLICAS)):
            cabeceras = [
                (b"access-control-allow-origin", b"*"),
                (b"access-control-allow-methods", b"GET, POST"),
                (b"access-control-allow-headers", b"Content-Type"),
                (b"access-control-max-age", b"600"),
                (b"content-length", b"0"),
            ]
            await send({"type": "http.response.start", "status": 204, "headers": cabeceras})
            await send({"type": "http.response.body", "body": b""})
            return
        await self.app(scope, receive, send)
