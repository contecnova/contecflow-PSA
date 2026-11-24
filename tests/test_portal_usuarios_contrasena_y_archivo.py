"""Usuarios del portal: contraseña puesta a mano, eliminar o archivar y restaurar (23-11-2026).

Migración `205_portal_usuarios` (`client_users.archived_at`/`archived_by`);
servicio `app/services/client_portal_service/usuarios.py`; documentado en
docs/seguridad/politicas_de_cuenta.md §«Portal de clientes: contraseña a mano,
eliminar y archivar».

- La contraseña a mano pasa la política de la empresa, no vuelve en la
  respuesta y no queda en la auditoría (que sí guarda quién, a quién, si obliga
  a cambiarla y si se envió).
- «Eliminar»: sin historial borra; con historial archiva (no entra, fuera de la
  lista por defecto, historial conservado) y se puede restaurar.
- Aislamiento por empresa y capacidad `clientes.gestionar`.
"""
from __future__ import annotations

import json

from app.models.client_portal import ClientMessage, ClientUser
from app.models.enterprise import AuditLog
from tests.conftest import auth

BASE = "/api/v1/portal"
CLAVE = "Zq7!vLm#2pXr9Tw"
OTRA = "Kw4$uNe8@rTy6Pb"


def _alta(client, token, email="pu@acme.example", **extra):
    datos = {"full_name": "Paula Usuaria", "email": email, "client_org_id": "cli-pu", **extra}
    r = client.post(f"{BASE}/clients", headers=auth(token), json=datos)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def _empresa_cliente(db):
    from app.models.clients import Client
    if db.get(Client, "cli-pu") is None:
        db.add(Client(id="cli-pu", name="Acme PU", organization_id="1", created_by="admin-test-id"))
        db.commit()


def _proyecto(db):
    from app.models.project import Project, ProjectStatus, ProjectType
    if db.get(Project, "prj-pu") is None:
        db.add(Project(id="prj-pu", organization_id="1", code="PRJ-PU", name="Proyecto PU",
                       project_type=ProjectType.consulting, status=ProjectStatus.active, created_by="admin-test-id"))
        db.commit()


def _login(client, email, clave):
    return client.post(f"{BASE}/auth/login", json={"email": email, "password": clave})


def _auditoria(db, client_id):
    return db.query(AuditLog).filter(AuditLog.resource_id == client_id).all()


# ── Contraseña a mano ────────────────────────────────────────────────────────

def test_la_contrasena_a_mano_pasa_la_politica(client, db, admin_token):
    _empresa_cliente(db)
    u = _alta(client, admin_token)
    r = client.post(f"{BASE}/clients/{u['id']}/set-password", headers=auth(admin_token), json={"password": "Ab1!"})
    assert r.status_code == 400 and r.json().get("code") == "contrasena_min_caracteres", r.text
    assert client.post(f"{BASE}/clients/{u['id']}/set-password", headers=auth(admin_token),
                       json={"password": CLAVE}).status_code == 200
    r = client.post(f"{BASE}/clients/{u['id']}/set-password", headers=auth(admin_token), json={"password": CLAVE})
    assert r.status_code == 400 and r.json().get("code") == "portal_usuario_contrasena_igual_a_la_actual", r.text


