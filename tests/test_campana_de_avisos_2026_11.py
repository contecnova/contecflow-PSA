"""Campana de avisos (16-11-2026): operadores y portal de clientes.

- `GET /enterprise/notifications/unread-count`: un COUNT de los avisos sin leer
  de quien llama, y de nadie más.
- Los títulos de los avisos se guardan sin emojis (en origen: validador de los
  modelos), y la lista trae `created_at_iso` para la hora relativa.
- Portal: `unread-count`, marcar uno (sólo los suyos: el de otro es un 404) y la
  lista con `payload` filtrado (sólo las claves de navegación).
- Los avisos de ticket que se mandan al cliente solicitante y los mensajes del
  equipo al proyecto quedan también en la campana del portal.
"""
from __future__ import annotations

import uuid

from app.models.collaboration import CollaborationNotification, NotificationKind
from app.models.enterprise import Notification
from tests.conftest import auth
from tests.test_portal_idiomas_restos_2026_11 import _cliente_del_portal, _entrar


def _aviso(db, user_id, titulo="Aviso", leido=False, activo=True):
    n = Notification(user_id=user_id, type="system", title=titulo, is_read=leido, is_active=activo)
    db.add(n)
    db.commit()
    return n


# ── Operadores ───────────────────────────────────────────────────────────────

def test_contador_solo_cuenta_los_avisos_sin_leer_de_quien_llama(client, admin_token, db):
    _aviso(db, "admin-test-id")
    _aviso(db, "admin-test-id")
    _aviso(db, "admin-test-id", leido=True)
    _aviso(db, "admin-test-id", activo=False)
    _aviso(db, "pm-test-id")  # de otra persona: no cuenta
    r = client.get("/api/v1/enterprise/notifications/unread-count", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"unread_count": 2}


def test_contador_coincide_con_el_de_la_lista_y_baja_al_marcar(client, admin_token, db):
    a = _aviso(db, "admin-test-id")
    _aviso(db, "admin-test-id")
    lista = client.get("/api/v1/enterprise/notifications", headers=auth(admin_token)).json()["data"]
    assert lista["unread_count"] == 2
    assert all(n["created_at_iso"] and "T" in n["created_at_iso"] for n in lista["notifications"])
    client.post(f"/api/v1/enterprise/notifications/{a.id}/read", headers=auth(admin_token))
    r = client.get("/api/v1/enterprise/notifications/unread-count", headers=auth(admin_token))
    assert r.json()["data"]["unread_count"] == 1


def test_contador_exige_sesion(client):
    assert client.get("/api/v1/enterprise/notifications/unread-count").status_code == 401


def test_los_titulos_de_aviso_se_guardan_sin_emojis(db):
    from app.services.notifications import notify_user
    n = notify_user(db, "admin-test-id", "system", "🎉 Contecflow v11 Enterprise activo ✅", "cuerpo")
    db.commit()
    assert n.title == "Contecflow v11 Enterprise activo"
    assert _aviso(db, "admin-test-id", "⚠️ SLA en riesgo").title == "SLA en riesgo"


def test_la_semilla_no_trae_emojis_en_los_titulos():
    from pathlib import Path
    from app.core.sin_emojis import sin_emojis
    fuente = Path("app/db/seed_parts/enterprise.py").read_text(encoding="utf-8")
    assert "Contecflow v11 Enterprise activo" in fuente
    assert sin_emojis("🎉 Hola") == "Hola" and sin_emojis(None) is None


# ── Portal de clientes ───────────────────────────────────────────────────────

def _aviso_cliente(db, cliente, titulo="Tu ticket tiene respuesta", payload=None, leido=False):
    n = CollaborationNotification(
        id=str(uuid.uuid4()), organization_id=cliente.organization_id or "1",
        client_user_id=cliente.id, kind=NotificationKind.system, title=titulo,
        payload=payload or {}, is_read=leido)
    db.add(n)
    db.commit()
    return n


