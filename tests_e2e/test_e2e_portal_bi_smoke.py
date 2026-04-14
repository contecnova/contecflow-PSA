"""Smoke E2E: portal multi-proyecto + BI click-to-filter."""
import uuid
from sqlalchemy import or_

from tests_e2e.conftest import BASE_URL
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
    db = SessionLocal()
    try:
        admin = db.query(User).filter(or_(User.username == "admin", User.email == "admin@clarive.com")).first()
        if admin:
            admin.username = "admin"
            admin.email = "admin@clarive.com"
            admin.is_active = True
            admin.status = UserStatus.active
            admin.role = UserRole.admin
            admin.hashed_password = get_password_hash("clarive2024!")
        else:
            admin = User(
                username="admin",
                email="admin@clarive.com",
                full_name="Admin Smoke",
                role=UserRole.admin,
                status=UserStatus.active,
                is_active=True,
                hashed_password=get_password_hash("clarive2024!"),
            )
            db.add(admin)
        db.commit()
    finally:
        db.close()


def _login_backoffice(page):
    page.goto(f"{BASE_URL}/login")
    page.wait_for_load_state("networkidle")
    page.fill('#login-user', 'admin')
    page.fill('#login-pass', 'clarive2024!')
    page.click('button:has-text("Iniciar"), button:has-text("Login"), button:has-text("Entrar")')
    page.wait_for_url(f"{BASE_URL}/**")


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
        data={"username": "admin", "password": "clarive2024!"},
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
