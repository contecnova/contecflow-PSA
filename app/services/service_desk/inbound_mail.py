"""Correo entrante al Service Desk: de un correo a un ticket, o a su comentario.

Auditoria 2026-11. La entrada de correo era un webhook que abria SIEMPRE un
ticket nuevo (`EML-xxxx`, fuera de la numeracion), asignado al primer
administrador, sin organizacion y sin reconocer al remitente. La respuesta del
cliente a un aviso abria otro ticket. Ahora, venga del buzon (IMAP o
Microsoft 365, ver `buzones.py`) o de una pasarela por webhook:

1. Se descartan los correos automaticos (fuera de oficina, rebotes, listas) y
   los repetidos: sin eso, dos sistemas que se contestan solos se llenan de
   tickets.
2. Si el asunto lleva `[INC-0042]` —lo ponen todos los avisos— es una
   respuesta: se añade como comentario del solicitante. Un ticket resuelto se
   reabre; uno cerrado o cancelado da lugar a uno nuevo enlazado.
3. Si no, se crea el ticket por el camino de siempre: numeracion, politica de
   SLA, reglas de enrutado y asignacion automatica.
4. El remitente se reconoce como contacto del portal o como usuario interno.
5. Los adjuntos se guardan como documentos del ticket.
"""
from __future__ import annotations

import email
import email.policy
import hashlib
import html
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from typing import Optional

from sqlalchemy.orm import Session

from app.models.client_portal import ClientUser
from app.models.service_desk import (
    InboundMessage,
    Ticket,
    TicketComment,
    TicketLink,
    TicketLinkType,
    TicketStatus,
)
from app.models.user import User, UserRole
from app.services import settings_service as _ss
from app.services.service_desk.ticket_events import como_organizacion
from app.services.sla_service import TICKET_PREFIXES

logger = logging.getLogger(__name__)

#: `[INC-0042]` con cualquiera de los prefijos de ticket.
_MARCA = re.compile(r"\[(" + "|".join(sorted(set(TICKET_PREFIXES.values()) | {"TKT"})) + r")-(\d{1,9})\]")

#: Donde empieza el texto citado de una respuesta, en los clientes habituales.
_CORTES_DE_CITA = [
    re.compile(p, re.IGNORECASE | re.MULTILINE) for p in (
        r"^\s*-{2,}\s*(original message|mensaje original|forwarded message|mensaje reenviado)\s*-{2,}",
        r"^\s*On .{3,200}wrote:\s*$",
        r"^\s*El .{3,200}escribi[oó]:\s*$",
        r"^\s*Le .{3,200}a écrit\s*:\s*$",
        r"^\s*(From|De|Von)\s*:\s.+$",
        r"^\s*_{10,}\s*$",
    )
]

_REMITENTES_AUTOMATICOS = re.compile(r"^(mailer-daemon|postmaster|no-?reply|do-?not-?reply)@", re.IGNORECASE)


@dataclass
class Adjunto:
    nombre: str
    tipo: str
    contenido: bytes


@dataclass
class CorreoEntrante:
    remitente: str
    nombre: str
    asunto: str
    texto: str
    message_id: Optional[str] = None
    para: list[str] = field(default_factory=list)
    cabeceras: dict = field(default_factory=dict)
    adjuntos: list[Adjunto] = field(default_factory=list)


@dataclass
class Resultado:
    accion: str                    # created | commented | ignored
    ticket_id: Optional[str] = None
    numero: Optional[str] = None
    motivo: Optional[str] = None


# ── Lectura del mensaje ──────────────────────────────────────────────────────