def test_portal_contador_lista_y_marcar_solo_lo_del_cliente(client, admin_token, db):
    email, clave, cliente, _ = _cliente_del_portal(client, admin_token, db, code="PCA", idioma="es")
    _, _, otro, _ = _cliente_del_portal(client, admin_token, db, code="PCB", idioma="es")
    mio = _aviso_cliente(db, cliente, payload={"tipo": "ticket_replied", "seccion": "support",
                                                "ticket_id": "t-1", "interno": "no sale"})
    _aviso_cliente(db, cliente, leido=True)
    ajeno = _aviso_cliente(db, otro)
    _entrar(client, email, clave)

    r = client.get("/api/v1/portal/collaboration/notifications/unread-count")
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {"unread_count": 1}

    items = client.get("/api/v1/portal/collaboration/notifications", params={"limit": 5}).json()["items"]
    ids = {i["id"] for i in items}
    assert len(items) == 2 and mio.id in ids and ajeno.id not in ids
    del_mio = next(i for i in items if i["id"] == mio.id)
    assert del_mio["payload"] == {"tipo": "ticket_replied", "seccion": "support", "ticket_id": "t-1"}

    # El aviso de otro cliente no se puede marcar: 404 con código.
    r = client.post(f"/api/v1/portal/collaboration/notifications/{ajeno.id}/read")
    assert r.status_code == 404 and r.json()["code"] == "notificacion_no_encontrada"
    db.refresh(ajeno)
    assert ajeno.is_read is False

    assert client.post(f"/api/v1/portal/collaboration/notifications/{mio.id}/read").status_code == 200
    assert client.get("/api/v1/portal/collaboration/notifications/unread-count").json()["data"]["unread_count"] == 0


def test_portal_contador_exige_sesion_de_cliente(client, admin_token):
    # Un operador no es un cliente del portal.
    r = client.get("/api/v1/portal/collaboration/notifications/unread-count", headers=auth(admin_token))
    assert r.status_code in (401, 403)


def test_mensaje_del_equipo_avisa_a_los_clientes_del_proyecto(client, admin_token, db):
    email, clave, cliente, pid = _cliente_del_portal(client, admin_token, db, code="PCM", idioma="es")
    _, _, ajeno, _ = _cliente_del_portal(client, admin_token, db, code="PCN", idioma="es")
    r = client.post("/api/v1/portal/messages/team", headers=auth(admin_token), json={
        "project_id": pid, "subject": "Entrega del sprint", "body": "Ya está en preproducción."})
    assert r.status_code == 200, r.text
    avisos = db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == cliente.id).all()
    assert len(avisos) == 1
    assert avisos[0].title == "Entrega del sprint"
    assert avisos[0].payload == {"tipo": "mensaje_del_equipo", "seccion": "messages"}
    assert db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == ajeno.id).count() == 0

    # Una nota interna no avisa a nadie.
    client.post("/api/v1/portal/messages/team", headers=auth(admin_token), json={
        "project_id": pid, "body": "Nota interna", "is_internal": True})
    assert db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == cliente.id).count() == 1


def test_aviso_de_ticket_al_cliente_queda_en_su_campana(client, admin_token, db, monkeypatch):
    from app.models.client_portal import ClientUser
    from app.models.service_desk import Ticket
    from app.services.service_desk import correo
    from app.services.service_desk.ticket_event_processor import procesar_pendientes

    monkeypatch.setattr(correo, "enviar", lambda *a, **k: correo.ResultadoEnvio(True, message_id="<x@test>"))
    db.add(ClientUser(id="cli-campana", full_name="Lucia Cliente", email="lucia@cliente.com",
                      organization_id="1", is_active=True))
    db.commit()
    r = client.post("/api/v1/sd/tickets", headers=auth(admin_token), json={
        "title": "No imprime", "description": "Desde ayer", "ticket_type": "incident",
        "urgency": "medium", "impact": "user", "requester_name": "Lucia Cliente",
        "requester_email": "lucia@cliente.com"})
    assert r.status_code == 200, r.text
    tid = r.json()["data"]["id"]
    assert db.get(Ticket, tid).requester_client_id == "cli-campana"
    procesar_pendientes(db)

    avisos = db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == "cli-campana").all()
    assert len(avisos) == 1
    a = avisos[0]
    assert a.organization_id == "1"
    assert a.payload == {"tipo": "ticket_created", "seccion": "support", "ticket_id": tid}
    assert a.title and a.is_read is False
