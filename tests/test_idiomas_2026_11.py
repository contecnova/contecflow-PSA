"""Idiomas (revisión 2026-11): las traducciones personalizadas no llegaban a nadie.

- Las del back-office vivían en el localStorage del administrador.
- Las del portal se guardaban en el servidor, pero el portal leía el
  localStorage (que el cliente no tiene), y guardar una clave borraba las demás
  de ese idioma (fusión de primer nivel).
"""
from __future__ import annotations

from tests.conftest import auth
from tests.test_portal_wiki_tenant_isolation import _create_portal_client, _create_project, _portal_login


def test_EL_HALLAZGO_las_del_back_office_las_ve_toda_la_empresa(client, admin_token, pm_token):
    r = client.put("/api/v1/settings/app-translations", headers=auth(admin_token),
                   json={"translations": {"en": {"nav": {"projects": "Engagements"}}}})
    assert r.status_code == 200, r.text
    vistas = client.get("/api/v1/settings/app-translations", headers=auth(pm_token)).json()["data"]
    assert vistas == {"en": {"nav": {"projects": "Engagements"}}}


def test_solo_el_admin_las_cambia(client, pm_token):
    r = client.put("/api/v1/settings/app-translations", headers=auth(pm_token),
                   json={"translations": {"en": {"nav": {"projects": "X"}}}})
    assert r.status_code == 403


def test_no_cruzan_de_empresa(client, admin_token, db):
    from app.services.branding_service import guardar_traducciones_del_back_office, traducciones_del_back_office
    from app.models.mfa import Organization
    db.add(Organization(id="org-b", name="B", slug="org-b"))
    db.commit()
    guardar_traducciones_del_back_office(db, "org-b", {"en": {"nav": {"projects": "De B"}}})
    assert client.get("/api/v1/settings/app-translations", headers=auth(admin_token)).json()["data"] == {}
    assert traducciones_del_back_office(db, "org-b") == {"en": {"nav": {"projects": "De B"}}}


def test_EL_HALLAZGO_guardar_una_clave_no_borra_las_demas_y_vacio_quita():
    from app.services.branding_service import fusionar_traducciones
    actuales = {"en": {"login": "Sign in", "logout": "Sign out"}, "zh": {"login": "登录"}}
    assert fusionar_traducciones(actuales, {"en": {"login": "Log in"}}) == {
        "en": {"login": "Log in", "logout": "Sign out"}, "zh": {"login": "登录"}}
    assert fusionar_traducciones(actuales, {"zh": {"login": ""}}) == {"en": {"login": "Sign in", "logout": "Sign out"}}


def test_EL_HALLAZGO_el_portal_recibe_sus_traducciones(client, admin_token):
    r = client.post("/api/v1/portal/translations", headers=auth(admin_token), json={"en": {"nav_dashboard": "Home"}})
    assert r.status_code == 200, r.text
    pid = _create_project(client, admin_token, "IDI1", "Idiomas")
    _create_portal_client(client, admin_token, [pid], "idiomas@cliente.com", "Portal-Idiomas-2026!")
    client.cookies.clear()
    _portal_login(client, "idiomas@cliente.com", "Portal-Idiomas-2026!")
    marca = client.get("/api/v1/portal/branding").json()["data"]
    assert marca["translations"] == {"en": {"nav_dashboard": "Home"}}