def test_la_contrasena_a_mano_no_vuelve_ni_se_audita(client, db, admin_token):
    _empresa_cliente(db)
    u = _alta(client, admin_token)
    r = client.post(f"{BASE}/clients/{u['id']}/set-password", headers=auth(admin_token),
                    json={"password": CLAVE, "must_change_password": True, "send_access": False})
    assert r.status_code == 200, r.text
    assert CLAVE not in r.text
    datos = r.json()["data"]
    assert datos["must_change_password"] is True and datos["credenciales_enviadas"] is None
    entradas = [a for a in _auditoria(db, u["id"]) if a.action == "PORTAL_PASSWORD_SET"]
    assert len(entradas) == 1
    for a in _auditoria(db, u["id"]):
        for campo in (a.old_values, a.new_values, a.metadata_, a.resource_name):
            assert CLAVE not in (campo or "")
    meta = json.loads(entradas[0].metadata_)
    assert meta["must_change_password"] is True and meta["sent"] is False and meta["send_requested"] is False
    assert entradas[0].user_id == "admin-test-id"
    # Nunca en claro en la base de datos.
    fila = db.query(ClientUser).filter(ClientUser.id == u["id"]).first()
    db.refresh(fila)
    assert fila.hashed_password and CLAVE not in fila.hashed_password
    # Entra con ella y el portal le pide cambiarla.
    r = _login(client, "pu@acme.example", CLAVE)
    assert r.status_code == 200, r.text
    assert r.json()["data"]["client"]["must_change_password"] is True


def test_alta_con_contrasena_a_mano(client, db, admin_token):
    _empresa_cliente(db)
    r = client.post(f"{BASE}/clients", headers=auth(admin_token), json={
        "full_name": "Mano", "email": "mano@acme.example", "client_org_id": "cli-pu", "password": "abc"})
    assert r.status_code == 400 and r.json().get("code") == "contrasena_min_caracteres", r.text
    u = _alta(client, admin_token, email="mano@acme.example", password=CLAVE, must_change_password=False, send_access=False)
    assert u["credenciales_enviadas"] is None
    r = _login(client, "mano@acme.example", CLAVE)
    assert r.status_code == 200 and r.json()["data"]["client"]["must_change_password"] is False
    alta = [a for a in _auditoria(db, u["id"]) if a.action == "PORTAL_USER_CREATED"]
    assert alta and json.loads(alta[0].metadata_)["password_manual"] is True
    assert all(CLAVE not in (a.metadata_ or "") for a in alta)


def test_editar_ya_no_cambia_la_contrasena(client, db, admin_token):
    _empresa_cliente(db)
    u = _alta(client, admin_token)
    r = client.patch(f"{BASE}/clients/{u['id']}", headers=auth(admin_token), json={"password": CLAVE})
    assert r.status_code in (400, 404), r.text  # el endpoint convierte el ValueError del servicio
    assert r.json().get("code") == "portal_usuario_contrasena_solo_con_su_accion", r.text


# ── Eliminar, archivar y restaurar ───────────────────────────────────────────

