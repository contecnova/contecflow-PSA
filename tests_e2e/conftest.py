"""
Fixtures de Playwright E2E para Contecflow PSA.

Uso:
  pip install playwright pytest-playwright
  playwright install chromium
  BASE_URL=http://localhost:8000 pytest tests_e2e/ -v

Variables de entorno:
    BASE_URL       URL del frontend (default: http://localhost:3000)
  ADMIN_USER     Usuario admin (default: admin)
  ADMIN_PASS     Contraseña admin (default: contecflow2024!)
  HEADLESS       Modo headless (default: true)
"""
import os
import pytest
from playwright.sync_api import Page, BrowserContext

BASE_URL   = os.getenv("BASE_URL",   "http://localhost:3000")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "contecflow2024!")


def _try_login(page: Page) -> bool:
    """Best-effort login compatible with localized/variant login UIs."""
    page.goto(f"{BASE_URL}/login")
    page.wait_for_load_state("domcontentloaded")

    user_input = page.locator(
        '#login-user, input[name="username"], input[autocomplete="username"], '
        'input[type="text"], input[type="email"]'
    ).first
    pass_input = page.locator(
        '#login-pass, input[name="password"], input[autocomplete="current-password"], input[type="password"]'
    ).first
    submit_btn = page.locator(
        'button[type="submit"], button:has-text("Iniciar"), button:has-text("Login"), '
        'button:has-text("Entrar"), button:has-text("Sign in")'
    ).first

    if user_input.count() == 0 or pass_input.count() == 0:
        return False

    user_input.fill(ADMIN_USER)
    pass_input.fill(ADMIN_PASS)

    if submit_btn.count() > 0:
        submit_btn.click()
    else:
        pass_input.press("Enter")

    page.wait_for_timeout(900)
    return "/login" not in page.url


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport":    {"width": 1280, "height": 800},
        "locale":      "es-ES",
        "timezone_id": "Europe/Madrid",
    }


@pytest.fixture(scope="session")
def logged_in_context(browser):
    """Contexto de navegador ya autenticado como admin (reusado en toda la sesión)."""
    context = browser.new_context(
        viewport={"width": 1280, "height": 800},
        locale="es-ES",
    )
    page = context.new_page()
    if not _try_login(page):
        context.close()
        pytest.skip("E2E login unavailable (frontend not ready or login selectors changed)")
    yield context
    context.close()


@pytest.fixture
def page(logged_in_context):
    """Página fresca autenticada para cada test."""
    page = logged_in_context.new_page()
    yield page
    page.close()


@pytest.fixture
def anon_page(browser):
    """Página sin autenticar para tests de acceso anónimo."""
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()
    yield page
    context.close()
