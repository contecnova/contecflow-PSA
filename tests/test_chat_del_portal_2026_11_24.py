"""Chat del portal completo (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md).

Lo que se comprueba:

- «Solo el operador llama», en el servidor: el cliente recibe SIEMPRE 403
  `portal_llamada_solo_operador` (y queda auditado); el equipo llama con
  `clientes.llamar`; el cliente acepta, rechaza o cuelga; llamadas y vídeo se
  apagan por empresa.
- Adjuntos: validación por contenido (no solo extensión), tipos y tamaño por
  empresa, descarga solo para participantes con cabeceras seguras.
- Editar/borrar el propio mensaje con rastro (versiones + auditoría) y plazo;
  reacciones; citar solo dentro de la conversación.
- GRC: el cliente no ve pendientes de aprobación ni notas internas; retención
  y bloqueo legal de los tipos nuevos; RGPD (copia y supresión).
- Catálogo: códigos de error con texto en los 8 idiomas del portal, capacidad
  y ajustes declarados.

Ficheros: el almacén de objetos se sustituye por uno en memoria (no se escribe
en disco). LiveKit: credenciales de prueba (firma local, sin red).
"""
from __future__ import annotations

import hashlib
import pathlib
import re
from datetime import timedelta
from types import SimpleNamespace

import pytest

from app.core import codigos_de_error as cde
from app.models.settings import AppSetting
from tests.conftest import auth

# 24-11-2026: las rutas de LISTA del chat devuelven el sobre canónico de listas
# (`APIListResponse`: `{"items": [...], "meta": {...}}`, app/core/responses.py), como el
# resto de la API y como espera el frontend (desenvolverSobre); los objetos sueltos van en
# `{"data": ...}`. Los tests leían `data` también en las listas: ahora leen `items`.
RAIZ = pathlib.Path(__file__).resolve().parents[1]
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


# ── Dobles y ayudas ──────────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    """Solo asyncio (el WebSocket de la aplicación no corre bajo trio)."""
    return "asyncio"


class AlmacenEnMemoria:
    def __init__(self):
        self.ficheros: dict[str, bytes] = {}

    def save_bytes(self, key, data):
        from app.services.collaboration._storage import StoredFile
        self.ficheros[key] = data
        return StoredFile("memoria", key, len(data), hashlib.sha256(data).hexdigest())

    def read(self, key):
        return self.ficheros[key]

    def delete(self, key):
        self.ficheros.pop(key, None)


@pytest.fixture
def almacen(monkeypatch):
    from app.services.collaboration import _storage
    doble = AlmacenEnMemoria()
    monkeypatch.setattr(_storage, "storage", doble)
    # Sin antivirus real: limpio.
    monkeypatch.setattr(_storage, "scan_with_av", lambda datos: ("clean", {}))
    from app.services.collaboration import files
    monkeypatch.setattr(files, "scan_with_av", lambda datos: ("clean", {}))
    return doble


@pytest.fixture
def livekit(monkeypatch):
    from app.services.collaboration import livekit as lk
    monkeypatch.setattr(lk.CONFIG, "api_key", "clave-de-prueba")
    monkeypatch.setattr(lk.CONFIG, "api_secret", "firma-de-prueba-de-al-menos-32-caracteres")
    return lk


def _ajuste(db, org, clave, valor):
    from app.services.settings_service import invalidate_cache
    fila = db.query(AppSetting).filter(AppSetting.key == clave, AppSetting.organization_id == org).first()
    if fila is None:
        db.add(AppSetting(key=clave, value=str(valor), organization_id=org))
    else:
        fila.value = str(valor)
    db.commit()
    invalidate_cache(clave)


def _proyecto(client, token, code):
    r = client.post("/api/v1/projects", headers=auth(token), json={
        "name": f"Proyecto {code}", "code": code, "description": "x", "status": "active",
        "billing_type": "time_material", "is_billable": True})
    assert r.status_code in (200, 201), r.text
    return r.json()["data"]["id"]


