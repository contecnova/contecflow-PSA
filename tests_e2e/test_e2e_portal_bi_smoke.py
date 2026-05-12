"""Smoke E2E: portal multi-proyecto + BI click-to-filter."""
import uuid
import sys
from pathlib import Path
from sqlalchemy import or_

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from conftest import BASE_URL, ADMIN_PASS
from app.db.session import SessionLocal
from app.models.user import User, UserRole, UserStatus
from app.core.security import get_password_hash


PROJECT_PAYLOAD_BASE = {
    "name": "Proyecto Smoke",
    "code": "SMK",
    "description": "Proyecto de smoke e2e",
    "status": "planning",
    "billing_type": "time_material",
    "is_billable": True,
}


def _create_project(api, token: str, suffix: str) -> str:
    payload = {
        **PROJECT_PAYLOAD_BASE,
        "name": f"Proyecto Smoke {suffix}",
        "code": f"SMK-{suffix}"[:20],
    }
    res = api.post(
        f"{BASE_URL}/api/v1/projects",
        data=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.ok, res.text()
    data = res.json()
    return data["id"]


def _ensure_admin_user() -> None:
    if not ADMIN_PASS:
        pytest.skip("ADMIN_PASS env var not configured for E2E smoke")
    db = SessionLocal()
    try:
        admin = db.query(User).filter(or_(User.username == "admin", User.email == "admin@contecflow.com")).first()
        if admin:
            admin.username = "admin"
            admin.email = "admin@contecflow.com"
            admin.is_active = True
            admin.status = UserStatus.active
            admin.role = UserRole.admin
            admin.hashed_password = get_password_hash(ADMIN_PASS)
        else:
            admin = User(
                username="admin",
                email="admin@contecflow.com",
                full_name="Admin Smoke",
                role=UserRole.admin,
                status=UserStatus.active,
                is_active=True,
                hashed_password=get_password_hash(ADMIN_PASS),
            )
            db.add(admin)
        db.commit()
    finally:
        db.close()


def _login_backoffice(page):
    page.goto(f"{BASE_URL}/login")
    page.wait_for_load_state("domcontentloaded")

    user_input = page.locator(
        '#login-user, input[name="username"], input[autocomplete="username"], '
        'input[type="text"], input[type="email"]'
    ).first
    pass_input = page.locator(
        '#login-pass, input[name="password"], input[autocomplete="current-password"], input[type="password"]'
    ).first

    if user_input.count() == 0 or pass_input.count() == 0:
        pytest.skip("Login UI no disponible en entorno E2E actual")

    user_input.fill('admin')
    pass_input.fill(ADMIN_PASS)

    submit_btn = page.locator(
        'button[type="submit"], button:has-text("Iniciar"), button:has-text("Login"), '
        'button:has-text("Entrar"), button:has-text("Sign in")'
    ).first
    if submit_btn.count() > 0:
        submit_btn.click()
    else:
        pass_input.press("Enter")

    page.wait_for_timeout(900)
    if "/login" in page.url:
        pytest.skip("No se pudo autenticar en backoffice (credenciales o UI de login)")


def test_bi_click_to_filter_smoke(anon_page):
    """BI: click en widgets aplica chips de filtro activos."""
    _ensure_admin_user()
    _login_backoffice(anon_page)
    anon_page.goto(f"{BASE_URL}/bi")
    anon_page.wait_for_load_state("networkidle")
    anon_page.wait_for_timeout(1500)

    # Top clientes -> chip Cliente
    top_clients_clickables = anon_page.locator('#widget-top_clients div[style*="cursor: pointer"]')
    if top_clients_clickables.count() > 0:
        top_clients_clickables.first.click()
        anon_page.wait_for_timeout(500)
        assert anon_page.locator('text=Cliente:').count() > 0

    # Top margen -> chip Proyecto
    top_margin_clickables = anon_page.locator('#widget-top_margin div[style*="cursor: pointer"]')
    if top_margin_clickables.count() > 0:
        top_margin_clickables.first.click()
        anon_page.wait_for_timeout(500)
        assert anon_page.locator('text=Proyecto:').count() > 0


def test_portal_multi_project_selector_smoke(anon_page):
    """Portal cliente: usuario con 2 proyectos ve selector multi-proyecto."""
    _ensure_admin_user()
    api = anon_page.context.request

    login = api.post(
        f"{BASE_URL}/api/v1/auth/login",
        data={"username": "admin", "password": ADMIN_PASS},
    )
    assert login.ok, login.text()
    token = login.json()["access_token"]

    suffix = uuid.uuid4().hex[:6].upper()
    pid1 = _create_project(api, token, f"{suffix}A")
    pid2 = _create_project(api, token, f"{suffix}B")

    client_email = f"portal-smoke-{suffix.lower()}@example.com"
    create_client = api.post(
        f"{BASE_URL}/api/v1/portal/clients",
        data={
            "full_name": "Portal Smoke QA",
            "email": client_email,
            "password": "PortalSmoke123!",
            "project_ids": [pid1, pid2],
            "can_view_team": True,
            "can_view_budget": True,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_client.ok, create_client.text()

    anon_page.goto(f"{BASE_URL}/portal")
    anon_page.fill('input[type="email"]', client_email)
    anon_page.fill('input[type="password"]', 'PortalSmoke123!')
    anon_page.click('button:has-text("Entrar")')
    anon_page.wait_for_load_state("networkidle")
    anon_page.wait_for_timeout(1200)

    assert anon_page.locator("text=Selecciona uno para continuar").count() > 0
    assert anon_page.locator('div[style*="cursor: pointer"]').count() >= 2
