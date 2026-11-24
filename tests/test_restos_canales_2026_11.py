"""Restos de canales (17-11-2026): adjuntos desde la ficha del ticket, ediciones y
borrados de los hilos de Slack, errores del operador con codigo y festivos de la
semilla por empresa (migracion 182).

Sin red: Slack y Meta son los dobles de `test_canales_tiempo_real_2026_11`.
"""
import importlib.util
import json
from pathlib import Path
import pytest
from datetime import datetime, timedelta, timezone

from app.models.service_desk import ChannelConversation, ChannelMessage, TicketComment
from tests.conftest import auth
from tests.test_canales_tiempo_real_2026_11 import (  # noqa: F401  (fixtures)
    _Resp, _credenciales, _evento, _org, _slack, _webhook, almacen, empujes, red,
)


def _evento_slack(client, evento):
    return _evento(client, {"type": "event_callback", "team_id": "T1", "event": evento,
                            "authorizations": [{"user_id": "UBOT", "is_bot": True}]})


def _auditoria(db, accion, comentario_id):
    from app.models.enterprise import AuditLog
    return (db.query(AuditLog).filter(AuditLog.action == accion, AuditLog.resource == "ticket_comment",
                                      AuditLog.resource_id == comentario_id).one())


def test_slack_edicion_y_borrado_se_reflejan_en_el_comentario(client, admin_token, db, monkeypatch, red, empujes):
    from app.services.service_desk import canal_slack
    t = _org(client, admin_token, db)
    _slack(monkeypatch, t.organization_id)
    canal_slack.vincular_hilo(db, t, "C1", "111.1")
    db.commit()
    red.cuando("users.info", _Resp({"ok": True, "user": {"profile": {"real_name": "Cliente"}}}))
    _evento_slack(client, {"type": "message", "channel": "C1", "user": "U2", "ts": "222.2", "thread_ts": "111.1",
                           "text": "Texto original"})
    db.expire_all()
    c = db.query(TicketComment).filter(TicketComment.ticket_id == t.id, TicketComment.body == "Texto original").one()
    salidas = len([x for x in red.llamadas if "chat.postMessage" in x["url"]])

    # Un bot que edita no cambia nada.
    _evento_slack(client, {"type": "message", "subtype": "message_changed", "channel": "C1",
                           "message": {"bot_id": "B1", "user": "U2", "ts": "222.2", "thread_ts": "111.1", "text": "bot"}})
    # Edicion de la persona: texto nuevo, marca y auditoria con el anterior.
    _evento_slack(client, {"type": "message", "subtype": "message_changed", "channel": "C1",
                           "message": {"user": "U2", "ts": "222.2", "thread_ts": "111.1", "text": "Texto corregido"},
                           "previous_message": {"user": "U2", "ts": "222.2", "text": "Texto original"}})
    db.expire_all()
    c = db.get(TicketComment, c.id)
    assert c.body == "Texto corregido" and c.edited_at is not None and c.retracted_at is None
    a = _auditoria(db, "UPDATE", c.id)
    assert json.loads(a.old_values)["body"] == "Texto original"

    # Borrado: comentario retirado, el original en la auditoria.
    _evento_slack(client, {"type": "message", "subtype": "message_deleted", "channel": "C1", "deleted_ts": "222.2",
                           "previous_message": {"user": "U2", "ts": "222.2", "thread_ts": "111.1",
                                                "text": "Texto corregido"}})
    db.expire_all()
    c = db.get(TicketComment, c.id)
    assert c.retracted_at is not None and c.body == ""
    assert json.loads(_auditoria(db, "RETRACT", c.id).old_values)["body"] == "Texto corregido"
    # La ficha lo marca como retirado.
    r = client.get(f"/api/v1/sd/tickets/{t.id}", headers=auth(admin_token))
    fila = next(x for x in r.json()["data"]["comments"] if x["id"] == c.id)
    assert fila["retracted_at"] and fila["edited_at"]
    # Sin bucles: nada vuelve al hilo.
    assert len([x for x in red.llamadas if "chat.postMessage" in x["url"]]) == salidas


