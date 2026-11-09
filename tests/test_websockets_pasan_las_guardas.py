"""Los WebSocket pasan las guardas globales de la API.

Auditoria 2026-11: zona horaria, ABAC y matriz GRC se registran sobre todo el
router y pedian `Request` y `HTTPBearer`. En un WebSocket no hay `Request`: el
saludo de los cuatro WebSocket respondia 500 desde agosto (avisos en tiempo
real, avisos del portal, chat y documentos). Medido contra la pila local.
"""
from __future__ import annotations

import pytest
from starlette.websockets import WebSocketDisconnect

RUTAS = [
    "/api/v1/ws/notifications",
    "/api/v1/ws/portal-notifications",
    "/api/v1/collaboration/ws",
    "/api/v1/ws/doc/doc-1",
    "/api/v1/bi/intelligence/realtime/stream",   # revisión 2026-11: ahora con ticket
]


@pytest.mark.parametrize("ruta", RUTAS)
def test_un_ticket_malo_se_rechaza_en_el_saludo_y_no_revienta(client, ruta):
    # Antes: TypeError de HTTPBearer dentro de la pila de dependencias.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"{ruta}?ticket=no-vale") as ws:
            ws.receive_text()


# Con un ticket valido no se puede probar aqui: el manejador abre su propia
# sesion (`SessionLocal`) y no ve la base de pruebas. Se midio contra la pila
# local: con ticket de `/ws/ticket`, `/ws/notifications` se abre.


def test_las_guardas_siguen_leyendo_el_bearer_en_http():
    from starlette.requests import Request

    from app.core.credenciales_opcionales import credenciales_opcionales

    def pedir(cabecera):
        return Request({"type": "http", "headers": [(b"authorization", cabecera.encode())] if cabecera else []})

    assert credenciales_opcionales(pedir("Bearer abc")).credentials == "abc"
    assert credenciales_opcionales(pedir("Basic abc")) is None
    assert credenciales_opcionales(pedir("")) is None