def _escenario(client, token, db, code="CHP"):
    """Proyecto, usuario del portal con sesión abierta y conversación del equipo con él."""
    from app.models.client_portal import ClientUser
    pid = _proyecto(client, token, code)
    email, clave = f"{code.lower()}@cliente-chat.com", "ClaveSegura123!"
    r = client.post("/api/v1/portal/clients", headers=auth(token), json={
        "project_ids": [pid], "full_name": "Cliente Chat", "email": email, "password": clave,
        "can_request_changes": True, "language": "es"})
    assert r.status_code in (200, 201), r.text
    cliente = db.query(ClientUser).filter(ClientUser.email == email).one()
    r = client.post("/api/v1/portal/conversations/team", headers=auth(token), json={
        "title": "Consulta del cliente", "topic_type": "general", "project_id": pid,
        "client_user_ids": [cliente.id]})
    assert r.status_code == 200, r.text
    conv = r.json()["data"]["id"]
    r = client.post("/api/v1/portal/auth/login", json={"email": email, "password": clave})
    assert r.status_code == 200, r.text
    return SimpleNamespace(pid=pid, cliente=cliente, conv=conv, org=cliente.organization_id)


def _team(conv):
    return f"/api/v1/portal/conversations/team/{conv}"


def _portal(conv):
    return f"/api/v1/portal/conversations/{conv}"


def _codigo(r):
    return r.json().get("code")


# ── «Solo el operador llama» ─────────────────────────────────────────────────

def test_el_cliente_nunca_puede_iniciar_una_llamada(client, admin_token, db):
    from app.models.portal_conversations import PortalConversationAudit, PortalConversationCall
    e = _escenario(client, admin_token, db, "CL1")
    for kind in ("audio", "video"):
        r = client.post(f"{_portal(e.conv)}/calls", json={"kind": kind})
        assert r.status_code == 403, r.text
        assert _codigo(r) == "portal_llamada_solo_operador"
    # Sin cuerpo, también.
    assert client.post(f"{_portal(e.conv)}/calls").status_code == 403
    assert db.query(PortalConversationCall).filter(PortalConversationCall.conversation_id == e.conv).count() == 0
    denegados = db.query(PortalConversationAudit).filter(
        PortalConversationAudit.conversation_id == e.conv,
        PortalConversationAudit.action_type == "portal_conversation.call_start_denied").count()
    assert denegados >= 2


def test_el_operador_llama_y_el_cliente_acepta_y_cuelga(client, admin_token, db, livekit):
    from app.models.portal_conversations import PortalConversationAudit
    e = _escenario(client, admin_token, db, "CL2")
    r = client.post(f"{_team(e.conv)}/calls", headers=auth(admin_token), json={"kind": "video"})
    assert r.status_code == 200, r.text
    llamada = r.json()["data"]
    assert llamada["status"] == "ringing" and llamada["role"] == "host"
    assert llamada["livekit_token"] and not llamada["livekit_token"].startswith("dev:")
    assert llamada["is_recorded"] is False

    # Una segunda llamada en la misma conversación, no.
    r = client.post(f"{_team(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"})
    assert r.status_code == 409 and _codigo(r) == "portal_llamada_en_curso"

    # El cliente la ve sonar y la acepta: solo así recibe su token.
    sonando = client.get("/api/v1/portal/conversations/calls/ringing").json()["items"]
    assert [c["id"] for c in sonando] == [llamada["id"]]
    r = client.post(f"{_portal(e.conv)}/calls/{llamada['id']}/accept")
    assert r.status_code == 200, r.text
    aceptada = r.json()["data"]
    assert aceptada["status"] == "active" and aceptada["livekit_token"]
    assert aceptada["livekit_room"] == llamada["livekit_room"]

    r = client.post(f"{_portal(e.conv)}/calls/{llamada['id']}/end")
    assert r.status_code == 200 and r.json()["data"]["status"] == "ended"
    acciones = {a.action_type for a in db.query(PortalConversationAudit).filter(
        PortalConversationAudit.conversation_id == e.conv)}
    assert {"portal_conversation.call_started", "portal_conversation.call_accepted",
            "portal_conversation.call_ended"} <= acciones


def test_el_cliente_rechaza_y_no_puede_aceptar_despues(client, admin_token, db, livekit):
    e = _escenario(client, admin_token, db, "CL3")
    llamada = client.post(f"{_team(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"}).json()["data"]
    r = client.post(f"{_portal(e.conv)}/calls/{llamada['id']}/decline")
    assert r.status_code == 200 and r.json()["data"]["status"] == "declined"
    r = client.post(f"{_portal(e.conv)}/calls/{llamada['id']}/accept")
    assert r.status_code == 409 and _codigo(r) == "portal_llamada_terminada"


