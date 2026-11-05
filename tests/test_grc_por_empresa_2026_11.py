"""Matriz de permisos GRC y reglas SoD por empresa (revisión 2026-11).

Medido en la base de un despliegue: 2364 casillas sembradas SIN empresa. Con el
filtro de la sesión, un administrador de empresa veía la matriz vacía, cada
visita volvía a sembrarla, y lo que restringía se guardaba donde la comprobación
podía no leerlo (o se aplicaba a otras empresas). Ahora: valores globales por
defecto y excepciones por empresa, nombradas explícitamente.
"""
from __future__ import annotations

from app.db.session import sin_filtro_de_tenant
from app.models.billing_reports import RolePermission, SodRule
from app.models.mfa import Organization
from app.models.user import User, UserRole
from tests.conftest import HASH_DE_PRUEBA, _TEST_PASSWORD, auth


def _matriz(client, token):
    r = client.get("/api/v1/grc/permissions", headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]["matrix"]


def _globales(db):
    with sin_filtro_de_tenant(db):
        return db.query(RolePermission).filter(RolePermission.organization_id.is_(None)).count()


def test_EL_HALLAZGO_el_admin_de_empresa_ve_la_matriz_y_no_se_resiembra(client, admin_token, db):
    m = _matriz(client, admin_token)
    assert m.get("employee", {}).get("invoices"), "la matriz efectiva no está vacía"
    n = _globales(db)
    _matriz(client, admin_token)
    assert _globales(db) == n and n > 100, "una segunda visita no duplica las casillas globales"


def _empleado_de_otra(client, db):
    db.add(Organization(id="org-grc", name="Otra", slug="org-grc"))
    db.flush()
    db.add(User(id="emp-otra", username="emp_otra", email="emp@otra-empresa.com", full_name="Empleado otra",
                role=UserRole.employee, is_active=True, organization_id="org-grc", hashed_password=HASH_DE_PRUEBA))
    db.commit()
    r = client.post("/api/v1/auth/login", json={"username": "emp_otra", "password": _TEST_PASSWORD})
    assert r.status_code == 200, r.text
    return r.cookies.get("access_token")


def test_EL_HALLAZGO_la_restriccion_vale_en_su_empresa_y_solo_en_ella(client, admin_token, dev_token, db):
    _matriz(client, admin_token)
    otro = _empleado_de_otra(client, db)
    r = client.patch("/api/v1/grc/permissions/employee/projects/ver", headers=auth(admin_token), json={"allowed": False})
    assert r.status_code == 200, r.text
    assert _matriz(client, admin_token)["employee"]["projects"]["ver"] is False
    assert client.get("/api/v1/projects", headers=auth(dev_token)).status_code == 403, "se aplica en la empresa 1"
    assert client.get("/api/v1/projects", headers=auth(otro)).status_code != 403, "no se aplica en otra empresa"
    with sin_filtro_de_tenant(db):
        fila = db.query(RolePermission).filter(RolePermission.role == "employee", RolePermission.module == "projects",
                                               RolePermission.action == "ver", RolePermission.organization_id.is_(None)).one()
        assert fila.allowed is True, "el valor global no se toca"


def test_restablecer_quita_solo_lo_de_la_empresa(client, admin_token, dev_token, db):
    _matriz(client, admin_token)
    client.patch("/api/v1/grc/permissions/employee/projects/ver", headers=auth(admin_token), json={"allowed": False})
    n = _globales(db)
    assert client.post("/api/v1/grc/permissions/seed", headers=auth(admin_token)).status_code == 200
    assert _matriz(client, admin_token)["employee"]["projects"]["ver"] is True
    assert _globales(db) == n


def test_las_reglas_sod_se_siembran_una_vez_y_en_su_empresa(client, admin_token, db):
    for _ in range(2):
        assert client.get("/api/v1/grc/sod-rules", headers=auth(admin_token)).status_code == 200
    with sin_filtro_de_tenant(db):
        de_la_1 = db.query(SodRule).filter(SodRule.organization_id == "1").count()
        sin_empresa = db.query(SodRule).filter(SodRule.organization_id.is_(None)).count()
    assert de_la_1 > 0 and sin_empresa == 0
    from app.api.v1.endpoints.grc import DEFAULT_SOD_RULES
    assert de_la_1 == len(DEFAULT_SOD_RULES), "una segunda visita no duplica"
