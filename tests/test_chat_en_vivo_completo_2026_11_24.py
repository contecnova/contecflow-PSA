"""Chat en vivo de Soporte completo (24-11-2026, docs/portal/CHAT_DEL_PORTAL.md §10).

El tercer chat del portal (Soporte → Chat en vivo; el operador lo atiende en la
bandeja de canales) con lo mismo que los otros dos. Se comprueba:

- «Solo el operador llama», en el servidor: el cliente recibe SIEMPRE 403
  `portal_llamada_solo_operador` (auditado); el operador llama; el cliente
  acepta, rechaza o cuelga; grabar sin permiso de la empresa da 409
  `portal_grabacion_desactivada` (migración 214).
- Adjuntos validados por contenido y descarga solo por la API, con cabeceras seguras.
- Editar y borrar el propio mensaje con rastro (versiones + auditoría) y plazo.
- Reacciones (poner/quitar, emoji válido).
- Aislamiento de empresa: otro cliente u otra empresa no ven ni tocan nada.
- GRC: migración 211, tipos de retención/bloqueo legal y RGPD.

Reutiliza los dobles del almacén y de LiveKit de tests/test_chat_del_portal_2026_11_24.py.
Escrito sin ejecutar (la prueba general lo corre).
"""
from __future__ import annotations

import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from tests.conftest import auth
from tests.test_chat_del_portal_2026_11_24 import PDF, PNG, _ajuste, _proyecto, almacen, livekit  # noqa: F401

RAIZ = pathlib.Path(__file__).resolve().parents[1]
BASE = "/api/v1/sd/channels"


def _codigo(r):
    return r.json().get("code")


def _escenario(client, token, db, code="LV1"):
    """Cliente del portal con sesión abierta, su chat en vivo con una persona del equipo."""
    from app.models.client_portal import ClientUser
    pid = _proyecto(client, token, code)
    email, clave = f"{code.lower()}@cliente-vivo.com", "ClaveSegura123!"
    r = client.post("/api/v1/portal/clients", headers=auth(token), json={
        "project_ids": [pid], "full_name": "Cliente En Vivo", "email": email, "password": clave,
        "can_request_changes": True, "language": "es"})
    assert r.status_code in (200, 201), r.text
    cliente = db.query(ClientUser).filter(ClientUser.email == email).one()
    r = client.post("/api/v1/portal/auth/login", json={"email": email, "password": clave})
    assert r.status_code == 200, r.text
    r = client.post(f"{BASE}/livechat", json={"body": "Hola, necesito ayuda"})
    assert r.status_code == 200, r.text
    conv = r.json()["data"]["conversation"]["id"]
    assert client.post(f"{BASE}/livechat/{conv}/agent").status_code == 200
    r = client.post(f"{BASE}/conversations/{conv}/take", headers=auth(token))
    assert r.status_code == 200, r.text
    return SimpleNamespace(pid=pid, cliente=cliente, conv=conv, org=cliente.organization_id)


def _cli(conv):
    return f"{BASE}/livechat/{conv}"


def _ope(conv):
    return f"{BASE}/conversations/{conv}"


def _auditoria(db, accion):
    from app.models.enterprise import AuditLog
    return db.query(AuditLog).filter(AuditLog.action == accion.upper()).all()


# ── «Solo el operador llama» ─────────────────────────────────────────────────

def test_el_cliente_nunca_inicia_una_llamada_en_el_chat_en_vivo(client, admin_token, db):
    from app.models.service_desk.mercado import ChannelCall
    e = _escenario(client, admin_token, db, "LV1")
    for kind in ("audio", "video"):
        r = client.post(f"{_cli(e.conv)}/calls", json={"kind": kind})
        assert r.status_code == 403, r.text
        assert _codigo(r) == "portal_llamada_solo_operador"
    assert client.post(f"{_cli(e.conv)}/calls").status_code == 403
    assert db.query(ChannelCall).filter(ChannelCall.conversation_id == e.conv).count() == 0
    denegados = [a for a in _auditoria(db, "livechat.call_start_denied") if e.conv in (a.metadata_ or "")]
    assert len(denegados) >= 2
    # Sus ajustes nunca le ofrecen llamar.
    assert client.get(f"{BASE}/livechat/settings").json()["data"]["can_call"] is False


