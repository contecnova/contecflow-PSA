"""Canales del service desk (mejoras de mercado 16-11-2026): Slack interactivo,
WhatsApp Business (Cloud API) y chat en vivo con traspaso a agente.

Sin red: las llamadas salientes (`httpx.post`) se sustituyen por dobles y las
firmas se calculan aqui con el mismo algoritmo que el proveedor.
"""
import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest

from app.models.service_desk import ChannelConversation, ChannelMessage, Ticket
from app.models.settings import IntegrationCredential
from tests.conftest import auth


class _Respuesta:
    def __init__(self, datos=None):
        self._datos = datos or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._datos


@pytest.fixture
def llamadas(monkeypatch):
    hechas = []

    def falso_post(url, **kw):
        hechas.append({"url": url, **kw})
        return _Respuesta({"messages": [{"id": "wamid.SALIDA"}]})
    import httpx
    monkeypatch.setattr(httpx, "post", falso_post)
    return hechas


def _org(client, token, db):
    r = client.post("/api/v1/sd/tickets", headers=auth(token), json={
        "title": "empresa", "description": "empresa", "ticket_type": "incident"})
    return db.query(Ticket).filter(Ticket.id == r.json()["data"]["id"]).one().organization_id


# ── Slack ─────────────────────────────────────────────────────────────────────

def _firma_slack(secreto, cuerpo: bytes, marca: str) -> str:
    return "v0=" + hmac.new(secreto.encode(), f"v0:{marca}:{cuerpo.decode()}".encode(), hashlib.sha256).hexdigest()


def test_firma_de_slack_y_marca_de_tiempo():
    from app.services.service_desk.canal_slack import firma_valida
    cuerpo, marca = b"payload=%7B%7D", str(int(time.time()))
    assert firma_valida("s3cr3t", marca, cuerpo, _firma_slack("s3cr3t", cuerpo, marca))
    assert not firma_valida("s3cr3t", marca, cuerpo, _firma_slack("otro", cuerpo, marca))
    vieja = str(int(time.time()) - 3600)
    assert not firma_valida("s3cr3t", vieja, cuerpo, _firma_slack("s3cr3t", cuerpo, vieja))


def test_boton_de_slack_sin_firma_valida_es_403(client, monkeypatch):
    from app.services import integrations
    monkeypatch.setattr(integrations, "organizacion_del_workspace_de_slack", lambda db, t: None)
    monkeypatch.setattr(integrations, "secreto_de_firma_de_slack", lambda db, o: "s3cr3t")
    cuerpo = urlencode({"payload": json.dumps({"team": {"id": "T1"}, "actions": []})})
    r = client.post("/api/v1/sd/channels/slack/interactions", content=cuerpo,
                    headers={"Content-Type": "application/x-www-form-urlencoded",
                             "X-Slack-Request-Timestamp": str(int(time.time())), "X-Slack-Signature": "v0=mala"})
    assert r.status_code == 403


def test_boton_asignarme_actualiza_y_responde_por_response_url(client, admin_token, db, monkeypatch, llamadas):
    from app.models.user import User
    from app.services import integrations
    from app.services.service_desk import canal_slack
    tid = client.post("/api/v1/sd/tickets", headers=auth(admin_token), json={
        "title": "Desde Slack", "description": "x", "ticket_type": "incident"}).json()["data"]["id"]
    admin = db.query(User).filter(User.username == "admin").one()
    monkeypatch.setattr(integrations, "organizacion_del_workspace_de_slack", lambda db, t: admin.organization_id)
    monkeypatch.setattr(integrations, "secreto_de_firma_de_slack", lambda db, o: "s3cr3t")
    monkeypatch.setattr(integrations, "find_user_by_slack_name", lambda db, n, t=None: admin)
    payload = {"team": {"id": "T1"}, "user": {"username": "admin"}, "response_url": "https://hooks.slack.com/actions/x",
               "actions": [{"action_id": "sd_assign_me", "value": tid}]}
    cuerpo = urlencode({"payload": json.dumps(payload)}).encode()
    marca = str(int(time.time()))
    r = client.post("/api/v1/sd/channels/slack/interactions", content=cuerpo,
                    headers={"Content-Type": "application/x-www-form-urlencoded", "X-Slack-Request-Timestamp": marca,
                             "X-Slack-Signature": _firma_slack("s3cr3t", cuerpo, marca)})
    assert r.status_code == 200, r.text
    db.expire_all()
    assert db.query(Ticket).filter(Ticket.id == tid).one().assigned_to_user_id == admin.id
    assert llamadas and llamadas[0]["url"] == "https://hooks.slack.com/actions/x"
    assert not canal_slack.responder_por_url(db, "https://evil.example.com/x", {"text": "x"})


def test_comandos_del_service_desk_en_slack_y_teams():
    from app.api.v1.endpoints.integrations_hub import _COMANDOS
    assert {"ver", "comentar", "asignarme", "encurso", "resolver", "ticket"} <= set(_COMANDOS)


# ── WhatsApp ──────────────────────────────────────────────────────────────────