def test_sin_historial_se_borra_de_verdad(client, db, admin_token):
    _empresa_cliente(db)
    u = _alta(client, admin_token)
    r = client.delete(f"{BASE}/clients/{u['id']}", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"]["resultado"] == "eliminado"
    db.expire_all()
    assert db.query(ClientUser).filter(ClientUser.id == u["id"]).first() is None
    # Su contacto sigue, sin enlace.
    from app.models.clients import ClientContact
    ct = db.query(ClientContact).filter(ClientContact.client_id == "cli-pu",
                                        ClientContact.email == "pu@acme.example").first()
    assert ct is not None and ct.portal_user_id is None
    assert any(a.action == "PORTAL_USER_DELETED" for a in _auditoria(db, u["id"]))


def test_con_historial_se_archiva_no_entra_y_se_restaura(client, db, admin_token):
    _empresa_cliente(db)
    _proyecto(db)
    u = _alta(client, admin_token, password=CLAVE, must_change_password=False)
    db.add(ClientMessage(organization_id="1", project_id="prj-pu", body="Hola", sender_client_id=u["id"]))
    db.commit()
    assert _login(client, "pu@acme.example", CLAVE).status_code == 200

    r = client.delete(f"{BASE}/clients/{u['id']}", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["resultado"] == "archivado"
    assert datos["historial"].get("client_messages.sender_client_id") == 1
    db.expire_all()
    fila = db.query(ClientUser).filter(ClientUser.id == u["id"]).first()
    assert fila is not None and fila.archived_at is not None and fila.is_active is False
    assert fila.archived_by == "admin-test-id"
    # El historial se conserva con su autor.
    assert db.query(ClientMessage).filter(ClientMessage.sender_client_id == u["id"]).count() == 1
    # No entra.
    assert _login(client, "pu@acme.example", CLAVE).status_code == 401
    # Fuera de la lista por defecto; dentro con «Ver archivados».
    # La lista es paginada (`lista_paginada`): las filas vienen en `items`, no en `data`.
    ids = [x["id"] for x in client.get(f"{BASE}/clients", headers=auth(admin_token),
                                       params={"client_org_id": "cli-pu"}).json()["items"]]
    assert u["id"] not in ids
    lista = client.get(f"{BASE}/clients", headers=auth(admin_token),
                       params={"client_org_id": "cli-pu", "include_archived": "true"}).json()["items"]
    assert [x["archived_at"] for x in lista if x["id"] == u["id"]][0]
    # Ni «Reactivar», ni contraseña, ni reenviar mientras esté archivado.
    assert client.patch(f"{BASE}/clients/{u['id']}", headers=auth(admin_token),
                        json={"is_active": True}).json().get("code") == "portal_usuario_archivado"
    assert client.post(f"{BASE}/clients/{u['id']}/set-password", headers=auth(admin_token),
                       json={"password": OTRA}).status_code == 409
    assert any(a.action == "PORTAL_USER_ARCHIVED" for a in _auditoria(db, u["id"]))

    r = client.post(f"{BASE}/clients/{u['id']}/restore", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert _login(client, "pu@acme.example", CLAVE).status_code == 200
    r = client.post(f"{BASE}/clients/{u['id']}/restore", headers=auth(admin_token))
    assert r.status_code == 409 and r.json().get("code") == "portal_usuario_no_archivado"
    assert any(a.action == "PORTAL_USER_RESTORED" for a in _auditoria(db, u["id"]))


def test_el_criterio_de_historial_cubre_las_tablas_que_apuntan_al_usuario():
    from app.services.client_portal_service.usuarios import NO_SON_HISTORIAL, referencias_a_usuarios_del_portal
    tablas = {t for t, _ in referencias_a_usuarios_del_portal()}
    # La lista de lo que NO es historial no nombra tablas que no existen.
    assert NO_SON_HISTORIAL <= tablas, NO_SON_HISTORIAL - tablas
    # Lo que sí es historial incluye lo esencial del portal.
    for t in ("client_messages", "feature_requests", "client_surveys"):
        assert t in tablas and t not in NO_SON_HISTORIAL


# ── Aislamiento y capacidad ──────────────────────────────────────────────────

def test_otra_empresa_no_toca_sus_usuarios(client, db, admin_token):
    from app.models.mfa import Organization
    if db.get(Organization, "org-pu-b") is None:
        db.add(Organization(id="org-pu-b", name="B", slug="org-pu-b", is_active=True))
    db.add(ClientUser(id="cu-org-b", organization_id="org-pu-b", full_name="Ajena", email="ajena@b.example",
                      is_active=True))
    db.commit()
    for metodo, ruta, cuerpo in (("POST", "/set-password", {"password": CLAVE}), ("DELETE", "", None),
                                 ("POST", "/restore", None)):
        r = client.request(metodo, f"{BASE}/clients/cu-org-b{ruta}", headers=auth(admin_token), json=cuerpo)
        assert r.status_code == 404, (metodo, ruta, r.status_code, r.text)
    db.expire_all()
    assert db.query(ClientUser).filter(ClientUser.id == "cu-org-b").first() is not None


def test_sin_clientes_gestionar_no_hay_acciones(client, db, admin_token, dev_token):
    _empresa_cliente(db)
    u = _alta(client, admin_token)
    for metodo, ruta, cuerpo in (("POST", "/set-password", {"password": CLAVE}), ("DELETE", "", None),
                                 ("POST", "/restore", None)):
        r = client.request(metodo, f"{BASE}/clients/{u['id']}{ruta}", headers=auth(dev_token), json=cuerpo)
        assert r.status_code == 403, (metodo, ruta, r.status_code)