def test_el_operador_llama_el_cliente_acepta_y_no_se_graba(client, admin_token, db, livekit):  # noqa: F811
    e = _escenario(client, admin_token, db, "LV2")
    r = client.post(f"{_ope(e.conv)}/calls", headers=auth(admin_token), json={"kind": "video"})
    assert r.status_code == 200, r.text
    llamada = r.json()["data"]
    assert llamada["status"] == "ringing" and llamada["role"] == "host" and llamada["is_recorded"] is False
    r = client.post(f"{_ope(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"})
    assert r.status_code == 409 and _codigo(r) == "portal_llamada_en_curso"

    sonando = client.get(f"{BASE}/livechat/calls/ringing").json()["items"]
    assert [c["id"] for c in sonando] == [llamada["id"]]
    r = client.post(f"{_cli(e.conv)}/calls/{llamada['id']}/accept")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "active" and r.json()["data"]["livekit_token"]

    # Grabar con clientes sin que la empresa lo permita (apagado por defecto): 409, desde los dos lados.
    r = client.post(f"{_ope(e.conv)}/calls/{llamada['id']}/recording", headers=auth(admin_token))
    assert r.status_code == 409 and _codigo(r) == "portal_grabacion_desactivada"
    r = client.post(f"{_cli(e.conv)}/calls/{llamada['id']}/recording")
    assert r.status_code == 409 and _codigo(r) == "portal_grabacion_desactivada"

    r = client.post(f"{_cli(e.conv)}/calls/{llamada['id']}/end")
    assert r.status_code == 200 and r.json()["data"]["status"] == "ended"
    for accion in ("livechat.call_started", "livechat.call_accepted", "livechat.call_ended",
                   "livechat.call_recording_denied"):
        assert _auditoria(db, accion), accion


def test_el_cliente_rechaza_y_las_llamadas_se_apagan_por_empresa(client, admin_token, db, livekit):  # noqa: F811
    e = _escenario(client, admin_token, db, "LV3")
    llamada = client.post(f"{_ope(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"}).json()["data"]
    r = client.post(f"{_cli(e.conv)}/calls/{llamada['id']}/decline")
    assert r.status_code == 200 and r.json()["data"]["status"] == "declined"
    assert _auditoria(db, "livechat.call_declined")
    _ajuste(db, e.org, "PORTAL_CHAT_CALLS_ENABLED", "false")
    r = client.post(f"{_ope(e.conv)}/calls", headers=auth(admin_token), json={"kind": "audio"})
    assert r.status_code == 403 and _codigo(r) == "portal_llamadas_desactivadas"


# ── Adjuntos ─────────────────────────────────────────────────────────────────

def test_adjuntos_validados_por_contenido_y_descarga_por_la_api(client, admin_token, db, almacen):  # noqa: F811
    e = _escenario(client, admin_token, db, "LV4")
    # Un PNG con extensión .pdf: lo que dicen los bytes no casa con la extensión.
    r = client.post(f"{_cli(e.conv)}/attachments", files={"file": ("factura.pdf", PNG, "application/pdf")})
    assert r.status_code == 415, r.text
    # Un ejecutable disfrazado tampoco entra.
    r = client.post(f"{_cli(e.conv)}/attachments", files={"file": ("x.exe", b"MZ\x90\x00" * 10, "application/octet-stream")})
    assert r.status_code == 415

    r = client.post(f"{_cli(e.conv)}/attachments", files={"file": ("captura.png", PNG, "image/png")},
                    data={"caption": "Mira el error"})
    assert r.status_code == 200, r.text
    m = r.json()["data"]
    assert m["body"] == "Mira el error" and len(m["attachments"]) == 1
    adj = m["attachments"][0]
    assert adj["is_image"] is True and adj["mime_type"] == "image/png"
    assert any(k.startswith(f"livechat/{e.org}/{e.conv}/") for k in almacen.ficheros)

    r = client.get(f"{_cli(e.conv)}/attachments/{adj['id']}")
    assert r.status_code == 200 and r.content == PNG
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-disposition"].startswith("attachment")
    assert "no-store" in r.headers["cache-control"]
    # El operador de la empresa también, por su ruta.
    r = client.get(f"{_ope(e.conv)}/files/{adj['id']}", headers=auth(admin_token))
    assert r.status_code == 200 and r.content == PNG
    assert _auditoria(db, "livechat.attachment_uploaded") and _auditoria(db, "livechat.attachment_downloaded")

    # Adjuntos apagados por la empresa: 403.
    _ajuste(db, e.org, "PORTAL_CHAT_ATTACHMENTS_ENABLED", "false")
    r = client.post(f"{_ope(e.conv)}/files", headers=auth(admin_token), files={"file": ("a.pdf", PDF, "application/pdf")})
    assert r.status_code == 403 and _codigo(r) == "portal_adjuntos_desactivados"


