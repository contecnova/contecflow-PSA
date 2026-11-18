"""Contacto principal ↔ contactos ↔ usuarios del portal, empresa vs. persona y GRC (18-11-2026).

- La ficha del cliente refleja (`contact_*`) al contacto `is_primary`, que es la fuente.
- Los datos de la empresa (`phone`, `email`) son suyos, no del contacto.
- Cada usuario del portal es un contacto del cliente.
- Contactos: auditoría, RGPD (copia y supresión), bloqueo legal, retención y mínimo privilegio.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.models.client_portal import ClientUser
from app.models.clients import Client, ClientContact
from app.models.enterprise import AuditLog
from tests.conftest import auth

URL = "/api/v1/clients"


def _alta(client, token, **extra):
    datos = {"name": "Cliente Correlacionado SL", "industry": "technology", **extra}
    r = client.post(URL, json=datos, headers=auth(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]


def _contactos(client, token, cid):
    r = client.get(f"{URL}/{cid}/contacts", headers=auth(token))
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    return cuerpo["items"] if "items" in cuerpo else cuerpo["data"]


def _ficha(client, token, cid):
    return client.get(f"{URL}/{cid}", headers=auth(token)).json()["data"]


def _principales(db, cid):
    db.expire_all()
    return db.query(ClientContact).filter(ClientContact.client_id == cid, ClientContact.is_active == True,  # noqa: E712
                                          ClientContact.is_primary == True).all()  # noqa: E712


# ── Contacto principal ───────────────────────────────────────────────────────

def test_alta_con_contacto_nuevo_crea_el_contacto_principal(client, admin_token, db):
    c = _alta(client, admin_token, phone="+34 900 000 000", email="info@empresa.es",
              contact_name="Ana García", contact_email="ana@empresa.es", contact_phone="+34 600 1", contact_role="CTO")
    cts = _contactos(client, admin_token, c["id"])
    assert len(cts) == 1 and cts[0]["full_name"] == "Ana García" and cts[0]["is_primary"]
    assert cts[0]["phone"] == "+34 600 1" and cts[0]["job_title"] == "CTO"
    # Empresa y persona, separadas.
    f = _ficha(client, admin_token, c["id"])
    assert (f["phone"], f["email"]) == ("+34 900 000 000", "info@empresa.es")
    assert (f["contact_phone"], f["contact_email"]) == ("+34 600 1", "ana@empresa.es")
    assert f["primary_contact_id"] == cts[0]["id"]


def test_editar_la_ficha_con_el_email_de_un_contacto_existente_lo_reutiliza(client, admin_token, db):
    c = _alta(client, admin_token)
    otro = client.post(f"{URL}/{c['id']}/contacts", json={"full_name": "Luis", "email": "luis@x.es"},
                       headers=auth(admin_token)).json()["data"]
    r = client.patch(f"{URL}/{c['id']}", json={"contact_name": "Luis Pérez", "contact_email": "LUIS@x.es"},
                     headers=auth(admin_token))
    assert r.status_code == 200, r.text
    cts = _contactos(client, admin_token, c["id"])
    assert len(cts) == 1 and cts[0]["id"] == otro["id"] and cts[0]["is_primary"]
    assert cts[0]["full_name"] == "Luis Pérez"


def test_editar_la_ficha_cambia_el_principal_y_queda_uno(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Ana", contact_email="ana@a.es")
    r = client.patch(f"{URL}/{c['id']}", json={"contact_name": "Berta", "contact_email": "berta@a.es"},
                     headers=auth(admin_token))
    assert r.status_code == 200
    ps = _principales(db, c["id"])
    assert [p.email for p in ps] == ["berta@a.es"]
    assert len(_contactos(client, admin_token, c["id"])) == 2      # Ana sigue como contacto


def test_elegir_principal_existente_desde_la_ficha(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Ana", contact_email="ana@a.es")
    b = client.post(f"{URL}/{c['id']}/contacts", json={"full_name": "Berta", "email": "b@a.es"},
                    headers=auth(admin_token)).json()["data"]
    r = client.patch(f"{URL}/{c['id']}", json={"primary_contact_id": b["id"]}, headers=auth(admin_token))
    assert r.status_code == 200
    assert r.json()["data"]["contact_name"] == "Berta" and r.json()["data"]["primary_contact_id"] == b["id"]
    assert [p.id for p in _principales(db, c["id"])] == [b["id"]]


def test_marcar_principal_desde_el_contacto(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Ana", contact_email="ana@a.es")
    b = client.post(f"{URL}/{c['id']}/contacts", json={"full_name": "Berta", "email": "b@a.es", "phone": "7"},
                    headers=auth(admin_token)).json()["data"]
    r = client.post(f"{URL}/{c['id']}/contacts/{b['id']}/primary", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    f = _ficha(client, admin_token, c["id"])
    assert (f["contact_name"], f["contact_email"], f["contact_phone"]) == ("Berta", "b@a.es", "7")
    assert [p.id for p in _principales(db, c["id"])] == [b["id"]]
    # Y por PATCH del contacto (is_primary) también.
    ana = next(x for x in _contactos(client, admin_token, c["id"]) if x["full_name"] == "Ana")
    client.patch(f"{URL}/{c['id']}/contacts/{ana['id']}", json={"is_primary": True}, headers=auth(admin_token))
    assert [p.id for p in _principales(db, c["id"])] == [ana["id"]]
    assert _ficha(client, admin_token, c["id"])["contact_name"] == "Ana"


def test_editar_el_contacto_principal_actualiza_el_reflejo(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Ana", contact_email="ana@a.es")
    ct = _contactos(client, admin_token, c["id"])[0]
    r = client.patch(f"{URL}/{c['id']}/contacts/{ct['id']}",
                     json={"full_name": "Ana María", "phone": "+34 1", "job_title": "CEO", "notes": "n"},
                     headers=auth(admin_token))
    assert r.status_code == 200, r.text
    f = _ficha(client, admin_token, c["id"])
    assert (f["contact_name"], f["contact_phone"], f["contact_role"]) == ("Ana María", "+34 1", "CEO")
    assert f["phone"] is None                                          # la empresa no hereda el teléfono


def test_borrar_el_principal_vacia_la_ficha(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Ana", contact_email="ana@a.es")
    ct = _contactos(client, admin_token, c["id"])[0]
    assert client.delete(f"{URL}/{c['id']}/contacts/{ct['id']}", headers=auth(admin_token)).status_code == 200
    f = _ficha(client, admin_token, c["id"])
    assert f["contact_name"] is None and f["contact_email"] is None and f["primary_contact_id"] is None
    db.expire_all()
    assert db.get(ClientContact, ct["id"]).deactivated_at is not None


def test_marcar_principal_en_cliente_de_otra_empresa_da_404(client, admin_token, db):
    from app.models.mfa import Organization
    from app.models.user import User, UserRole, UserStatus
    if not db.get(Organization, "org-ajena-ctc"):
        db.add(Organization(id="org-ajena-ctc", name="Ajena", slug="ajena-ctc"))
        db.flush()
    db.add(User(id="ajeno-ctc", username="ajeno_ctc", email="ajeno@ctc.es", full_name="Ajeno",
                role=UserRole.admin, status=UserStatus.active, is_active=True, organization_id="org-ajena-ctc",
                hashed_password="x"))
    cli = Client(name="Ajeno SA", organization_id="org-ajena-ctc", created_by="ajeno-ctc")
    db.add(cli)
    db.flush()
    ct = ClientContact(client_id=cli.id, organization_id="org-ajena-ctc", full_name="Zoe")
    db.add(ct)
    db.commit()
    r = client.post(f"{URL}/{cli.id}/contacts/{ct.id}/primary", headers=auth(admin_token))
    assert r.status_code == 404


# ── Usuarios del portal ↔ contactos ──────────────────────────────────────────

def _usuario_del_portal(client, token, cid, email="portal@a.es", nombre="Pepa Portal"):
    r = client.post("/api/v1/portal/clients", headers=auth(token), json={
        "client_org_id": cid, "full_name": nombre, "email": email, "password": "Secreta-123", "phone": "+34 5"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_crear_usuario_del_portal_crea_o_reutiliza_su_contacto(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Ana", contact_email="ana@a.es")
    u = _usuario_del_portal(client, admin_token, c["id"])               # nuevo
    _usuario_del_portal(client, admin_token, c["id"], email="ANA@a.es", nombre="Ana")   # reutiliza a Ana
    cts = {x["email"].lower(): x for x in _contactos(client, admin_token, c["id"])}
    assert set(cts) == {"ana@a.es", "portal@a.es"}
    assert cts["portal@a.es"]["portal_user_id"] == u["id"] and cts["portal@a.es"]["portal_active"] is True
    assert cts["ana@a.es"]["portal_user_id"] and cts["ana@a.es"]["is_primary"]


def test_editar_y_desactivar_el_usuario_del_portal_mantiene_su_contacto(client, admin_token, db):
    c = _alta(client, admin_token)
    u = _usuario_del_portal(client, admin_token, c["id"])
    client.patch(f"/api/v1/portal/clients/{u['id']}", headers=auth(admin_token),
                 json={"full_name": "Pepa Nueva", "email": "pepa@a.es"})
    client.patch(f"/api/v1/portal/clients/{u['id']}", headers=auth(admin_token), json={"is_active": False})
    [ct] = _contactos(client, admin_token, c["id"])
    assert (ct["full_name"], ct["email"]) == ("Pepa Nueva", "pepa@a.es")
    assert ct["portal_active"] is False                               # sigue, sin acceso


def test_dar_acceso_al_portal_desde_un_contacto(client, admin_token, db):
    c = _alta(client, admin_token)
    ct = client.post(f"{URL}/{c['id']}/contacts", json={"full_name": "Carla", "email": "carla@a.es"},
                     headers=auth(admin_token)).json()["data"]
    r = client.post(f"{URL}/{c['id']}/contacts/{ct['id']}/portal-access", json={"password": "Secreta-123"},
                    headers=auth(admin_token))
    assert r.status_code == 200, r.text
    db.expire_all()
    u = db.get(ClientUser, r.json()["data"]["id"])
    assert (u.email, u.full_name, u.client_org_id) == ("carla@a.es", "Carla", c["id"])
    assert db.get(ClientContact, ct["id"]).portal_user_id == u.id
    # Ya tiene acceso: 409. Y respeta el máximo de usuarios del portal.
    r = client.post(f"{URL}/{c['id']}/contacts/{ct['id']}/portal-access", json={"password": "Secreta-123"},
                    headers=auth(admin_token))
    assert r.status_code == 409
    from app.models.clients import ClientPortalConfig
    db.query(ClientPortalConfig).filter(ClientPortalConfig.client_id == c["id"]).update({"max_portal_users": 1})
    db.commit()
    otro = client.post(f"{URL}/{c['id']}/contacts", json={"full_name": "Dani", "email": "dani@a.es"},
                       headers=auth(admin_token)).json()["data"]
    r = client.post(f"{URL}/{c['id']}/contacts/{otro['id']}/portal-access", json={"password": "Secreta-123"},
                    headers=auth(admin_token))
    assert r.status_code == 400


# ── GRC ──────────────────────────────────────────────────────────────────────

def test_auditoria_de_contactos_con_antes_y_despues(client, admin_token, db):
    c = _alta(client, admin_token)
    ct = client.post(f"{URL}/{c['id']}/contacts", json={"full_name": "Eva", "email": "eva@a.es"},
                     headers=auth(admin_token)).json()["data"]
    client.patch(f"{URL}/{c['id']}/contacts/{ct['id']}", json={"phone": "+34 9"}, headers=auth(admin_token))
    client.post(f"{URL}/{c['id']}/contacts/{ct['id']}/primary", headers=auth(admin_token))
    client.delete(f"{URL}/{c['id']}/contacts/{ct['id']}", headers=auth(admin_token))
    filas = db.query(AuditLog).filter(AuditLog.resource == "client_contacts", AuditLog.resource_id == ct["id"]) \
        .order_by(AuditLog.created_at, AuditLog.id).all()
    acciones = [f.action for f in filas]
    assert acciones.count("CREATE") == 1 and acciones.count("UPDATE") == 2 and acciones.count("DEACTIVATE") == 1
    edicion = next(f for f in filas if f.action == "UPDATE" and "phone" in (f.new_values or ""))
    assert json.loads(edicion.new_values) == {"phone": "+34 9"} and json.loads(edicion.old_values) == {"phone": None}
    assert all(f.user_id == "admin-test-id" for f in filas)


def _solicitud(db, tipo, email):
    from app.models.cab import GDPRRequestType
    from app.models.user import User
    from app.services.cab_service.gdpr import create_gdpr_request, process_gdpr_request
    admin = db.query(User).filter(User.id == "admin-test-id").one()
    r = create_gdpr_request(SimpleNamespace(request_type=GDPRRequestType(tipo), subject_user_id=None,
                                            subject_email=email, notes=None), admin, db)
    return lambda: process_gdpr_request(r["id"], admin, db)


def test_rgpd_acceso_incluye_contacto_y_usuario_del_portal(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Fe", contact_email="fe@a.es")
    _usuario_del_portal(client, admin_token, c["id"], email="fe@a.es", nombre="Fe")
    datos = _solicitud(db, "access", "FE@a.es")()["data"]
    assert [x["full_name"] for x in datos["client_contacts"]] == ["Fe"]
    assert [x["email"] for x in datos["portal_users"]] == ["fe@a.es"]


def test_rgpd_supresion_anonimiza_y_la_ficha_deja_de_reflejarlo(client, admin_token, db):
    c = _alta(client, admin_token, contact_name="Gil", contact_email="gil@a.es", contact_phone="1")
    ct_id = _contactos(client, admin_token, c["id"])[0]["id"]
    _solicitud(db, "erasure", "gil@a.es")()
    db.expire_all()
    ct = db.get(ClientContact, ct_id)
    assert ct is not None and ct.full_name == "[ERASED]" and ct.email is None and ct.phone is None
    assert not ct.is_active and not ct.is_primary
    cli = db.get(Client, c["id"])
    assert cli.contact_name is None and cli.contact_email is None and cli.name == "Cliente Correlacionado SL"


def test_rgpd_supresion_respeta_el_bloqueo_legal(client, admin_token, db):
    from app.core.errores import ErrorDeDominio
    from app.models.governance import LegalHold
    c = _alta(client, admin_token, contact_name="Hugo", contact_email="hugo@a.es")
    db.add(LegalHold(organization_id="1", case_reference="CASO-CTC", entity="client_contacts",
                     field="client_id", value=c["id"]))
    db.commit()
    procesar = _solicitud(db, "erasure", "hugo@a.es")
    with pytest.raises(ErrorDeDominio) as e:
        procesar()
    assert e.value.status_code == 409 and "CASO-CTC" in str(e.value.detail)
    db.expire_all()
    assert _contactos(client, admin_token, c["id"])[0]["email"] == "hugo@a.es"


def test_los_contactos_desactivados_son_un_tipo_retenible():
    from app.db.bloqueo_legal import TIPOS
    t = TIPOS["client_contacts"]
    assert t.modelo() is ClientContact and set(t.campos) == {"id", "client_id", "email"}


def test_el_externo_no_ve_los_datos_de_contacto():
    from app.services.politica_de_visibilidad import recortar_contacto_de_cliente, recortar_ficha_de_cliente
    externo = SimpleNamespace(role="subcontractor", is_superadmin=False)
    interno = SimpleNamespace(role="employee", is_superadmin=False)
    fila = {"id": "1", "full_name": "Ana", "email": "a@a.es", "phone": "1", "notes": "n"}
    assert recortar_contacto_de_cliente(externo, fila) == {"id": "1", "full_name": "Ana", "email": None,
                                                          "phone": None, "notes": None}
    assert recortar_contacto_de_cliente(interno, fila) == fila
    ficha = recortar_ficha_de_cliente(externo, {"contact_email": "a@a.es", "contact_phone": "1", "contacts": [fila]})
    assert ficha["contact_email"] is None and ficha["contacts"][0]["email"] is None


# ── Migración 183 ────────────────────────────────────────────────────────────

def _migracion():
    import importlib.util
    from pathlib import Path
    ruta = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "183_contacto_principal_correlacionado.py"
    spec = importlib.util.spec_from_file_location("m183", ruta)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_migracion_crea_el_principal_deja_uno_y_es_idempotente(db):
    m = _migracion()
    cli = Client(name="Legado SA", organization_id="1", contact_name="Iris", contact_email="iris@l.es")
    db.add(cli)
    db.flush()
    viejo = ClientContact(client_id=cli.id, organization_id="1", full_name="Otro", email="otro@l.es", is_primary=True)
    db.add(viejo)
    u = ClientUser(client_org_id=cli.id, organization_id="1", full_name="Juan", email="juan-ctc@l.es")
    db.add(u)
    db.commit()
    con = db.connection()
    r1 = m.correlacionar(con)
    n1 = m.enlazar_usuarios_del_portal(con)
    db.commit()
    assert r1["creados"] >= 1 and n1 >= 1
    db.expire_all()
    ps = _principales(db, cli.id)
    assert [p.email for p in ps] == ["iris@l.es"]
    assert db.query(ClientContact).filter(ClientContact.portal_user_id == u.id).count() == 1
    con = db.connection()
    assert m.correlacionar(con) == {"creados": 0, "cambiados": 0}
    assert m.enlazar_usuarios_del_portal(con) == 0
