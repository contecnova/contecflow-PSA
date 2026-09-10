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

Auditoria 2026-08 (hallazgo 22). Las 21 consultas y escrituras de este fichero
estan en `app/services/collaboration/portal.py`, y con ellas se corrigio que el
portal era **una segunda via de envio de mensajes sin los controles de la
primera**: sus mensajes no se indexaban para busqueda —lo que solo importa con
el backend OpenSearch, donde quedaban invisibles; con Postgres o SQLite la
busqueda lee la tabla—, no pasaban por DLP, no creaban hilos, y su reparto de
notificaciones era parcial
y se protegia con una comparacion entre dos espacios de identificadores que
nunca podia ser falsa. Ahora el envio es el unico que hay,
`messages.send_message`, con el remitente marcado como cliente.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.endpoints.client_portal import get_current_client
from app.core.responses import APIListResponse, APIResponse
from app.db.session import get_db
from app.models.client_portal import ClientUser
from app.schemas.collaboration import (
    MessageCreate,
    MessageOut,
    ReactionToggle,
    ReadUpdate,
    SearchHit,
    SearchResponse,
)
from app.services.collaboration import portal as svc

router = APIRouter()


@router.get("/conversations", response_model=APIListResponse[dict], summary="Mis conversaciones (cliente)")
def list_conversations(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    items = svc.list_conversations(db, current_client)
    return APIListResponse.ok(items=items, total=len(items))


@router.get("/conversations/{conversation_id}/messages", response_model=APIListResponse[MessageOut], summary="Mensajes (cliente)")
def list_messages(
    conversation_id: str,
    before: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.services.collaboration.messages import _serialize_message

    filas = svc.list_messages(
        db, current_client, conversation_id, before=before, limit=limit)
    items = [MessageOut(**_serialize_message(db, m)) for m in filas]
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/messages", response_model=APIResponse[MessageOut], summary="Enviar mensaje (cliente)")
def send_message(
    payload: MessageCreate,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    from app.services.collaboration.messages import _serialize_message

    msg = svc.send_message(db, current_client, payload)
    return APIResponse.ok(data=MessageOut(**_serialize_message(db, msg)))


@router.post("/messages/{message_id}/reactions", response_model=APIResponse[dict], summary="Toggle reacción (cliente)")
def toggle_reaction(
    message_id: str,
    payload: ReactionToggle,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(
        data=svc.toggle_reaction(db, current_client, message_id, payload.emoji))


@router.post("/conversations/{conversation_id}/read", response_model=APIResponse[dict], summary="Marcar leído (cliente)")
def mark_read(
    conversation_id: str,
    payload: ReadUpdate,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    svc.mark_read(db, current_client, conversation_id, payload.last_message_id)
    return APIResponse.ok(data={"ok": True})


@router.get("/notifications", response_model=APIListResponse[dict], summary="Notificaciones del cliente")
def list_notifs(
    unread_only: bool = False,
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    items = svc.list_notifications(db, current_client, unread_only=unread_only)
    return APIListResponse.ok(items=items, total=len(items))


@router.post("/notifications/mark-all-read", response_model=APIResponse[dict], summary="Marcar todas leídas (cliente)")
def mark_all_read(
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    return APIResponse.ok(
        data={"marked": svc.mark_all_notifications_read(db, current_client)})


@router.get("/search", response_model=APIResponse[SearchResponse], summary="Búsqueda en mis conversaciones")
def search(
    q: str = Query("", max_length=500),
    limit: int = Query(50, le=200),
    current_client: ClientUser = Depends(get_current_client),
    db: Session = Depends(get_db),
):
    hits = svc.search(db, current_client, query=q, limit=limit)
    return APIResponse.ok(
        data=SearchResponse(hits=[SearchHit(**h) for h in hits], total=len(hits)))
