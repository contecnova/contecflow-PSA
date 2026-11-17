"""Canales en tiempo real (17-11-2026): hilos de Slack ↔ ticket (Events API),
adjuntos de WhatsApp con ventana de 24 h, chat del portal por WebSocket y
asistente del portal con IA.

Sin red: Slack, Meta y el LLM son dobles. Las firmas se calculan aqui con el
algoritmo de cada proveedor.
"""
import hashlib
import hmac
import json
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest

from app.models.service_desk import ChannelConversation, ChannelMessage, ServiceCategory, ServiceItem, Ticket, TicketComment
from app.models.settings import IntegrationCredential
from tests.conftest import auth

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


# ── Doble de HTTP (cliente_httpx) ─────────────────────────────────────────────

class _Resp:
    def __init__(self, datos=None, contenido=b"", tipo="application/json", estado=200):
        self._datos, self.contenido, self.estado = datos, contenido, estado
        self.headers = {"content-type": tipo, "content-length": str(len(contenido))}

    def raise_for_status(self):
        if self.estado >= 400:
            import httpx
            raise httpx.HTTPStatusError("error", request=None, response=None)

    def json(self):
        return self._datos or {}

    def iter_bytes(self):
        yield self.contenido


class Red:
    """Responde por trozos de URL y apunta cada llamada."""

    def __init__(self):
        self.llamadas, self.rutas = [], []

    def cuando(self, trozo, resp):
        self.rutas.append((trozo, resp))

    def _resp(self, metodo, url, kw):
        self.llamadas.append({"metodo": metodo, "url": url, **kw})
        for trozo, resp in self.rutas:
            if trozo in url:
                return resp(url, kw) if callable(resp) else resp
        return _Resp({"ok": True})

    def __call__(self, **_kw):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, **kw):
        return self._resp("GET", url, kw)

    def post(self, url, **kw):
        return self._resp("POST", url, kw)

    @contextmanager
    def stream(self, metodo, url, **kw):
        yield self._resp(metodo, url, kw)


@pytest.fixture
def red(monkeypatch):
    r = Red()
    from app.services.service_desk import canal_slack, canal_whatsapp
    monkeypatch.setattr(canal_slack, "_cliente", lambda timeout: r)
    monkeypatch.setattr(canal_whatsapp, "_cliente", lambda timeout: r)
    return r


@pytest.fixture(autouse=True)
def almacen(monkeypatch):
    """Almacen de documentos en memoria: los tests no escriben en uploads/."""
    from app.services import s3_service
    ficheros = {}

    class Falso:
        def upload_file(self, file_content, file_name, document_id, version_num, content_type="application/octet-stream"):
            clave = f"documents/{document_id}/v{version_num}/{file_name}"
            ficheros[clave] = file_content
            return clave, len(file_content)

        def get_file_bytes(self, clave):
            return ficheros[clave]
    monkeypatch.setattr(s3_service, "file_storage", Falso())
    return ficheros


@pytest.fixture
def empujes(monkeypatch):
    from app.services.service_desk import canales_en_vivo
    hechos = []
    monkeypatch.setattr(canales_en_vivo, "_empujar", lambda destinos, m: hechos.append((list(destinos), m)))
    canales_en_vivo._bandejas.clear()
    return hechos


def _org(client, token, db):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "Ticket con hilo", "description": "x", "ticket_type": "incident"})
    t = db.query(Ticket).filter(Ticket.id == r.json()["data"]["id"]).one()
    return t


def _admin(db):
    from app.models.user import User
    return db.query(User).filter(User.username == "admin").one()


# ── Slack ─────────────────────────────────────────────────────────────────────

def _firma(secreto, cuerpo: bytes, marca: str) -> str:
    return "v0=" + hmac.new(secreto.encode(), f"v0:{marca}:{cuerpo.decode()}".encode(), hashlib.sha256).hexdigest()


