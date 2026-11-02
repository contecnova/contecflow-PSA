"""Correo entrante: hilo, contacto, organizacion, bucles, adjuntos y buzon.

Auditoria 2026-11. Antes cada correo abria un ticket nuevo `EML-xxxx`, sin
organizacion y asignado al primer administrador; la respuesta del cliente a un
aviso abria otro. Y el SMS se aceptaba sin firma de Twilio.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
from email.message import EmailMessage

import pytest

ORG = "1"


@pytest.fixture()
def contacto(db):
    from app.models.client_portal import ClientUser
    from app.models.clients import Client  # noqa: F401  (registro del mapper)

    c = ClientUser(full_name="Ana Cliente", email="ana@cliente.com", organization_id=ORG,
                   phone="+34600111222", is_active=True)
    db.add(c)
    db.commit()
    return c


def _correo(asunto="La VPN no conecta", texto="Desde esta mañana", remitente="ana@cliente.com",
            message_id=None, **cabeceras):
    from app.services.service_desk.inbound_mail import CorreoEntrante
    return CorreoEntrante(remitente=remitente, nombre="Ana", asunto=asunto, texto=texto,
                          message_id=message_id, cabeceras={k.replace("_", "-"): v for k, v in cabeceras.items()})


def _procesar(db, correo, org=ORG):
    from app.services.service_desk.inbound_mail import procesar
    r = procesar(db, org, correo)
    db.commit()
    return r


def test_un_correo_nuevo_abre_un_ticket_con_numeracion_y_contacto(db, contacto):
    from app.models.service_desk import Ticket

    r = _procesar(db, _correo(message_id="<1@x>"))
    t = db.get(Ticket, r.ticket_id)
    assert (r.accion, t.number, t.organization_id) == ("created", "INC-0001", ORG)
    assert t.requester_client_id == contacto.id, "el remitente es un contacto del portal"
    assert t.source == "email"


def test_la_respuesta_con_el_numero_en_el_asunto_va_al_mismo_ticket(db, contacto):
    from app.models.service_desk import Ticket, TicketComment

    primero = _procesar(db, _correo(message_id="<1@x>"))
    r = _procesar(db, _correo(asunto="RE: [INC-0001] La VPN no conecta", message_id="<2@x>",
                              texto="Ya funciona.\n\nEl lun, 16 mar 2026 escribió:\n> Hemos reiniciado"))
    assert (r.accion, r.ticket_id) == ("commented", primero.ticket_id)
    assert db.query(Ticket).count() == 1
    c = db.query(TicketComment).filter(TicketComment.ticket_id == primero.ticket_id).one()
    assert c.body == "Ya funciona.", "el texto citado no se quita"
    assert c.author_client_id == contacto.id and c.is_public


def test_la_respuesta_reabre_un_resuelto_y_reanuda_uno_pendiente(db, contacto):
    from app.models.service_desk import Ticket

    t = db.get(Ticket, _procesar(db, _correo(message_id="<1@x>")).ticket_id)
    for antes, n in (("resolved", 2), ("pending_client", 3)):
        t.status = antes
        db.commit()
        _procesar(db, _correo(asunto="[INC-0001] otra", message_id=f"<{n}@x>"))
        db.refresh(t)
        assert t.status.value == "in_progress", antes


def test_la_respuesta_a_un_cerrado_abre_uno_nuevo_enlazado(db, contacto):
    from app.models.service_desk import Ticket, TicketLink

    viejo = db.get(Ticket, _procesar(db, _correo(message_id="<1@x>")).ticket_id)
    viejo.status = "closed"
    db.commit()
    r = _procesar(db, _correo(asunto="[INC-0001] vuelve a fallar", message_id="<2@x>"))
    assert r.accion == "created" and r.numero == "INC-0002"
    assert db.query(TicketLink).filter(TicketLink.source_id == r.ticket_id,
                                       TicketLink.target_id == viejo.id).count() == 1


def test_un_extraño_que_cita_un_numero_no_comenta_ticket_ajeno(db, contacto):
    _procesar(db, _correo(message_id="<1@x>"))
    r = _procesar(db, _correo(asunto="[INC-0001] hola", remitente="otro@fuera.com", message_id="<2@x>"))
    assert r.accion == "created" and r.numero == "INC-0002"


@pytest.mark.parametrize("cabeceras", [
    {"auto_submitted": "auto-replied"}, {"precedence": "bulk"}, {"x_autoreply": "yes"},
])
def test_las_respuestas_automaticas_no_abren_tickets(db, contacto, cabeceras):
    from app.models.service_desk import InboundMessage, Ticket

    r = _procesar(db, _correo(message_id="<1@x>", **cabeceras))
    assert r.accion == "ignored" and db.query(Ticket).count() == 0
    assert db.query(InboundMessage).one().outcome == "ignored"


def test_el_mismo_correo_dos_veces_es_un_solo_ticket(db, contacto):
    from app.models.service_desk import Ticket

    _procesar(db, _correo(message_id="<1@x>"))
    assert _procesar(db, _correo(message_id="<1@x>")).accion == "ignored"
    _procesar(db, _correo())   # sin Message-ID: cuenta la huella
    assert _procesar(db, _correo()).accion == "ignored"
    assert db.query(Ticket).count() == 2


def test_un_correo_mime_con_adjunto_guarda_el_documento(db, contacto, monkeypatch):
    from app.models.documents import Document
    from app.services.s3_service import file_storage
    from app.services.service_desk.inbound_mail import desde_mime

    monkeypatch.setattr(file_storage, "upload_file",
                        lambda file_content, file_name, document_id, version_num, content_type: (f"k/{file_name}", len(file_content)))
    m = EmailMessage()
    m["From"] = "Ana <ana@cliente.com>"
    m["To"] = "soporte@empresa.com"
    m["Subject"] = "Captura del error"
    m["Message-ID"] = "<mime@x>"
    m.set_content("Adjunto la captura")
    m.add_attachment(b"PNGDATA", maintype="image", subtype="png", filename="error.png")
    correo = desde_mime(m.as_bytes())
    assert correo.texto.strip() == "Adjunto la captura" and correo.para == ["soporte@empresa.com"]

    from app.models.user import User
    db.query(User).filter(User.id == "admin-test-id").update({"organization_id": ORG})
    db.commit()
    r = _procesar(db, correo)
    doc = db.query(Document).filter(Document.ticket_id == r.ticket_id).one()
    assert doc.title == "error.png" and doc.created_by is not None


def test_el_webhook_identifica_la_organizacion_por_la_direccion(db, monkeypatch):
    from app.core.config import settings
    from app.models.service_desk import Ticket
    from app.models.settings import AppSetting
    from app.services.service_desk.inbound_email_service import process_inbound_email

    db.add(AppSetting(key="SD_INBOUND_ADDRESS", value="soporte@cliente-b.com", organization_id="org-b"))
    db.commit()
    monkeypatch.setattr(settings, "INBOUND_EMAIL_SECRET", "s")
    r = process_inbound_email(db, {"from": "x@y.com", "recipient": "Soporte@Cliente-B.com",
                                   "subject": "hola", "body-plain": "?"}, provided_secret="s")
    db.commit()
    from app.db.session import sin_filtro_de_tenant
    with sin_filtro_de_tenant(db):
        assert db.get(Ticket, r.ticket_id).organization_id == "org-b"


# ── El buzon ─────────────────────────────────────────────────────────────────

def test_el_buzon_procesa_marca_leidos_y_anota_los_que_fallan(db, contacto, monkeypatch):
    from app.models.service_desk import InboundMessage, Ticket
    from app.services.service_desk import buzones, inbound_mail

    leidos = []

    def crudo(mid, asunto):
        m = EmailMessage()
        m["From"], m["Subject"], m["Message-ID"] = "ana@cliente.com", asunto, mid
        m.set_content("texto")
        return m.as_bytes()

    mensajes = [buzones.Mensaje("1", crudo("<a@x>", "uno"), lambda: leidos.append("1")),
                buzones.Mensaje("2", crudo("<b@x>", "dos"), lambda: leidos.append("2"))]
    monkeypatch.setattr(buzones, "get_provider_config",
                        lambda db, p, org_id=None: {"protocol": "imap", "host": "h", "user": "u", "password": "p"})
    monkeypatch.setattr(buzones, "_leer_imap", lambda cfg, maximo: iter(mensajes))
    real = inbound_mail.procesar

    def procesar(db, org, correo):
        if correo.asunto == "dos":
            raise RuntimeError("roto")
        return real(db, org, correo)
    monkeypatch.setattr(inbound_mail, "procesar", procesar)

    assert buzones.leer_buzon(db, ORG) == {"created": 1, "commented": 0, "ignored": 0, "failed": 1}
    assert leidos == ["1", "2"], "uno que falla se marca leido: si no, se reintenta para siempre"
    assert db.query(Ticket).count() == 1
    fallo = db.query(InboundMessage).filter(InboundMessage.outcome == "failed").one()
    assert fallo.message_id == "<b@x>" and "roto" in fallo.reason


# ── SMS ──────────────────────────────────────────────────────────────────────

def _firma(token, url, params):
    datos = url + "".join(f"{k}{params[k]}" for k in sorted(params))
    return base64.b64encode(hmac.new(token.encode(), datos.encode(), hashlib.sha1).digest()).decode()


def test_un_sms_sin_firma_o_con_firma_falsa_se_rechaza(client, db, monkeypatch):
    from app.models.service_desk import Ticket
    from app.services.service_desk import multichannel_service, sms_service

    monkeypatch.setattr(sms_service, "_get_twilio_config", lambda: ("sid", "token", "+3491"))
    acuses = []
    # El acuse por SMS saldria a la API de Twilio de verdad.
    monkeypatch.setattr(multichannel_service, "send_sms", lambda to, body: acuses.append(to))
    url = "http://testserver/api/v1/sd/multichannel/inbound/sms"
    datos = {"From": "+34600111222", "To": "+3491", "Body": "hola"}
    assert client.post(url, data=datos).status_code == 403
    assert client.post(url, data=datos, headers={"X-Twilio-Signature": "falsa"}).status_code == 403
    assert db.query(Ticket).count() == 0
    ok = client.post(url, data=datos, headers={"X-Twilio-Signature": _firma("token", url, datos)})
    assert ok.status_code == 200, ok.text
    assert db.query(Ticket).count() == 1 and acuses == ["+34600111222"]


def test_sin_token_de_twilio_no_entra_ningun_sms(monkeypatch):
    from app.services.service_desk import sms_service

    monkeypatch.setattr(sms_service, "_get_twilio_config", lambda: (None, None, None))
    assert sms_service.validate_twilio_signature("u", {}, "cualquiera") is False


def test_los_avisos_piden_respuesta_a_la_direccion_de_soporte(db, contacto, monkeypatch):
    """El hilo completo: el aviso sale con Reply-To al buzon y el numero en el asunto."""
    from app.models.settings import AppSetting
    from app.services.service_desk import correo
    from app.services.service_desk.ticket_event_processor import procesar_pendientes

    salidos = []
    monkeypatch.setattr(correo, "enviar", lambda db, org, para, asunto, html, texto, *, responder_a=None:
                        salidos.append((para, asunto, responder_a)) or correo.ResultadoEnvio(True))
    from app.services.settings_service import invalidate_cache
    db.add(AppSetting(key="SD_INBOUND_ADDRESS", value="soporte@empresa.com", organization_id=ORG))
    db.commit()
    invalidate_cache("SD_INBOUND_ADDRESS")  # como hace el endpoint de ajustes
    _procesar(db, _correo(message_id="<1@x>"))
    procesar_pendientes(db)
    acuse = next(s for s in salidos if s[0] == "ana@cliente.com")
    assert acuse[2] == "soporte@empresa.com" and "[INC-0001]" in acuse[1]
    # Y la respuesta a ese asunto vuelve al mismo ticket.
    assert _procesar(db, _correo(asunto=f"RE: {acuse[1]}", message_id="<2@x>")).accion == "commented"
