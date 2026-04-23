"""Regresion E2E amplia de paginas autenticadas.

Objetivo:
- Recorrer rutas declaradas en App.jsx (sin rutas dinamicas con parametros)
- Detectar errores de render, errores JS y respuestas 5xx en API
"""

from __future__ import annotations

import re
from pathlib import Path

from conftest import BASE_URL


_APP_FILE = Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.jsx"
_ROUTE_RE = re.compile(r'<Route\s+path="(?P<path>/[^\"]*)"')

_SKIP_ROUTES = {
    "/login",
    "/reset-password",
    "/portal",
    "/403",
    "/*",
    "/",
}


def _all_static_routes() -> list[str]:
    content = _APP_FILE.read_text(encoding="utf-8")
    seen: set[str] = set()
    routes: list[str] = []

    for m in _ROUTE_RE.finditer(content):
        path = m.group("path")
        if not path or path in _SKIP_ROUTES:
            continue
        if ":" in path:
            continue
        if path in seen:
            continue
        seen.add(path)
        routes.append(path)

    return routes


def _is_benign_console_error(msg: str) -> bool:
    lowered = msg.lower()
    return (
        "favicon" in lowered
        or "resizeobserver loop" in lowered
        or "unsupported icon style" in lowered
    )


def test_all_static_pages_regression(page):
    routes = _all_static_routes()
    failures: list[str] = []

    for route in routes:
        js_errors: list[str] = []
        page_errors: list[str] = []
        api_5xx: list[str] = []

        def on_console(message):
            if message.type == "error":
                txt = message.text or ""
                if not _is_benign_console_error(txt):
                    js_errors.append(txt)

        def on_page_error(exc):
            page_errors.append(str(exc))

        def on_response(res):
            url = res.url or ""
            if "/api/v1/" in url and res.status >= 500:
                api_5xx.append(f"{res.status} {url}")

        page.on("console", on_console)
        page.on("pageerror", on_page_error)
        page.on("response", on_response)

        page.goto(f"{BASE_URL}{route}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        body_text = page.locator("body").inner_text().strip()
        has_main = page.locator("main, #main-content").count() > 0

        if not body_text or not has_main:
            failures.append(f"{route}: vista vacia o sin contenedor principal")

        if page_errors:
            failures.append(f"{route}: pageerror -> {' | '.join(page_errors[:3])}")

        if js_errors:
            failures.append(f"{route}: console.error -> {' | '.join(js_errors[:3])}")

        if api_5xx:
            failures.append(f"{route}: api 5xx -> {' | '.join(api_5xx[:3])}")

        page.remove_listener("console", on_console)
        page.remove_listener("pageerror", on_page_error)
        page.remove_listener("response", on_response)

    assert not failures, "\n" + "\n".join(failures)