def _html_a_texto(contenido: str) -> str:
    sin_bloques = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", "", contenido)
    con_saltos = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>", "\n", sin_bloques)
    texto = html.unescape(re.sub(r"<[^>]+>", "", con_saltos))
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def desde_mime(crudo: bytes) -> CorreoEntrante:
    """Un correo RFC 822 tal como lo entregan IMAP o Microsoft 365."""
    msg: EmailMessage = email.message_from_bytes(crudo, policy=email.policy.default)
    nombre, remitente = parseaddr(str(msg.get("From", "")))
    cuerpo = msg.get_body(preferencelist=("plain", "html"))
    texto = ""
    if cuerpo is not None:
        contenido = cuerpo.get_content()
        texto = _html_a_texto(contenido) if cuerpo.get_content_type() == "text/html" else contenido
    adjuntos = []
    for parte in msg.iter_attachments():
        datos = parte.get_payload(decode=True)
        if datos:
            adjuntos.append(Adjunto(parte.get_filename() or "adjunto", parte.get_content_type(), datos))
    para = [a for _, a in getaddresses(msg.get_all("To", []) + msg.get_all("Cc", []) + msg.get_all("Delivered-To", []))]
    return CorreoEntrante(
        remitente=remitente.strip().lower(), nombre=nombre.strip(), asunto=str(msg.get("Subject", "")).strip(),
        texto=texto, message_id=(msg.get("Message-ID") or "").strip() or None,
        para=[p.lower() for p in para if p],
        cabeceras={k.lower(): str(v) for k, v in msg.items()},
        adjuntos=adjuntos,
    )


def desde_webhook(payload: dict) -> CorreoEntrante:
    """El formato de las pasarelas (Mailgun, Postmark, SendGrid)."""
    nombre, remitente = parseaddr(str(payload.get("from") or payload.get("From") or payload.get("sender") or ""))
    texto = payload.get("stripped-text") or payload.get("body-plain") or payload.get("text") or payload.get("TextBody")
    if not texto:
        texto = _html_a_texto(str(payload.get("html") or payload.get("body-html") or payload.get("HtmlBody") or ""))
    destino = str(payload.get("recipient") or payload.get("to") or payload.get("To") or "")
    cabeceras = {}
    for clave in ("auto-submitted", "precedence", "x-autoreply", "x-autorespond"):
        for variante in (clave, clave.title()):
            if variante in payload:
                cabeceras[clave] = str(payload[variante])
    return CorreoEntrante(
        remitente=remitente.strip().lower(), nombre=nombre.strip(),
        asunto=str(payload.get("subject") or payload.get("Subject") or "").strip(),
        texto=str(texto), message_id=str(payload.get("Message-Id") or payload.get("message-id")
                                          or payload.get("MessageID") or "").strip() or None,
        para=[a.lower() for _, a in getaddresses([destino]) if a],
        cabeceras=cabeceras,
    )


def es_automatico(correo: CorreoEntrante) -> Optional[str]:
    """El motivo si es un correo que nadie ha escrito; None si es de una persona."""
    c = correo.cabeceras
    if (c.get("auto-submitted") or "no").strip().lower() != "no":
        return "auto-submitted"
    if c.get("x-autoreply") or c.get("x-autorespond"):
        return "respuesta automática"
    if (c.get("precedence") or "").strip().lower() in {"bulk", "junk", "list", "auto_reply"}:
        return "envío masivo"
    if _REMITENTES_AUTOMATICOS.match(correo.remitente or ""):
        return "remitente automático"
    return None


def quitar_cita(texto: str) -> str:
    """Lo que el cliente ha escrito, sin el correo anterior citado debajo."""
    corte = len(texto)
    for patron in _CORTES_DE_CITA:
        m = patron.search(texto)
        if m and m.start() < corte:
            corte = m.start()
    lineas = [li for li in texto[:corte].splitlines() if not li.lstrip().startswith(">")]
    return "\n".join(lineas).strip()


# ── Organizacion, contacto y ticket ──────────────────────────────────────────

def organizacion_por_direccion(db: Session, direcciones: list[str]) -> Optional[str]:
    """La organizacion cuya direccion de soporte (`SD_INBOUND_ADDRESS`) recibio el correo."""
    from app.db.session import sin_filtro_de_tenant
    from app.models.settings import AppSetting

    buscadas = {d.strip().lower() for d in direcciones if d}
    if not buscadas:
        return None
    with sin_filtro_de_tenant(db):
        filas = db.query(AppSetting).filter(AppSetting.key == "SD_INBOUND_ADDRESS").all()
    for fila in filas:
        if (fila.value or "").strip().lower() in buscadas and fila.organization_id:
            return fila.organization_id
    return None


@dataclass
class Contacto:
    email: str
    nombre: str
    usuario: Optional[User] = None
    cliente: Optional[ClientUser] = None


