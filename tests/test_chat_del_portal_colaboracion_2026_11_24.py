"""Pestaña «Chat» del portal sobre colaboración (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §9).

- «Solo el operador llama»: `POST /portal/collaboration/calls` siempre 403
  (auditado); el equipo llama con `clientes.llamar` y si la empresa lo permite;
  el cliente ve sonar, acepta (token propio), rechaza o cuelga.
- Sin grabación, asistente ni transcripción con clientes (409).
- Adjuntos del cliente: validación por contenido y por empresa; descarga solo
  por la API; el equipo sube con las mismas reglas si hay clientes.
- Editar/borrar el propio mensaje con rastro (`edited_by_client_id`,
  `change_type`), plazo; reacciones validadas; citas dentro de la conversación
  y visibles en la lista del cliente.
- RGPD (copia y supresión) y bloqueo legal.
"""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest

from tests.conftest import auth
# Mismos dobles (almacén en memoria, LiveKit de prueba) y ayudas que el chat formal.
from tests.test_chat_del_portal_2026_11_24 import (  # noqa: F401
    PDF, PNG, _ajuste, _codigo, _proyecto, almacen, anyio_backend, livekit,
)

# 24-11-2026: las rutas de LISTA del chat devuelven el sobre canónico de listas
# (`APIListResponse`: `{"items": [...], "meta": {...}}`, app/core/responses.py), como el
# resto de la API y como espera el frontend (desenvolverSobre); los objetos sueltos van en
# `{"data": ...}`. Los tests leían `data` también en las listas: ahora leen `items`.
P = "/api/v1/portal/collaboration"


def _escenario(client, token, db, code):
    """Usuario del portal con sesión y un grupo de colaboración con él y con el admin."""
    from app.models.client_portal import ClientUser
    from app.models.collaboration import (
        CollaborationConversation, CollaborationConversationMember, CollaborationGroupConversation,
        CollaborationWorkspace,
    )
    from app.models.user import User
    pid = _proyecto(client, token, code)
    email, clave = f"{code.lower()}@cliente-colab.com", "ClaveSegura123!"
    r = client.post("/api/v1/portal/clients", headers=auth(token), json={
        "project_ids": [pid], "full_name": "Cliente Colab", "email": email, "password": clave,
        "can_request_changes": True, "language": "es"})
    assert r.status_code in (200, 201), r.text
    cliente = db.query(ClientUser).filter(ClientUser.email == email).one()
    org = cliente.organization_id
    admin = db.query(User).filter(User.organization_id == org, User.role == "admin").first()
    ws = db.query(CollaborationWorkspace).filter(CollaborationWorkspace.organization_id == org).first()
    if ws is None:
        ws = CollaborationWorkspace(organization_id=org, name="Empresa")
        db.add(ws)
        db.flush()
    conv = CollaborationConversation(organization_id=org, kind="group", workspace_id=ws.id)
    db.add(conv)
    db.flush()
    grupo = CollaborationGroupConversation(organization_id=org, workspace_id=ws.id, conversation_id=conv.id,
                                           title="Soporte", created_by=admin.id)
    db.add(grupo)
    db.flush()
    db.add(CollaborationConversationMember(organization_id=org, conversation_id=conv.id, group_id=grupo.id,
                                           user_id=admin.id, is_admin=True))
    db.add(CollaborationConversationMember(organization_id=org, conversation_id=conv.id, group_id=grupo.id,
                                           client_user_id=cliente.id))
    db.commit()
    from app.services.collaboration._permissions import invalidate_membership
    invalidate_membership(admin.id)
    assert client.post("/api/v1/portal/auth/login", json={"email": email, "password": clave}).status_code == 200
    return SimpleNamespace(conv=conv.id, cliente=cliente, admin=admin, org=org)


def _mensaje(client, conv, texto="Hola equipo", parent=None):
    r = client.post(f"{P}/messages", json={"conversation_id": conv, "body": texto, "parent_message_id": parent})
    assert r.status_code == 200, r.text
    return r.json()["data"]


# ── Solo el operador llama ───────────────────────────────────────────────────

def test_el_cliente_nunca_inicia_y_queda_auditado(client, admin_token, db):
    from app.models.collaboration import CollaborationAuditEvent, CollaborationCall
    e = _escenario(client, admin_token, db, "CC1")
    for cuerpo in ({"conversation_id": e.conv, "kind": "video"}, {"conversation_id": e.conv}, None):
        r = client.post(f"{P}/calls", json=cuerpo) if cuerpo else client.post(f"{P}/calls")
        assert r.status_code == 403 and _codigo(r) == "portal_llamada_solo_operador"
    assert db.query(CollaborationCall).filter(CollaborationCall.conversation_id == e.conv).count() == 0
    assert db.query(CollaborationAuditEvent).filter(CollaborationAuditEvent.action == "call.start_denied").count() >= 2


