"""RGPD del chat del portal: copia y supresión de lo de un usuario del portal (24-11-2026).

Docs: docs/portal/CHAT_DEL_PORTAL.md §GRC. Lo llama la solicitud RGPD de una
persona que es usuario del portal (`cab_service/gdpr.py`), ANTES de anonimizar
su cuenta (se le identifica por su correo, que la anonimización cambia).

- **Copia (art. 15 y 20)**: sus mensajes del chat del portal (texto que
  escribió, sin ocultar), el rastro de sus ediciones y borrados, sus adjuntos
  (nombre, tipo, tamaño, fecha y huella; el fichero se entrega aparte si se
  pide), sus reacciones y las llamadas que contestó o rechazó.
- **Supresión (art. 17)**: el texto de sus mensajes pasa a «[ERASED]», se
  borran las versiones de sus mensajes, sus adjuntos (fila y fichero, al
  confirmar) y sus reacciones. Las llamadas se quedan (son metadatos de
  servicio, sin contenido) con la cuenta ya anonimizada. Bajo bloqueo legal
  de alguno de sus adjuntos se rechaza con 409 ANTES de tocar nada.

No hace `commit`: va dentro de la transacción única de la solicitud.
"""
from __future__ import annotations

from typing import Iterable

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.codigos_de_error import error
from app.models.portal_conversations import (
    PortalConversationAttachment,
    PortalConversationCall,
    PortalConversationMessage,
    PortalConversationMessageVersion,
    PortalConversationReaction,
)

BORRADO = "[ERASED]"


def _fecha(v) -> str | None:
    return str(v)[:19] if v else None


def copia(db: Session, client_ids: Iterable[str], org: str) -> dict:
    ids = list(client_ids)
    if not ids:
        return {"portal_chat": {"messages": [], "attachments": [], "reactions": [], "calls": [], "edits": []}}
    mensajes = db.query(PortalConversationMessage).filter(
        PortalConversationMessage.organization_id == org,
        PortalConversationMessage.sender_client_id.in_(ids),
    ).order_by(PortalConversationMessage.created_at).all()
    ids_mensajes = [m.id for m in mensajes]
    versiones = db.query(PortalConversationMessageVersion).filter(
        PortalConversationMessageVersion.organization_id == org,
        PortalConversationMessageVersion.message_id.in_(ids_mensajes),
    ).all() if ids_mensajes else []
    adjuntos = db.query(PortalConversationAttachment).filter(
        PortalConversationAttachment.organization_id == org,
        PortalConversationAttachment.uploaded_by_client_id.in_(ids),
    ).all()
    reacciones = db.query(PortalConversationReaction).filter(
        PortalConversationReaction.organization_id == org,
        PortalConversationReaction.client_user_id.in_(ids),
    ).all()
    llamadas = db.query(PortalConversationCall).filter(
        PortalConversationCall.organization_id == org,
        or_(PortalConversationCall.answered_by_client_id.in_(ids),
            PortalConversationCall.declined_by_client_id.in_(ids),
            PortalConversationCall.ended_by_client_id.in_(ids)),
    ).all()
    return {"portal_chat": {
        "messages": [{"conversation_id": m.conversation_id, "body": m.raw_body or m.body,
                      "type": getattr(m.message_type, "value", m.message_type),
                      "created_at": _fecha(m.created_at), "edited_at": _fecha(m.edited_at),
                      "deleted_at": _fecha(m.deleted_at)} for m in mensajes],
        "edits": [{"message_id": v.message_id, "change_type": v.change_type, "body": v.raw_body or v.body,
                   "at": _fecha(v.edited_at)} for v in versiones],
        "attachments": [{"conversation_id": a.conversation_id, "name": a.name, "mime_type": a.mime_type,
                         "size_bytes": a.size_bytes, "sha256": a.sha256, "created_at": _fecha(a.created_at),
                         "deleted_at": _fecha(a.deleted_at)} for a in adjuntos],
        "reactions": [{"message_id": r.message_id, "emoji": r.emoji, "at": _fecha(r.created_at)} for r in reacciones],
        "calls": [{"conversation_id": c.conversation_id, "kind": c.kind, "status": c.status,
                   "created_at": _fecha(c.created_at), "answered_at": _fecha(c.answered_at),
                   "ended_at": _fecha(c.ended_at), "duration_seconds": c.duration_seconds} for c in llamadas],
    }}


def exigir_sin_bloqueo_legal(db: Session, client_ids: Iterable[str], org: str) -> None:
    from app.db.bloqueo_legal import _bloqueo_de, bloqueos_activos
    ids = list(client_ids)
    if not ids:
        return
    activos = bloqueos_activos(db, org)
    if not activos:
        return
    casos = set()
    for a in db.query(PortalConversationAttachment).filter(
            PortalConversationAttachment.organization_id == org,
            PortalConversationAttachment.uploaded_by_client_id.in_(ids)).all():
        b = _bloqueo_de("portal_conversation_attachments", a, activos)
        if b is not None:
            casos.add(b.case_reference)
    if casos:
        raise error(409, "bloqueo_legal_no_suprimible", casos=", ".join(sorted(casos)))


def suprimir(db: Session, client_ids: Iterable[str], org: str) -> dict:
    ids = list(client_ids)
    if not ids:
        return {"messages": 0, "attachments": 0, "reactions": 0, "edits": 0}
    exigir_sin_bloqueo_legal(db, ids, org)
    mensajes = db.query(PortalConversationMessage).filter(
        PortalConversationMessage.organization_id == org,
        PortalConversationMessage.sender_client_id.in_(ids),
    ).all()
    ids_mensajes = [m.id for m in mensajes]
    n_versiones = 0
    if ids_mensajes:
        for v in db.query(PortalConversationMessageVersion).filter(
                PortalConversationMessageVersion.message_id.in_(ids_mensajes)).all():
            db.delete(v)
            n_versiones += 1
    for m in mensajes:
        m.body = BORRADO
        m.raw_body = None
    adjuntos = db.query(PortalConversationAttachment).filter(
        PortalConversationAttachment.organization_id == org,
        PortalConversationAttachment.uploaded_by_client_id.in_(ids),
    ).all()
    for a in adjuntos:
        db.delete(a)  # el fichero se borra al confirmar (evento del modelo)
    reacciones = db.query(PortalConversationReaction).filter(
        PortalConversationReaction.organization_id == org,
        PortalConversationReaction.client_user_id.in_(ids),
    ).all()
    for r in reacciones:
        db.delete(r)
    db.flush()
    return {"messages": len(mensajes), "attachments": len(adjuntos), "reactions": len(reacciones),
            "edits": n_versiones}
