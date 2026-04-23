"""Smoke E2E for authenticated dashboard and reporting flows.

Covers:
- Dashboard first load renders content on first visit.
- Dashboard widgets do not trigger critical JS errors.
- Reports presets (templates) open and run without page crashes/console errors.
"""

from __future__ import annotations

from tests_e2e.conftest import BASE_URL


def _is_benign_console_error(msg: str) -> bool:
    lowered = (msg or "").lower()
    return (
        "favicon" in lowered
        or "resizeobserver loop" in lowered
        or "unsupported icon style" in lowered
    )


def _attach_error_collectors(page):
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
    return js_errors, page_errors, on_console, on_page_error


def test_dashboard_and_reporting_smoke(page):
    js_errors, page_errors, on_console, on_page_error = _attach_error_collectors(page)

    # 1) Dashboard should render on first authenticated visit.
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(3500)

    has_dashboard_title = (
        page.get_by_text("Dashboard").count() > 0
        or page.get_by_text("Panel de control").count() > 0
    )
    widget_count = page.locator(".react-grid-item").count()

    assert has_dashboard_title, "Dashboard title not rendered on first visit"
    assert widget_count > 0, "No dashboard widgets rendered on first visit"

    # 2) Open reports and run a subset of templates from presets.
    page.goto(f"{BASE_URL}/reports")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(1500)

    page.get_by_role("button", name="⚡ Plantillas").click()
    page.wait_for_timeout(800)

    cards = page.locator("button:has-text('→')")
    total_cards = cards.count()

    # When the analytics backend is unavailable (503) the catalogue is empty and
    # all presets are filtered out — that is expected behaviour for a partial-stack
    # local environment. Only assert page renders without crashing.
    preset_failures: list[str] = []

    if total_cards > 0:
        # Run first 8 templates to keep smoke fast while covering major categories.
        to_run = min(8, total_cards)

        for i in range(to_run):
            page.get_by_role("button", name="⚡ Plantillas").click()
            page.wait_for_timeout(250)

            card = page.locator("button:has-text('→')").nth(i)
            label = card.inner_text().strip()
            card.click()
            page.wait_for_timeout(1400)

            # If the report result is unavailable, UI shows this explicit error state.
            unavailable = page.get_by_text("Plantilla no disponible").count() > 0
            if unavailable:
                preset_failures.append(f"preset[{i}] {label}: unavailable")

    page.remove_listener("console", on_console)
    page.remove_listener("pageerror", on_page_error)

    # Filter out expected HTTP resource errors from analytics/catalogue backend.
    hard_js_errors = [
        e for e in js_errors
        if "failed to load resource" not in e.lower()
    ]

    assert not page_errors, "pageerror found: " + " | ".join(page_errors[:4])
    assert not hard_js_errors, "console.error found: " + " | ".join(hard_js_errors[:4])
    assert not preset_failures, "report preset failures: " + " | ".join(preset_failures)
