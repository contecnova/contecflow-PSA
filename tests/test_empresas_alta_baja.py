"""Alta, suspensión y control de empresas (revisión multitenant 2026-11).

- El alta no creaba a nadie: una empresa nueva no tenía quien entrara.
- Suspender no pedía motivo ni quedaba constancia.
- Los límites del plan solo se miraban al asignar un usuario existente:
  crear usuarios o proyectos no los respetaba.
"""
from __future__ import annotations

from app.models.mfa import Organization
from tests.conftest import auth
from app.core.errores import ErrorDeDominio


def _alta(client, token, **extra):
    r = client.post("/api/v1/organizations", headers=auth(token), json={
        "name": "Cliente Nuevo", "slug": "cliente-nuevo", "max_users": 2, "max_projects": 1, **extra})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_EL_HALLAZGO_el_alta_crea_el_primer_admin_y_puede_entrar(client, superadmin_token, db):
    datos = _alta(client, superadmin_token, admin_email="jefa@cliente-nuevo.com", admin_name="Jefa")
    assert datos["initial_password"]
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"username": "jefa@cliente-nuevo.com",
                                                "password": datos["initial_password"]})
    assert r.status_code == 200, r.text
    me = client.get("/api/v1/auth/me").json()
    assert me["role"] == "admin" and me["organization_id"] == datos["id"]


def test_EL_HALLAZGO_suspender_pide_motivo_y_reactivar_lo_borra(client, superadmin_token, db):
    org = _alta(client, superadmin_token)["id"]
    h = auth(superadmin_token)
    assert client.patch(f"/api/v1/organizations/{org}", headers=h, json={"is_active": False}).status_code == 422
    r = client.patch(f"/api/v1/organizations/{org}", headers=h,
                     json={"is_active": False, "suspension_reason": "Impago"})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.get(Organization, org).suspension_reason == "Impago"
    client.patch(f"/api/v1/organizations/{org}", headers=h, json={"is_active": True})
    db.expire_all()
    fila = db.get(Organization, org)
    assert fila.is_active and fila.suspension_reason is None


def test_EL_HALLAZGO_el_limite_de_usuarios_y_proyectos_se_cumple(client, superadmin_token, db):
    datos = _alta(client, superadmin_token, admin_email="jefa@cliente-nuevo.com")
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"username": "jefa@cliente-nuevo.com", "password": datos["initial_password"]})
    nuevo = {"username": "u2", "email": "u2@cliente-nuevo.com", "full_name": "U2", "role": "employee",
             "password": "OtraClave-2026!x"}
    assert client.post("/api/v1/users", json=nuevo).status_code in (200, 201)  # 2 de 2
    r = client.post("/api/v1/users", json={**nuevo, "username": "u3", "email": "u3@cliente-nuevo.com"})
    assert r.status_code == 409 and "límite" in r.text
    proyecto = {"name": "P", "status": "active", "billing_type": "time_material"}
    assert client.post("/api/v1/projects", json={**proyecto, "code": "CN1"}).status_code in (200, 201)
    r = client.post("/api/v1/projects", json={**proyecto, "code": "CN2"})
    assert r.status_code == 409 and "límite" in r.text


def test_el_dominio_no_se_repite_entre_empresas(client, superadmin_token, db):
    _alta(client, superadmin_token, domain="app.cliente.com")
    r = client.post("/api/v1/organizations", headers=auth(superadmin_token), json={
        "name": "Otra", "slug": "otra", "domain": "app.cliente.com"})
    assert r.status_code == 400 and "dominio" in r.text


def test_el_limite_de_usuarios_tambien_por_scim(client, superadmin_token, db):
    """Medido el 09-11-2026: SCIM creaba usuarios sin mirar el cupo del plan."""
    from fastapi import HTTPException
    import pytest
    from app.services.scim_service import create_scim_user, process_bulk_operation
    datos = _alta(client, superadmin_token, admin_email="jefa@cliente-nuevo.com", max_users=1)  # el admin ya ocupa 1
    org = datos["id"]
    with pytest.raises((HTTPException, ErrorDeDominio)) as e:
        create_scim_user(org, {"userName": "scim1", "emails": [{"value": "scim1@cliente-nuevo.com"}]}, db)
    assert e.value.status_code == 409
    with pytest.raises(ValueError, match="límite"):
        process_bulk_operation(org, {"method": "POST", "path": "/Users",
                                     "data": {"userName": "scim2", "emails": [{"value": "scim2@cliente-nuevo.com"}]}}, db)
