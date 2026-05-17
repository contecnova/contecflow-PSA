"""Auditoria A11y automatizada (baseline WCAG) en rutas clave.

No pretende sustituir una auditoria manual completa, pero detecta debt comun:
- landmarks principales presentes
- controles interactivos con nombre accesible
- imagenes con alt
- campos de formulario etiquetados
- navegacion de foco por teclado (Tab)
"""

from __future__ import annotations

from conftest import BASE_URL


A11Y_ROUTES = [
    "/tasks",
    "/projects",
    "/reports",
    "/org-chart",
]


def _collect_critical_a11y_issues(page) -> list[str]:
    issues: list[str] = []

    # 1) Landmark principal
    if page.locator("main, [role='main']").count() == 0:
        issues.append("missing-main-landmark")

    # 2) Interactive elements must have accessible name
    unlabeled_clickables = page.locator(
        "button:not([aria-label]):not([aria-labelledby]):not(:has-text('*')), "
        "a[href]:not([aria-label]):not([aria-labelledby]):not(:has-text('*'))"
    ).count()
    if unlabeled_clickables > 0:
        issues.append(f"unlabeled-interactive:{unlabeled_clickables}")

    # 3) Images should provide alt attribute
    missing_alt = page.locator("img:not([alt])").count()
    if missing_alt > 0:
        issues.append(f"images-without-alt:{missing_alt}")

    # 4) Form controls require label/aria-label association
    unlabeled_fields = page.locator(
        "input:not([type='hidden']):not([aria-label]):not([aria-labelledby]):not([id]), "
        "select:not([aria-label]):not([aria-labelledby]):not([id]), "
        "textarea:not([aria-label]):not([aria-labelledby]):not([id])"
    ).count()
    if unlabeled_fields > 0:
        issues.append(f"unlabeled-form-controls:{unlabeled_fields}")

    return issues


def _keyboard_focus_changes_with_tab(page) -> bool:
    body = page.locator("body")
    body.click(position={"x": 10, "y": 10})

    active_before = page.evaluate("() => document.activeElement?.tagName || null")
    page.keyboard.press("Tab")
    page.wait_for_timeout(100)
    active_after = page.evaluate("() => document.activeElement?.tagName || null")

    return active_after is not None and active_after != active_before


def test_accessibility_wcag_baseline(page):
    failures: list[str] = []

    for route in A11Y_ROUTES:
        page.goto(f"{BASE_URL}{route}")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)

        issues = _collect_critical_a11y_issues(page)
        if issues:
            failures.append(f"{route}: {' | '.join(issues)}")

        if not _keyboard_focus_changes_with_tab(page):
            failures.append(f"{route}: keyboard-focus-tab-no-change")

    assert not failures, "\n" + "\n".join(failures)
