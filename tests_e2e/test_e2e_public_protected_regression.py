"""Regresion E2E para acceso publico y proteccion de rutas."""

from __future__ import annotations

from conftest import BASE_URL


_PUBLIC_ROUTES = [
    "/login",
    "/reset-password",
    "/portal",
]

_PROTECTED_SAMPLE_ROUTES = [
    "/tasks",
    "/projects",
    "/invoices",
    "/service-desk",
    "/settings",
]


def test_public_routes_do_not_crash(anon_page):
    failures: list[str] = []

    for route in _PUBLIC_ROUTES:
        page_errors: list[str] = []

        def on_page_error(exc):
            page_errors.append(str(exc))

        anon_page.on("pageerror", on_page_error)
        anon_page.goto(f"{BASE_URL}{route}")
        anon_page.wait_for_load_state("domcontentloaded")
        anon_page.wait_for_timeout(600)

        title = anon_page.title()
        body = anon_page.locator("body").inner_text().strip()
        if not body:
            failures.append(f"{route}: body vacio")
        if "500" in title:
            failures.append(f"{route}: title sugiere 500")
        if page_errors:
            failures.append(f"{route}: pageerror -> {' | '.join(page_errors[:3])}")

        anon_page.remove_listener("pageerror", on_page_error)

    assert not failures, "\n" + "\n".join(failures)


def test_protected_routes_redirect_to_login_when_anonymous(anon_page):
    failures: list[str] = []

    for route in _PROTECTED_SAMPLE_ROUTES:
        anon_page.goto(f"{BASE_URL}{route}")
        anon_page.wait_for_timeout(800)
        current = anon_page.url
        if "/login" not in current:
            failures.append(f"{route}: no redirige a /login (url={current})")

    assert not failures, "\n" + "\n".join(failures)