# ── Editar, borrar, citar y reaccionar ───────────────────────────────────────

def test_editar_y_borrar_el_propio_mensaje_deja_rastro(client, admin_token, db):
    from app.models.service_desk.mercado import ChannelMessage, ChannelMessageVersion
    e = _escenario(client, admin_token, db, "LV5")
    r = client.post(f"{_cli(e.conv)}/messages", json={"body": "Texto con erata"})
    assert r.status_code == 200, r.text
    mid = r.json()["data"]["message"]["id"]

    r = client.put(f"{_cli(e.conv)}/messages/{mid}", json={"body": "Texto corregido"})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["body"] == "Texto corregido" and r.json()["data"]["edited_at"]
    versiones = client.get(f"{_ope(e.conv)}/messages/{mid}/versions", headers=auth(admin_token)).json()["items"]
    assert [v["body"] for v in versiones] == ["Texto con erata"] and versiones[0]["change_type"] == "edit"
    assert _auditoria(db, "livechat.message_edited")

    # El operador no edita lo del cliente.
    r = client.put(f"{_ope(e.conv)}/messages/{mid}", headers=auth(admin_token), json={"body": "x"})
    assert r.status_code == 403 and _codigo(r) == "portal_mensaje_no_propio"

    r = client.delete(f"{_cli(e.conv)}/messages/{mid}")
    assert r.status_code == 200 and r.json()["data"]["is_deleted"] is True and r.json()["data"]["body"] == ""
    tipos = [v.change_type for v in db.query(ChannelMessageVersion).filter(ChannelMessageVersion.message_id == mid)]
    assert sorted(tipos) == ["delete", "edit"]
    assert db.get(ChannelMessage, mid).deleted_at is not None
    assert _auditoria(db, "livechat.message_deleted")
    r = client.put(f"{_cli(e.conv)}/messages/{mid}", json={"body": "otra vez"})
    assert r.status_code == 409 and _codigo(r) == "portal_mensaje_ya_borrado"


def test_editar_fuera_de_plazo_da_409(client, admin_token, db):
    from app.models.service_desk.mercado import ChannelMessage
    e = _escenario(client, admin_token, db, "LV6")
    _ajuste(db, e.org, "PORTAL_CHAT_EDIT_WINDOW_MINUTES", "1")
    r = client.post(f"{BASE}/conversations/{e.conv}/reply", headers=auth(admin_token), json={"body": "Respuesta"})
    assert r.status_code == 200, r.text
    mid = r.json()["data"]["id"]
    m = db.get(ChannelMessage, mid)
    m.created_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()
    r = client.put(f"{_ope(e.conv)}/messages/{mid}", headers=auth(admin_token), json={"body": "Respuesta mejor"})
    assert r.status_code == 409 and _codigo(r) == "portal_mensaje_fuera_de_plazo"


def test_citar_solo_dentro_de_la_conversacion(client, admin_token, db):
    e = _escenario(client, admin_token, db, "LV7")
    primero = client.post(f"{_cli(e.conv)}/messages", json={"body": "Primero"}).json()["data"]["message"]["id"]
    r = client.post(f"{BASE}/conversations/{e.conv}/reply", headers=auth(admin_token),
                    json={"body": "Respondo a eso", "reply_to_message_id": primero})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["reply_to"]["id"] == primero
    r = client.post(f"{_cli(e.conv)}/messages", json={"body": "x", "reply_to_message_id": "no-existe"})
    assert r.status_code == 422 and _codigo(r) == "portal_mensaje_citado_no_valido"


def test_reacciones_se_ponen_y_se_quitan(client, admin_token, db):
    e = _escenario(client, admin_token, db, "LV8")
    mid = client.post(f"{_cli(e.conv)}/messages", json={"body": "Gracias"}).json()["data"]["message"]["id"]
    r = client.post(f"{_ope(e.conv)}/messages/{mid}/reactions", headers=auth(admin_token), json={"emoji": "👍"})
    assert r.status_code == 200 and r.json()["data"]["added"] is True
    r = client.post(f"{_cli(e.conv)}/messages/{mid}/reactions", json={"emoji": "👍"})
    assert r.status_code == 200 and r.json()["data"]["added"] is True
    mensajes = client.get(f"{_cli(e.conv)}/messages").json()["data"]["messages"]
    assert len([x for x in mensajes if x["id"] == mid][0]["reactions"]) == 2
    r = client.post(f"{_cli(e.conv)}/messages/{mid}/reactions", json={"emoji": "👍"})
    assert r.json()["data"]["added"] is False
    r = client.post(f"{_cli(e.conv)}/messages/{mid}/reactions", json={"emoji": "abc"})
    assert r.status_code == 422 and _codigo(r) == "portal_reaccion_no_valida"
    assert _auditoria(db, "livechat.reaction_added") and _auditoria(db, "livechat.reaction_removed")