def contacto_de(db: Session, correo: CorreoEntrante) -> Contacto:
    """Quien escribe: contacto del portal, usuario interno o un externo sin cuenta."""
    from sqlalchemy import func

    cliente = db.query(ClientUser).filter(func.lower(ClientUser.email) == correo.remitente,
                                          ClientUser.is_active == True).first()  # noqa: E712
    if cliente is not None:
        return Contacto(correo.remitente, cliente.full_name, cliente=cliente)
    usuario = db.query(User).filter(func.lower(User.email) == correo.remitente,
                                    User.is_active == True).first()  # noqa: E712
    if usuario is not None:
        return Contacto(correo.remitente, usuario.full_name, usuario=usuario)
    return Contacto(correo.remitente, correo.nombre or correo.remitente)


def ticket_citado(db: Session, asunto: str) -> Optional[Ticket]:
    m = _MARCA.search(asunto or "")
    if not m:
        return None
    return db.query(Ticket).filter(Ticket.number == f"{m.group(1)}-{m.group(2).zfill(4)}").first()


def clave_del_mensaje(correo: CorreoEntrante) -> str:
    """El Message-ID; sin él, una huella estable del remitente, asunto y texto.

    Estable entre procesos: `hash()` de Python cambia en cada arranque, y dos
    workers no reconocerian el mismo correo.
    """
    if correo.message_id:
        return correo.message_id[:255]
    huella = hashlib.sha1(f"{correo.remitente}|{correo.asunto}|{correo.texto}".encode(), usedforsecurity=False)
    return f"sin-id:{huella.hexdigest()}"


def _es_del_ticket(ticket: Ticket, contacto: Contacto) -> bool:
    """Si quien responde puede comentar el ticket: el solicitante o alguien de dentro."""
    if contacto.usuario is not None:
        return True
    if contacto.cliente is not None:
        return contacto.cliente.id == ticket.requester_client_id or (
            ticket.client_id is not None and contacto.cliente.client_org_id == ticket.client_id)
    return bool(ticket.requester_email) and ticket.requester_email.lower() == contacto.email


def _comentar(db: Session, ticket: Ticket, contacto: Contacto, texto: str) -> None:
    from app.schemas.service_desk import TicketUpdateIn
    from app.services.service_desk.ticket_update_service import apply_ticket_update

    db.add(TicketComment(
        ticket_id=ticket.id, organization_id=ticket.organization_id, body=texto, is_public=True,
        author_user_id=contacto.usuario.id if contacto.usuario else None,
        author_client_id=contacto.cliente.id if contacto.cliente else None,
        author_name=None if (contacto.usuario or contacto.cliente) else contacto.nombre,
    ))
    estado = getattr(ticket.status, "value", ticket.status)
    nuevo = None
    if estado in ("pending_client", "pending_third"):
        nuevo = "in_progress"   # el cliente ha contestado: el reloj vuelve a correr
    elif estado == "resolved" and _ss.get_runtime_bool(db, "SD_REOPEN_ON_REPLY", ticket.organization_id):
        nuevo = "in_progress"
    if nuevo:
        apply_ticket_update(db, ticket, ticket.id, TicketUpdateIn(status=nuevo), current_user_id=None,
                            old_assigned_to=ticket.assigned_to_user_id, old_support_level=ticket.support_level)


