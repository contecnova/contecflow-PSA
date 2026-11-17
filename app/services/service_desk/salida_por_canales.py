"""Lo que sale del ticket por los canales conversacionales (17-11-2026).

Un ticket puede estar atado a conversaciones de WhatsApp (el telefono del
cliente) y de Slack (el hilo de su tarjeta). Lo que el agente contesta sale por
ellas:

- Desde la bandeja de conversaciones (`conversaciones.responder`): por el canal
  de esa conversacion, ya.
- Desde el ticket (comentario publico de un agente): la bandeja de eventos del
  ticket (`ticket_event_processor`, evento `commented`) llama a
  `al_comentar`, que lo envia a cada conversacion abierta del ticket.

Sin duplicados ni bucles: cada mensaje del canal guarda el comentario que es
(`ticket_comment_id`). Si la conversacion ya tiene un mensaje de ese
comentario —porque entro por ella o porque ya salio— no se envia.

WhatsApp respeta la ventana de 24 h (plantilla fuera de ella). Cada mensaje
guarda como se entrego (`delivery_status`): `sent`, `template`, `failed` u
`outside_window`. Esta capa no lanza en la salida desde el ticket: un fallo del
canal no debe repetir los correos del evento al reintentarlo.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from app.core.errores import ErrorDeDominio
from app.models.service_desk import ChannelConversation, ChannelMessage, Ticket

logger = logging.getLogger(__name__)

#: Canales que salen hacia fuera (el chat del portal se entrega por WebSocket).
CANALES_DE_SALIDA = ("whatsapp", "slack")


def exigir_que_se_pueda_enviar(db: Session, conv: ChannelConversation) -> None:
    """409 antes de guardar nada si el canal no puede llevar el mensaje."""
    if conv.channel == "whatsapp":
        from app.services.service_desk import canal_whatsapp
        if not canal_whatsapp.ventana_abierta(conv) and canal_whatsapp.plantilla(db, conv.organization_id) is None:
            raise ErrorDeDominio(409, "Han pasado más de 24 h desde el último mensaje del cliente y no hay "
                                      "plantilla de WhatsApp configurada: el mensaje no se puede enviar.")
    elif conv.channel == "slack":
        from app.services.service_desk import canal_slack
        if not canal_slack.token_del_bot(db, conv.organization_id):
            raise ErrorDeDominio(409, "Slack sin token de bot en la empresa: no se puede contestar en el hilo.")


def _numero_del_ticket(db: Session, conv: ChannelConversation) -> Optional[str]:
    return db.query(Ticket.number).filter(Ticket.id == conv.ticket_id).scalar() if conv.ticket_id else None


def entregar(db: Session, conv: ChannelConversation, m: ChannelMessage, texto: str,
             autor: Optional[str] = None) -> None:
    """Envia `texto` (lo que ve el cliente) por el canal y anota el resultado en `m`."""
    ext, estado = None, None
    if conv.channel == "whatsapp" and conv.external_id:
        from app.services.service_desk import canal_whatsapp
        ext, estado = canal_whatsapp.enviar_en_conversacion(db, conv, texto, _numero_del_ticket(db, conv))
    elif conv.channel == "slack":
        from app.services.service_desk import canal_slack
        ext = canal_slack.responder_en_hilo(db, conv, texto, autor)
        estado = "sent" if ext else "failed"
    if ext:
        m.external_message_id = ext
    m.delivery_status = estado


def entregar_adjunto(db: Session, conv: ChannelConversation, fichero, document_id: str, caption: str,
                     agente) -> ChannelMessage:
    """Un documento del ticket por el canal. Lanza 409/422 si el canal no puede llevarlo."""
    from app.services.service_desk import conversaciones
    if conv.channel == "whatsapp":
        from app.services.service_desk import canal_whatsapp
        if not canal_whatsapp.ventana_abierta(conv):
            raise ErrorDeDominio(409, "Fuera de la ventana de 24 h de WhatsApp: los adjuntos solo salen "
                                      "después de un mensaje del cliente.")
    elif conv.channel == "slack":
        exigir_que_se_pueda_enviar(db, conv)
    else:
        raise ErrorDeDominio(422, "Este canal no admite enviar adjuntos desde aquí.")
    cuerpo = f"[adjunto: {fichero.nombre}]" + (f"\n{caption}" if caption else "")
    m = conversaciones.anotar(db, conv, "out", "agent", cuerpo, author_user_id=agente.id)
    m.attachment_document_id = document_id
    if conv.channel == "whatsapp":
        from app.services.service_desk import canal_whatsapp
        ext, estado = canal_whatsapp.enviar_adjunto(db, conv, fichero, caption)
    else:
        from app.services.service_desk import canal_slack
        ext = canal_slack.subir_al_hilo(db, conv, fichero, caption)
        estado = "sent" if ext else "failed"
    if ext:
        m.external_message_id = ext
    m.delivery_status = estado
    return m


def al_comentar(db: Session, ticket: Ticket, comment_id: str) -> dict:
    """Respuesta publica de un agente en el ticket: a cada conversacion abierta atada.

    No confirma (lo hace quien procesa el evento) y no lanza.
    """
    from app.models.service_desk import TicketComment
    from app.services.service_desk import canales_en_vivo, conversaciones
    from app.services.traduccion.salida import texto_para_cliente

    c = db.get(TicketComment, comment_id)
    if c is None or not c.is_public or not c.author_user_id or c.system_template:
        return {"sent": 0}
    convs = (db.query(ChannelConversation)
             .filter(ChannelConversation.ticket_id == ticket.id, ChannelConversation.status != "closed",
                     ChannelConversation.channel.in_(CANALES_DE_SALIDA)).all())
    enviados = 0
    for conv in convs:
        ya = db.query(ChannelMessage.id).filter(ChannelMessage.conversation_id == conv.id,
                                                ChannelMessage.ticket_comment_id == c.id).first()
        if ya:
            continue
        try:
            texto = texto_para_cliente(db, ticket.organization_id, "ticket_comment", c.id, c.body)
            m = conversaciones.anotar(db, conv, "out", "agent", c.body, author_user_id=c.author_user_id)
            m.ticket_comment_id = c.id
            m.language = c.language
            autor = c.author_user.full_name if conv.channel == "slack" and c.author_user is not None else None
            entregar(db, conv, m, texto, autor)
            db.flush()
            canales_en_vivo.avisar_mensaje(db, conv, m)
            enviados += int(m.delivery_status in ("sent", "template"))
        except Exception:
            logger.warning("salida por %s del comentario %s fallida", conv.channel, c.id, exc_info=True)
    return {"sent": enviados}