def _slack(monkeypatch, org):
    from app.services import integrations
    from app.services.service_desk import canal_slack
    monkeypatch.setattr(integrations, "organizacion_del_workspace_de_slack", lambda db, t: org)
    monkeypatch.setattr(integrations, "secreto_de_firma_de_slack", lambda db, o: "s3cr3t")
    monkeypatch.setattr(canal_slack, "token_del_bot", lambda db, o: "xoxb-1" if o == org else None)
    canal_slack._personas.clear()


def _evento(client, payload, secreto="s3cr3t"):
    cuerpo = json.dumps(payload).encode()
    marca = str(int(time.time()))
    return client.post("/api/v1/sd/channels/slack/events", content=cuerpo, headers={
        "Content-Type": "application/json", "X-Slack-Request-Timestamp": marca,
        "X-Slack-Signature": _firma(secreto, cuerpo, marca)})


def test_url_verification_firmada(client, monkeypatch):
    from app.services.service_desk import canal_slack
    monkeypatch.setattr(canal_slack, "_secretos_de_firma", lambda db: ["otro", "s3cr3t"])
    r = _evento(client, {"type": "url_verification", "challenge": "reto-123"})
    assert r.status_code == 200 and r.text == "reto-123"
    assert _evento(client, {"type": "url_verification", "challenge": "x"}, secreto="malo").status_code == 403


def test_respuesta_en_hilo_entra_como_comentario_con_su_autor_y_adjunto(client, admin_token, db, monkeypatch, red, empujes):
    from app.models.documents import Document
    from app.services.service_desk import canal_slack
    t = _org(client, admin_token, db)
    org, admin = t.organization_id, _admin(db)
    _slack(monkeypatch, org)
    canal_slack.vincular_hilo(db, t, "C1", "111.1")
    db.commit()
    red.cuando("users.info", _Resp({"ok": True, "user": {"profile": {"email": admin.email.upper(), "real_name": "Admin"}}}))
    red.cuando("files.slack.com", _Resp(contenido=PNG, tipo="image/png"))
    mensaje = {"type": "message", "channel": "C1", "user": "U1", "ts": "222.2", "thread_ts": "111.1",
               "text": "Adjunto la captura", "files": [{"name": "captura.png", "mimetype": "image/png", "size": len(PNG),
                                                       "url_private_download": "https://files.slack.com/f/captura.png"}]}
    payload = {"type": "event_callback", "team_id": "T1", "event": mensaje,
               "authorizations": [{"user_id": "UBOT", "is_bot": True}]}
    assert _evento(client, payload).status_code == 200
    db.expire_all()
    c = db.query(TicketComment).filter(TicketComment.ticket_id == t.id, TicketComment.body.like("Adjunto la captura%")).one()
    assert c.is_public and c.author_user_id == admin.id
    doc = db.query(Document).filter(Document.ticket_id == t.id).one()
    assert doc.title == "captura.png"
    descarga = [x for x in red.llamadas if "files.slack.com" in x["url"]][0]
    assert descarga["headers"]["Authorization"] == "Bearer xoxb-1"
    m = db.query(ChannelMessage).filter(ChannelMessage.external_message_id == "222.2").one()
    assert m.ticket_comment_id == c.id and m.attachment_document_id == doc.id
    # Reintento de Slack: no duplica.
    assert _evento(client, payload).status_code == 200
    db.expire_all()
    assert db.query(TicketComment).filter(TicketComment.ticket_id == t.id, TicketComment.body.like("Adjunto%")).count() == 1
    # Lo que entro por el hilo no vuelve al hilo (sin bucle).
    from app.services.service_desk.salida_por_canales import al_comentar
    antes = len([x for x in red.llamadas if "chat.postMessage" in x["url"]])
    al_comentar(db, t, c.id)
    assert len([x for x in red.llamadas if "chat.postMessage" in x["url"]]) == antes


