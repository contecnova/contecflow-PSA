"""De `Descarga` (servicio, sin HTTP) a la respuesta HTTP.

Auditoria 2026-11 (item 36). Se usa `StreamingResponse` con un solo trozo, como
hacian los servicios, para que la respuesta (cuerpo, `Content-Type` y
cabeceras) sea la misma de antes.
"""
from __future__ import annotations

from fastapi.responses import StreamingResponse

from app.core.descargas import Descarga


def respuesta_de_descarga(descarga: Descarga) -> StreamingResponse:
    return StreamingResponse(
        iter([descarga.contenido]),
        media_type=descarga.media_type,
        headers=dict(descarga.cabeceras),
    )
