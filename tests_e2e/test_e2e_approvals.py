"""E2E: Aprobaciones - CRUD de workflows y pasos desde la UI."""
from uuid import uuid4

from conftest import BASE_URL


def test_approvals_workflow_crud(page):
    """Crea un workflow, añade un paso, lo verifica y limpia el dato en UI."""
    suffix = uuid4().hex[:8]
    workflow_name = f"Aprobacion E2E {suffix}"
    step_name = f"Paso E2E {suffix}"

    page.goto(f"{BASE_URL}/approvals")
    page.wait_for_load_state("networkidle")

    heading = page.get_by_role("heading", name="Aprobaciones")
    assert heading.is_visible()

    page.get_by_role("button", name="Flujos").click()
    page.wait_for_timeout(600)

    page.get_by_role("button", name="Nuevo flujo").click()
    dialog = page.get_by_role("dialog")
    dialog.locator('input[id*="-name"]').fill(workflow_name)
    dialog.locator('select[id*="-entity-type"]').select_option("change_request")
    dialog.locator('input[id*="-description"]').fill("Workflow creado por regression e2e")
    dialog.get_by_role("button", name="Crear flujo").click()

    page.wait_for_timeout(1200)
    assert page.get_by_text(workflow_name, exact=True).first.is_visible()
    assert page.get_by_role("button", name="Añadir paso").is_visible()

    page.get_by_role("button", name="Añadir paso").click()
    step_dialog = page.get_by_role("dialog")
    step_dialog.locator('input[id*="-name"]').fill(step_name)
    step_dialog.locator('select[id*="-approver-role"]').select_option("admin")
    step_dialog.get_by_role("button", name="Añadir paso").click()

    page.wait_for_timeout(1200)
    assert page.get_by_text(step_name, exact=True).first.is_visible()

    page.get_by_role("button", name="Volver").click()
    page.wait_for_timeout(800)

    workflow_card = page.locator('[role="button"]').filter(has_text=workflow_name).first
    assert workflow_card.is_visible()
    workflow_card.get_by_role("button").click()

    confirm_dialog = page.get_by_role("heading", name="⚠️ Confirmar acción")
    assert confirm_dialog.is_visible()
    page.get_by_role("button", name="Confirmar").click()

    page.wait_for_timeout(1200)
    assert page.locator('[role="button"]').filter(has_text=workflow_name).count() == 0
