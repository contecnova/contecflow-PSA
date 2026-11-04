"""Revisión multitenant del 04-11-2026: lo que se encontró midiendo con dos empresas.

Sobre una copia de la base, con una segunda organización y su admin, se
recorrieron las 578 rutas GET buscando ids, correos y nombres de la otra:
una sola ruta los enseñaba (ajustes por ticket guardados como globales). Además:

- desactivar una organización solo frenaba el SSO y la passkey; el login con
  contraseña, los tokens ya emitidos, las claves de API y el portal seguían;
- `deps.get_current_client` (colaboración y conversaciones del portal) no
  publicaba el tenant, y `TenantSession` sin contexto no filtra;
- el resumen de informes programados (SQL a mano) contaba los de todas.
"""
from __future__ import annotations

from app.models.mfa import Organization
from app.models.settings import AppSetting
from app.models.user import User, UserRole
from tests.conftest import HASH_DE_PRUEBA, auth

CLAVE = "ClientPass123!"


def _otra_empresa(db, activa=True):
    db.add(Organization(id="org-b", name="Empresa B", slug="empresa-b", is_active=activa))
    db.add(User(id="admin-b", username="admin_b", email="admin@empresa-b.com", full_name="Admin B",
                role=UserRole.admin, is_active=True, organization_id="org-b",
                hashed_password=HASH_DE_PRUEBA))
    db.commit()


def _login(client, email):
    from tests.conftest import _TEST_PASSWORD
    return client.post("/api/v1/auth/login", json={"username": email, "password": _TEST_PASSWORD})


def _desactivar(db, org_id):
    db.query(Organization).filter(Organization.id == org_id).update({"is_active": False})
    db.commit()


def test_EL_HALLAZGO_una_empresa_desactivada_no_entra_con_contrasena(client, db):
    _otra_empresa(db, activa=False)
    r = _login(client, "admin@empresa-b.com")
    assert r.status_code == 403 and "desactivada" in r.text


def test_EL_HALLAZGO_desactivar_corta_las_sesiones_ya_abiertas(client, db):
    _otra_empresa(db)
    r = _login(client, "admin@empresa-b.com")
    assert r.status_code == 200, r.text
    assert client.cookies.get("access_token"), "la sesion va en la cookie"
    assert client.get("/api/v1/projects").status_code == 200
    _desactivar(db, "org-b")
    r = client.get("/api/v1/projects")
    assert r.status_code == 403 and "desactivada" in r.text


def test_desactivar_corta_tambien_el_portal(client, pm_token, db):
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Portal", "code": "MTP1", "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    client.post("/api/v1/portal/clients", headers=auth(pm_token), json={
        "project_ids": [pid], "full_name": "Cli", "email": "cli@mt.com", "password": CLAVE, "language": "es"})
    client.cookies.clear()
    assert client.post("/api/v1/portal/auth/login", json={"email": "cli@mt.com", "password": CLAVE}).status_code == 200
    assert client.get("/api/v1/portal/auth/me").status_code == 200
    db.add(Organization(id="1", name="Org 1", slug="org-1")) if not db.get(Organization, "1") else None
    db.commit()
    _desactivar(db, "1")
    assert client.get("/api/v1/portal/feature-requests").status_code == 403


def test_EL_HALLAZGO_el_cliente_del_portal_de_colaboracion_publica_su_tenant(client, pm_token, db):
    from starlette.requests import Request
    from app.core.deps import get_current_client
    pid = client.post("/api/v1/projects", headers=auth(pm_token), json={
        "name": "Colab", "code": "MTC1", "status": "active", "billing_type": "time_material"}).json()["data"]["id"]
    client.post("/api/v1/portal/clients", headers=auth(pm_token), json={
        "project_ids": [pid], "full_name": "Cli", "email": "colab@mt.com", "password": CLAVE, "language": "es"})
    client.cookies.clear()
    client.post("/api/v1/portal/auth/login", json={"email": "colab@mt.com", "password": CLAVE})
    token = client.cookies.get("portal_access_token")
    peticion = Request({"type": "http", "headers": [(b"cookie", f"portal_access_token={token}".encode())]})
    db.info.pop("organization_id", None)
    db.info.pop("is_superadmin", None)
    get_current_client(peticion, None, db)
    assert db.info.get("organization_id") == "1" and db.info.get("is_superadmin") is False


def test_EL_HALLAZGO_los_ajustes_de_un_ticket_van_con_su_organizacion(db):
    from app.models.service_desk import Ticket
    from app.services.service_desk import dynamic_ticket_fields_service as campos
    from app.services.service_desk import ticket_ops_service as ops
    t = Ticket(id="t-mt", number="INC-MT-1", title="x", description="x", organization_id="1", status="pending_client",
               ticket_type="incident", priority="p3_medium")
    db.add(t)
    db.commit()
    campos.save_ticket_dynamic_fields(db, t.id, {"modelo": "X1"})
    ops.save_pending_snapshot(db, t)
    db.commit()
    filas = db.query(AppSetting).filter(AppSetting.key.like("sd.ticket.%")).all()
    assert sorted((f.key.split(".")[2], f.organization_id) for f in filas) == [
        ("dynamic_fields", "1"), ("pending_snapshot", "1")]
    assert campos.get_ticket_dynamic_fields(db, t.id) == {"modelo": "X1"}


def test_EL_HALLAZGO_el_resumen_de_informes_programados_es_de_la_empresa(db):
    from app.models.billing_reports import ScheduledReport
    from app.services.scheduled_reports_compat import summarize_scheduled_reports
    _otra_empresa(db)
    db.add(ScheduledReport(name="De la 1", organization_id="1"))
    db.add(ScheduledReport(name="De la B", organization_id="org-b"))
    db.add(ScheduledReport(name="Otra de la B", organization_id="org-b"))
    db.commit()
    db.info["is_superadmin"], db.info["organization_id"] = False, "org-b"
    assert summarize_scheduled_reports(db)["total"] == 2
    db.info["is_superadmin"] = True
    assert summarize_scheduled_reports(db)["total"] == 3