def test_llamadas_y_video_se_apagan_por_empresa(client, admin_token, db, livekit):
    e = _escenario(client, admin_token, db, "CL4")
    _ajuste(db, e.org, "PORTAL_CHAT_VIDEO_ENABLED", "false")
    r = client.post(f"{_team(e.conv)}/calls", headers=auth(admin_token), json={"kind": "video"})
    assert r.status_code == 403 and _codigo(r) == "portal_videollamadas_desactivadas"
    _ajuste(db, e.org, "PORTAL_CHAT_CALLS_ENABLED", "false")
    r = client.post(f"{_team(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"})
    assert r.status_code == 403 and _codigo(r) == "portal_llamadas_desactivadas"
    ajustes = client.get("/api/v1/portal/conversations/team/settings", headers=auth(admin_token)).json()["data"]
    assert ajustes["calls_enabled"] is False and ajustes["can_call"] is False
    # Al cliente nunca se le ofrece llamar.
    assert client.get("/api/v1/portal/conversations/settings").json()["data"]["can_call"] is False


def test_una_llamada_sin_respuesta_pasa_a_perdida(client, admin_token, db, livekit):
    from app.models.portal_conversations import PortalConversationCall
    e = _escenario(client, admin_token, db, "CL5")
    llamada = client.post(f"{_team(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"}).json()["data"]
    fila = db.get(PortalConversationCall, llamada["id"])
    fila.created_at = fila.created_at - timedelta(minutes=10)
    db.commit()
    assert client.get("/api/v1/portal/conversations/calls/ringing").json()["items"] == []
    r = client.post(f"{_portal(e.conv)}/calls/{llamada['id']}/accept")
    assert r.status_code == 409


# ── Adjuntos ─────────────────────────────────────────────────────────────────

def test_el_cliente_sube_una_imagen_y_el_equipo_la_descarga(client, admin_token, db, almacen):
    e = _escenario(client, admin_token, db, "AD1")
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("captura.png", PNG, "image/png")},
                    data={"caption": "Así se ve el fallo"})
    assert r.status_code == 200, r.text
    m = r.json()["data"]
    assert m["message_type"] == "attachment" and m["body"] == "Así se ve el fallo"
    (adjunto,) = m["attachments"]
    assert adjunto["is_image"] and adjunto["mime_type"] == "image/png" and "storage_key" not in adjunto
    r = client.get(f"{_team(e.conv)}/attachments/{adjunto['id']}", headers=auth(admin_token))
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment")
    # Y el propio cliente también.
    assert client.get(f"{_portal(e.conv)}/attachments/{adjunto['id']}").content == PNG


def test_el_contenido_manda_sobre_la_extension(client, admin_token, db, almacen):
    e = _escenario(client, admin_token, db, "AD2")
    # Un PNG renombrado a .pdf (sin declarar tipo): se rechaza por los bytes.
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("factura.pdf", PNG, "application/octet-stream")})
    assert r.status_code == 415 and _codigo(r) == "portal_adjunto_contenido_no_coincide"
    # Un ejecutable con nombre de texto.
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("notas.txt", b"MZ\x90\x00binario", "text/plain")})
    assert r.status_code == 415
    # SVG: nunca en el chat del portal, aunque la empresa lo pida.
    _ajuste(db, e.org, "PORTAL_CHAT_ALLOWED_EXTENSIONS", ".svg,.pdf")
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("logo.svg", b"<svg/>", "image/svg+xml")})
    assert r.status_code == 415 and _codigo(r) == "portal_adjunto_tipo_no_permitido"
    assert client.post(f"{_portal(e.conv)}/attachments", files={"file": ("ok.pdf", PDF, "application/pdf")}).status_code == 200


def test_tipos_tamano_y_activacion_por_empresa(client, admin_token, db, almacen):
    e = _escenario(client, admin_token, db, "AD3")
    _ajuste(db, e.org, "PORTAL_CHAT_ALLOWED_EXTENSIONS", ".pdf")
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("foto.png", PNG, "image/png")})
    assert r.status_code == 415 and _codigo(r) == "portal_adjunto_tipo_no_permitido"
    _ajuste(db, e.org, "PORTAL_CHAT_MAX_FILE_MB", "1")
    grande = PDF + b"0" * (1024 * 1024 + 10)
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("grande.pdf", grande, "application/pdf")})
    assert r.status_code == 413 and _codigo(r) == "fichero_demasiado_grande"
    _ajuste(db, e.org, "PORTAL_CHAT_ATTACHMENTS_ENABLED", "false")
    r = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("ok.pdf", PDF, "application/pdf")})
    assert r.status_code == 403 and _codigo(r) == "portal_adjuntos_desactivados"