def test_mensajes_de_bots_y_ediciones_se_ignoran(client, admin_token, db, monkeypatch, red, empujes):
    from app.services.service_desk import canal_slack
    t = _org(client, admin_token, db)
    _slack(monkeypatch, t.organization_id)
    canal_slack.vincular_hilo(db, t, "C1", "111.1")
    db.commit()
    base = {"type": "message", "channel": "C1", "ts": "333.3", "thread_ts": "111.1", "text": "eco"}
    for evento in ({**base, "user": "UBOT"}, {**base, "bot_id": "B1", "user": "U2"},
                   {**base, "user": "U2", "subtype": "message_changed"}):
        _evento(client, {"type": "event_callback", "team_id": "T1", "event": evento,
                         "authorizations": [{"user_id": "UBOT", "is_bot": True}]})
    db.expire_all()
    assert db.query(TicketComment).filter(TicketComment.ticket_id == t.id, TicketComment.body == "eco").count() == 0


def test_firma_de_evento_de_otra_empresa_es_403(client, admin_token, db, monkeypatch):
    t = _org(client, admin_token, db)
    _slack(monkeypatch, t.organization_id)
    r = _evento(client, {"type": "event_callback", "team_id": "T1", "event": {}}, secreto="ajeno")
    assert r.status_code == 403


def test_respuesta_del_agente_sale_al_hilo_y_crear_desde_slack_ata_el_hilo(client, admin_token, db, monkeypatch, red, empujes):
    from app.services.service_desk import canal_slack
    from app.services.service_desk.comment_service import add_internal_comment
    from app.services.service_desk.salida_por_canales import al_comentar
    t = _org(client, admin_token, db)
    admin = _admin(db)
    _slack(monkeypatch, t.organization_id)
    red.cuando("chat.postMessage", _Resp({"ok": True, "ts": "999.9"}))
    # /contecflow ticket con token de bot: la tarjeta se publica y su hilo queda atado.
    db.info["slack_canal"] = "C7"
    db.info["organization_id"], db.info["is_superadmin"] = t.organization_id, False
    r = canal_slack.crear(db, "La VPN no conecta", admin)
    assert r["response_type"] == "ephemeral"
    conv = db.query(ChannelConversation).filter(ChannelConversation.channel == "slack",
                                                ChannelConversation.external_id == "C7:999.9").one()
    nuevo = db.get(Ticket, conv.ticket_id)
    c = add_internal_comment(db, nuevo, nuevo.id, "Reinicia el cliente VPN", True, admin)
    db.commit()
    assert al_comentar(db, nuevo, c.id)["sent"] == 1
    salida = [x for x in red.llamadas if "chat.postMessage" in x["url"]][-1]
    assert salida["json"]["thread_ts"] == "999.9" and "Reinicia el cliente VPN" in salida["json"]["text"]
    assert al_comentar(db, nuevo, c.id)["sent"] == 0      # idempotente


def test_canal_de_entrada_abre_ticket_con_hilo(client, admin_token, db, monkeypatch, red, empujes):
    from app.services.settings_service import update_setting
    t = _org(client, admin_token, db)
    org = t.organization_id
    _slack(monkeypatch, org)
    update_setting("SD_SLACK_INTAKE_CHANNELS", "CIN", org, db)
    db.commit()
    red.cuando("users.info", _Resp({"ok": True, "user": {"profile": {"email": "nadie@fuera.example", "real_name": "Eva"}}}))
    red.cuando("chat.postMessage", _Resp({"ok": True, "ts": "500.1"}))
    _evento(client, {"type": "event_callback", "team_id": "T1", "event": {
        "type": "message", "channel": "CIN", "user": "U9", "ts": "500.0", "text": "No funciona la impresora"}})
    db.expire_all()
    conv = db.query(ChannelConversation).filter(ChannelConversation.external_id == "CIN:500.0").one()
    nuevo = db.get(Ticket, conv.ticket_id)
    assert nuevo.source == "slack" and nuevo.requester_name == "Cliente externo (Eva)"


# ── WhatsApp ──────────────────────────────────────────────────────────────────

