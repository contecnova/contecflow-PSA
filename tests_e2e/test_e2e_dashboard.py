"""E2E: Dashboard principal y BI."""
import pytest
from conftest import BASE_URL


def test_dashboard_carga(page):
    """El dashboard principal carga sin errores."""
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_load_state("networkidle")
    # No debe haber error 500 ni pantalla en blanco
    assert "500" not in page.title()
    assert page.locator("body").inner_text() != ""


def test_dashboard_muestra_kpis(page):
    """El dashboard muestra al menos un KPI o card de resumen."""
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    # KPIs, cards, o algún número visible
    assert page.locator('[class*="kpi"], [class*="card"], h2, h3').count() > 0


def test_bi_dashboard_carga(page):
    """El dashboard BI carga y muestra widgets."""
    page.goto(f"{BASE_URL}/bi")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2000)
    assert page.locator("body").inner_text() != ""


def test_bi_boton_configurar(page):
    """El botón de configurar widgets es visible en el BI."""
    page.goto(f"{BASE_URL}/bi")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    btn = page.locator('button:has-text("Configurar"), button:has-text("⚙")').first
    assert btn.is_visible()


def test_bi_panel_tema_abre(page):
    """El panel de tema se abre al hacer clic en el botón."""
    page.goto(f"{BASE_URL}/bi")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1500)
    tema_btn = page.locator('button:has-text("Tema"), button:has-text("🎨")').first
    if tema_btn.is_visible():
        tema_btn.click()
        page.wait_for_timeout(800)
        # Panel lateral debe aparecer con opciones de color
        assert page.locator('text=acento, text=Color, input[type="color"]').count() > 0


def test_executive_redirige_a_bi(page):
    """/executive redirige al dashboard BI."""
    page.goto(f"{BASE_URL}/executive")
    page.wait_for_load_state("networkidle")
    assert "/bi" in page.url


def test_sidebar_navegacion_completa(page):
    """Los links del sidebar llevan a páginas válidas."""
    page.goto(f"{BASE_URL}/dashboard")
    page.wait_for_load_state("networkidle")

    nav_links = ["/projects", "/tasks", "/service-desk"]
    for url in nav_links:
        page.goto(f"{BASE_URL}{url}")
        page.wait_for_load_state("networkidle")
        assert "404" not in page.title()
        assert page.locator("main, #main-content").count() > 0
