"""En qué empresa entra cada persona, según el modo del despliegue.

Revisión multitenant 2026-11 (ver app/services/entrada_service.py). Antes la
empresa salía siempre de `users.organization_id`: quien pertenecía a varias no
podía entrar en las otras ni cambiar.
"""
from __future__ import annotations

import pytest

from app.core.config import settings
from app.models.mfa import Organization
from app.models.project import Project, ProjectStatus, ProjectType
from app.models.user import UserOrganizationMembership
from tests.conftest import _TEST_PASSWORD

PM = "pm@contecflow.com"


@pytest.fixture
def dos_empresas(db):
    """El PM pertenece a la 1 (su ficha) y a la B (pertenencia). Un proyecto en cada una."""
    if not db.get(Organization, "1"):
        db.add(Organization(id="1", name="Empresa Uno", slug="uno"))
    db.add(Organization(id="org-b", name="Empresa B", slug="empresa-b"))
    db.flush()
    db.add(UserOrganizationMembership(user_id="pm-test-id", organization_id="org-b"))
    for org, code in (("1", "UNO1"), ("org-b", "BEE1")):
        db.add(Project(code=code, name=f"Proyecto {code}", status=ProjectStatus.active, pm_id="pm-test-id",
                       project_type=ProjectType.development, organization_id=org))
    db.commit()


@pytest.fixture
def modo(monkeypatch):
    def poner(valor, raiz=""):
        monkeypatch.setattr(settings, "TENANT_ENTRY_MODE", valor)
        monkeypatch.setattr(settings, "TENANT_ROOT_DOMAIN", raiz)
    return poner


def _entrar(client, **extra):
    client.cookies.clear()
    return client.post("/api/v1/auth/login", json={"username": PM, "password": _TEST_PASSWORD, **extra})


def _proyectos(client, **kw):
    r = client.get("/api/v1/projects", **kw)
    assert r.status_code == 200, r.text
    datos = r.json()
    filas = datos.get("items") or datos.get("data") or []
    return sorted(p["code"] for p in filas)


# ── Correo + selector (por defecto) ──────────────────────────────────────────

def test_con_una_sola_empresa_se_entra_directo(client, db, modo):
    modo("email_selector")
    r = _entrar(client)
    assert r.status_code == 200 and not r.json()["organization_selection_required"]
    assert client.cookies.get("access_token")


def test_EL_HALLAZGO_con_varias_empresas_se_elige_y_se_ve_solo_la_elegida(client, db, dos_empresas, modo):
    modo("email_selector")
    r = _entrar(client)
    assert r.status_code == 200, r.text
    datos = r.json()
    assert datos["organization_selection_required"] is True
    assert not client.cookies.get("access_token"), "aún no hay sesión"
    assert sorted(o["id"] for o in datos["organizations"]) == ["1", "org-b"]
    r = client.post("/api/v1/auth/select-organization",
                    json={"selection_token": datos["selection_token"], "organization_id": "org-b"})
    assert r.status_code == 200, r.text
    assert _proyectos(client) == ["BEE1"]
    # Cambiar de empresa en la sesión
    r = client.post("/api/v1/auth/switch-organization", json={"organization_id": "1"})
    assert r.status_code == 200, r.text
    assert _proyectos(client) == ["UNO1"]
    assert client.get("/api/v1/auth/organizations").json()["current"] == "1"


def test_no_se_elige_una_empresa_ajena(client, db, dos_empresas, modo):
    modo("email_selector")
    token = _entrar(client).json()["selection_token"]
    db.add(Organization(id="org-c", name="C", slug="c"))
    db.commit()
    r = client.post("/api/v1/auth/select-organization", json={"selection_token": token, "organization_id": "org-c"})
    assert r.status_code == 401


def test_quitar_la_pertenencia_corta_el_acceso_a_esa_empresa(client, db, dos_empresas, modo):
    modo("email_selector")
    token = _entrar(client).json()["selection_token"]
    client.post("/api/v1/auth/select-organization", json={"selection_token": token, "organization_id": "org-b"})
    assert _proyectos(client) == ["BEE1"]
    db.query(UserOrganizationMembership).filter(UserOrganizationMembership.organization_id == "org-b").delete()
    db.commit()
    assert _proyectos(client) == ["UNO1"], "vuelve a la empresa de su ficha"


def test_el_refresco_conserva_la_empresa(client, db, dos_empresas, modo):
    modo("email_selector")
    token = _entrar(client).json()["selection_token"]
    client.post("/api/v1/auth/select-organization", json={"selection_token": token, "organization_id": "org-b"})
    assert client.post("/api/v1/auth/refresh").status_code == 200
    assert _proyectos(client) == ["BEE1"]


def test_una_empresa_desactivada_no_aparece_en_el_selector(client, db, dos_empresas, modo):
    modo("email_selector")
    db.query(Organization).filter(Organization.id == "org-b").update({"is_active": False})
    db.commit()
    r = _entrar(client)
    assert r.status_code == 200 and not r.json()["organization_selection_required"]
    assert _proyectos(client) == ["UNO1"]


# ── Campo empresa en el login ────────────────────────────────────────────────

def test_modo_campo_empresa(client, db, dos_empresas, modo):
    modo("org_field")
    assert client.get("/api/v1/auth/entry-config").json()["mode"] == "org_field"
    assert _entrar(client).status_code == 401, "sin código de empresa no se entra"
    db.add(Organization(id="org-c", name="C", slug="c"))
    db.commit()
    malo = _entrar(client, organization="c")
    assert malo.status_code == 401 and "Credenciales" in malo.text, "misma respuesta que una contraseña mala"
    assert _entrar(client, organization="empresa-b").status_code == 200
    assert _proyectos(client) == ["BEE1"]
    assert client.post("/api/v1/auth/switch-organization", json={"organization_id": "1"}).status_code == 409


# ── Subdominio ───────────────────────────────────────────────────────────────

def test_modo_subdominio(client, db, dos_empresas, modo):
    modo("subdomain", raiz="contecflow.test")
    host_b = {"host": "empresa-b.contecflow.test"}
    cfg = client.get("/api/v1/auth/entry-config", headers=host_b).json()
    assert cfg["mode"] == "subdomain" and cfg["organization"]["slug"] == "empresa-b"
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"username": PM, "password": _TEST_PASSWORD}, headers=host_b)
    assert r.status_code == 200 and not r.json()["organization_selection_required"], r.text
    assert _proyectos(client, headers=host_b) == ["BEE1"]
    # La misma sesión en el host de otra empresa no vale.
    slug_uno = db.get(Organization, "1").slug
    assert client.get("/api/v1/projects", headers={"host": f"{slug_uno}.contecflow.test"}).status_code == 403
    # Quien no es miembro de la empresa del host no entra.
    db.add(Organization(id="org-c", name="C", slug="c"))
    db.commit()
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"username": PM, "password": _TEST_PASSWORD},
                    headers={"host": "c.contecflow.test"})
    assert r.status_code == 401


def test_dominio_propio(client, db, dos_empresas, modo):
    modo("subdomain", raiz="contecflow.test")
    db.query(Organization).filter(Organization.id == "org-b").update({"domain": "app.empresa-b.com"})
    db.commit()
    client.cookies.clear()
    r = client.post("/api/v1/auth/login", json={"username": PM, "password": _TEST_PASSWORD},
                    headers={"host": "app.empresa-b.com"})
    assert r.status_code == 200, r.text
    assert _proyectos(client, headers={"host": "app.empresa-b.com"}) == ["BEE1"]