def _credenciales(db, org, plantilla=False):
    from app.core.encryption import encrypt_value
    db.add(IntegrationCredential(organization_id=org, provider="whatsapp", key="phone_number_id", value="555"))
    for clave, valor in (("app_secret", "app-secret"), ("access_token", "tok"), ("verify_token", "v")):
        db.add(IntegrationCredential(organization_id=org, provider="whatsapp", key=clave,
                                     value_encrypted=encrypt_value(valor)))
    if plantilla:
        db.add(IntegrationCredential(organization_id=org, provider="whatsapp", key="template_name", value="seguimiento"))
    db.commit()
    from app.services.integration_credentials_service import invalidate_cache
    invalidate_cache("whatsapp")


def _webhook(client, mensaje):
    cuerpo = json.dumps({"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "555"}, "contacts": [{"wa_id": "34600", "profile": {"name": "Lucía"}}],
        "messages": [mensaje]}}]}]}).encode()
    firma = "sha256=" + hmac.new(b"app-secret", cuerpo, hashlib.sha256).hexdigest()
    return client.post("/api/v1/sd/channels/whatsapp/webhook", content=cuerpo,
                       headers={"Content-Type": "application/json", "X-Hub-Signature-256": firma})


def _medio(contenido, tipo):
    def responder(url, kw):
        return _Resp({"url": "https://lookaside.fbsbx.com/m/1", "mime_type": tipo, "file_size": len(contenido)})
    return responder


def test_whatsapp_imagen_se_guarda_y_virus_se_rechaza(client, admin_token, db, red, empujes):
    from app.models.documents import Document
    t = _org(client, admin_token, db)
    _credenciales(db, t.organization_id)
    red.cuando("/MEDIA-OK", _medio(PNG, "image/png"))
    red.cuando("/MEDIA-VIRUS", _medio(EICAR, "text/plain"))
    contenidos = {"ok": PNG, "virus": EICAR}
    estado = {"siguiente": "ok"}
    red.cuando("lookaside.fbsbx.com", lambda url, kw: _Resp(contenido=contenidos[estado["siguiente"]]))
    assert _webhook(client, {"from": "34600", "id": "wamid.T", "type": "text", "text": {"body": "Hola"}}).status_code == 200
    r = _webhook(client, {"from": "34600", "id": "wamid.I", "type": "image",
                          "image": {"id": "MEDIA-OK", "mime_type": "image/png", "caption": "Pantallazo"}})
    assert r.status_code == 200, r.text
    estado["siguiente"] = "virus"
    _webhook(client, {"from": "34600", "id": "wamid.V", "type": "document",
                      "document": {"id": "MEDIA-VIRUS", "mime_type": "text/plain", "filename": "x.txt"}})
    db.expire_all()
    conv = db.query(ChannelConversation).filter(ChannelConversation.channel == "whatsapp").one()
    docs = db.query(Document).filter(Document.ticket_id == conv.ticket_id).all()
    assert len(docs) == 1 and docs[0].title.endswith(".png")
    imagen = db.query(ChannelMessage).filter(ChannelMessage.external_message_id == "wamid.I").one()
    assert imagen.attachment_document_id == docs[0].id and imagen.body.startswith("Pantallazo")
    virus = db.query(ChannelMessage).filter(ChannelMessage.external_message_id == "wamid.V").one()
    assert "rechazado (virus)" in virus.body and virus.attachment_document_id is None
    media = [x for x in red.llamadas if "MEDIA-OK" in x["url"]][0]
    assert media["headers"]["Authorization"] == "Bearer tok"


def test_whatsapp_url_de_medio_fuera_de_meta_no_se_descarga(client, admin_token, db, red, empujes):
    t = _org(client, admin_token, db)
    _credenciales(db, t.organization_id)
    red.cuando("/MEDIA-X", _Resp({"url": "https://169.254.169.254/latest", "mime_type": "image/png"}))
    _webhook(client, {"from": "34600", "id": "wamid.X", "type": "image", "image": {"id": "MEDIA-X"}})
    assert not [x for x in red.llamadas if "169.254" in x["url"]]


