"""Cada WebSocket de la API pasa por nginx con sus cabeceras de Upgrade (revisión 2026-11).

Medido antes: `nginx.frontend.conf` sólo reenviaba el Upgrade de `/api/v1/ws/`.
La colaboración, el tiempo real de BI y los paneles compartidos negociaban
contra `location /api/`, sin Upgrade, y en producción no se abrían nunca.
"""
from __future__ import annotations

import re
from pathlib import Path

from starlette.routing import WebSocketRoute

from app.main import app

CONF = Path(__file__).resolve().parents[1] / "frontend" / "nginx.frontend.conf"


def _rutas_websocket() -> list[str]:
    rutas = []

    def recorrer(lista, prefijo=""):
        for r in lista:
            if isinstance(r, WebSocketRoute):
                rutas.append(prefijo + r.path)
            elif hasattr(r, "routes"):          # montajes y routers envueltos
                recorrer(r.routes, prefijo + getattr(r, "path", ""))
    recorrer(app.router.routes)
    return sorted(set(rutas))


def _patron_de_nginx() -> re.Pattern:
    texto = CONF.read_text(encoding="utf-8")
    m = re.search(r"location ~ (\^/api/v1/\S+) \{\n(?:(?!\n    \}).)*?proxy_set_header Upgrade", texto, re.S)
    assert m, "no hay una location por expresión regular con proxy_set_header Upgrade"
    return re.compile(m.group(1))


def test_cada_websocket_encaja_en_la_location_con_upgrade():
    rutas = _rutas_websocket()
    assert len(rutas) >= 6, rutas                     # la comprobación mira: dice cuántas recorrió
    patron = _patron_de_nginx()
    ejemplo = lambda r: re.sub(r"\{[^}]+\}", "x1", r)
    fuera = [r for r in rutas if not patron.match(ejemplo(r))]
    assert not fuera, f"WebSocket sin Upgrade en nginx: {fuera}"


def test_la_location_no_se_traga_rutas_http():
    patron = _patron_de_nginx()
    for r in ("/api/v1/bi/intelligence/ml/forecast/revenue", "/api/v1/collaboration/messages", "/api/v1/bi/collaboration/dashboards/x/comments"):
        assert not patron.match(r), r
