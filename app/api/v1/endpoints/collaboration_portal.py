"""Portal-facing collaboration endpoints (ClientUser).

These let portal clients participate in collaboration conversations they have
been invited to (cross-org groups / direct chats / shared channels).

Endpoints:
  GET  /portal/collaboration/conversations
  GET  /portal/collaboration/conversations/{id}/messages
  POST /portal/collaboration/messages
  POST /portal/collaboration/messages/{id}/reactions
  POST /portal/collaboration/conversations/{id}/read
  GET  /portal/collaboration/notifications
  POST /portal/collaboration/notifications/mark-all-read
  GET  /portal/collaboration/search
"""
from app.core.timeutil import utcnow
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.api.v1.endpoints.client_portal import get_current_client
from app.models.client_portal import ClientUser
from app.models.collaboration import (
    CollaborationChannel, CollaborationConversation,
    CollaborationConversationMember, CollaborationDirectConversation,
    CollaborationGroupConversation,
    CollaborationMessage, CollaborationNotification,
    CollaborationReaction, CollaborationRead,
)
from app.schemas.collaboration import (
    MessageCreate, MessageOut, ReactionToggle, ReadUpdate,
    SearchHit, SearchResponse,
)
from app.services.collaboration import audit_log
from app.services.collaboration._bus import (
    conv_channel,
)
from app.services.collaboration._permissions import is_client_conversation_participant
from app.services.traffic_control_service import consume_quota
from app.core.responses import APIListResponse, APIResponse

router = APIRouter()


def _client_conversation_ids(db: Session, client: ClientUser) -> set[str]:
    direct_ids = {
        r[0]
        for r in db.query(CollaborationDirectConversation.conversation_id).filter(
            or_(
                CollaborationDirectConversation.client_user_a_id == client.id,
                CollaborationDirectConversation.client_user_b_id == client.id,
            )
        ).all()
    }
    member_ids = {
        r[0]
        for r in db.query(CollaborationConversationMember.conversation_id).filter(
            CollaborationConversationMember.client_user_id == client.id
        ).all()
    }
    return direct_ids | member_ids


@router.get("/conversations", response_model=APIListResponse[dict], summary="Mis conversaciones (cliente)")
def list_conversations(current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    ids = _client_conversation_ids(db, current_client)
    out = []
    for conv in db.query(CollaborationConversation).filter(CollaborationConversation.id.in_(list(ids) or [""])).all():
        title = None
        if conv.kind == "channel":
            ch = db.query(CollaborationChannel).filter(CollaborationChannel.conversation_id == conv.id).first()
            title = f"# {ch.name}" if ch else None
        elif conv.kind == "direct":
            d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.conversation_id == conv.id).first()
            title = "Chat directo"
            if d:
                title = "Soporte" if d.user_a_id else title
        elif conv.kind == "group":
            g = db.query(CollaborationGroupConversation).filter(CollaborationGroupConversation.conversation_id == conv.id).first()
            title = (g and g.title) or "Grupo"
        out.append({
            "id": conv.id, "kind": conv.kind, "title": title,
            "last_activity_at": conv.last_activity_at,
        })
    return APIListResponse.ok(items=out, total=len(out))


