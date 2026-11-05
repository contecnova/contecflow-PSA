"""👍 / 👎 de las respuestas de IA (revisión 2026-11, lo que contecmind tenía).

El asistente interno y el chat del portal guardan cada valoración en
`ai_answer_feedback` (una por mensaje y quien vota; votar otra vez la cambia).
Un 👎 lleva la pregunta a «Preguntas sin respuesta» de la base de conocimiento,
aunque la respuesta citara artículos: si no sirvió, falta algo.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_chat import (AIAnswerFeedback, AIClientChatMessage, AIClientChatSession, AIConversation,
                                AIMessage)


def _guardar(db: Session, *, org, canal: str, mensaje_id: str, pregunta: Optional[str], util: bool,
             comentario: Optional[str], user_id=None, client_user_id=None) -> AIAnswerFeedback:
    fila = db.query(AIAnswerFeedback).filter(AIAnswerFeedback.channel == canal,
                                             AIAnswerFeedback.message_id == mensaje_id).first()
    if fila is None:
        fila = AIAnswerFeedback(organization_id=org, channel=canal, message_id=mensaje_id, user_id=user_id,
                                client_user_id=client_user_id)
        db.add(fila)
    fila.question, fila.helpful = (pregunta or "")[:4000] or None, bool(util)
    fila.comment = (comentario or "").strip()[:2000] or None
    if not util and pregunta:
        from app.services.service_desk.kb_calidad import registrar_hueco
        registrar_hueco(db, pregunta, f"{canal}_feedback")
    db.commit()
    return fila


def valorar_del_asistente(db: Session, usuario, mensaje_id: str, util: bool, comentario: Optional[str]) -> dict:
    mensaje = db.query(AIMessage).filter(AIMessage.id == mensaje_id, AIMessage.role == "assistant").first()
    conv = db.get(AIConversation, mensaje.conversation_id) if mensaje else None
    if conv is None or conv.user_id != usuario.id:
        raise LookupError("mensaje")
    pregunta = (db.query(AIMessage.content)
                .filter(AIMessage.conversation_id == conv.id, AIMessage.role == "user",
                        AIMessage.created_at <= mensaje.created_at)
                .order_by(AIMessage.created_at.desc()).first())
    fila = _guardar(db, org=usuario.organization_id, canal="assistant", mensaje_id=mensaje_id,
                    pregunta=pregunta[0] if pregunta else None, util=util, comentario=comentario,
                    user_id=usuario.id)
    return {"helpful": fila.helpful}


def valorar_del_portal(db: Session, cliente, mensaje_id: str, util: bool, comentario: Optional[str]) -> dict:
    mensaje = db.query(AIClientChatMessage).filter(AIClientChatMessage.id == mensaje_id,
                                                   AIClientChatMessage.role == "assistant").first()
    sesion = db.get(AIClientChatSession, mensaje.session_id) if mensaje else None
    if sesion is None or sesion.client_user_id != cliente.id:
        raise LookupError("mensaje")
    pregunta = (db.query(AIClientChatMessage.content)
                .filter(AIClientChatMessage.session_id == sesion.id, AIClientChatMessage.role == "user",
                        AIClientChatMessage.created_at <= mensaje.created_at)
                .order_by(AIClientChatMessage.created_at.desc()).first())
    fila = _guardar(db, org=getattr(cliente, "organization_id", None), canal="portal", mensaje_id=mensaje_id,
                    pregunta=pregunta[0] if pregunta else None, util=util, comentario=comentario,
                    client_user_id=cliente.id)
    return {"helpful": fila.helpful}
