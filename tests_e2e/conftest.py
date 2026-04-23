"""
Fixtures de Playwright E2E para Contecflow PSA.

Uso:
  pip install playwright pytest-playwright
  playwright install chromium
  BASE_URL=http://localhost:8000 pytest tests_e2e/ -v

Variables de entorno:
  BASE_URL       URL del frontend (default: http://localhost)
  ADMIN_USER     Usuario admin (default: admin)
  ADMIN_PASS     Contraseña admin (default: contecflow2024!)
  HEADLESS       Modo headless (default: true)
"""
import os
import pytest
from playwright.sync_api import Page, BrowserContext

BASE_URL   = os.getenv("BASE_URL",   "http://localhost")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "contecflow2024!")


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
    page.goto(f"{BASE_URL}/login")
    page.fill('#login-user', ADMIN_USER)
    page.fill('#login-pass', ADMIN_PASS)
    page.click('button[type="submit"], button:has-text("Iniciar"), button:has-text("Login")')
    page.wait_for_timeout(800)
    page.wait_for_url(f"{BASE_URL}/**", timeout=10000)
    if "/login" in page.url:
        raise RuntimeError("E2E login failed: still on /login after submit")
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
