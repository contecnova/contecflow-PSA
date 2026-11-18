"""Conversaciones de los canales del service desk (mejoras de mercado 16-11-2026).

Un canal conversacional (WhatsApp, chat en vivo del portal) guarda la
conversacion (`sd_channel_conversations`) y sus mensajes
(`sd_channel_messages`) y la ata a un ticket, que es lo que trabaja el equipo:

- El primer mensaje del cliente abre el ticket por el camino de siempre de los
  canales (`build_channel_ticket`: numeracion, SLA, enrutado, asignacion y
  avisos). Los siguientes son comentarios publicos del ticket.
- En el chat en vivo la conversacion empieza con el asistente (`bot`): contesta
  con los articulos de la base de conocimiento que encajan; el cliente puede
  pedir una persona (`waiting_agent`) y un agente la toma (`agent`). Es el
  traspaso a agente.
- Lo que el agente escribe en la conversacion va al cliente por su canal y
  queda tambien como comentario publico del ticket.

Todo se acota a la empresa de la conversacion; las listas para el agente, a la
de quien mira.

Canales en tiempo real (17-11-2026):

- Cada mensaje, traspaso y cierre se empuja por WebSocket al cliente y a los
  operadores con la bandeja abierta (`canales_en_vivo`), despues de confirmar.
- Slack (hilos) y WhatsApp salen por `salida_por_canales`; el mensaje guarda
  el comentario del ticket que es (`ticket_comment_id`) para que la bandeja de
  eventos del ticket no lo vuelva a enviar.
- Un mensaje entrante puede traer un adjunto (`adjuntos_de_canal.Fichero`): se
  guarda como documento del ticket con sus comprobaciones.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.codigos_de_error import error as error_con_codigo
from app.models.service_desk import ChannelConversation, ChannelMessage, Ticket, TicketComment
from app.models.service_desk._enums import ESTADOS_DE_TICKET_CERRADOS

CANALES = ("whatsapp", "livechat", "slack", "teams")
ESTADOS = ("bot", "waiting_agent", "agent", "closed")
#: Cuantos articulos sugiere el asistente del chat como mucho.
MAX_SUGERENCIAS_DEL_BOT = 3
#: Largo maximo de un mensaje de un canal (WhatsApp admite 4096).
MAX_MENSAJE = 4096


def _ahora():
    return datetime.now(timezone.utc)


def abrir_o_seguir(db: Session, org_id, canal: str, external_id: Optional[str], *, client_user=None,
                   visitor_name: Optional[str] = None, language: Optional[str] = None) -> ChannelConversation:
    """La conversacion abierta de ese interlocutor en ese canal, o una nueva."""
    if canal not in CANALES:
        raise error_con_codigo(422, "canal_desconocido")
    q = db.query(ChannelConversation).filter(
        ChannelConversation.organization_id == org_id, ChannelConversation.channel == canal,
        ChannelConversation.status != "closed")
    if external_id:
        q = q.filter(ChannelConversation.external_id == external_id)
    elif client_user is not None:
        q = q.filter(ChannelConversation.client_user_id == client_user.id)
    conv = q.order_by(ChannelConversation.created_at.desc()).first() if (external_id or client_user) else None
    if conv is not None and conv.ticket_id:
        ticket = db.get(Ticket, conv.ticket_id)
        if ticket is not None and getattr(ticket.status, "value", ticket.status) in ESTADOS_DE_TICKET_CERRADOS:
            conv.status = "closed"
            conv = None
    if conv is None:
        conv = ChannelConversation(
            organization_id=org_id, channel=canal, external_id=external_id,
            client_user_id=client_user.id if client_user is not None else None,
            visitor_name=(visitor_name or (client_user.full_name if client_user is not None else None) or None),
            language=(language or None), status="bot" if canal == "livechat" else "waiting_agent",
        )
        db.add(conv)
        db.flush()
    return conv


def anotar(db: Session, conv: ChannelConversation, direction: str, author_type: str, body: str,
           author_user_id: Optional[str] = None, external_message_id: Optional[str] = None) -> Optional[ChannelMessage]:
    """Guarda el mensaje. Un mensaje externo repetido (reintento del canal) se ignora: None."""
    texto = (body or "").strip()[:MAX_MENSAJE]
    if not texto:
        raise error_con_codigo(422, "mensaje_vacio")
    if external_message_id and db.query(ChannelMessage.id).filter(
            ChannelMessage.conversation_id == conv.id,
            ChannelMessage.external_message_id == external_message_id).first():
        return None
    m = ChannelMessage(organization_id=conv.organization_id, conversation_id=conv.id, direction=direction,
                       author_type=author_type, author_user_id=author_user_id, body=texto,
                       external_message_id=external_message_id)
    db.add(m)
    conv.last_message_at = _ahora()
    if direction == "in":
        conv.last_inbound_at = conv.last_message_at
    db.flush()
    return m


def _asegurar_ticket(db: Session, conv: ChannelConversation, primer_texto: str, client_user=None,
                     telefono: Optional[str] = None) -> Ticket:
    if conv.ticket_id:
        t = db.get(Ticket, conv.ticket_id)
        if t is not None:
            return t
    from app.services.service_desk.ticket_creation_service import build_channel_ticket
    nombre = conv.visitor_name or (client_user.full_name if client_user is not None else None)
    ticket = build_channel_ticket(
        db, org_id=conv.organization_id, titulo=primer_texto.splitlines()[0][:200] or conv.channel,
        descripcion=primer_texto, source=conv.channel, requester_client=client_user,
        requester_name=nombre, requester_email=getattr(client_user, "email", None), requester_phone=telefono,
    )
    conv.ticket_id = ticket.id
    db.flush()
    return ticket


def _reactivar(ticket: Ticket) -> None:
    """Responde el cliente a un ticket que esperaba por el: vuelve a curso y el SLA sigue
    (lo mismo que `comment_service.add_client_comment`)."""
    from app.models.service_desk import TicketStatus
    if ticket.status != TicketStatus.pending_client:
        return
    ticket.status = TicketStatus.in_progress
    if ticket.sla_paused_at:
        pausa = ticket.sla_paused_at if ticket.sla_paused_at.tzinfo else ticket.sla_paused_at.replace(tzinfo=timezone.utc)
        ticket.sla_pause_minutes = (ticket.sla_pause_minutes or 0) + int((_ahora() - pausa).total_seconds() / 60)
        ticket.sla_paused_at = None


def _guardar_adjuntos(db: Session, conv: ChannelConversation, ticket: Ticket, m: ChannelMessage, adjuntos) -> str:
    """Guarda el adjunto (o la lista) en el ticket y devuelve la nota que se anade al texto.
    El mensaje apunta al primero que se guarda."""
    from app.services.service_desk import adjuntos_de_canal
    notas = []
    for adjunto in (adjuntos if isinstance(adjuntos, list) else [adjuntos]):
        r = adjuntos_de_canal.guardar(db, ticket, nombre=adjunto.nombre, tipo=adjunto.tipo,
                                      contenido=adjunto.contenido, origen=conv.channel,
                                      descripcion=f"{conv.channel}: {conv.visitor_name or ''}".strip())
        if r.document_id:
            m.attachment_document_id = m.attachment_document_id or r.document_id
            notas.append(f"[adjunto: {r.nombre}]")
        else:
            notas.append(f"[adjunto rechazado ({r.motivo}): {r.nombre}]")
    return "\n".join(notas)


def mensaje_del_cliente(db: Session, conv: ChannelConversation, texto: str, *, client_user=None,
                        telefono: Optional[str] = None, external_message_id: Optional[str] = None,
                        con_bot: bool = False, autor_usuario=None, autor_nombre: Optional[str] = None,
                        adjunto=None, nota_de_adjunto: Optional[str] = None) -> dict:
    """Lo que escribe el cliente: se guarda, va al ticket y, en modo `bot`, se contesta.

    `autor_usuario` / `autor_nombre` (hilos de Slack): quien escribio, si no es
    el cliente de la conversacion. `adjunto` (`adjuntos_de_canal.Fichero`): se
    guarda en el ticket; `nota_de_adjunto`: lo que se anota si no se pudo bajar.

    Devuelve `{"message": ..., "bot": [...articulos...] | None, "duplicate": bool}`.
    """
    m = anotar(db, conv, "in", "customer", texto, external_message_id=external_message_id)
    if m is None:
        return {"message": None, "bot": None, "duplicate": True}
    sugerencias = None
    respuesta_del_bot = None
    if con_bot and conv.status == "bot":
        from app.services.service_desk.kb_sugerencias import sugerir
        sugerencias = sugerir(db, texto, solo_publico=True, limite=MAX_SUGERENCIAS_DEL_BOT)
        if sugerencias:
            # Traduccion en tiempo real: los articulos, en su version publicada
            # en el idioma del cliente si la hay.
            from app.services.traduccion.kb import localizar
            from app.services.traduccion.salida import idioma_del_cliente
            sugerencias = localizar(db, sugerencias, idioma_del_cliente(db, conv=conv)[0])
            respuesta_del_bot = anotar(db, conv, "out", "bot", "\n".join(
                f"{s.get('number') or ''} {s.get('title')}".strip() for s in sugerencias))
    else:
        nuevo = conv.ticket_id is None
        ticket = _asegurar_ticket(db, conv, texto, client_user=client_user, telefono=telefono)
        notas = [n for n in (nota_de_adjunto, _guardar_adjuntos(db, conv, ticket, m, adjunto) if adjunto else None) if n]
        if notas:
            m.body = (m.body + "\n" + "\n".join(notas))[:MAX_MENSAJE]
        if nuevo:
            # El primer mensaje ya es la descripcion del ticket; los demas, comentarios.
            if notas:
                ticket.description = (ticket.description or "") + "\n" + "\n".join(notas)
        else:
            es_interno = autor_usuario is not None
            comentario = TicketComment(
                ticket_id=ticket.id, body=m.body, is_public=True,
                author_user_id=autor_usuario.id if es_interno else None,
                author_client_id=client_user.id if (client_user is not None and not es_interno) else None,
                author_name=None if (es_interno or client_user is not None) else (autor_nombre or conv.visitor_name))
            db.add(comentario)
            db.flush()
            m.ticket_comment_id = comentario.id
            if not es_interno:
                _reactivar(ticket)
    db.commit()
    from app.services.service_desk import canales_en_vivo
    canales_en_vivo.avisar_mensaje(db, conv, m)
    if respuesta_del_bot is not None:
        canales_en_vivo.avisar_mensaje(db, conv, respuesta_del_bot)
    return {"message": serializar_mensaje(m), "bot": sugerencias, "duplicate": False}


def pedir_agente(db: Session, conv: ChannelConversation, client_user=None) -> ChannelConversation:
    """El cliente pide una persona: la conversacion espera agente y nace su ticket."""
    if conv.status == "closed":
        raise error_con_codigo(409, "conversacion_cerrada")
    if conv.status == "bot":
        primeros = [m.body for m in db.query(ChannelMessage).filter(
            ChannelMessage.conversation_id == conv.id, ChannelMessage.author_type == "customer")
            .order_by(ChannelMessage.created_at).all()]
        _asegurar_ticket(db, conv, "\n".join(primeros) or conv.channel, client_user=client_user)
        conv.status = "waiting_agent"
        aviso = anotar(db, conv, "out", "system", "waiting_agent")
        db.commit()
        from app.services.service_desk import canales_en_vivo
        canales_en_vivo.avisar_mensaje(db, conv, aviso)
        canales_en_vivo.avisar_estado(db, conv)
    db.commit()
    return conv


def del_cliente(db: Session, conv_id: str, client_user) -> ChannelConversation:
    """La conversacion de ese cliente del portal; 404 si no es suya."""
    conv = db.query(ChannelConversation).filter(ChannelConversation.id == conv_id,
                                                ChannelConversation.client_user_id == client_user.id).first()
    if conv is None:
        raise error_con_codigo(404, "conversacion_no_encontrada")
    return conv


def abrir_chat_del_portal(db: Session, client_user, texto: Optional[str],
                          language: Optional[str] = None) -> dict:
    """Abre (o sigue) el chat en vivo del cliente y, si trae texto, lo anota.

    Devuelve `{"conversation", "messages", "bot"}` para el portal.
    """
    conv = abrir_o_seguir(db, client_user.organization_id, "livechat", None, client_user=client_user,
                          language=language)
    respuesta = None
    if texto and texto.strip():
        respuesta = mensaje_del_cliente(db, conv, texto, client_user=client_user, con_bot=True)
    db.commit()
    return {"conversation": serializar(db, conv), "messages": mensajes(db, conv, para_cliente=True),
            "bot": (respuesta or {}).get("bot")}


def _de_la_empresa(db: Session, conv_id: str, org_id) -> ChannelConversation:
    conv = db.query(ChannelConversation).filter(ChannelConversation.id == conv_id,
                                                ChannelConversation.organization_id == org_id).first()
    if conv is None:
        raise error_con_codigo(404, "conversacion_no_encontrada")
    return conv


def tomar(db: Session, conv_id: str, agente) -> ChannelConversation:
    conv = _de_la_empresa(db, conv_id, agente.organization_id)
    if conv.status == "closed":
        raise error_con_codigo(409, "conversacion_cerrada")
    conv.status = "agent"
    conv.assigned_user_id = agente.id
    if conv.ticket_id:
        t = db.get(Ticket, conv.ticket_id)
        if t is not None and not t.assigned_to_user_id:
            t.assigned_to_user_id = agente.id
    aviso = anotar(db, conv, "out", "system", "agent_joined", author_user_id=agente.id)
    db.commit()
    from app.services.service_desk import canales_en_vivo
    canales_en_vivo.avisar_mensaje(db, conv, aviso)
    canales_en_vivo.avisar_estado(db, conv)
    return conv


def responder(db: Session, conv_id: str, agente, texto: str, *, client_text: Optional[str] = None,
              client_language: Optional[str] = None) -> ChannelMessage:
    """El agente contesta: va al cliente por su canal y al ticket como comentario publico.

    Traduccion en tiempo real (16-11-2026): sale en el idioma del cliente
    (`traduccion.salida`): la vista previa (`client_text`) o, sin ella, la
    traduccion automatica si la empresa la quiere. Se traduce UNA vez: el
    comentario del ticket lleva la misma version.

    17-11-2026: WhatsApp y Slack salen por `salida_por_canales` (ventana de 24 h
    y plantilla en WhatsApp; el hilo del ticket en Slack). Fuera de la ventana y
    sin plantilla no se guarda nada: 409.
    """
    from app.services.service_desk import canales_en_vivo, salida_por_canales
    from app.services.traduccion import salida as _salida

    conv = _de_la_empresa(db, conv_id, agente.organization_id)
    if conv.status == "closed":
        raise error_con_codigo(409, "conversacion_cerrada")
    salida_por_canales.exigir_que_se_pueda_enviar(db, conv)
    if conv.status != "agent":
        conv.status, conv.assigned_user_id = "agent", agente.id
    canal = conv.channel if conv.channel in CANALES else "livechat"
    prep = _salida.preparar(db, conv.organization_id, canal, texto, usuario=agente, conv=conv,
                            texto_cliente=client_text, idioma_cliente=client_language)
    m = anotar(db, conv, "out", "agent", prep.cuerpo, author_user_id=agente.id)
    m.language = prep.idioma
    _salida.anotar_autor(db, conv.organization_id, "channel_message", m.id, prep, agente, "channel_message")
    if conv.ticket_id:
        from app.services.service_desk.comment_service import add_internal_comment
        t = db.get(Ticket, conv.ticket_id)
        if t is not None:
            comentario = add_internal_comment(db, t, t.id, texto, True, agente, salida=prep)
            db.flush()
            m.ticket_comment_id = comentario.id
    db.flush()
    salida_por_canales.entregar(db, conv, m, _salida.texto_para_cliente(
        db, conv.organization_id, "channel_message", m.id, prep.cuerpo), autor=agente.full_name)
    db.commit()
    canales_en_vivo.avisar_mensaje(db, conv, m)
    return m


def enviar_adjunto(db: Session, conv_id: str, agente, document_id: str,
                   caption: Optional[str] = None) -> ChannelMessage:
    """El agente envia un documento del ticket por el canal (WhatsApp o el hilo de Slack)."""
    from app.services.audit import audit_log
    from app.services.service_desk import adjuntos_de_canal, canales_en_vivo, salida_por_canales

    conv = _de_la_empresa(db, conv_id, agente.organization_id)
    if conv.status == "closed":
        raise error_con_codigo(409, "conversacion_cerrada")
    ticket = db.get(Ticket, conv.ticket_id) if conv.ticket_id else None
    if ticket is None:
        raise error_con_codigo(409, "conversacion_sin_ticket")
    fichero = adjuntos_de_canal.leer(db, ticket, document_id)
    m = salida_por_canales.entregar_adjunto(db, conv, fichero, document_id, (caption or "").strip()[:1024], agente)
    audit_log(db, agente, "SEND", "channel_attachment", document_id, fichero.nombre,
              metadata={"conversation_id": conv.id, "channel": conv.channel, "ticket_id": ticket.id,
                        "delivery_status": m.delivery_status})
    db.commit()
    canales_en_vivo.avisar_mensaje(db, conv, m)
    return m


def detalle_para_agente(db: Session, conv_id: str, org_id, desde: Optional[str] = None) -> dict:
    """Una conversacion de la empresa con sus mensajes y lo que se puede enviar
    por el canal (los adjuntos de su ticket, 17-11-2026)."""
    from app.services.service_desk.adjuntos_de_canal import listar as adjuntos_del_ticket
    conv = _de_la_empresa(db, conv_id, org_id)
    ticket = db.get(Ticket, conv.ticket_id) if conv.ticket_id else None
    return {"conversation": serializar(db, conv), "messages": mensajes(db, conv, desde),
            "attachments": adjuntos_del_ticket(db, ticket)}


def del_ticket_para_adjuntos(db: Session, ticket_id: str, org_id) -> dict:
    """Conversaciones abiertas de WhatsApp/Slack de un ticket de la empresa y sus
    documentos: lo que la ficha del ticket puede enviar por el canal (17-11-2026).
    El envio va por `enviar_adjunto`, el mismo que usa la bandeja."""
    from app.services.service_desk.adjuntos_de_canal import listar as adjuntos_del_ticket
    from app.services.service_desk.salida_por_canales import CANALES_DE_SALIDA
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id, Ticket.organization_id == org_id).first()
    if ticket is None:
        raise error_con_codigo(404, "ticket_no_encontrado")
    convs = (db.query(ChannelConversation)
             .filter(ChannelConversation.ticket_id == ticket.id, ChannelConversation.organization_id == org_id,
                     ChannelConversation.channel.in_(CANALES_DE_SALIDA), ChannelConversation.status != "closed")
             .order_by(ChannelConversation.last_message_at.desc().nullslast()).all())
    return {"conversations": [serializar(db, c) for c in convs],
            "attachments": adjuntos_del_ticket(db, ticket) if convs else []}


def cerrar(db: Session, conv_id: str, agente) -> ChannelConversation:
    conv = _de_la_empresa(db, conv_id, agente.organization_id)
    conv.status = "closed"
    aviso = anotar(db, conv, "out", "system", "closed", author_user_id=agente.id)
    db.commit()
    from app.services.service_desk import canales_en_vivo
    canales_en_vivo.avisar_mensaje(db, conv, aviso)
    canales_en_vivo.avisar_estado(db, conv)
    return conv


def listar(db: Session, org_id, estado: Optional[str], page: int, page_size: int,
           canal: Optional[str] = None) -> dict:
    q = db.query(ChannelConversation).filter(ChannelConversation.organization_id == org_id)
    if canal:
        q = q.filter(ChannelConversation.channel == canal)
    if estado:
        q = q.filter(ChannelConversation.status == estado)
    else:
        q = q.filter(ChannelConversation.status != "closed")
    total = q.count()
    filas = (q.order_by(ChannelConversation.last_message_at.desc().nullslast(), ChannelConversation.created_at.desc())
             .offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "items": [serializar(db, c) for c in filas]}


def mensajes(db: Session, conv: ChannelConversation, desde: Optional[str] = None, tope: int = 200,
             para_cliente: bool = False) -> list[dict]:
    """Los mensajes de la conversacion. `para_cliente`: lo que ve el cliente (con el
    original del agente debajo si la empresa lo quiere: `TRANSLATION_INCLUDE_ORIGINAL`)."""
    q = db.query(ChannelMessage).filter(ChannelMessage.conversation_id == conv.id)
    if desde:
        ultimo = db.get(ChannelMessage, desde)
        if ultimo is not None:
            q = q.filter(ChannelMessage.created_at > ultimo.created_at)
    filas = q.order_by(ChannelMessage.created_at).limit(tope).all()
    if not para_cliente:
        return [serializar_mensaje(m, db) for m in filas]
    from app.services.traduccion.salida import texto_para_cliente
    salida = []
    for m in filas:
        datos = serializar_mensaje(m, db)
        if m.author_type == "agent":
            datos["body"] = texto_para_cliente(db, conv.organization_id, "channel_message", m.id, m.body)
        salida.append(datos)
    return salida


def _nombre_del_adjunto(db: Session, document_id: str) -> Optional[str]:
    from app.models.documents import DocumentVersion
    fila = (db.query(DocumentVersion.file_name).filter(DocumentVersion.document_id == document_id)
            .order_by(DocumentVersion.version_num.desc()).first())
    return fila[0] if fila else None


def serializar_mensaje(m: ChannelMessage, db: Optional[Session] = None) -> dict:
    datos = {"id": m.id, "direction": m.direction, "author_type": m.author_type, "body": m.body,
             "language": m.language, "delivery_status": m.delivery_status,
             "attachment_document_id": m.attachment_document_id,
             "created_at": m.created_at.isoformat() if m.created_at else None}
    if db is not None and m.attachment_document_id:
        datos["attachment_name"] = _nombre_del_adjunto(db, m.attachment_document_id)
    return datos


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def serializar(db: Session, c: ChannelConversation) -> dict:
    numero = db.query(Ticket.number).filter(Ticket.id == c.ticket_id).scalar() if c.ticket_id else None
    datos = {"id": c.id, "channel": c.channel, "status": c.status, "visitor_name": c.visitor_name,
             "external_id": c.external_id if c.channel != "livechat" else None,
             "ticket_id": c.ticket_id, "ticket_number": numero, "assigned_user_id": c.assigned_user_id,
             "language": c.language,
             "client_read_at": _iso(c.client_read_at), "agent_read_at": _iso(c.agent_read_at),
             "last_message_at": _iso(c.last_message_at), "created_at": _iso(c.created_at)}
    if c.channel == "whatsapp":
        from app.services.service_desk.canal_whatsapp import estado_de_la_ventana
        datos["whatsapp_window"] = estado_de_la_ventana(db, c)
    return datos