def test_ventana_de_24h_plantilla_y_adjunto(client, admin_token, db, red, empujes):
    from app.services.service_desk import adjuntos_de_canal
    t = _org(client, admin_token, db)
    org = t.organization_id
    _credenciales(db, org)
    salidas = iter(range(1, 100))
    red.cuando("/messages", lambda url, kw: _Resp({"messages": [{"id": f"wamid.OUT{next(salidas)}"}]}))
    red.cuando("/media", _Resp({"id": "MEDIA-UP"}))
    _webhook(client, {"from": "34600", "id": "wamid.1", "type": "text", "text": {"body": "Hola"}})
    db.expire_all()
    conv = db.query(ChannelConversation).filter(ChannelConversation.channel == "whatsapp").one()
    # Dentro de la ventana: texto libre y adjunto del ticket.
    assert client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                       json={"body": "Lo miro"}).status_code == 200
    ticket = db.get(Ticket, conv.ticket_id)
    r = adjuntos_de_canal.guardar(db, ticket, nombre="guia.pdf", tipo="application/pdf",
                                  contenido=b"%PDF-1.4\n" + b"0" * 32, origen="test")
    db.commit()
    r = client.post(f"/api/v1/sd/channels/conversations/{conv.id}/attachments", headers=auth(admin_token),
                    json={"document_id": r.document_id, "caption": "La guía"})
    assert r.status_code == 200, r.text
    envio = [x for x in red.llamadas if x["url"].endswith("/messages")][-1]
    assert envio["json"]["type"] == "document" and envio["json"]["document"]["id"] == "MEDIA-UP"
    # Fuera de la ventana y sin plantilla: 409 y nada guardado.
    conv = db.get(ChannelConversation, conv.id)
    conv.last_inbound_at = datetime.now(timezone.utc) - timedelta(hours=30)
    db.commit()
    antes = db.query(ChannelMessage).filter(ChannelMessage.conversation_id == conv.id).count()
    assert client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                       json={"body": "¿Sigue?"}).status_code == 409
    db.expire_all()
    assert db.query(ChannelMessage).filter(ChannelMessage.conversation_id == conv.id).count() == antes
    # Con plantilla: sale dentro de ella.
    db.add(IntegrationCredential(organization_id=org, provider="whatsapp", key="template_name", value="seguimiento"))
    db.commit()
    from app.services.integration_credentials_service import invalidate_cache
    invalidate_cache("whatsapp")
    r = client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                    json={"body": "¿Sigue?\nGracias"})
    assert r.status_code == 200 and r.json()["data"]["delivery_status"] == "template"
    envio = [x for x in red.llamadas if x["url"].endswith("/messages")][-1]
    assert envio["json"]["type"] == "template" and envio["json"]["template"]["name"] == "seguimiento"
    assert "\n" not in envio["json"]["template"]["components"][0]["parameters"][1]["text"]


# ── Chat del portal en tiempo real ────────────────────────────────────────────

def _cliente(db, org, email="cli.tr@example.com"):
    from app.models.client_portal import ClientUser
    c = ClientUser(organization_id=org, full_name="Cliente TR", email=email, is_active=True)
    db.add(c)
    db.commit()
    return c


def test_chat_en_vivo_empuja_a_cada_lado_y_acota(client, admin_token, db, empujes):
    import asyncio
    from app.services.service_desk import canales_en_vivo, conversaciones
    t = _org(client, admin_token, db)
    org, admin = t.organization_id, _admin(db)
    cliente, otro = _cliente(db, org), _cliente(db, org, "otro.tr@example.com")
    conv = conversaciones.abrir_o_seguir(db, org, "livechat", None, client_user=cliente)
    db.commit()

    async def en_sesion(fn, *a):
        return fn(*a)
    asyncio.run(canales_en_vivo.mensaje_del_operador(en_sesion, db, admin, {"type": "channel_watch"}))
    conversaciones.mensaje_del_cliente(db, conv, "Hola", client_user=cliente, con_bot=True)
    assert any(admin.id in d and m["type"] == "sd_channel" and m["event"] == "message" for d, m in empujes)
    conversaciones.pedir_agente(db, conv, client_user=cliente)
    conversaciones.tomar(db, conv.id, admin)
    assert any(d == [f"client:{cliente.id}"] and m["event"] == "status" and m["conversation"]["status"] == "agent"
               for d, m in empujes)
    empujes.clear()
    conversaciones.responder(db, conv.id, admin, "Te ayudo")
    al_cliente = [m for d, m in empujes if d == [f"client:{cliente.id}"] and m["event"] == "message"]
    assert al_cliente and al_cliente[0]["message"]["body"] == "Te ayudo"
    # Escribiendo y leido: solo sobre conversaciones propias.
    empujes.clear()
    asyncio.run(canales_en_vivo.mensaje_del_portal(en_sesion, db, otro, {"type": "livechat_typing", "conversation_id": conv.id}))
    assert empujes == []
    asyncio.run(canales_en_vivo.mensaje_del_portal(en_sesion, db, cliente, {"type": "livechat_read", "conversation_id": conv.id}))
    db.refresh(conv)
    assert conv.client_read_at is not None
    assert any(m["event"] == "read" and m["by"] == "customer" for _d, m in empujes)


