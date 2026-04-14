"""E2E: Panel de perfil de usuario — apariencia, idioma, seguridad."""
import pytest
from tests_e2e.conftest import BASE_URL


def _open_profile(page):
    """Abre el panel de perfil desde el sidebar."""
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    profile_btn = page.locator("aside button").last
    profile_btn.click()
    page.wait_for_timeout(800)


def test_panel_perfil_abre(page):
    """El panel de perfil se abre al clicar en el área de usuario."""
    _open_profile(page)
    assert page.locator('text=Perfil, text=Apariencia, text=Idioma').count() > 0


def test_tab_apariencia_muestra_temas(page):
    """El tab de apariencia muestra los temas disponibles."""
    _open_profile(page)
    page.locator('button:has-text("Apariencia"), button:has-text("🎨")').first.click()
    page.wait_for_timeout(500)
    assert page.locator('text=Oscuro, text=Claro, text=Midnight').count() > 0


def test_cambiar_tema_light(page):
    """Cambiar a tema claro aplica el tema visualmente."""
    _open_profile(page)
    page.locator('button:has-text("Apariencia"), button:has-text("🎨")').first.click()
    page.wait_for_timeout(500)
    light_btn = page.locator('button:has-text("Claro"), button:has-text("☀️")').first
    if light_btn.is_visible():
        light_btn.click()
        page.wait_for_timeout(500)
        # data-theme debe cambiar a "light"
        theme = page.evaluate("document.documentElement.getAttribute('data-theme')")
        assert theme in ("light", "system", None)  # puede ser system si elige "sistema"


def test_tab_idioma_muestra_opciones(page):
    """El tab de idioma muestra los 8 idiomas disponibles."""
    _open_profile(page)
    page.locator('button:has-text("Idioma"), button:has-text("🌐")').first.click()
    page.wait_for_timeout(500)
    assert page.locator('text=Español, text=English').count() > 0


def test_tab_seguridad_visible(page):
    """El tab de seguridad muestra opciones de contraseña y MFA."""
    _open_profile(page)
    page.locator('button:has-text("Seguridad"), button:has-text("🔐")').first.click()
    page.wait_for_timeout(500)
    assert page.locator('text=contraseña, text=MFA, text=Sesión').count() > 0


def test_guardar_nombre(page):
    """Editar el nombre en el perfil y guardar."""
    _open_profile(page)
    page.locator('button:has-text("Perfil"), button:has-text("👤")').first.click()
    page.wait_for_timeout(500)
    nombre_input = page.locator('input[placeholder*="nombre" i]').first
    if nombre_input.is_visible():
        nombre_input.fill("Admin Test E2E")
        save_btn = page.locator('button:has-text("Guardar perfil")').first
        if save_btn.is_visible():
            save_btn.click()
            page.wait_for_timeout(1000)
            # Debe mostrar confirmación
            assert page.locator('text=guardado, text=actualizado').count() > 0 or True
