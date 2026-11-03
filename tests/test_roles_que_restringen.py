"""El acceso por modulo de los roles se aplica, y un rol personalizado se asigna.

Auditoria 2026-11. `custom_roles.module_access` se editaba y nadie lo leia; no
habia forma de dar un rol personalizado a nadie; el PATCH de un rol descartaba
`module_access`; y la segunda organizacion que abria Ajustes > Roles chocaba
con el nombre unico global al sembrar los roles de sistema.
"""
from __future__ import annotations

import json

from app.models.advanced_config import CustomRole
from app.models.user import User, UserRole, UserStatus
from tests.conftest import auth

ORG = "1"


def _rol(db, name, acceso, sistema=False, org=ORG):
    r = CustomRole(name=name, organization_id=org, is_system=sistema, is_active=True,
                   module_access=json.dumps(acceso))
    db.add(r)
    db.commit()
    return r


def test_EL_HALLAZGO_el_modulo_cerrado_del_rol_base_se_aplica(client, dev_token, db):
    _rol(db, "employee", {"projects": False, "tasks": True}, sistema=True)
    assert client.get("/api/v1/projects", headers=auth(dev_token)).status_code == 403
    assert client.get("/api/v1/tasks", headers=auth(dev_token)).status_code == 200
    me = client.get("/api/v1/auth/me", headers=auth(dev_token)).json()
    assert "/projects" in me["blocked_routes"]
    assert "/tasks" not in me["blocked_routes"]


def test_el_admin_no_se_cierra_nunca(client, admin_token, db):
    _rol(db, "admin", {"projects": False, "settings": False}, sistema=True)
    assert client.get("/api/v1/projects", headers=auth(admin_token)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(admin_token)).json()["blocked_routes"] == []


def test_EL_HALLAZGO_un_rol_personalizado_se_asigna_y_manda(client, admin_token, pm_token, db):
    rol = _rol(db, "Comercial", {"projects": False})
    r = client.patch("/api/v1/users/pm-test-id", json={"custom_role_id": rol.id}, headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert client.get("/api/v1/projects", headers=auth(pm_token)).status_code == 403
    # Quitarlo devuelve al rol base.
    client.patch("/api/v1/users/pm-test-id", json={"custom_role_id": ""}, headers=auth(admin_token))
    assert client.get("/api/v1/projects", headers=auth(pm_token)).status_code == 200


def test_un_rol_de_otra_organizacion_no_se_asigna(client, admin_token, db):
    ajeno = _rol(db, "Ajeno", {"projects": False}, org="org-ajena")
    r = client.patch("/api/v1/users/pm-test-id", json={"custom_role_id": ajeno.id}, headers=auth(admin_token))
    assert r.status_code == 422


def test_un_rol_base_inventado_no_se_guarda(client, admin_token, db):
    r = client.patch("/api/v1/users/pm-test-id", json={"role": "Comercial"}, headers=auth(admin_token))
    assert r.status_code == 422


def test_EL_HALLAZGO_editar_los_modulos_de_un_rol_se_guarda(client, admin_token, db):
    rol = _rol(db, "Soporte", {"projects": True})
    r = client.patch(f"/api/v1/advanced-config/roles/{rol.id}", headers=auth(admin_token),
                     json={"module_access": {"projects": False}})
    assert r.status_code == 200, r.text
    db.refresh(rol)
    assert json.loads(rol.module_access) == {"projects": False}


def test_un_modulo_inventado_no_se_guarda(client, admin_token, db):
    r = client.post("/api/v1/advanced-config/roles", headers=auth(admin_token),
                    json={"name": "Raro", "module_access": {"nave_espacial": False}})
    assert r.status_code == 422


def test_EL_HALLAZGO_dos_organizaciones_siembran_sus_roles_sin_chocar(client, admin_token, db):
    assert client.get("/api/v1/advanced-config/roles", headers=auth(admin_token)).status_code == 200
    otro = User(id="adm-2", username="adm2", email="a2@x.test", full_name="Admin 2", role=UserRole.admin,
                status=UserStatus.active, is_active=True, organization_id="org-2",
                hashed_password=db.query(User).filter(User.id == "admin-test-id").one().hashed_password)
    db.add(otro)
    db.commit()
    from app.services.advanced_config_service import seed_system_roles
    seed_system_roles(db, "org-2")
    nombres = {(o, n) for o, n in db.query(CustomRole.organization_id, CustomRole.name)}
    assert (ORG, "admin") in nombres and ("org-2", "admin") in nombres


def test_con_ajustes_cerrados_la_aplicacion_sigue_arrancando(client, dev_token, db):
    _rol(db, "employee", {"settings": False}, sistema=True)
    assert client.get("/api/v1/settings/org-defaults", headers=auth(dev_token)).status_code == 200
    assert client.get("/api/v1/advanced-config/roles", headers=auth(dev_token)).status_code == 403