def test_quien_no_participa_no_descarga(client, admin_token, db, almacen):
    from app.models.client_portal import ClientUser
    e = _escenario(client, admin_token, db, "AD4")
    m = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("a.pdf", PDF, "application/pdf")}).json()["data"]
    adjunto = m["attachments"][0]["id"]
    # Otro usuario del portal del mismo proyecto, fuera de la conversación.
    otro = "ad4-otro@cliente-chat.com"
    client.post("/api/v1/portal/clients", headers=auth(admin_token), json={
        "project_ids": [e.pid], "full_name": "Otra Persona", "email": otro, "password": "ClaveSegura123!",
        "can_request_changes": True, "language": "es"})
    assert db.query(ClientUser).filter(ClientUser.email == otro).count() == 1
    assert client.post("/api/v1/portal/auth/login", json={"email": otro, "password": "ClaveSegura123!"}).status_code == 200
    r = client.get(f"{_portal(e.conv)}/attachments/{adjunto}")
    assert r.status_code == 404


def test_el_cliente_de_otra_empresa_no_ve_la_conversacion():
    from app.services.portal_conversation_service._comun import _cliente_puede_ver
    participante = SimpleNamespace(removed_at=None, client_user_id="c1", client_org_id=None)
    conv = SimpleNamespace(organization_id="empresa-a", project_id=None, participants=[participante])
    mismo = SimpleNamespace(id="c1", organization_id="empresa-a", client_org_id=None, get_project_ids=lambda: [])
    ajeno = SimpleNamespace(id="c1", organization_id="empresa-b", client_org_id=None, get_project_ids=lambda: [])
    assert _cliente_puede_ver(conv, mismo) is True
    assert _cliente_puede_ver(conv, ajeno) is False


def test_validacion_de_fichero_sin_http():
    from app.core.errores import ErrorDeDominio
    from app.services.portal_conversation_service.adjuntos import validar_fichero
    from app.services.portal_conversation_service.ajustes import AjustesDelChat, _extensiones
    ajustes = AjustesDelChat(True, True, True, (".png", ".pdf"), 5, 60, 60)
    assert validar_fichero("a.png", "image/png", PNG, ajustes) == "image/png"
    assert validar_fichero("a.pdf", "", PDF, ajustes) == "application/pdf"
    with pytest.raises(ErrorDeDominio) as e:
        validar_fichero("a.pdf", "", PNG, ajustes)
    assert e.value.code == "portal_adjunto_contenido_no_coincide"
    with pytest.raises(ErrorDeDominio):
        validar_fichero("sin_extension", "", PNG, ajustes)
    # Las extensiones de la empresa solo acotan el catálogo (sin SVG ni comprimidos).
    assert _extensiones(".PDF, png, .svg, .zip, .exe") == (".pdf", ".png")


# ── Editar, borrar, reaccionar, citar ────────────────────────────────────────

def _mensaje_del_cliente(client, conv, texto="Hola equipo"):
    r = client.post(f"{_portal(conv)}/messages", json={"body": texto, "message_type": "text"})
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_editar_el_propio_mensaje_deja_rastro(client, admin_token, db):
    from app.models.portal_conversations import PortalConversationAudit, PortalConversationMessageVersion
    e = _escenario(client, admin_token, db, "ED1")
    m = _mensaje_del_cliente(client, e.conv, "Primera version del texto")
    r = client.put(f"{_portal(e.conv)}/messages/{m['id']}", json={"body": "Texto corregido"})
    assert r.status_code == 200, r.text
    editado = r.json()["data"]
    assert editado["body"] == "Texto corregido" and editado["edited_at"]
    assert editado["raw_body"] is None  # el cliente no recibe el texto sin ocultar
    versiones = db.query(PortalConversationMessageVersion).filter(
        PortalConversationMessageVersion.message_id == m["id"]).all()
    assert [v.body for v in versiones] == ["Primera version del texto"]
    # El equipo ve el historial; el cliente no tiene esa ruta.
    r = client.get(f"{_team(e.conv)}/messages/{m['id']}/versions", headers=auth(admin_token))
    assert r.status_code == 200 and r.json()["items"][0]["change_type"] == "edit"
    assert db.query(PortalConversationAudit).filter(
        PortalConversationAudit.target_id == m["id"],
        PortalConversationAudit.action_type == "portal_conversation.message_edited").count() == 1


