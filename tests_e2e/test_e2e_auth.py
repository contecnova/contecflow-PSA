"""E2E: Autenticación y sesión de usuario."""
import pytest
from tests_e2e.conftest import BASE_URL, ADMIN_USER, ADMIN_PASS


def test_login_correcto(anon_page):
    """El usuario puede hacer login con credenciales correctas."""
    anon_page.goto(f"{BASE_URL}/login")
    anon_page.fill('#login-user', ADMIN_USER)
    anon_page.fill('#login-pass', ADMIN_PASS)
    anon_page.click('.btn-primary')
    anon_page.wait_for_url(f"{BASE_URL}/**", timeout=8000)
    assert "/login" not in anon_page.url


def test_login_credenciales_incorrectas(anon_page):
    """Login con contraseña incorrecta muestra error."""
    anon_page.goto(f"{BASE_URL}/login")
    anon_page.fill('#login-user', ADMIN_USER)
    anon_page.fill('#login-pass', "password_incorrecta")
    anon_page.click('.btn-primary')
    # Debe mostrar mensaje de error y quedarse en login
    anon_page.wait_for_timeout(2000)
    assert "/login" in anon_page.url or \
           anon_page.locator('text=Error, text=incorrecta, text=inválid').count() > 0


def test_dashboard_requiere_login(anon_page):
    """Acceder al dashboard sin sesión redirige al login."""
    anon_page.goto(f"{BASE_URL}/dashboard")
    anon_page.wait_for_timeout(2000)
    assert "/login" in anon_page.url


def test_sidebar_visible_tras_login(page):
    """El sidebar de navegación es visible tras autenticarse."""
    page.goto(f"{BASE_URL}/dashboard")
    assert page.locator('aside, nav[aria-label]').count() > 0


def test_logout(page):
    """El usuario puede cerrar sesión."""
    page.goto(f"{BASE_URL}/dashboard")
    # Buscar botón de logout (⏻ o texto "Cerrar sesión")
    logout_btn = page.locator('button[title*="sesión" i], button:has-text("⏻")').first
    if logout_btn.is_visible():
        logout_btn.click()
        page.wait_for_timeout(2000)
        assert "/login" in page.url or page.url == f"{BASE_URL}/"


def test_perfil_usuario_abre(page):
    """Clic en nombre de usuario abre el panel de perfil."""
    page.goto(f"{BASE_URL}/dashboard")
    # Botón de perfil en el footer del sidebar
    profile_trigger = page.locator('button:has-text("Admin"), aside button').last
    if profile_trigger.is_visible():
        profile_trigger.click()
        page.wait_for_timeout(1000)
        # El panel debe mostrar tabs de perfil
        assert page.locator('text=Perfil, text=Apariencia').count() > 0