def test_operador_de_otra_empresa_no_recibe_ni_toca(client, admin_token, db, empujes):
    import asyncio
    from types import SimpleNamespace
    from app.services.service_desk import canales_en_vivo, conversaciones
    t = _org(client, admin_token, db)
    cliente = _cliente(db, t.organization_id)
    conv = conversaciones.abrir_o_seguir(db, t.organization_id, "livechat", None, client_user=cliente)
    db.commit()
    ajeno = SimpleNamespace(id="u-ajeno", organization_id="otra-org", role=_admin(db).role, full_name="Ajeno")

    async def en_sesion(fn, *a):
        return fn(*a)
    asyncio.run(canales_en_vivo.mensaje_del_operador(en_sesion, db, ajeno, {"type": "channel_read", "conversation_id": conv.id}))
    db.refresh(conv)
    assert conv.agent_read_at is None and empujes == []
    assert "u-ajeno" not in canales_en_vivo.operadores_en_bandeja(t.organization_id)


# ── Asistente del portal con IA ───────────────────────────────────────────────

def _servicio(db, org):
    cat = ServiceCategory(organization_id=org, name="IT")
    db.add(cat)
    db.flush()
    item = ServiceItem(organization_id=org, category_id=cat.id, name="Portátil", description="Equipo nuevo",
                       is_visible_to_clients=True)
    db.add(item)
    db.commit()
    return item


@pytest.fixture
def llm(monkeypatch):
    from app.services.service_desk import asistente_del_portal_ia
    estado = {"respuestas": [], "llamadas": []}

    def falso(db, cliente, mensajes, sistema, max_tokens):
        estado["llamadas"].append({"mensajes": mensajes, "sistema": sistema})
        return estado["respuestas"].pop(0) if estado["respuestas"] else None
    monkeypatch.setattr(asistente_del_portal_ia, "_llamar_ia", falso)
    return estado


def test_asistente_ia_estado_de_sus_tickets_en_su_idioma(client, admin_token, db, llm):
    from app.models.enterprise import AuditLog
    from app.services.service_desk import asistente_del_portal as asistente
    t = _org(client, admin_token, db)
    cliente = _cliente(db, t.organization_id)
    t.requester_client_id = cliente.id
    db.commit()
    llm["respuestas"] = [json.dumps({"tool": "portal_ticket_status", "arguments": {"number": t.number}, "reply": ""}),
                         "Votre ticket est en cours."]
    r = asistente.interpretar(db, cliente, f"Où en est {t.number} ?", "fr")
    assert r["engine"] == "ai" and r["intent"] == "ticket_status" and r["language"] == "fr"
    assert [x["number"] for x in r["result"]["tickets"]] == [t.number] and r["reply"] == "Votre ticket est en cours."
    assert "French" in llm["llamadas"][0]["sistema"] and "French" in llm["llamadas"][1]["sistema"]
    assert db.query(AuditLog).filter(AuditLog.action == "PORTAL_ASSISTANT", AuditLog.resource_id == cliente.id).count() >= 1