def test_adjuntos_desde_la_ficha_del_ticket_y_errores_con_codigo(client, admin_token, db, red, empujes):
    from app.services.service_desk import adjuntos_de_canal
    t = _org(client, admin_token, db)
    org = t.organization_id
    _credenciales(db, org)
    red.cuando("/messages", _Resp({"messages": [{"id": "wamid.OUT"}]}))
    red.cuando("/media", _Resp({"id": "MEDIA-UP"}))
    _webhook(client, {"from": "34600", "id": "wamid.1", "type": "text", "text": {"body": "Hola"}})
    db.expire_all()
    conv = db.query(ChannelConversation).filter(ChannelConversation.channel == "whatsapp").one()
    from app.models.service_desk import Ticket
    ticket = db.get(Ticket, conv.ticket_id)
    doc = adjuntos_de_canal.guardar(db, ticket, nombre="guia.pdf", tipo="application/pdf",
                                    contenido=b"%PDF-1.4\n" + b"0" * 32, origen="test")
    db.commit()

    r = client.get(f"/api/v1/sd/channels/tickets/{ticket.id}/conversations", headers=auth(admin_token))
    assert r.status_code == 200, r.text
    datos = r.json()["data"]
    assert [c["id"] for c in datos["conversations"]] == [conv.id]
    assert [a["id"] for a in datos["attachments"]] == [doc.document_id]
    # Un ticket que no existe en la empresa: 404 con codigo.
    r = client.get("/api/v1/sd/channels/tickets/no-existe/conversations", headers=auth(admin_token))
    assert r.status_code == 404 and r.json()["code"] == "ticket_no_encontrado"

    # Fuera de la ventana de 24 h: 409 con codigo del catalogo del operador.
    conv = db.get(ChannelConversation, conv.id)
    conv.last_inbound_at = datetime.now(timezone.utc) - timedelta(hours=30)
    db.commit()
    r = client.post(f"/api/v1/sd/channels/conversations/{conv.id}/attachments", headers=auth(admin_token),
                    json={"document_id": doc.document_id})
    assert r.status_code == 409 and r.json()["code"] == "whatsapp_adjunto_fuera_de_ventana"
    r = client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                    json={"body": "¿Sigue?"})
    assert r.status_code == 409 and r.json()["code"] == "whatsapp_fuera_de_ventana"
    assert db.query(ChannelMessage).filter(ChannelMessage.attachment_document_id == doc.document_id).count() == 0


def test_slack_sin_token_es_409_con_codigo(client, admin_token, db, monkeypatch, red, empujes):
    from app.services.service_desk import canal_slack
    t = _org(client, admin_token, db)
    _slack(monkeypatch, t.organization_id)
    monkeypatch.setattr(canal_slack, "token_del_bot", lambda db, o: None)
    conv = canal_slack.vincular_hilo(db, t, "C1", "111.1")
    db.commit()
    r = client.post(f"/api/v1/sd/channels/conversations/{conv.id}/reply", headers=auth(admin_token),
                    json={"body": "Hola"})
    assert r.status_code == 409 and r.json()["code"] == "slack_sin_token"


def test_festivos_sin_empresa_pasan_a_cada_empresa(db):
    """Paso de datos de la migracion 182 (idempotente).

    24-11-2026 (migración 208, empresa obligatoria): `holidays.organization_id` ya es
    NOT NULL en el esquema de los modelos, así que el festivo sin empresa no cabe en la
    base de los tests. El paso de la 182 se prueba sobre una base aparte con las tablas
    como estaban en la 182 (empresa opcional), y en la base actual se comprueba que la
    fila sin empresa ya no puede existir.
    """
    import uuid
    from datetime import date
    import sqlalchemy as sa
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError
    ruta = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "182_comentarios_de_canal_y_festivos_por_empresa.py"
    spec = importlib.util.spec_from_file_location("migracion_182", ruta)
    migracion = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracion)

    motor = sa.create_engine("sqlite://")
    orgs = ["org-a", "org-b"]
    with motor.begin() as con:
        con.execute(text("CREATE TABLE organizations (id VARCHAR(36) PRIMARY KEY)"))
        con.execute(text("CREATE TABLE holidays (id VARCHAR(36) PRIMARY KEY, organization_id VARCHAR(36), "
                         "name VARCHAR(200) NOT NULL, date DATE NOT NULL, type VARCHAR(40), "
                         "applies_to VARCHAR(40), office_id VARCHAR(36))"))
        for org in orgs:
            con.execute(text("INSERT INTO organizations (id) VALUES (:id)"), {"id": org})
        con.execute(text("INSERT INTO holidays (id, organization_id, name, date, type) "
                         "VALUES (:id, NULL, 'Fiesta global', :d, 'national')"),
                    {"id": str(uuid.uuid4()), "d": date(2026, 12, 8)})
    with motor.begin() as con:
        assert migracion.festivos_por_empresa(con) == len(orgs)
    with motor.begin() as con:
        for org in orgs:
            assert con.execute(text("SELECT COUNT(*) FROM holidays WHERE organization_id = :o "
                                    "AND name = 'Fiesta global'"), {"o": org}).scalar() == 1
        assert con.execute(text("SELECT COUNT(*) FROM holidays WHERE organization_id IS NULL")).scalar() == 0
        assert migracion.festivos_por_empresa(con) == 0
    motor.dispose()

    # En la base actual (208) el festivo sin empresa ya no cabe.
    with pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO holidays (id, organization_id, name, date, type) "
                        "VALUES (:id, NULL, 'Fiesta global', :d, 'national')"),
                   {"id": str(uuid.uuid4()), "d": date(2026, 12, 8)})
    db.rollback()
