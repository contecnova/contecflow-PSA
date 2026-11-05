"""Explicador de accesos (revisión 2026-11): qué capa decide y que diga lo que de verdad pasa.

Cada caso monta una restricción en una capa, pregunta al explicador y hace la
petición real con el mismo usuario: si el explicador dice «deniega la capa X»,
la API tiene que contestar 403 con el motivo de esa capa.
"""
from __future__ import annotations

import json

import pytest

from app.models.advanced_config import CustomRole
from app.models.enterprise import ProjectPermission, ProjectPermissionLevel
from app.models.mfa import Organization
from app.models.project import Project, ProjectType
from app.models.user import User
from app.services import grc_service
from tests.conftest import auth

URL = "/api/v1/grc/access-explainer"


def _usuario(db, username):
    return db.query(User).filter(User.username == username).first()


def _explicar(client, token, user, metodo, camino):
    r = client.get(URL, params={"user_id": user.id, "method": metodo, "path": camino}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _capa(resultado, id_):
    return next(c for c in resultado["layers"] if c["layer"] == id_)


def test_el_rol_del_endpoint_deniega_y_la_api_tambien(client, db, admin_token, dev_token):
    dev = _usuario(db, "dev_test")
    r = _explicar(client, admin_token, dev, "GET", "/api/v1/settings/setup-checklist")
    assert r["verdict"] == "deny" and r["decided_by"] == "role"
    assert _capa(r, "role")["required"] == ["admin"] and _capa(r, "role")["role"] == "employee"
    assert client.get("/api/v1/settings/setup-checklist", headers=auth(dev_token)).status_code == 403


def test_EL_HALLAZGO_la_matriz_grc_de_la_empresa_deniega(client, db, admin_token, pm_token):
    pm = _usuario(db, "pm_test")
    grc_service.upsert_permission(db, "pm", "projects", "crear", False, None, pm.organization_id)
    db.commit()
    r = _explicar(client, admin_token, pm, "POST", "/api/v1/projects")
    assert r["decided_by"] == "grc"
    assert {k: _capa(r, "grc")[k] for k in ("module", "action", "role", "company_row")} == \
        {"module": "projects", "action": "crear", "role": "pm", "company_row": True}
    real = client.post("/api/v1/projects", json={"name": "X"}, headers=auth(pm_token))
    assert real.status_code == 403 and "gobierno" in real.json()["detail"]


def test_un_modulo_cerrado_en_el_rol(client, db, admin_token, dev_token):
    dev = _usuario(db, "dev_test")
    rol = CustomRole(name="Sin partes", organization_id=dev.organization_id, is_active=True,
                     module_access=json.dumps({"timesheets": False}))
    db.add(rol)
    db.flush()
    dev.custom_role_id = rol.id
    db.commit()
    r = _explicar(client, admin_token, dev, "GET", "/api/v1/timesheets/my")
    assert r["decided_by"] == "modules" and _capa(r, "modules")["module"] == "timesheets"
    real = client.get("/api/v1/timesheets/my", headers=auth(dev_token))
    assert real.status_code == 403 and "timesheets" in real.json()["detail"]


def test_un_permiso_de_proyecto_de_solo_lectura(client, db, admin_token, pm_token):
    pm = _usuario(db, "pm_test")
    db.add(Project(id="p-expl", name="P", code="PEXPL", project_type=ProjectType.development,
                   organization_id=pm.organization_id))
    db.add(ProjectPermission(project_id="p-expl", user_id=pm.id, level=ProjectPermissionLevel.viewer,
                             organization_id=pm.organization_id))
    db.commit()
    r = _explicar(client, admin_token, pm, "PATCH", "/api/v1/projects/p-expl")
    capa = _capa(r, "project")
    assert r["decided_by"] == "project" and capa["level"] == "viewer" and capa["project_id"] == "p-expl"
    real = client.patch("/api/v1/projects/p-expl", json={"name": "Y"}, headers=auth(pm_token))
    assert real.status_code == 403 and "lectura" in real.json()["detail"]
    # Leer sí puede: la misma capa lo deja pasar.
    assert _capa(_explicar(client, admin_token, pm, "GET", "/api/v1/projects/p-expl"), "project")["verdict"] == "allow"


def test_permitido_dice_que_lo_de_dentro_del_servicio_no_se_ve(client, db, admin_token):
    admin = _usuario(db, "admin")
    r = _explicar(client, admin_token, admin, "GET", "projects")     # sin /api/v1: se completa
    assert r["verdict"] == "allow" and r["decided_by"] is None and r["template"] == "/api/v1/projects"
    assert _capa(r, "service")["verdict"] == "unknown"
    assert [c["layer"] for c in r["layers"]] == ["route", "abac", "grc", "account", "modules", "project", "role",
                                                 "service", "tenant"]


@pytest.mark.parametrize("metodo,camino,motivo", [
    ("GET", "/api/v1/no-existe", "not_found"),
    ("DELETE", "/api/v1/settings/setup-checklist", "method_not_allowed"),
])
def test_ruta_que_no_existe_o_metodo_equivocado(client, db, admin_token, metodo, camino, motivo):
    r = _explicar(client, admin_token, _usuario(db, "admin"), metodo, camino)
    assert r["decided_by"] == "route" and r["layers"][0]["detail"] == motivo


def test_solo_admin_y_solo_gente_de_su_empresa(client, db, admin_token, pm_token):
    db.add(Organization(id="org-expl", name="Otra", slug="org-expl"))
    db.add(User(id="u-ajeno", username="ajeno", email="ajeno@x.com", full_name="Ajeno", hashed_password="x",
                organization_id="org-expl"))
    db.commit()
    ajeno = db.get(User, "u-ajeno")
    assert client.get(URL, params={"user_id": ajeno.id, "path": "/api/v1/projects"},
                      headers=auth(admin_token)).status_code == 404
    assert client.get(URL, params={"user_id": _usuario(db, "pm_test").id, "path": "/api/v1/projects"},
                      headers=auth(pm_token)).status_code == 403
    rutas = client.get(URL + "/routes", headers=auth(admin_token)).json()["data"]
    assert {"method": "GET", "path": "/api/v1/projects"} in rutas and len(rutas) > 1000


@pytest.mark.parametrize("usuario,token", [("dev_test", "dev_token"), ("admin", "admin_token")])
def test_el_explicador_dice_lo_que_hace_la_api(client, db, request, usuario, token):
    """Barrido de todas las GET sin parámetros, en los dos sentidos: lo que niega,
    la API lo rechaza (403; 401 en las del portal, que no aceptan usuarios
    internos), y lo que da por permitido, la API no lo rechaza con 403. Lo que no
    sabe evaluar queda en «unknown», nunca en «allow». Dice cuántas miró."""
    from app.main import app
    from app.services.explicar_acceso import explicar, rutas
    u, tok = _usuario(db, usuario), request.getfixturevalue(token)
    candidatas = [r["path"] for r in rutas(app) if r["method"] == "GET" and "{" not in r["path"]
                  and "/stream" not in r["path"] and "/export" not in r["path"]]
    veredictos = {c: explicar(db, app, u, "GET", c)["verdict"] for c in candidatas}
    assert len(candidatas) > 500
    assert sum(v == "allow" for v in veredictos.values()) > 300
    estado = {c: client.get(c, headers=auth(tok)).status_code for c in candidatas}
    assert [c for c, v in veredictos.items() if v == "deny" and estado[c] not in (401, 403)] == []
    assert [c for c, v in veredictos.items() if v == "allow" and estado[c] == 403] == []