def test_asistente_ia_no_ve_tickets_ajenos(client, admin_token, db, llm):
    from app.services.service_desk import asistente_del_portal as asistente
    t = _org(client, admin_token, db)             # ticket del admin, no del cliente
    cliente = _cliente(db, t.organization_id)
    llm["respuestas"] = [json.dumps({"tool": "portal_ticket_status", "arguments": {"number": t.number}}), "Nada"]
    r = asistente.interpretar(db, cliente, f"Dame el estado de {t.number}", "es")
    assert r["result"]["tickets"] == []


def test_asistente_ia_propone_y_solo_crea_al_confirmar(client, admin_token, db, llm):
    from app.services.service_desk import asistente_del_portal as asistente
    t = _org(client, admin_token, db)
    item = _servicio(db, t.organization_id)
    cliente = _cliente(db, t.organization_id)
    antes = db.query(Ticket).count()
    llm["respuestas"] = [json.dumps({"tool": "portal_catalog_request", "reply": "¿Lo pido?",
                                     "arguments": {"service_item_id": item.id, "description": "Para Ana"}})]
    r = asistente.interpretar(db, cliente, "Necesito un portátil para Ana", "es")
    assert r["intent"] == "catalog_request" and r["action"]["params"]["service_item_id"] == item.id
    assert db.query(Ticket).count() == antes      # nada sin confirmar
    hecho = asistente.confirmar(db, cliente, r["action"]["id"])
    assert hecho["status"] == "executed" and db.query(Ticket).count() == antes + 1
    # Un id inventado (o de otra empresa) no se propone.
    llm["respuestas"] = [json.dumps({"tool": "portal_catalog_request", "arguments": {"service_item_id": "inventado"}})]
    assert asistente.interpretar(db, cliente, "Quiero un yate", "es")["intent"] == "catalog_no_match"


def test_asistente_ia_herramienta_desconocida_y_caida_a_palabras(client, admin_token, db, llm):
    from app.services.service_desk import asistente_del_portal as asistente
    t = _org(client, admin_token, db)
    cliente = _cliente(db, t.organization_id)
    llm["respuestas"] = [json.dumps({"tool": "borrar_todo", "arguments": {}, "reply": "No puedo"})]
    r = asistente.interpretar(db, cliente, "Borra todo", "es")
    assert r["intent"] == "none" and r["engine"] == "ai"
    llm["respuestas"] = []                         # IA no disponible
    r = asistente.interpretar(db, cliente, "He olvidado mi contraseña", "de")
    assert r["engine"] == "rules" and r["notice"] == "ai_unavailable" and r["intent"] == "password_reset_unavailable"


def test_asistente_ia_busca_en_la_kb_publicada(client, admin_token, db, llm):
    from app.models.service_desk import KBArticle, KBStatus
    from app.services.service_desk import asistente_del_portal as asistente
    t = _org(client, admin_token, db)
    org = t.organization_id
    db.add(KBArticle(organization_id=org, number="KB-1", title="Configurar la VPN", body="Abre el cliente VPN y entra",
                     status=KBStatus.published, is_public=True))
    db.add(KBArticle(organization_id=org, number="KB-2", title="VPN interna", body="Solo para el equipo VPN",
                     status=KBStatus.published, is_public=False))
    db.commit()
    cliente = _cliente(db, org)
    llm["respuestas"] = [json.dumps({"tool": "portal_kb_search", "arguments": {"query": "configurar VPN"}}),
                         "Sigue el artículo KB-1."]
    r = asistente.interpretar(db, cliente, "¿Cómo configuro la VPN?", "es")
    assert r["intent"] == "kb_answer" and [a["number"] for a in r["articles"]] == ["KB-1"]
    assert "KB-2" not in llm["llamadas"][1]["sistema"]


def test_politica_de_la_kb_del_portal_existe():
    from app.services.ai_chat.tool_execution.politica import POLITICAS_DEL_PORTAL
    from app.services.ai_provider_service import MODULOS_DE_IA
    assert POLITICAS_DEL_PORTAL["portal_kb_search"].escribe is False
    assert "portal_assistant" in MODULOS_DE_IA