def test_no_se_edita_lo_ajeno_ni_fuera_de_plazo(client, admin_token, db):
    from app.models.portal_conversations import PortalConversationMessage
    e = _escenario(client, admin_token, db, "ED2")
    del_equipo = client.post(f"{_team(e.conv)}/messages", headers=auth(admin_token),
                             json={"body": "Respuesta del equipo", "message_type": "text"}).json()["data"]
    r = client.put(f"{_portal(e.conv)}/messages/{del_equipo['id']}", json={"body": "cambiado"})
    assert r.status_code == 403 and _codigo(r) == "portal_mensaje_no_propio"
    m = _mensaje_del_cliente(client, e.conv)
    fila = db.get(PortalConversationMessage, m["id"])
    fila.created_at = fila.created_at - timedelta(hours=3)
    db.commit()
    _ajuste(db, e.org, "PORTAL_CHAT_EDIT_WINDOW_MINUTES", "60")
    r = client.delete(f"{_portal(e.conv)}/messages/{m['id']}")
    assert r.status_code == 409 and _codigo(r) == "portal_mensaje_fuera_de_plazo"


def test_borrar_quita_texto_adjuntos_y_fichero(client, admin_token, db, almacen):
    from app.models.portal_conversations import PortalConversationAttachment, PortalConversationMessageVersion
    e = _escenario(client, admin_token, db, "ED3")
    m = client.post(f"{_portal(e.conv)}/attachments", files={"file": ("a.pdf", PDF, "application/pdf")},
                    data={"caption": "Adjunto el informe"}).json()["data"]
    clave = db.query(PortalConversationAttachment).filter(PortalConversationAttachment.message_id == m["id"]).one().storage_key
    assert clave in almacen.ficheros
    r = client.delete(f"{_portal(e.conv)}/messages/{m['id']}")
    assert r.status_code == 200, r.text
    borrado = r.json()["data"]
    assert borrado["is_deleted"] and borrado["body"] == "" and borrado["attachments"] == []
    assert clave not in almacen.ficheros
    assert db.query(PortalConversationMessageVersion).filter(
        PortalConversationMessageVersion.message_id == m["id"],
        PortalConversationMessageVersion.change_type == "delete").count() == 1


def test_reacciones_se_ponen_y_se_quitan(client, admin_token, db):
    e = _escenario(client, admin_token, db, "RE1")
    m = _mensaje_del_cliente(client, e.conv)
    r = client.post(f"{_portal(e.conv)}/messages/{m['id']}/reactions", json={"emoji": "👍"})
    assert r.status_code == 200 and r.json()["data"]["added"] is True
    r = client.post(f"{_team(e.conv)}/messages/{m['id']}/reactions", headers=auth(admin_token), json={"emoji": "👍"})
    assert r.json()["data"]["added"] is True
    mensajes = client.get(f"{_team(e.conv)}/messages", headers=auth(admin_token)).json()["items"]
    assert len(next(x for x in mensajes if x["id"] == m["id"])["reactions"]) == 2
    r = client.post(f"{_portal(e.conv)}/messages/{m['id']}/reactions", json={"emoji": "👍"})
    assert r.json()["data"]["added"] is False
    r = client.post(f"{_portal(e.conv)}/messages/{m['id']}/reactions", json={"emoji": "<b>x</b>"})
    assert r.status_code == 422 and _codigo(r) == "portal_reaccion_no_valida"


def test_citar_solo_dentro_de_la_conversacion(client, admin_token, db):
    e = _escenario(client, admin_token, db, "CI1")
    m = _mensaje_del_cliente(client, e.conv)
    r = client.post(f"{_team(e.conv)}/messages", headers=auth(admin_token),
                    json={"body": "Respondo a esto", "message_type": "text", "parent_message_id": m["id"]})
    assert r.status_code == 200 and r.json()["data"]["reply_to"]["id"] == m["id"]
    r = client.post(f"{_portal(e.conv)}/messages", json={"body": "x", "parent_message_id": "no-existe"})
    assert r.status_code == 400 or r.status_code == 422
    assert _codigo(r) == "portal_mensaje_citado_no_valido"
    # Por la ruta de texto solo entra texto.
    r = client.post(f"{_portal(e.conv)}/messages", json={"body": "x", "message_type": "approval_decision"})
    assert _codigo(r) == "portal_tipo_de_mensaje_no_valido"