def test_el_equipo_llama_y_el_cliente_acepta_rechaza_y_cuelga(client, admin_token, db, livekit):
    e = _escenario(client, admin_token, db, "CC2")
    r = client.post("/api/v1/collaboration/calls/start", headers=auth(admin_token), json={"conversation_id": e.conv, "kind": "video"})
    assert r.status_code == 200, r.text
    call_id = r.json()["data"]["call_id"]
    sonando = client.get(f"{P}/calls/ringing").json()["items"]
    assert [c["id"] for c in sonando] == [call_id] and sonando[0]["status"] == "ringing"
    r = client.post(f"{P}/calls/{call_id}/accept")
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert datos["livekit_token"] and datos["is_recorded"] is False
    # Ya no suena para él; cuelga.
    assert client.get(f"{P}/calls/ringing").json()["items"] == []
    assert client.post(f"{P}/calls/{call_id}/end").status_code == 200

    r = client.post("/api/v1/collaboration/calls/start", headers=auth(admin_token), json={"conversation_id": e.conv, "kind": "audio"})
    otra = r.json()["data"]["call_id"]
    assert client.post(f"{P}/calls/{otra}/decline").json()["data"]["status"] == "declined"
    r = client.post(f"{P}/calls/{otra}/accept")
    assert r.status_code == 409 and _codigo(r) == "portal_llamada_terminada"


def test_llamar_a_clientes_respeta_los_ajustes_de_la_empresa(client, admin_token, db, livekit):
    e = _escenario(client, admin_token, db, "CC3")
    _ajuste(db, e.org, "PORTAL_CHAT_VIDEO_ENABLED", "false")
    r = client.post("/api/v1/collaboration/calls/start", headers=auth(admin_token), json={"conversation_id": e.conv, "kind": "video"})
    assert r.status_code == 403 and _codigo(r) == "portal_videollamadas_desactivadas"
    _ajuste(db, e.org, "PORTAL_CHAT_CALLS_ENABLED", "false")
    r = client.post("/api/v1/collaboration/calls/start", headers=auth(admin_token), json={"conversation_id": e.conv, "kind": "audio"})
    assert r.status_code == 403 and _codigo(r) == "portal_llamadas_desactivadas"


def test_sin_capacidad_no_se_llama_a_clientes(db):
    from app.core.errores import ErrorDeDominio
    from app.services.collaboration import portal_chat
    usuario = SimpleNamespace(id="u", organization_id=None, is_superadmin=False)
    original = portal_chat.conversacion_con_clientes
    try:
        portal_chat.conversacion_con_clientes = lambda db, cid: True
        import app.core.capacidades as caps
        antes = caps.tiene
        caps.tiene = lambda db, user, cap: False
        try:
            with pytest.raises(ErrorDeDominio) as e:
                portal_chat.exigir_llamada_permitida(db, usuario, "c", "audio")
            assert e.value.code == "portal_llamada_sin_capacidad"
        finally:
            caps.tiene = antes
    finally:
        portal_chat.conversacion_con_clientes = original


def test_no_se_graba_con_clientes(client, admin_token, db, livekit):
    e = _escenario(client, admin_token, db, "CC4")
    call_id = client.post("/api/v1/collaboration/calls/start", headers=auth(admin_token),
                          json={"conversation_id": e.conv, "kind": "audio"}).json()["data"]["call_id"]
    from app.core.errores import ErrorDeDominio
    from app.services.collaboration import calls
    with pytest.raises(ErrorDeDominio) as err:
        calls.start_recording(db, e.admin, call_id)
    assert err.value.code == "portal_llamada_no_se_graba"


# ── Adjuntos ─────────────────────────────────────────────────────────────────

