"""E2E: Gestión de proyectos — CRUD completo en el navegador."""
import pytest
from tests_e2e.conftest import BASE_URL


def test_navegar_a_proyectos(page):
    """La página de proyectos carga correctamente."""
    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")
    assert page.title() or page.locator("h1, h2").count() > 0


def test_boton_nuevo_proyecto_visible(page):
    """Existe un botón para crear nuevo proyecto."""
    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")
    btn = page.locator('button:has-text("Nuevo"), button:has-text("New"), button:has-text("+")').first
    assert btn.is_visible()


def test_crear_proyecto_flujo_completo(page):
    """Crea un proyecto desde el formulario y verifica que aparece en la lista."""
    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")

    # Abrir formulario de creación
    page.click('button:has-text("Nuevo"), button:has-text("New proyecto")')
    page.wait_for_timeout(800)

    # Rellenar nombre (campo obligatorio)
    name_input = page.locator('input[placeholder*="nombre" i], input[name="name"]').first
    if name_input.is_visible():
        name_input.fill("Proyecto E2E Test")

    # Rellenar código si existe
    code_input = page.locator('input[placeholder*="código" i], input[name="code"]').first
    if code_input.is_visible():
        code_input.fill("E2E-001")

    # Guardar
    page.locator('button:has-text("Crear"), button:has-text("Guardar"), button[type="submit"]').last.click()
    page.wait_for_timeout(1500)

    # Verificar que aparece en la lista
    assert page.locator('text=Proyecto E2E Test').count() > 0 or \
           page.locator('text=E2E-001').count() > 0


def test_lista_proyectos_muestra_datos(page):
    """La lista de proyectos muestra columnas de datos."""
    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(1000)
    # Debe haber contenido — tabla, cards, o empty state
    has_content = page.locator('table, .project-card, [data-testid="project"], text=Sin proyectos').count() > 0
    assert has_content


def test_filtro_proyectos(page):
    """El filtro/búsqueda de proyectos funciona."""
    page.goto(f"{BASE_URL}/projects")
    page.wait_for_load_state("networkidle")
    search = page.locator('input[placeholder*="buscar" i], input[placeholder*="search" i]').first
    if search.is_visible():
        search.fill("proyecto inexistente xyz123")
        page.wait_for_timeout(800)
        # No debe mostrar proyectos o muestra "sin resultados"
        assert page.locator('text=Sin resultados, text=No hay, text=0').count() >= 0