# ── Aislamiento de empresa ───────────────────────────────────────────────────

def test_otra_empresa_u_otro_cliente_no_ven_ni_tocan_el_chat(client, admin_token, db):
    from app.core.errores import ErrorDeDominio
    from app.services.service_desk import chat_en_vivo
    e = _escenario(client, admin_token, db, "LV9")
    ajeno = SimpleNamespace(id=e.cliente.id, organization_id="otra-org")
    with pytest.raises(ErrorDeDominio) as exc:
        chat_en_vivo.conversacion_del_cliente(db, e.conv, ajeno)
    assert exc.value.status_code == 404
    otro_cliente = SimpleNamespace(id="otro-cliente", organization_id=e.org)
    with pytest.raises(ErrorDeDominio):
        chat_en_vivo.conversacion_del_cliente(db, e.conv, otro_cliente)
    operador_ajeno = SimpleNamespace(id="u-ajeno", organization_id="otra-org")
    with pytest.raises(ErrorDeDominio) as exc:
        chat_en_vivo.conversacion_del_operador(db, e.conv, operador_ajeno)
    assert exc.value.status_code == 404
    # Sin sesión del portal, nada.
    client.cookies.clear()
    assert client.get(f"{_cli(e.conv)}/messages").status_code in (401, 403)


# ── GRC ──────────────────────────────────────────────────────────────────────

def test_migracion_211_encadenada_e_idempotente():
    fuente = (RAIZ / "alembic/versions/211_chat_en_vivo_completo.py").read_text(encoding="utf-8")
    assert 'revision = "211_chat_en_vivo_completo"' in fuente
    assert 'down_revision = "210_chat_del_portal_colaboracion"' in fuente
    assert 'sa.Column("organization_id", sa.String(36), sa.ForeignKey("organizations.id", ondelete="CASCADE"),\n                     nullable=False)' in fuente
    assert "def downgrade" in fuente and "drop_table" in fuente and "drop_column" in fuente
    assert "batch_alter_table" in fuente


def test_retencion_y_bloqueo_legal_conocen_los_tipos_nuevos():
    from app.db.bloqueo_legal import TIPOS
    for clave in ("sd_channel_attachments", "sd_channel_message_versions", "sd_channel_calls"):
        assert clave in TIPOS
        assert TIPOS[clave].modelo().__tablename__ == clave


def test_rgpd_copia_y_suprime_lo_del_cliente(client, admin_token, db, almacen):  # noqa: F811
    from app.services.service_desk import chat_en_vivo
    e = _escenario(client, admin_token, db, "LV10")
    mid = client.post(f"{_cli(e.conv)}/messages", json={"body": "Mi teléfono es 600000000"}).json()["data"]["message"]["id"]
    client.put(f"{_cli(e.conv)}/messages/{mid}", json={"body": "Llamadme"})
    client.post(f"{_cli(e.conv)}/messages/{mid}/reactions", json={"emoji": "👍"})
    client.post(f"{_cli(e.conv)}/attachments", files={"file": ("c.png", PNG, "image/png")})
    copia = chat_en_vivo.copia_rgpd(db, [e.cliente.id], e.org)["livechat"]
    assert any(m["body"] == "Llamadme" for m in copia["messages"])
    assert copia["edits"] and copia["attachments"] and copia["reactions"]
    r = chat_en_vivo.suprimir_rgpd(db, [e.cliente.id], e.org)
    db.commit()
    assert r["attachments"] == 1 and r["reactions"] == 1 and r["edits"] >= 1
    copia = chat_en_vivo.copia_rgpd(db, [e.cliente.id], e.org)["livechat"]
    assert all(m["body"] == "[ERASED]" for m in copia["messages"])
    assert not copia["attachments"] and not copia["reactions"] and not copia["edits"]
    assert not any(k.startswith(f"livechat/{e.org}/") for k in almacen.ficheros)