def test_el_cliente_sube_y_descarga_con_validacion(client, admin_token, db, almacen):
    e = _escenario(client, admin_token, db, "CA1")
    r = client.post(f"{P}/conversations/{e.conv}/attachments", files={"file": ("foto.png", PNG, "image/png")},
                    data={"caption": "Así se ve"})
    assert r.status_code == 200, r.text
    m = r.json()["data"]
    assert m["type"] == "file" and m["client_user_id"] == e.cliente.id
    (adjunto,) = m["attachments"]
    assert "download_url" not in adjunto
    r = client.get(f"{P}/attachments/{adjunto['id']}")
    assert r.status_code == 200 and r.content == PNG and r.headers["x-content-type-options"] == "nosniff"
    r = client.post(f"{P}/conversations/{e.conv}/attachments", files={"file": ("doc.pdf", PNG, "application/octet-stream")})
    assert r.status_code == 415 and _codigo(r) == "portal_adjunto_contenido_no_coincide"
    _ajuste(db, e.org, "PORTAL_CHAT_ATTACHMENTS_ENABLED", "false")
    r = client.post(f"{P}/conversations/{e.conv}/attachments", files={"file": ("ok.pdf", PDF, "application/pdf")})
    assert r.status_code == 403 and _codigo(r) == "portal_adjuntos_desactivados"