# ── GRC: lo que el cliente no debe ver ───────────────────────────────────────

def test_el_cliente_no_ve_pendientes_del_equipo_ni_notas_internas(client, admin_token, db):
    e = _escenario(client, admin_token, db, "GR1")
    r = client.post(f"{_team(e.conv)}/messages", headers=auth(admin_token),
                    json={"body": "Nota solo para el equipo", "message_type": "text", "is_internal_note": True})
    assert r.status_code == 200
    lista = client.get("/api/v1/portal/conversations").json()["items"]
    conv = next(c for c in lista if c["id"] == e.conv)
    assert not conv["last_message"] or conv["last_message"]["body"] != "Nota solo para el equipo"
    r = client.put("/api/v1/portal/conversations/team/policies/general", headers=auth(admin_token),
                   json={"requires_team_message_approval": True})
    assert r.status_code == 200, r.text
    client.post(f"{_team(e.conv)}/messages", headers=auth(admin_token), json={"body": "Pendiente de revisar", "message_type": "text"})
    cuerpos = [m["body"] for m in client.get(f"{_portal(e.conv)}/messages").json()["items"]]
    assert "Pendiente de revisar" not in cuerpos and "Nota solo para el equipo" not in cuerpos


def test_tipos_de_retencion_y_bloqueo_legal_del_chat():
    from app.db.bloqueo_legal import TIPOS
    for clave in ("portal_conversation_attachments", "portal_conversation_message_versions", "portal_conversation_calls"):
        tipo = TIPOS[clave]
        modelo = tipo.modelo()
        assert all(hasattr(modelo, c) for c in tipo.campos), clave
        assert hasattr(modelo, "organization_id")


def test_rgpd_copia_y_supresion_del_usuario_del_portal(client, admin_token, db, almacen):
    from app.models.portal_conversations import PortalConversationAttachment, PortalConversationMessage
    from app.services.portal_conversation_service import rgpd
    e = _escenario(client, admin_token, db, "RG1")
    _mensaje_del_cliente(client, e.conv, "Mi mensaje personal")
    client.post(f"{_portal(e.conv)}/attachments", files={"file": ("dni.pdf", PDF, "application/pdf")})
    copia = rgpd.copia(db, [e.cliente.id], e.org)["portal_chat"]
    assert any(m["body"] == "Mi mensaje personal" for m in copia["messages"])
    assert [a["name"] for a in copia["attachments"]] == ["dni.pdf"]
    informe = rgpd.suprimir(db, [e.cliente.id], e.org)
    db.commit()
    assert informe["attachments"] == 1
    assert db.query(PortalConversationAttachment).filter(PortalConversationAttachment.uploaded_by_client_id == e.cliente.id).count() == 0
    assert almacen.ficheros == {}
    cuerpos = {m.body for m in db.query(PortalConversationMessage).filter(PortalConversationMessage.sender_client_id == e.cliente.id)}
    assert cuerpos == {rgpd.BORRADO}


# ── Tiempo real ──────────────────────────────────────────────────────────────

def test_los_avisos_van_solo_a_los_participantes():
    from app.services.portal_conversation_service import en_vivo
    p_equipo = SimpleNamespace(removed_at=None, user_id="u1", client_user_id=None, client_org_id=None)
    p_cliente = SimpleNamespace(removed_at=None, user_id=None, client_user_id="c1", client_org_id=None)
    p_fuera = SimpleNamespace(removed_at="ayer", user_id="u9", client_user_id=None, client_org_id=None)
    conv = SimpleNamespace(id="x", organization_id="o", participants=[p_equipo, p_cliente, p_fuera],
                           created_by_user_id="u2", created_by_client_id=None)
    destinos = set(en_vivo.destinos(None, conv, excepto_usuario="u2"))
    assert destinos == {"u1", "client:c1"}
    assert set(en_vivo.destinos(None, conv, incluir_clientes=False)) == {"u1", "u2"}