def _credenciales_whatsapp(db, org, secreto="app-secret"):
    from app.core.encryption import encrypt_value
    db.add(IntegrationCredential(organization_id=org, provider="whatsapp", key="phone_number_id", value="555"))
    for clave, valor in (("app_secret", secreto), ("access_token", "tok"), ("verify_token", "verifica")):
        db.add(IntegrationCredential(organization_id=org, provider="whatsapp", key=clave, value_encrypted=encrypt_value(valor)))
    db.commit()


def _mensaje(texto, mid="wamid.1"):
    return {"entry": [{"changes": [{"value": {
        "metadata": {"phone_number_id": "555"},
        "contacts": [{"wa_id": "34600111222", "profile": {"name": "Lucía"}}],
        "messages": [{"from": "34600111222", "id": mid, "type": "text", "text": {"body": texto}}]}}]}]}


def _firma_meta(secreto, cuerpo: bytes) -> str:
    return "sha256=" + hmac.new(secreto.encode(), cuerpo, hashlib.sha256).hexdigest()


def test_whatsapp_abre_ticket_ignora_repetidos_y_contesta(client, admin_token, db, llamadas):
    org = _org(client, admin_token, db)
    _credenciales_whatsapp(db, org)
    cuerpo = json.dumps(_mensaje("La impresora no imprime")).encode()
    r = client.post("/api/v1/sd/channels/whatsapp/webhook", content=cuerpo,
                    headers={"Content-Type": "application/json", "X-Hub-Signature-256": _firma_meta("app-secret", cuerpo)})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/sd/channels/whatsapp/webhook", content=cuerpo,
                    headers={"Content-Type": "application/json", "X-Hub-Signature-256": _firma_meta("app-secret", cuerpo)})
    assert r.json()["data"]["duplicates"] == 1
    db.expire_all()
    conv = db.query(ChannelConversation).filter(ChannelConversation.channel == "whatsapp").one()
    ticket = db.query(Ticket).filter(Ticket.id == conv.ticket_id).one()
    assert ticket.organization_id == org and ticket.source == "whatsapp"
    assert db.query(ChannelMessage).filter(ChannelMessage.conversation_id == conv.id).count() == 1

    r = client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                    json={"body": "Ya vamos"})
    assert r.status_code == 200, r.text
    assert llamadas[-1]["url"].endswith("/555/messages") and llamadas[-1]["json"]["to"] == "34600111222"
    assert llamadas[-1]["headers"]["Authorization"] == "Bearer tok"


def test_whatsapp_con_firma_mala_es_403(client, admin_token, db):
    org = _org(client, admin_token, db)
    _credenciales_whatsapp(db, org)
    cuerpo = json.dumps(_mensaje("hola")).encode()
    r = client.post("/api/v1/sd/channels/whatsapp/webhook", content=cuerpo,
                    headers={"Content-Type": "application/json", "X-Hub-Signature-256": _firma_meta("otro", cuerpo)})
    assert r.status_code == 403


def test_alta_del_webhook_de_whatsapp(client, admin_token, db):
    org = _org(client, admin_token, db)
    _credenciales_whatsapp(db, org)
    ok = client.get("/api/v1/sd/channels/whatsapp/webhook",
                    params={"hub.mode": "subscribe", "hub.verify_token": "verifica", "hub.challenge": "1234"})
    assert ok.status_code == 200 and ok.text == "1234"
    assert client.get("/api/v1/sd/channels/whatsapp/webhook",
                      params={"hub.mode": "subscribe", "hub.verify_token": "no", "hub.challenge": "1"}).status_code == 403


# ── Chat en vivo con traspaso a agente ────────────────────────────────────────

def test_chat_en_vivo_traspaso_a_agente(client, admin_token, db):
    from app.models.client_portal import ClientUser
    from app.services.service_desk import conversaciones
    org = _org(client, admin_token, db)
    cliente = ClientUser(organization_id=org, full_name="Portal Uno", email="portal.uno@example.com", is_active=True)
    db.add(cliente)
    db.commit()
    conv = conversaciones.abrir_o_seguir(db, org, "livechat", None, client_user=cliente)
    assert conv.status == "bot"
    conversaciones.mensaje_del_cliente(db, conv, "No me deja entrar al correo", client_user=cliente, con_bot=True)
    assert conv.ticket_id is None
    conversaciones.pedir_agente(db, conv, client_user=cliente)
    assert conv.status == "waiting_agent" and conv.ticket_id

    items = client.get("/api/v1/sd/channels/conversations", params={"status": "waiting_agent"},
                       headers=auth(admin_token)).json()["items"]
    assert [c["id"] for c in items] == [conv.id]
    assert client.post(f"/api/v1/sd/channels/conversations/{conv.id}/take", headers=auth(admin_token)).status_code == 200
    assert client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                       json={"body": "Hola, te ayudo"}).status_code == 200
    db.expire_all()
    autores = [m.author_type for m in db.query(ChannelMessage).filter(ChannelMessage.conversation_id == conv.id)
               .order_by(ChannelMessage.created_at)]
    assert "agent" in autores and autores[0] == "customer"
