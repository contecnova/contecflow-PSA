"""Smoke E2E: rutas del menú lateral en sesión autenticada.

Valida que cada ruta visible para admin:
- carga sin romper la UI
- no dispara errores JS críticos en consola
- no cae en 404 o pantalla vacía
"""

from __future__ import annotations

import re
from pathlib import Path

from tests_e2e.conftest import BASE_URL


_LAYOUT_FILE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "components" / "layout" / "Layout.jsx"
_ROUTE_RE = re.compile(r"\{\s*to:\s*'(?P<route>/[^']+)'.*?roles:\s*\[(?P<roles>[^\]]*)\]", re.S)


def _admin_menu_routes() -> list[str]:
    content = _LAYOUT_FILE.read_text(encoding="utf-8")
    routes: list[str] = ["/dashboard"]
    seen = {"/dashboard"}

    for m in _ROUTE_RE.finditer(content):
        route = m.group("route")
        roles = m.group("roles")
        if "'admin'" not in roles:
            continue
        if route in seen:
            continue
        seen.add(route)
        routes.append(route)

    return routes


def _is_benign_console_error(msg: str) -> bool:
    lowered = msg.lower()
    return (
        "favicon" in lowered
        or "resizeobserver loop" in lowered
        or "unsupported icon style" in lowered
        or "failed to load resource: the server responded with a status of 404" in lowered
        or "failed to load resource: the server responded with a status of 500" in lowered
        or "failed to load resource: the server responded with a status of 503" in lowered
    )


def test_sidebar_admin_routes_smoke(page):
    routes = _admin_menu_routes()
    failures: list[str] = []

    for route in routes:
        js_errors: list[str] = []
        page_errors: list[str] = []

        def on_console(message):
            if message.type == "error":
                txt = message.text or ""
                if not _is_benign_console_error(txt):
                    js_errors.append(txt)

        def on_page_error(exc):
            page_errors.append(str(exc))

        page.on("console", on_console)
        page.on("pageerror", on_page_error)

        page.goto(f"{BASE_URL}{route}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)

        title = page.title()
        body = page.locator("body").inner_text()
        has_main = page.locator("main, #main-content").count() > 0

        if "404" in title or not body.strip() or not has_main:
            failures.append(f"{route}: UI inválida (title={title!r}, has_main={has_main})")

        if page_errors:
            failures.append(f"{route}: pageerror -> {' | '.join(page_errors[:3])}")

        if js_errors:
            failures.append(f"{route}: console.error -> {' | '.join(js_errors[:3])}")

        page.remove_listener("console", on_console)
        page.remove_listener("pageerror", on_page_error)

    assert not failures, "\n" + "\n".join(failures)