def test_el_equipo_sube_con_las_reglas_del_portal_si_hay_clientes(client, admin_token, db, almacen):
    e = _escenario(client, admin_token, db, "CA2")
    r = client.post("/api/v1/collaboration/attachments", headers=auth(admin_token),
                    data={"conversation_id": e.conv}, files={"file": ("logo.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 415 and _codigo(r) == "portal_adjunto_tipo_no_permitido"


def test_quien_no_participa_no_descarga(client, admin_token, db, almacen):
    from app.models.client_portal import ClientUser
    e = _escenario(client, admin_token, db, "CA3")
    m = client.post(f"{P}/conversations/{e.conv}/attachments", files={"file": ("a.pdf", PDF, "application/pdf")}).json()["data"]
    adjunto = m["attachments"][0]["id"]
    otro = "ca3-otro@cliente-colab.com"
    client.post("/api/v1/portal/clients", headers=auth(admin_token), json={
        "project_ids": [], "full_name": "Otra Persona", "email": otro, "password": "ClaveSegura123!",
        "can_request_changes": True, "language": "es"})
    if db.query(ClientUser).filter(ClientUser.email == otro).count():
        assert client.post("/api/v1/portal/auth/login", json={"email": otro, "password": "ClaveSegura123!"}).status_code == 200
        assert client.get(f"{P}/attachments/{adjunto}").status_code == 404


# ── Editar, borrar, reaccionar, citar ────────────────────────────────────────

def test_editar_y_borrar_dejan_rastro(client, admin_token, db, almacen):
    from app.models.collaboration import CollaborationMessageVersion
    e = _escenario(client, admin_token, db, "CE1")
    m = _mensaje(client, e.conv, "Primera version")
    r = client.put(f"{P}/messages/{m['id']}", json={"body": "Corregido"})
    assert r.status_code == 200 and r.json()["data"]["body"] == "Corregido" and r.json()["data"]["edited_at"]
    r = client.delete(f"{P}/messages/{m['id']}")
    assert r.status_code == 200 and r.json()["data"]["status"] == "deleted"
    versiones = db.query(CollaborationMessageVersion).filter(CollaborationMessageVersion.message_id == m["id"]).order_by(
        CollaborationMessageVersion.edited_at).all()
    assert [(v.change_type, v.body, v.edited_by_client_id) for v in versiones] == [
        ("edit", "Primera version", e.cliente.id), ("delete", "Corregido", e.cliente.id)]
    r = client.get(f"{P}/messages/{m['id']}/versions")
    assert r.status_code == 200 and len(r.json()["items"]) == 2


def test_no_se_toca_lo_ajeno_ni_fuera_de_plazo(client, admin_token, db):
    from app.models.collaboration import CollaborationMessage
    from app.services.collaboration import messages as svc
    e = _escenario(client, admin_token, db, "CE2")
    del_equipo = svc.send_message(db, e.admin, body="Respuesta", conversation_id=e.conv)
    r = client.put(f"{P}/messages/{del_equipo.id}", json={"body": "x"})
    assert r.status_code == 403 and _codigo(r) == "portal_mensaje_no_propio"
    m = _mensaje(client, e.conv)
    fila = db.get(CollaborationMessage, m["id"])
    fila.sent_at = fila.sent_at - timedelta(hours=5)
    db.commit()
    r = client.delete(f"{P}/messages/{m['id']}")
    assert r.status_code == 409 and _codigo(r) == "portal_mensaje_fuera_de_plazo"


def test_reacciones_validas_y_citas(client, admin_token, db):
    from app.services.collaboration import messages as svc
    e = _escenario(client, admin_token, db, "CR1")
    m = _mensaje(client, e.conv)
    assert client.post(f"{P}/messages/{m['id']}/reactions", json={"emoji": "👍"}).json()["data"]["added"] is True
    r = client.post(f"{P}/messages/{m['id']}/reactions", json={"emoji": "<b>"})
    assert r.status_code == 422 and _codigo(r) == "portal_reaccion_no_valida"
    # El equipo responde en hilo: el cliente lo ve en su lista, con la cita.
    respuesta = svc.send_message(db, e.admin, body="Te respondo", conversation_id=e.conv, parent_message_id=m["id"])
    lista = client.get(f"{P}/conversations/{e.conv}/messages").json()["items"]
    fila = next(x for x in lista if x["id"] == respuesta.id)
    assert fila["reply_to"]["id"] == m["id"]
    r = client.post(f"{P}/messages", json={"conversation_id": e.conv, "body": "x", "parent_message_id": "no-existe"})
    assert r.status_code == 422 and _codigo(r) == "portal_mensaje_citado_no_valido"


def test_leido_por_el_equipo_en_la_lista(client, admin_token, db):
    from app.services.collaboration import messages as svc
    e = _escenario(client, admin_token, db, "CL9")
    m = _mensaje(client, e.conv)
    svc.mark_read(db, e.admin, e.conv, m["id"])
    conv = next(c for c in client.get(f"{P}/conversations").json()["items"] if c["id"] == e.conv)
    assert conv["team_last_read_at"]


# ── Tiempo real ──────────────────────────────────────────────────────────────

def test_avisos_al_portal_sin_contenido():
    from app.services.collaboration.portal_chat import aviso_para_el_portal
    aviso = aviso_para_el_portal({"type": "message.created", "conversation_id": "c", "payload": {"body": "secreto"}}, "yo")
    assert aviso == {"type": "portal_collab", "event": "message.created", "conversation_id": "c", "call_id": None}
    assert aviso_para_el_portal({"type": "typing", "conversation_id": "c", "payload": {"client_user_id": "yo"}}, "yo") is None


@pytest.mark.anyio
async def test_el_socket_del_portal_solo_atiende_su_tipo():
    from app.services.collaboration import portal_chat
    llamadas = []

    async def en_sesion(fn, *a):
        llamadas.append(fn.__name__)
        return False

    assert await portal_chat.mensaje_del_portal(en_sesion, None, None, {"type": "otro"}) is False
    assert await portal_chat.mensaje_del_portal(en_sesion, None, SimpleNamespace(id="c"), {"type": "portal_collab_typing", "conversation_id": "x"}) is True
    assert llamadas == ["_participa"]


# ── RGPD ─────────────────────────────────────────────────────────────────────

def test_rgpd_copia_y_supresion(client, admin_token, db, almacen):
    from app.models.collaboration import CollaborationAttachment, CollaborationMessage
    from app.services.collaboration import portal_chat
    e = _escenario(client, admin_token, db, "CG1")
    _mensaje(client, e.conv, "Dato personal")
    client.post(f"{P}/conversations/{e.conv}/attachments", files={"file": ("dni.pdf", PDF, "application/pdf")})
    copia = portal_chat.copia_rgpd(db, [e.cliente.id], e.org)["portal_collaboration_chat"]
    assert any(m["body"] == "Dato personal" for m in copia["messages"]) and copia["attachments"]
    informe = portal_chat.suprimir_rgpd(db, [e.cliente.id], e.org)
    db.commit()
    assert informe["attachments"] >= 1
    assert db.query(CollaborationAttachment).filter(CollaborationAttachment.uploaded_by_client_id == e.cliente.id).count() == 0
    cuerpos = {m.body for m in db.query(CollaborationMessage).filter(CollaborationMessage.client_user_id == e.cliente.id)}
    assert cuerpos == {portal_chat.BORRADO}


def test_codigos_nuevos_en_los_idiomas():
    import pathlib
    from app.core import codigos_de_error as cde
    raiz = pathlib.Path(__file__).resolve().parents[1]
    for codigo in ("portal_llamada_sin_capacidad", "portal_llamada_no_se_graba"):
        assert codigo in cde.MENSAJES
        for idioma in ("es", "en", "de", "fr", "it", "pl", "pt", "zh"):
            assert f'"err_srv.{codigo}"' in (raiz / f"frontend/src/i18n/portal/{idioma}.ts").read_text(encoding="utf-8")


def test_la_migracion_210_cuelga_de_la_209():
    import pathlib
    fuente = (pathlib.Path(__file__).resolve().parents[1] / "alembic/versions/210_chat_del_portal_colaboracion.py").read_text(encoding="utf-8")
    assert 'down_revision = "209_chat_del_portal_completo"' in fuente
    assert "edited_by_client_id" in fuente and "change_type" in fuente