def _guardar_adjuntos(db: Session, ticket: Ticket, correo: CorreoEntrante) -> list[str]:
    """Los adjuntos como documentos del ticket. Devuelve los que no caben."""
    from app.models.documents import Document, DocumentCategory, DocumentVersion
    from app.services.s3_service import file_storage

    if not correo.adjuntos:
        return []
    limite = _ss.get_runtime_int(db, "SD_MAIL_MAX_ATTACHMENT_MB", ticket.organization_id) * 1024 * 1024
    # El documento necesita un usuario dueño: el agente, quien lo creo o un
    # administrador. Sin dueño de la organizacion, el acceso por documento lo
    # esconderia de los agentes.
    dueño = ticket.assigned_to_user_id or ticket.created_by_user_id
    if dueño is None:
        admin = db.query(User.id).filter(User.role == UserRole.admin, User.is_active == True,  # noqa: E712
                                         User.organization_id == ticket.organization_id).first()
        dueño = admin[0] if admin else None
    fuera = []
    for adj in correo.adjuntos:
        if dueño is None or len(adj.contenido) > limite:
            fuera.append(adj.nombre)
            continue
        clave, tamaño = file_storage.upload_file(
            file_content=adj.contenido, file_name=adj.nombre, document_id=ticket.id,
            version_num=1, content_type=adj.tipo,
        )
        doc = Document(title=adj.nombre, description=f"Adjunto del correo de {correo.remitente}",
                       category=DocumentCategory.other, ticket_id=ticket.id,
                       organization_id=ticket.organization_id, created_by=dueño)
        db.add(doc)
        db.flush()
        db.add(DocumentVersion(document_id=doc.id, version_num=1, file_key=clave, file_name=adj.nombre,
                               file_size=tamaño, file_mime_type=adj.tipo, change_note="Correo entrante",
                               created_by=dueño, organization_id=ticket.organization_id))
    return fuera


def _crear_ticket(db: Session, org_id: Optional[str], correo: CorreoEntrante, contacto: Contacto,
                  texto: str, sigue_a: Optional[Ticket] = None) -> Ticket:
    from app.services.service_desk.ticket_creation_service import build_channel_ticket

    descripcion = texto or "(sin texto)"
    if sigue_a is not None:
        descripcion = f"Sigue a {sigue_a.number}, que estaba cerrado.\n\n{descripcion}"
    ticket = build_channel_ticket(
        db, org_id=org_id, titulo=(correo.asunto or "(sin asunto)")[:500], descripcion=descripcion,
        source="email", requester_user=contacto.usuario, requester_client=contacto.cliente,
        requester_name=contacto.nombre, requester_email=contacto.email,
    )
    if sigue_a is not None:
        db.add(TicketLink(source_id=ticket.id, target_id=sigue_a.id, link_type=TicketLinkType.relates_to,
                          organization_id=org_id))
    return ticket


def procesar(db: Session, org_id: Optional[str], correo: CorreoEntrante) -> Resultado:
    """Convierte un correo en ticket o comentario. No confirma la transaccion."""
    with como_organizacion(db, org_id):
        clave = clave_del_mensaje(correo)
        if db.query(InboundMessage.id).filter(InboundMessage.message_id == clave).first():
            return Resultado("ignored", motivo="ya procesado")

        motivo = es_automatico(correo) or (None if correo.remitente else "sin remitente")
        if motivo:
            resultado = Resultado("ignored", motivo=motivo)
        else:
            contacto = contacto_de(db, correo)
            texto = quitar_cita(correo.texto)
            citado = ticket_citado(db, correo.asunto)
            if citado is not None and _es_del_ticket(citado, contacto):
                estado = getattr(citado.status, "value", citado.status)
                if estado in (TicketStatus.closed.value, TicketStatus.cancelled.value):
                    ticket = _crear_ticket(db, org_id, correo, contacto, texto, sigue_a=citado)
                    resultado = Resultado("created", ticket.id, ticket.number)
                else:
                    _comentar(db, citado, contacto, texto or "(sin texto)")
                    ticket = citado
                    resultado = Resultado("commented", ticket.id, ticket.number)
            else:
                ticket = _crear_ticket(db, org_id, correo, contacto, texto)
                resultado = Resultado("created", ticket.id, ticket.number)
            db.flush()
            fuera = _guardar_adjuntos(db, ticket, correo)
            if fuera:
                db.add(TicketComment(ticket_id=ticket.id, organization_id=ticket.organization_id, is_public=False,
                                     body="Adjuntos no guardados (tamaño o sin agente): " + ", ".join(fuera)))
        # Si otro worker procesa el mismo correo a la vez, la restriccion unica
        # tumba esta transaccion entera y su ticket no llega a existir.
        db.add(InboundMessage(organization_id=org_id, message_id=clave, channel="email",
                              sender=correo.remitente[:255] or None, ticket_id=resultado.ticket_id,
                              outcome=resultado.accion, reason=resultado.motivo,
                              received_at=datetime.now(timezone.utc)))
    return resultado