@router.get("/conversations/{conversation_id}/messages", response_model=APIListResponse[MessageOut], summary="Mensajes (cliente)")
def list_messages(conversation_id: str, before: Optional[str] = None, limit: int = Query(50, le=200), current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    if not is_client_conversation_participant(db, current_client, conversation_id):
        raise HTTPException(403, "No tienes acceso a esta conversación")
    q = db.query(CollaborationMessage).filter(
        CollaborationMessage.conversation_id == conversation_id,
        CollaborationMessage.parent_message_id == None,
    )
    if before:
        anchor = db.query(CollaborationMessage).filter(CollaborationMessage.id == before).first()
        if anchor:
            q = q.filter(CollaborationMessage.sent_at < anchor.sent_at)
    rows = q.order_by(CollaborationMessage.sent_at.desc()).limit(limit).all()
    rows.reverse()
    from app.services.collaboration.messages import _serialize_message
    items = [MessageOut(**_serialize_message(db, m)) for m in rows]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/messages", response_model=APIResponse[MessageOut], summary="Enviar mensaje (cliente)")
def send_message(payload: MessageCreate, current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    conv_id = payload.conversation_id
    if not conv_id:
        raise HTTPException(400, "conversation_id requerido")
    if not is_client_conversation_participant(db, current_client, conv_id):
        raise HTTPException(403, "No tienes acceso a esta conversación")

    quota = consume_quota(
        db,
        scope="collab.portal.message.client",
        tenant_id=getattr(current_client, "organization_id", None),
        subject=current_client.id,
        limit=25,
        window_seconds=60,
    )
    if not quota["allowed"]:
        raise HTTPException(status_code=429, detail=f"Portal message rate limit exceeded. Retry in {quota['retry_after']}s")

    msg = CollaborationMessage(
        organization_id=getattr(current_client, "organization_id", None),
        conversation_id=conv_id,
        client_user_id=current_client.id,
        type=payload.type or "text",
        body=payload.body,
        metadata_json=payload.metadata_json or {},
        sent_at=utcnow(),
        parent_message_id=payload.parent_message_id,
    )
    db.add(msg)
    db.flush()

    conv = db.query(CollaborationConversation).filter(CollaborationConversation.id == conv_id).first()
    if conv:
        conv.last_activity_at = utcnow()
        conv.last_message_id = msg.id

    # Notify counterparts
    if conv and conv.kind == "direct":
        d = db.query(CollaborationDirectConversation).filter(CollaborationDirectConversation.conversation_id == conv_id).first()
        if d:
            for uid in {d.user_a_id, d.user_b_id}:
                if uid and uid != current_client.id:
                    db.add(CollaborationNotification(
                        organization_id=msg.organization_id, user_id=uid,
                        kind="message", conversation_id=conv_id, message_id=msg.id,
                        title="Mensaje del cliente", body=(msg.body or "")[:200],
                        payload={},
                    ))
    audit_log.write(
        db, organization_id=msg.organization_id, actor_user_id=None, actor_client_id=current_client.id,
        action="message.sent", entity_type="message", entity_id=msg.id,
        payload={"conversation_id": conv_id, "kind": "client"},
    )
    db.commit()
    from app.services.collaboration.messages import _serialize_message, _publish_async
    _publish_async(conv_channel(conv_id), {
        "type": "message.created", "conversation_id": conv_id, "message_id": msg.id,
        "payload": _serialize_message(db, msg),
    })
    return APIResponse.ok(data=MessageOut(**_serialize_message(db, msg)))


@router.post("/messages/{message_id}/reactions", response_model=APIResponse[dict], summary="Toggle reacción (cliente)")
def toggle_reaction(message_id: str, payload: ReactionToggle, current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    msg = db.query(CollaborationMessage).filter(CollaborationMessage.id == message_id).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    if not is_client_conversation_participant(db, current_client, msg.conversation_id):
        raise HTTPException(403, "No tienes acceso")
    existing = db.query(CollaborationReaction).filter(
        CollaborationReaction.message_id == message_id,
        CollaborationReaction.client_user_id == current_client.id,
        CollaborationReaction.emoji == payload.emoji,
    ).first()
    if existing:
        db.delete(existing)
    else:
        db.add(CollaborationReaction(
            organization_id=msg.organization_id, message_id=message_id,
            client_user_id=current_client.id, emoji=payload.emoji,
        ))
    db.commit()
    return APIResponse.ok(data={"toggled": True, "added": existing is None})


@router.post("/conversations/{conversation_id}/read", response_model=APIResponse[dict], summary="Marcar leído (cliente)")
def mark_read(conversation_id: str, payload: ReadUpdate, current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    if not is_client_conversation_participant(db, current_client, conversation_id):
        raise HTTPException(403, "No tienes acceso")
    row = db.query(CollaborationRead).filter(
        CollaborationRead.conversation_id == conversation_id,
        CollaborationRead.client_user_id == current_client.id,
    ).first()
    org = getattr(current_client, "organization_id", None)
    if row:
        row.last_message_id = payload.last_message_id
        row.last_read_at = utcnow()
    else:
        db.add(CollaborationRead(
            organization_id=org,
            conversation_id=conversation_id,
            client_user_id=current_client.id,
            last_message_id=payload.last_message_id,
        ))
    db.commit()
    return APIResponse.ok(data={"ok": True})


@router.get("/notifications", response_model=APIListResponse[dict], summary="Notificaciones del cliente")
def list_notifs(unread_only: bool = False, current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    q = db.query(CollaborationNotification).filter(CollaborationNotification.client_user_id == current_client.id)
    if unread_only:
        q = q.filter(CollaborationNotification.is_read == False)
    rows = q.order_by(CollaborationNotification.created_at.desc()).limit(200).all()
    items = [{
        "id": n.id, "kind": n.kind, "title": n.title, "body": n.body,
        "conversation_id": n.conversation_id, "message_id": n.message_id,
        "is_read": n.is_read, "created_at": n.created_at,
    } for n in rows]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/notifications/mark-all-read", response_model=APIResponse[dict], summary="Marcar todas leídas (cliente)")
def mark_all_read(current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    n = db.query(CollaborationNotification).filter(
        CollaborationNotification.client_user_id == current_client.id,
        CollaborationNotification.is_read == False,
    ).update({"is_read": True, "read_at": utcnow()})
    db.commit()
    return APIResponse.ok(data={"marked": n})


@router.get("/search", response_model=APIResponse[SearchResponse], summary="Búsqueda en mis conversaciones")
def search(q: str = Query("", max_length=500), limit: int = Query(50, le=200),
           current_client: ClientUser = Depends(get_current_client), db: Session = Depends(get_db)):
    ids = list(_client_conversation_ids(db, current_client))
    if not ids:
        return APIResponse.ok(data=SearchResponse(hits=[], total=0))
    from app.services.collaboration._search import search_engine
    hits = search_engine.search(
        db, organization_id=getattr(current_client, "organization_id", None),
        query=q, conversation_ids=ids, limit=limit,
    )
    return APIResponse.ok(data=SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits)))