@pytest.mark.anyio
async def test_el_socket_solo_atiende_su_tipo():
    from app.services.portal_conversation_service import en_vivo
    llamadas = []

    async def en_sesion(fn, *a):
        llamadas.append(fn.__name__)

    assert await en_vivo.mensaje_del_portal(en_sesion, None, None, {"type": "livechat_typing"}) is False
    assert await en_vivo.mensaje_del_portal(en_sesion, None, None, {"type": "portal_conv_typing", "conversation_id": "legacy:1"}) is True
    assert llamadas == []
    assert await en_vivo.mensaje_del_operador(en_sesion, None, None, {"type": "portal_conv_typing", "conversation_id": "c"}) is True
    assert llamadas == ["_escribiendo_operador"]


# ── Catálogo: códigos, capacidad, ajustes ────────────────────────────────────

CODIGOS = (
    "portal_adjunto_tipo_no_permitido", "portal_adjunto_contenido_no_coincide", "portal_adjunto_no_disponible",
    "portal_adjuntos_desactivados", "portal_adjunto_no_encontrado", "portal_adjunto_en_cuarentena",
    "portal_adjunto_sin_acceso", "portal_mensaje_citado_no_valido", "portal_tipo_de_mensaje_no_valido",
    "portal_mensaje_no_editable", "portal_mensaje_no_propio", "portal_mensaje_ya_borrado",
    "portal_mensaje_fuera_de_plazo", "portal_mensaje_bajo_bloqueo_legal", "portal_reaccion_no_valida",
    "portal_llamada_tipo_no_valido", "portal_llamada_no_disponible", "portal_llamadas_desactivadas",
    "portal_videollamadas_desactivadas", "portal_llamada_sin_cliente", "portal_llamada_sin_acceso",
    "portal_llamada_en_curso", "portal_llamada_no_encontrada", "portal_llamada_terminada",
    "portal_llamada_solo_operador",
)


def test_codigos_en_el_catalogo_y_en_los_idiomas():
    assert set(CODIGOS) <= set(cde.MENSAJES)
    for idioma in ("es", "en", "de", "fr", "it", "pl", "pt", "zh"):
        fuente = (RAIZ / "frontend" / "src" / "i18n" / "portal" / f"{idioma}.ts").read_text(encoding="utf-8")
        for codigo in CODIGOS:
            assert f'"err_srv.{codigo}"' in fuente, (idioma, codigo)
        assert '"governedconversations.llamada_no_se_graba"' in fuente
    for idioma in ("es", "en", "zh"):
        fuente = (RAIZ / "frontend" / "src" / "i18n" / "langs" / f"{idioma}.mjs").read_text(encoding="utf-8")
        assert re.search(r"\n    portal_llamada_solo_operador:", fuente), idioma
        assert re.search(r"\n    PORTAL_CHAT_CALLS_ENABLED:", fuente), idioma


def test_capacidad_y_ajustes_declarados():
    from app.core.capacidades import CAPACIDADES
    from app.core.config import settings
    from app.services.settings_service import RUNTIME_FLAG_GROUPS
    assert "clientes.llamar" in CAPACIDADES
    assert "'clientes.llamar'" in (RAIZ / "frontend/src/permisos/capacidades.ts").read_text(encoding="utf-8")
    claves = {k for k, _, _ in RUNTIME_FLAG_GROUPS["portal_chat"]}
    assert claves == {"PORTAL_CHAT_CALLS_ENABLED", "PORTAL_CHAT_VIDEO_ENABLED", "PORTAL_CHAT_ATTACHMENTS_ENABLED",
                      "PORTAL_CHAT_ALLOWED_EXTENSIONS", "PORTAL_CHAT_MAX_FILE_MB",
                      "PORTAL_CHAT_EDIT_WINDOW_MINUTES", "PORTAL_CHAT_CALL_RING_SECONDS"}
    assert all(hasattr(settings, k) for k in claves)
    assert "id: 'portal-chat'" in (RAIZ / "frontend/src/pages/settings/catalogoDeAjustes.tsx").read_text(encoding="utf-8")


def test_la_migracion_209_cuelga_de_la_208():
    fuente = (RAIZ / "alembic" / "versions" / "209_chat_del_portal_completo.py").read_text(encoding="utf-8")
    assert 'down_revision = "208_empresa_obligatoria_y_portal"' in fuente
    for tabla in ("portal_conversation_message_versions", "portal_conversation_attachments",
                  "portal_conversation_reactions", "portal_conversation_calls"):
        assert tabla in fuente
